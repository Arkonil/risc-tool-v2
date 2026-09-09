"""Simulation iteration model.

An iteration is a single-variable (or double-variable) analysis derived from
one simulation output. It stores only references (``simulation_id``,
``scg_id``, ``sc_id``, ``so_id``) into the simulation repository's cache; the
risk segment config resolves from the referenced SCG at render time.

Iterations come in two variants:

* **Fixed** (``is_editable=False``): a read-only snapshot of the output's
  bands. ``groups`` mirrors ``default_groups`` and edits are not allowed.
* **Editable** (``is_editable=True``): created by cloning an existing
  iteration. ``default_groups`` stays pinned to the family's original output
  bands while ``groups`` holds the (modifiable) working bands.

Double-variable iterations (``iter_type=DOUBLE``) layer an additional banded
variable over a previous iteration's bands via a risk segment grid that maps
each ``(group, parent_band)`` cell to a target band.

Lineage fields (``family_root_id``, ``source_iteration_id``,
``previous_iteration_id``) plus the repository's :class:`IterationGraph` track
how iterations relate for display and cascade deletion.

Unlike content-addressed models, an iteration's identity is a simple unique
integer assigned sequentially by the simulation repository (mirroring v1's
iteration ids), and the object itself is deliberately mutable.
"""

import typing as t
from collections import OrderedDict

from pydantic import BaseModel, ConfigDict, Field

from risc_tool_v2.data.core.enums import IterationType, VariableType
from risc_tool_v2.data.core.uid import (
    IterationID,
    RiskSegmentID,
    SimulationConfigGeneratorID,
    SimulationConfigID,
    SimulationID,
    SimulationOutputID,
)
from risc_tool_v2.data.simulation.json.simulation_json import (
    CategoricalGroupJSON,
    GroupJSON,
    IterationJSON,
    NumericalGroupJSON,
)
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)

BandGroups = OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]
RiskSegmentGrid = dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]]


def _groups_to_json(
    groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
) -> OrderedDict[RiskSegmentID, GroupJSON]:
    """Convert band groups to their JSON models."""
    return OrderedDict(
        (
            gid,
            NumericalGroupJSON(
                type="numerical",
                lower_bound=group.lower_bound,
                upper_bound=group.upper_bound,
            )
            if isinstance(group, NumericalGroup)
            else CategoricalGroupJSON(
                type="categorical",
                categories=sorted(group.categories),
            ),
        )
        for gid, group in groups.items()
    )


def _groups_from_json(
    data: OrderedDict[RiskSegmentID, GroupJSON],
) -> OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]:
    """Reconstruct band groups from their JSON models."""
    groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] = (
        OrderedDict()
    )
    for gid, group_json in data.items():
        if group_json.type == "numerical":
            num_json = group_json
            groups[gid] = NumericalGroup(
                lower_bound=num_json.lower_bound, upper_bound=num_json.upper_bound
            )
        else:
            cat_json = group_json
            groups[gid] = CategoricalGroup(categories=frozenset(cat_json.categories))
    return groups


class SimulationIteration(BaseModel):
    """A simulation iteration wrapping one simulation output.

    Attributes:
        uid: Sequential integer identity assigned by the repository.
        name: Human-readable label (auto-generated at creation).
        simulation_id: The parent simulation whose output this derives from.
        scg_id: The simulation's config generator (risk segments, scalars, bad rates).
        sc_id: The simulation config that produced the output (content hash).
        so_id: The simulation output whose groups define this iteration's bands.
        variable_name: The banded variable's column name.
        variable_type: Whether the variable is numerical or categorical.
        iter_type: Single-variable or double-variable iteration.
        is_editable: Whether the iteration's bands may be edited.
        family_root_id: The founding fixed iteration of this iteration's family.
        source_iteration_id: The iteration this was cloned from (UNSET for a root).
        previous_iteration_id: The graph parent (chain predecessor), used when
            composing ancestor-level bands for double-variable grids.
        default_groups: The family's original bands (from the output or the
            auto-banded child grouping), never edited.
        groups: The working bands; equals ``default_groups`` for fixed
            iterations and holds the editable copy for editable ones.
        groups_mask: Whether each default group is active/hidden (double-variable).
        risk_segment_grid: Editable grid mapping (group, parent_band) -> band.
        default_risk_segment_grid: Original grid mapping, never edited.
    """

    model_config = ConfigDict(extra="forbid")

    uid: IterationID = IterationID.UNSET
    name: str
    simulation_id: SimulationID
    scg_id: SimulationConfigGeneratorID
    sc_id: SimulationConfigID
    so_id: SimulationOutputID
    variable_name: str
    variable_type: VariableType
    iter_type: IterationType = IterationType.SINGLE
    is_editable: bool = False
    family_root_id: IterationID = IterationID.UNSET
    source_iteration_id: IterationID = IterationID.UNSET
    previous_iteration_id: IterationID = IterationID.UNSET
    default_groups: BandGroups = Field(
        default_factory=OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]
    )
    groups: BandGroups = Field(
        default_factory=OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]
    )
    groups_mask: dict[RiskSegmentID, bool] = Field(
        default_factory=dict[RiskSegmentID, bool]
    )
    risk_segment_grid: RiskSegmentGrid = Field(
        default_factory=dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]]
    )
    default_risk_segment_grid: RiskSegmentGrid = Field(
        default_factory=dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]]
    )

    @property
    def is_double_var(self) -> bool:
        """Return True when this is a double-variable iteration."""
        return self.iter_type == IterationType.DOUBLE

    def effective_groups(
        self, default: bool = False
    ) -> OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]:
        """Return the groups that govern how the variable is banded.

        Args:
            default: If True, return the un-editable default bands.

        Returns:
            The default groups when ``default`` is True, otherwise the working
            (edited) groups for editable iterations and the default bands for
            fixed ones.
        """
        if default:
            return self.default_groups
        return self.groups if self.is_editable and self.groups else self.default_groups

    def effective_risk_segment_grid(self, default: bool = False) -> RiskSegmentGrid:
        """Return the grid that maps (group, parent_band) cells to bands.

        Args:
            default: If True, return the un-editable default grid.

        Returns:
            The default grid when ``default`` is True, otherwise the working
            (edited) grid for editable iterations and the default grid for
            fixed ones.
        """
        if default:
            return self.default_risk_segment_grid
        if self.is_editable and self.risk_segment_grid:
            return self.risk_segment_grid
        return self.default_risk_segment_grid

    def to_dict(self) -> IterationJSON:
        """Serialize this iteration to its JSON model."""
        return IterationJSON(
            uid=self.uid,
            name=self.name,
            simulation_id=self.simulation_id,
            scg_id=self.scg_id,
            sc_id=self.sc_id,
            so_id=self.so_id,
            variable_name=self.variable_name,
            variable_type=self.variable_type,
            iter_type=self.iter_type,
            is_editable=self.is_editable,
            family_root_id=self.family_root_id,
            source_iteration_id=self.source_iteration_id,
            previous_iteration_id=self.previous_iteration_id,
            default_groups=_groups_to_json(self.default_groups),
            groups=_groups_to_json(self.groups),
            groups_mask=self.groups_mask,
            risk_segment_grid=self.risk_segment_grid,
            default_risk_segment_grid=self.default_risk_segment_grid,
        )

    @classmethod
    def from_dict(cls, data: IterationJSON) -> t.Self:
        """Reconstruct an iteration from its JSON model."""
        return cls(
            uid=data.uid,
            name=data.name,
            simulation_id=data.simulation_id,
            scg_id=data.scg_id,
            sc_id=data.sc_id,
            so_id=data.so_id,
            variable_name=data.variable_name,
            variable_type=data.variable_type,
            iter_type=data.iter_type,
            is_editable=data.is_editable,
            family_root_id=data.family_root_id,
            source_iteration_id=data.source_iteration_id,
            previous_iteration_id=data.previous_iteration_id,
            default_groups=_groups_from_json(data.default_groups),
            groups=_groups_from_json(data.groups),
            groups_mask=data.groups_mask,
            risk_segment_grid=data.risk_segment_grid,
            default_risk_segment_grid=data.default_risk_segment_grid,
        )


__all__ = ["SimulationIteration"]
