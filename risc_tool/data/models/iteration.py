"""Pydantic data models for iterations.

This module defines models for numerical and categorical group definitions,
single-variable and double-variable iterations, and validation logic.
NO pandas DataFrames or Series are stored inside these model instances.
"""

import itertools
import math
import textwrap
import typing as t
from abc import abstractmethod
from collections import OrderedDict
from string import Template

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from risc_tool.data.models.config import RiskSegmentConfig
from risc_tool.data.models.enums import (
    IterationType,
    LossRateTypes,
    RSDetCol,
    VariableType,
)
from risc_tool.data.models.iteration_group import (
    CategoricalGroup,
    GroupBase,
    NumericalGroup,
    SupportsGroups,
    rebuild_group_dict,
)
from risc_tool.data.models.json_models import IterationJSON
from risc_tool.data.models.types import GroupID, IterationID, RiskSegmentID
from risc_tool.utils.logging import get_logger
from risc_tool.utils.wrap_text import TAB

logger = get_logger(__name__)


def _format_bound(value: float) -> str:
    """Format a group bound as a valid Python literal."""
    if math.isinf(value):
        return "float('-inf')" if value < 0 else "float('inf')"
    return str(value)


def _apply_groups[TTargetGroup: GroupBase](
    iteration: SupportsGroups[TTargetGroup],
    groups_items: t.Iterable[tuple[GroupID, GroupBase]],
    default_groups_items: t.Iterable[tuple[GroupID, GroupBase]],
    group_cls: type[TTargetGroup],
) -> None:
    """Apply typed groups/default_groups to an iteration instance."""
    iteration.groups = rebuild_group_dict(groups_items, group_cls)
    iteration.set_default_groups(rebuild_group_dict(default_groups_items, group_cls))


class IterationBase[TGroup: GroupBase](BaseModel):
    """Base Pydantic model for all iteration objects."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    var_type: VariableType
    iter_type: IterationType

    uid: IterationID
    name: str
    variable_name: str
    active: bool = True

    groups: OrderedDict[GroupID, TGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, TGroup]()
    )
    default_groups: OrderedDict[GroupID, TGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, TGroup]()
    )

    @property
    def pretty_name(self) -> str:
        parts = [f"Iteration #{self.uid}"]
        if self.name:
            parts.append(self.name)
        return " - ".join(parts)

    def rename(self, new_name: str) -> None:
        """Rename iteration with normalized user input."""
        self.name = new_name.strip()

    @abstractmethod
    def validate_groups(
        self, default: bool = False
    ) -> tuple[list[str], list[str], list[GroupID]]:
        raise NotImplementedError()

    @abstractmethod
    def set_group(
        self,
        group_id: GroupID,
        lower_bound: float,
        upper_bound: float,
        categories: set[str],
    ) -> None:
        raise NotImplementedError()

    def get_group_mapping_expr(self, default: bool) -> pl.Expr:
        target_groups = self.default_groups if default else self.groups

        expr = pl.when(False).then(pl.lit(None))

        for gid, g in target_groups.items():
            expr = expr.when(g.predicate(self.variable_name)).then(gid.value)

        expr = expr.otherwise(None).cast(pl.UInt16, strict=False)

        return expr

    def generate_sas_code_for_groups(self, default: bool, mapping: dict[int, int]):
        """Generates SAS code to create this iteration."""
        groups = self.default_groups if default else self.groups

        code_template = (
            "if missing($VARIABLE_NAME) then $OUTPUT_VARIABLE_NAME = $MISSING;\n"
        )

        for group_id, group in groups.items():
            if not group.is_valid():
                continue

            code_template += (
                f"else if {group.sas_code_template('$VARIABLE_NAME')} then\n"
                f"    $OUTPUT_VARIABLE_NAME = $GROUP_INDEX_{mapping.get(group_id, group_id)};\n"
            )

        code_template += "else $OUTPUT_VARIABLE_NAME = $MISSING;\n"

        return code_template

    def to_dict(self) -> IterationJSON[TGroup]:
        """Convert Iteration instance to IterationJSON Pydantic model."""
        return IterationJSON(
            var_type=self.var_type,
            iter_type=self.iter_type,
            uid=self.uid,
            name=self.name,
            variable_name=self.variable_name,
            groups=self.groups,
            default_groups=self.default_groups,
        )


class NumericalIterationMixin(IterationBase[NumericalGroup]):
    """Mixin / field container for numerical iteration groups."""

    groups: OrderedDict[GroupID, NumericalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, NumericalGroup]()
    )
    default_groups: OrderedDict[GroupID, NumericalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, NumericalGroup]()
    )

    def validate_groups(
        self, default: bool = False
    ) -> tuple[list[str], list[str], list[GroupID]]:
        warnings: list[str] = []
        errors: list[str] = []
        invalid_groups: list[GroupID] = []
        intervals: list[tuple[GroupID, float, float]] = []

        target_groups = self.default_groups if default else self.groups

        for group_id, group in target_groups.items():
            lower_bound = group.lower_bound
            upper_bound = group.upper_bound

            if lower_bound >= upper_bound:
                warnings.append(
                    f"Invalid bounds in row {group_id}: lower bound ({lower_bound}) >= upper bound ({upper_bound})"
                )
                invalid_groups.append(group_id)

            if group_id not in invalid_groups:
                intervals.append((group_id, lower_bound, upper_bound))

        # Check monotonic bounds and overlaps
        if intervals:
            lbs = [i[1] for i in intervals]
            ubs = [i[2] for i in intervals]

            sorted_intervals = sorted(intervals, key=lambda t: t[1])
            overlaps: list[str] = []
            for i in range(len(sorted_intervals) - 1):
                if sorted_intervals[i][2] > sorted_intervals[i + 1][1]:
                    overlaps.append(
                        f"{sorted_intervals[i][0]}. ({sorted_intervals[i][1]}, {sorted_intervals[i][2]}] "
                        f"and {sorted_intervals[i + 1][0]}. ({sorted_intervals[i + 1][1]}, {sorted_intervals[i + 1][2]}]"
                    )

            is_mono_dec = all(x >= y for x, y in itertools.pairwise(lbs))
            is_mono_inc = all(x <= y for x, y in itertools.pairwise(lbs))
            if not is_mono_dec and not is_mono_inc:
                warnings.append(
                    "Lower bounds of the groups are not monotonic. This may lead to unexpected behavior."
                )

            is_ub_dec = all(x >= y for x, y in itertools.pairwise(ubs))
            is_ub_inc = all(x <= y for x, y in itertools.pairwise(ubs))
            if not is_ub_dec and not is_ub_inc:
                warnings.append(
                    "Upper bounds of the groups are not monotonic. This may lead to unexpected behavior."
                )

            if overlaps:
                errors.append(f"Following intervals overlap: {overlaps}")

        warnings = [f"Iteration {self.uid}: {w}" for w in warnings]
        errors = [f"Iteration {self.uid}: {e}" for e in errors]
        return warnings, errors, invalid_groups

    def set_default_groups(self, groups: OrderedDict[GroupID, NumericalGroup]) -> None:
        """Set the default groups for the iteration."""
        self.default_groups = OrderedDict(
            (gid, group.model_copy(deep=True)) for gid, group in groups.items()
        )
        self.groups = OrderedDict(
            (gid, group.model_copy(deep=True)) for gid, group in groups.items()
        )

    def set_group(
        self,
        group_id: GroupID,
        lower_bound: float,
        upper_bound: float,
        categories: set[str],
    ) -> None:
        """Set a single group's bounds."""
        self.groups[group_id] = NumericalGroup(
            lower_bound=lower_bound, upper_bound=upper_bound
        )


class CategoricalIterationMixin(IterationBase[CategoricalGroup]):
    """Mixin / field container for categorical iteration groups."""

    groups: OrderedDict[GroupID, CategoricalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, CategoricalGroup]()
    )
    default_groups: OrderedDict[GroupID, CategoricalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, CategoricalGroup]()
    )

    def validate_groups(
        self, default: bool = False
    ) -> tuple[list[str], list[str], list[GroupID]]:
        warnings: list[str] = []
        errors: list[str] = []
        invalid_groups: list[GroupID] = []

        assigned_categories: set[str] = set()
        target_groups = self.default_groups if default else self.groups

        for group_id, group in target_groups.items():
            if not group.categories:
                warnings.append(f"Group at index {group_id} is empty.")
                invalid_groups.append(group_id)
                continue

            for cat in group.categories:
                # if all_categories and cat not in all_categories:
                #     warnings.append(
                #         f"Category '{cat}' in group at index {group_id} is not in the variable's unique values."
                #     )
                #     invalid_groups.append(group_id)

                if cat in assigned_categories:
                    errors.append(f"Category '{cat}' is assigned to multiple groups.")

                assigned_categories.add(cat)

        # if all_categories and len(all_categories - assigned_categories) > 0:
        #     unassigned = ", ".join(sorted(all_categories - assigned_categories))
        #     warnings.append(
        #         f"The following categories are not assigned to any group: {unassigned}"
        #     )

        warnings = [f"Iteration {self.uid}: {w}" for w in warnings]
        errors = [f"Iteration {self.uid}: {e}" for e in errors]
        return warnings, errors, invalid_groups

    def set_default_groups(
        self, groups: OrderedDict[GroupID, CategoricalGroup]
    ) -> None:
        """Set the default groups for the iteration."""
        self.default_groups = OrderedDict(
            (gid, group.model_copy(deep=True)) for gid, group in groups.items()
        )
        self.groups = OrderedDict(
            (gid, group.model_copy(deep=True)) for gid, group in groups.items()
        )

    def set_group(
        self,
        group_id: GroupID,
        lower_bound: float,
        upper_bound: float,
        categories: set[str],
    ) -> None:
        """Set a single group's categories."""
        self.groups[group_id] = CategoricalGroup(categories=categories)


class SingleVarIteration[TGroup: GroupBase](IterationBase[TGroup]):
    """Single variable iteration model storing segment details as Pydantic models."""

    iter_type: IterationType = IterationType.SINGLE
    risk_segment_details: RiskSegmentConfig = Field(
        default_factory=lambda: RiskSegmentConfig()
    )

    def update_maf(
        self, loss_rate_type: LossRateTypes, maf_map: dict[RiskSegmentID, float]
    ) -> None:
        """Update MAF factors for risk segment details."""
        for seg_id, maf in maf_map.items():
            if seg_id in self.risk_segment_details.segments:
                if loss_rate_type == LossRateTypes.DLR:
                    self.risk_segment_details.segments[seg_id].maf_dlr = maf
                elif loss_rate_type == LossRateTypes.ULR:
                    self.risk_segment_details.segments[seg_id].maf_ulr = maf

    def update_color(
        self,
        color_type: t.Literal[RSDetCol.BG_COLOR, RSDetCol.FONT_COLOR],
        color_map: dict[RiskSegmentID, str],
    ) -> None:
        """Update colors for risk segment details."""
        for seg_id, color in color_map.items():
            if seg_id in self.risk_segment_details.segments:
                if color_type == RSDetCol.BG_COLOR:
                    self.risk_segment_details.segments[seg_id].bg_color = color
                elif color_type == RSDetCol.FONT_COLOR:
                    self.risk_segment_details.segments[seg_id].font_color = color

    def get_risk_segment_expr(
        self, default: bool, prev_seg_col: str | None = None
    ) -> pl.Expr:
        return self.get_group_mapping_expr(default=default)

    def to_dict(self) -> IterationJSON[TGroup]:
        """Convert Iteration instance to IterationJSON Pydantic model."""
        return IterationJSON(
            var_type=self.var_type,
            iter_type=self.iter_type,
            uid=self.uid,
            name=self.name,
            variable_name=self.variable_name,
            groups=self.groups,
            default_groups=self.default_groups,
            risk_segment_details=self.risk_segment_details,
        )

    def generate_sas_code(self, default: bool) -> Template:
        groups = self.default_groups if default else self.groups
        mapping = {group_id.value: group_id.value for group_id in groups}

        code_template = "format $OUTPUT_VARIABLE_NAME $50.;\n\n"
        code_template += self.generate_sas_code_for_groups(default, mapping=mapping)
        return Template(code_template)

    def generate_python_code(self, default: bool) -> Template:
        groups = self.default_groups if default else self.groups

        group_definitions = ""
        if self.var_type == VariableType.NUMERICAL:
            for group_id, group in groups.items():
                num_group = t.cast(NumericalGroup, group)
                lower_bound = num_group.lower_bound
                upper_bound = num_group.upper_bound
                if (
                    math.isnan(lower_bound)
                    or math.isnan(upper_bound)
                    or lower_bound >= upper_bound
                ):
                    continue

                group_definitions += (
                    f"pd.Interval({_format_bound(lower_bound)}, "
                    f"{_format_bound(upper_bound)}, closed='right'): "
                    f"$GROUP_INDEX_{group_id.value},\n"
                )

        elif self.var_type == VariableType.CATEGORICAL:
            for group_id, group in groups.items():
                cat_group = t.cast(CategoricalGroup, group)
                if not cat_group.categories:
                    continue

                cats_formatted = ", ".join(
                    f'"{cat}"' for cat in sorted(cat_group.categories)
                )
                group_definitions += (
                    f"({cats_formatted},): $GROUP_INDEX_{group_id.value},\n"
                )

        code_template = f"iter_{self.uid}_map = {{\n"
        code_template += textwrap.indent(group_definitions, TAB)
        code_template += "}\n"
        code_template += (
            f"iter_{self.uid}_map = pd.Series("
            f"data=iter_{self.uid}_map.values(), index=list(iter_{self.uid}_map.keys()))\n\n"
        )
        code_template += (
            f'$DATA["$OUTPUT_VARIABLE_NAME"] = '
            f'create_mapped_variable($DATA["$VARIABLE_NAME"], iter_{self.uid}_map)\n'
        )

        return Template(code_template)


class DoubleVarIteration[TGroup: GroupBase](IterationBase[TGroup]):
    """Double variable iteration model storing grid cells as typed dict mapping."""

    iter_type: IterationType = IterationType.DOUBLE
    groups_mask: dict[GroupID, bool] = Field(default_factory=dict[GroupID, bool])
    risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = Field(
        default_factory=dict[GroupID, dict[RiskSegmentID, RiskSegmentID]]
    )
    default_risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = (
        Field(default_factory=dict[GroupID, dict[RiskSegmentID, RiskSegmentID]])
    )

    def set_risk_segment_grid_cell(
        self,
        group_id: GroupID,
        parent_seg_id: RiskSegmentID,
        target_seg_id: RiskSegmentID,
    ) -> None:
        """Set a single grid cell target segment."""
        if group_id not in self.risk_segment_grid:
            self.risk_segment_grid[group_id] = {}
        self.risk_segment_grid[group_id][parent_seg_id] = target_seg_id

    def get_risk_segment_expr(
        self, default: bool, prev_seg_col: str | None = None
    ) -> pl.Expr:
        """Return a Polars expression mapping values to risk segment IDs based on grid."""
        if prev_seg_col is None:
            raise ValueError(
                "prev_seg_col must be provided for double variable iterations."
            )

        target_grid = (
            self.default_risk_segment_grid if default else self.risk_segment_grid
        )
        target_groups = self.default_groups if default else self.groups

        expr = pl.when(False).then(pl.lit(None))

        for gid, group_map in target_grid.items():
            if (g := target_groups.get(gid)) is None or not self.groups_mask.get(
                gid, False
            ):
                logger.warning(
                    "Group ID %s not found in iteration %s. Skipping grid mapping for this group.",
                    gid,
                    self.uid,
                )
                continue

            for parent_seg_id, target_seg_id in group_map.items():
                expr = expr.when(
                    (g.predicate(self.variable_name))
                    & (pl.col(prev_seg_col) == parent_seg_id.value)
                ).then(target_seg_id.value)

        expr = expr.otherwise(None).cast(pl.UInt16, strict=False)

        return expr

    def to_dict(self) -> IterationJSON[TGroup]:
        """Convert Iteration instance to IterationJSON Pydantic model."""
        return IterationJSON(
            var_type=self.var_type,
            iter_type=self.iter_type,
            uid=self.uid,
            name=self.name,
            variable_name=self.variable_name,
            groups=self.groups,
            default_groups=self.default_groups,
            groups_mask=self.groups_mask,
            risk_segment_grid=self.risk_segment_grid,
            default_risk_segment_grid=self.default_risk_segment_grid,
        )

    def generate_sas_code(self, default: bool) -> Template:
        risk_segment_grid = (
            self.default_risk_segment_grid if default else self.risk_segment_grid
        )

        code_template = "format $OUTPUT_VARIABLE_NAME $50.;\n\n"
        code_template += (
            "if missing($VARIABLE_NAME) or missing($PREV_ITER_OUT_NAME) then "
            "$OUTPUT_VARIABLE_NAME = $MISSING;\n"
        )

        parent_seg_ids: set[RiskSegmentID] = set()
        for g_map in risk_segment_grid.values():
            parent_seg_ids.update(g_map.keys())

        for column in sorted(parent_seg_ids):
            mapping = {
                group_id.value: g_map[column].value
                for group_id, g_map in risk_segment_grid.items()
                if column in g_map
            }

            code_template += (
                f"else if $PREV_ITER_OUT_NAME = $GROUP_INDEX_{column} then do;\n"
            )
            code_template += textwrap.indent(
                text=self.generate_sas_code_for_groups(
                    default=default, mapping=mapping
                ),
                prefix=TAB,
            )
            code_template += "end;\n"

        code_template += "else $OUTPUT_VARIABLE_NAME = $MISSING;\n"
        return Template(code_template)

    def generate_python_code(self, default: bool) -> Template:
        risk_segment_grid = (
            self.default_risk_segment_grid if default else self.risk_segment_grid
        )
        groups = self.default_groups if default else self.groups

        invalid_groups: list[GroupID] = []
        group_definitions = ""

        if self.var_type == VariableType.NUMERICAL:
            for group_id, group in groups.items():
                num_group = t.cast(NumericalGroup, group)
                lower_bound = num_group.lower_bound
                upper_bound = num_group.upper_bound
                if (
                    math.isnan(lower_bound)
                    or math.isnan(upper_bound)
                    or lower_bound >= upper_bound
                ):
                    invalid_groups.append(group_id)
                    continue

                group_definitions += (
                    f"pd.Interval({_format_bound(lower_bound)}, "
                    f"{_format_bound(upper_bound)}, closed='right'),\n"
                )
        elif self.var_type == VariableType.CATEGORICAL:
            for group_id, group in groups.items():
                cat_group = t.cast(CategoricalGroup, group)
                if not cat_group.categories:
                    invalid_groups.append(group_id)
                    continue

                cats_formatted = ", ".join(
                    f'"{cat}"' for cat in sorted(cat_group.categories)
                )
                group_definitions += f"({cats_formatted},),\n"

        group_definitions = "[\n" + textwrap.indent(group_definitions, TAB) + "]"

        parent_seg_ids: list[RiskSegmentID] = sorted({
            seg for g_map in risk_segment_grid.values() for seg in g_map
        })

        grid_definition = ""
        for g_id in groups:
            if g_id in invalid_groups:
                continue

            g_map = risk_segment_grid.get(g_id, {})
            grid_definition += "["
            grid_definition += ", ".join(
                f"$GROUP_INDEX_{g_map.get(col, RiskSegmentID(0))}"
                for col in parent_seg_ids
            )
            grid_definition += "],\n"
        grid_definition = "[\n" + textwrap.indent(grid_definition, TAB) + "]"

        column_definition = (
            "[" + ", ".join(f"$GROUP_INDEX_{col}" for col in parent_seg_ids) + "]"
        )

        code_template = f"iter_{self.uid}_grid = pd.DataFrame(\n"
        code_template += textwrap.indent(f"data={grid_definition},\n", TAB)
        code_template += textwrap.indent(f"columns={column_definition},\n", TAB)
        code_template += textwrap.indent(f"index={group_definitions},\n", TAB)
        code_template += ")\n\n"
        code_template += (
            f'$DATA["$OUTPUT_VARIABLE_NAME"] = '
            f'create_grid_mapped_variable($DATA["$VARIABLE_NAME"], $DATA["$PREV_ITER_OUT_NAME"], iter_{self.uid}_grid)\n'
        )

        return Template(code_template)


class NumericalSingleVarIteration(
    SingleVarIteration[NumericalGroup], NumericalIterationMixin
):
    var_type: VariableType = VariableType.NUMERICAL


class CategoricalSingleVarIteration(
    SingleVarIteration[CategoricalGroup], CategoricalIterationMixin
):
    var_type: VariableType = VariableType.CATEGORICAL


class NumericalDoubleVarIteration(
    DoubleVarIteration[NumericalGroup], NumericalIterationMixin
):
    var_type: VariableType = VariableType.NUMERICAL


class CategoricalDoubleVarIteration(
    DoubleVarIteration[CategoricalGroup], CategoricalIterationMixin
):
    var_type: VariableType = VariableType.CATEGORICAL


Iteration = (
    NumericalSingleVarIteration
    | NumericalDoubleVarIteration
    | CategoricalSingleVarIteration
    | CategoricalDoubleVarIteration
)


def iteration_from_dict[TGroup: GroupBase](data: IterationJSON[TGroup]):
    """Reconstruct Iteration instance from IterationJSON Pydantic model or dict."""

    if data.iter_type == IterationType.SINGLE:
        assert data.risk_segment_details is not None

        if data.var_type == VariableType.NUMERICAL:
            iteration = NumericalSingleVarIteration(
                var_type=VariableType.NUMERICAL,
                uid=data.uid,
                name=data.name,
                variable_name=data.variable_name,
                risk_segment_details=data.risk_segment_details,
            )
            _apply_groups(
                iteration,
                data.groups.items(),
                data.default_groups.items(),
                NumericalGroup,
            )
        else:
            iteration = CategoricalSingleVarIteration(
                var_type=VariableType.CATEGORICAL,
                uid=data.uid,
                name=data.name,
                variable_name=data.variable_name,
                risk_segment_details=data.risk_segment_details,
            )
            _apply_groups(
                iteration,
                data.groups.items(),
                data.default_groups.items(),
                CategoricalGroup,
            )

    else:
        assert data.groups_mask is not None
        assert data.risk_segment_grid is not None
        assert data.default_risk_segment_grid is not None

        if data.var_type == VariableType.NUMERICAL:
            iteration = NumericalDoubleVarIteration(
                var_type=VariableType.NUMERICAL,
                uid=data.uid,
                name=data.name,
                variable_name=data.variable_name,
            )
            _apply_groups(
                iteration,
                data.groups.items(),
                data.default_groups.items(),
                NumericalGroup,
            )

        else:
            iteration = CategoricalDoubleVarIteration(
                var_type=VariableType.CATEGORICAL,
                uid=data.uid,
                name=data.name,
                variable_name=data.variable_name,
            )
            _apply_groups(
                iteration,
                data.groups.items(),
                data.default_groups.items(),
                CategoricalGroup,
            )

        iteration.groups_mask = data.groups_mask
        iteration.risk_segment_grid = data.risk_segment_grid
        iteration.default_risk_segment_grid = data.default_risk_segment_grid

    return iteration


__all__ = [
    "CategoricalDoubleVarIteration",
    "CategoricalGroup",
    "CategoricalIterationMixin",
    "CategoricalSingleVarIteration",
    "DoubleVarIteration",
    "Iteration",
    "IterationBase",
    "NumericalDoubleVarIteration",
    "NumericalGroup",
    "NumericalIterationMixin",
    "NumericalSingleVarIteration",
    "SingleVarIteration",
    "iteration_from_dict",
]
