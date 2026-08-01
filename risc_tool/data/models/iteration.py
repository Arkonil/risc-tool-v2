"""Pydantic data models for iterations.

This module defines models for numerical and categorical group definitions,
single-variable and double-variable iterations, and validation logic.
NO pandas DataFrames or Series are stored inside these model instances.
"""

import math
import typing as t
from abc import abstractmethod
from collections import OrderedDict
from collections.abc import Iterable

import polars as pl
from pydantic import BaseModel, ConfigDict, Field, field_validator

from risc_tool.data.models.config import RiskSegmentConfig
from risc_tool.data.models.enums import (
    IterationType,
    LossRateTypes,
    RSDetCol,
    VariableType,
)
from risc_tool.data.models.types import GroupID, IterationID, RiskSegmentID
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)

TGroup = t.TypeVar("TGroup", bound="GroupBase")


class GroupBase(BaseModel, frozen=True):
    """Base Pydantic model for a single group, either numerical or categorical."""

    @abstractmethod
    def is_valid(self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def predicate(self, variable_name: str) -> pl.Expr:
        raise NotImplementedError()


class NumericalGroup(GroupBase, frozen=True):
    """Single numerical group defined by lower and upper numeric bounds."""

    lower_bound: float = float("-inf")
    upper_bound: float = float("inf")

    @field_validator("lower_bound", mode="before")
    @classmethod
    def parse_nan_or_none_lower(cls, v: object) -> float:
        if v is None:
            return float("-inf")
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            if isinstance(v, float) and math.isnan(v):
                return float("-inf")
            return float(v)
        raise TypeError(f"Expected numeric value or None, got {type(v).__name__}")

    @field_validator("upper_bound", mode="before")
    @classmethod
    def parse_nan_or_none_upper(cls, v: object) -> float:
        if v is None:
            return float("inf")
        if isinstance(v, (int, float, str)) and not isinstance(v, bool):
            if isinstance(v, float) and math.isnan(v):
                return float("inf")
            return float(v)
        raise TypeError(f"Expected numeric value or None, got {type(v).__name__}")

    def is_valid(self) -> bool:
        """Check if bounds are present and lower < upper."""
        if self.lower_bound is None or self.upper_bound is None:
            return False
        return self.lower_bound < self.upper_bound

    def predicate(self, variable_name: str) -> pl.Expr:
        """Return a Polars expression for this group's bounds."""
        return pl.col(variable_name).is_between(
            self.lower_bound, self.upper_bound, closed="right"
        )


class CategoricalGroup(GroupBase, frozen=True):
    """Single categorical group defined by a set of category strings."""

    categories: set[str] = Field(default_factory=set)

    @field_validator("categories", mode="before")
    @classmethod
    def parse_categories(cls, v: object) -> set[str]:
        if isinstance(v, (list, tuple, set)):
            return {str(item) for item in t.cast(Iterable[object], v)}
        return set()

    def is_valid(self) -> bool:
        """Check if group contains at least one category."""
        return len(self.categories) > 0

    def predicate(self, variable_name: str) -> pl.Expr:
        """Return a Polars expression for this group's categories."""
        return pl.col(variable_name).is_in(self.categories)


class IterationBase(BaseModel, t.Generic[TGroup]):
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
    def _validate(self, default: bool = False):
        raise NotImplementedError()

    @abstractmethod
    def set_group(
        self,
        group_id: GroupID,
        lower_bound: float,
        upper_bound: float,
        categories: set[str],
    ):
        raise NotImplementedError()

    def get_group_mapping_expr(self, default: bool) -> pl.Expr:
        target_groups = self.default_groups if default else self.groups

        expr = pl.when(False).then(pl.lit(None))

        for gid, g in target_groups.items():
            expr = expr.when(g.predicate(self.variable_name)).then(gid.value)

        expr = expr.otherwise(None).cast(pl.UInt16, strict=False)

        return expr


class NumericalIterationMixin(IterationBase[NumericalGroup]):
    """Mixin / field container for numerical iteration groups."""

    groups: OrderedDict[GroupID, NumericalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, NumericalGroup]()
    )
    default_groups: OrderedDict[GroupID, NumericalGroup] = Field(
        default_factory=lambda: OrderedDict[GroupID, NumericalGroup]()
    )

    def _validate(
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

            is_mono_dec = all(x >= y for x, y in zip(lbs[:-1], lbs[1:]))
            is_mono_inc = all(x <= y for x, y in zip(lbs[:-1], lbs[1:]))
            if not is_mono_dec and not is_mono_inc:
                warnings.append(
                    "Lower bounds of the groups are not monotonic. This may lead to unexpected behavior."
                )

            is_ub_dec = all(x >= y for x, y in zip(ubs[:-1], ubs[1:]))
            is_ub_inc = all(x <= y for x, y in zip(ubs[:-1], ubs[1:]))
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

    def _validate(
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


class SingleVarIteration(IterationBase[TGroup], t.Generic[TGroup]):
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


class DoubleVarIteration(IterationBase[TGroup], t.Generic[TGroup]):
    """Double variable iteration model storing grid cells as typed dict mapping."""

    iter_type: IterationType = IterationType.DOUBLE
    groups_mask: dict[GroupID, bool] = Field(default_factory=lambda: {})
    risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = Field(
        default_factory=lambda: {}
    )
    default_risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = (
        Field(default_factory=lambda: {})
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

__all__ = [
    "NumericalGroup",
    "CategoricalGroup",
    "IterationBase",
    "NumericalIterationMixin",
    "CategoricalIterationMixin",
    "SingleVarIteration",
    "DoubleVarIteration",
    "NumericalSingleVarIteration",
    "CategoricalSingleVarIteration",
    "NumericalDoubleVarIteration",
    "CategoricalDoubleVarIteration",
    "Iteration",
]
