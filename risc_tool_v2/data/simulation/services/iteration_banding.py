"""Double-variable iteration banding: plan child bands and a risk segment grid.

Layers a new variable's bands over a parent's existing bands. For each parent
band a limited auto-banding window (``upgrade_limit``/``downgrade_limit``
around the parent's position in the band order) is banded; the combined cut
points become the child's default bands. Each ``(child band, parent band)``
cell then picks the highest target band in that window whose (scalar-adjusted)
dev bad rate falls under its upper bound.
"""

import itertools
import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.enums import VariableType
from risc_tool_v2.data.core.uid import RiskSegmentID
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.simulation.models.groups import CategoricalGroup, NumericalGroup
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar
from risc_tool_v2.data.simulation.services.auto_band import (
    create_auto_categorical_bands,
    create_auto_numeric_bands,
    does_high_value_implies_high_risk,
)
from risc_tool_v2.data.simulation.services.iterate import segment_assignment_expr

RiskSegmentGrid = dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]]
BandGroups = OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup]


def _replace_outer_numeric_bounds(
    groups: BandGroups, value_range: tuple[float, float] | None
) -> BandGroups:
    """Replace the outer bounds of numerical groups with the value range."""
    if value_range is None or not groups:
        return groups

    minimum, maximum = value_range
    lowest_group_id = min(
        groups.keys(),
        key=lambda gid: (
            t.cast(NumericalGroup, groups[gid]).lower_bound,
            t.cast(NumericalGroup, groups[gid]).upper_bound,
            gid,
        ),
    )
    highest_group_id = max(
        groups.keys(),
        key=lambda gid: (
            t.cast(NumericalGroup, groups[gid]).upper_bound,
            t.cast(NumericalGroup, groups[gid]).lower_bound,
            gid,
        ),
    )

    lowest_group = t.cast(NumericalGroup, groups[lowest_group_id])
    groups[lowest_group_id] = NumericalGroup(
        lower_bound=minimum,
        upper_bound=lowest_group.upper_bound,
    )

    highest_group = t.cast(NumericalGroup, groups[highest_group_id])
    groups[highest_group_id] = NumericalGroup(
        lower_bound=highest_group.lower_bound,
        upper_bound=maximum,
    )

    return groups


def _reindex_groups_and_grid(
    groups: BandGroups, grid: RiskSegmentGrid
) -> tuple[BandGroups, RiskSegmentGrid]:
    """Reindex groups and grid to use fresh contiguous child band ids."""
    reindexed_groups: BandGroups = OrderedDict()
    reindexed_grid: RiskSegmentGrid = {}
    for idx, old_gid in enumerate(groups.keys()):
        new_gid = RiskSegmentID(int=idx)
        reindexed_groups[new_gid] = groups[old_gid]
        reindexed_grid[new_gid] = dict(grid[old_gid])
    return reindexed_groups, reindexed_grid


def _apply_auto_rank(
    grid: RiskSegmentGrid,
    ordered_parent_segments: list[RiskSegmentID],
    segment_order: list[RiskSegmentID],
) -> RiskSegmentGrid:
    """Enforce monotone non-decreasing target bands across rows and columns."""
    pos_of = {seg_id: idx for idx, seg_id in enumerate(segment_order)}
    ordered_group_ids = list(grid.keys())

    for gid in ordered_group_ids:
        max_pos = -1
        for parent_seg in ordered_parent_segments:
            target = grid[gid][parent_seg]
            if target not in pos_of:
                continue
            max_pos = max(max_pos, pos_of[target])
            grid[gid][parent_seg] = segment_order[max_pos]

    for parent_seg in ordered_parent_segments:
        max_seen = -1
        for gid in ordered_group_ids:
            target = grid[gid][parent_seg]
            if target not in pos_of:
                continue
            pos = pos_of[target]
            if pos < max_seen:
                pos = max_seen
            else:
                max_seen = pos
            grid[gid][parent_seg] = segment_order[pos]

    return grid


def plan_double_var_bands(
    *,
    base_lf: pl.LazyFrame,
    variable_name: str,
    variable_type: VariableType,
    parent_col: str,
    metric: Metric,
    loss_rate_scalar: LossRateScalar,
    numerator: str,
    denominator: str | None,
    mob: int,
    risk_segment_config: RiskSegmentConfig,
    use_scalar: bool,
    upgrade_limit: int,
    downgrade_limit: int,
    auto_rank_ordering: bool,
    ordered_parent_segments: list[RiskSegmentID],
    unfiltered_value_range: tuple[float, float] | None = None,
) -> tuple[BandGroups, RiskSegmentGrid, list[str]]:
    """Plan default child bands and the risk segment grid for a double-variable iteration.

    Args:
        base_lf: Filtered dev frame that already carries the parent band column.
        variable_name: The child variable being banded.
        variable_type: Whether the child variable is numerical or categorical.
        parent_col: Alias of the parent band column within ``base_lf``.
        metric: The dev bad rate metric used to place bands.
        loss_rate_scalar: The risk scalar used to adjust band thresholds.
        numerator: Bad count column.
        denominator: Average balance column (None for unit bad rate).
        mob: Months-on-book used for annualization.
        risk_segment_config: The root simulation's risk segment config.
        use_scalar: Whether to apply scalar factors when placing bands.
        upgrade_limit: Max band positions a cell may move up.
        downgrade_limit: Max band positions a cell may move down.
        auto_rank_ordering: Whether to enforce monotone grid cells.
        ordered_parent_segments: The root segment ids in band order (columns).
        unfiltered_value_range: Unfiltered (min, max) of the numeric child
            variable used to widen the outermost bands.

    Returns:
        A tuple of (child groups, risk segment grid, warnings).

    Raises:
        ValueError: If a required input is missing or inconsistent.
    """
    warnings: list[str] = []
    metric_expr = metric.metric_expr
    if metric_expr is None:
        raise ValueError(f"Metric '{metric.name}' has no compiled expression.")

    transformed = risk_segment_config.get_segments(normalize=True)
    segment_order = list(transformed.keys())
    segment_pos = {seg_id: idx for idx, seg_id in enumerate(segment_order)}

    if variable_type == VariableType.NUMERICAL:
        direction_denominator = denominator
        direction_lf = base_lf
        if direction_denominator is None:
            direction_denominator = "__DIRECTION_DENOM__"
            direction_lf = base_lf.with_columns(
                pl.lit(1.0).alias(direction_denominator)
            )

        hv_imp_hr = does_high_value_implies_high_risk(
            base_lf=direction_lf,
            variable=variable_name,
            numerator=numerator,
            denominator=direction_denominator,
        )

        parent_present = [
            RiskSegmentID(v)
            for v in base_lf.select(pl.col(parent_col).drop_nulls().unique().sort())
            .collect()
            .get_column(parent_col)
            .to_list()
            if v is not None
        ]
        parent_present = [
            seg_id for seg_id in parent_present if seg_id in segment_pos
        ]

        cut_points: set[float] = set()
        for parent_seg in parent_present:
            pos = segment_pos[parent_seg]
            start = max(0, pos - upgrade_limit)
            end = min(len(segment_order), pos + downgrade_limit + 1)
            allowed_seg_ids = segment_order[start:end]
            sub_cfg = RiskSegmentConfig(
                segments=OrderedDict(
                    (seg_id, transformed[seg_id]) for seg_id in allowed_seg_ids
                )
            )

            seg_lf = base_lf.filter(pl.col(parent_col) == str(parent_seg))
            seg_groups = create_auto_numeric_bands(
                base_lf=seg_lf,
                variable=variable_name,
                risk_segment_config=sub_cfg,
                loss_rate_scalar=loss_rate_scalar,
                numerator=numerator,
                denominator=denominator,
                mob=mob,
                use_scalar=use_scalar,
                hv_imp_hr=hv_imp_hr,
            )
            for group in seg_groups.values():
                cut_points.add(float(group.lower_bound))
                cut_points.add(float(group.upper_bound))

        sorted_points = sorted(cut_points)
        pair_points = list(itertools.pairwise(sorted_points))
        if not pair_points:
            pair_points = [(float("-inf"), float("inf"))]

        if hv_imp_hr is False:
            pair_points = list(reversed(pair_points))

        groups: BandGroups = OrderedDict(
            (
                RiskSegmentID(int=idx),
                NumericalGroup(lower_bound=float(lower), upper_bound=float(upper)),
            )
            for idx, (lower, upper) in enumerate(pair_points)
        )
        groups = _replace_outer_numeric_bounds(groups, unfiltered_value_range)
    else:
        categorical_groups = create_auto_categorical_bands(
            base_lf=base_lf,
            variable=variable_name,
            risk_segment_config=risk_segment_config,
            loss_rate_scalar=loss_rate_scalar,
            numerator=numerator,
            denominator=denominator,
            mob=mob,
            use_scalar=use_scalar,
        )
        groups = OrderedDict(
            (RiskSegmentID(int=idx), group)
            for idx, (_old_gid, group) in enumerate(categorical_groups.items())
        )

    current_group_col = "__iteration_segment"
    metric_df = (
        base_lf.with_columns(segment_assignment_expr(groups, variable_name))
        .group_by(pl.col(parent_col), pl.col(current_group_col))
        .agg(metric_expr.alias("__value"))
        .collect()
    )

    metric_map: dict[tuple[str, str], float] = {}
    for row in metric_df.iter_rows():
        pseg, cgrp, value = row
        if pseg is None or cgrp is None or value is None:
            continue
        metric_map[(str(pseg), str(cgrp))] = float(value)

    grid: RiskSegmentGrid = {}
    for gid in groups:
        row_map: dict[RiskSegmentID, RiskSegmentID] = {}
        for parent_seg in ordered_parent_segments:
            if parent_seg not in segment_pos:
                row_map[parent_seg] = parent_seg
                continue

            metric_value = metric_map.get((str(parent_seg), str(gid)))
            if metric_value is None:
                row_map[parent_seg] = parent_seg
                continue

            pos = segment_pos[parent_seg]
            start = max(0, pos - upgrade_limit)
            end = min(len(segment_order), pos + downgrade_limit + 1)
            allowed_seg_ids = segment_order[start:end]

            chosen_seg = allowed_seg_ids[-1]
            for target_seg in allowed_seg_ids:
                seg_obj = transformed[target_seg]
                if use_scalar:
                    scaled_metric = metric_value * max(
                        seg_obj.maf(loss_rate_scalar.loss_rate_type)
                        * loss_rate_scalar.portfolio_scalar,
                        1.0,
                    )
                else:
                    scaled_metric = metric_value

                if scaled_metric < seg_obj.upper_rate:
                    chosen_seg = target_seg
                    break

            row_map[parent_seg] = chosen_seg

        grid[gid] = row_map

    ordered_ids = list(groups.keys())
    if variable_type == VariableType.NUMERICAL:
        i = 1
        while i < len(ordered_ids):
            prev_gid = ordered_ids[i - 1]
            curr_gid = ordered_ids[i]
            if grid[curr_gid] != grid[prev_gid]:
                i += 1
                continue

            prev_group = t.cast(NumericalGroup, groups[prev_gid])
            curr_group = t.cast(NumericalGroup, groups[curr_gid])
            groups[prev_gid] = NumericalGroup(
                lower_bound=min(prev_group.lower_bound, curr_group.lower_bound),
                upper_bound=max(prev_group.upper_bound, curr_group.upper_bound),
            )
            del groups[curr_gid]
            del grid[curr_gid]
            ordered_ids.pop(i)
    else:
        i1 = 0
        while i1 < len(ordered_ids):
            i2 = i1 + 1
            while i2 < len(ordered_ids):
                gid1 = ordered_ids[i1]
                gid2 = ordered_ids[i2]
                if grid[gid1] != grid[gid2]:
                    i2 += 1
                    continue

                cat1 = t.cast(CategoricalGroup, groups[gid1])
                cat2 = t.cast(CategoricalGroup, groups[gid2])
                groups[gid1] = CategoricalGroup(
                    categories=frozenset(cat1.categories | cat2.categories)
                )
                del groups[gid2]
                del grid[gid2]
                ordered_ids.pop(i2)

            i1 += 1

        sort_order = sorted(
            ordered_ids,
            key=lambda gid: tuple(
                segment_pos[grid[gid][parent_seg]]
                for parent_seg in ordered_parent_segments
                if parent_seg in segment_pos
            ),
        )
        sorted_groups: BandGroups = OrderedDict(
            (gid, groups[gid]) for gid in sort_order
        )
        sorted_grid = {gid: grid[gid] for gid in sort_order}
        groups, grid = _reindex_groups_and_grid(sorted_groups, sorted_grid)

    if variable_type == VariableType.NUMERICAL and ordered_ids:
        groups, grid = _reindex_groups_and_grid(groups, grid)

    if auto_rank_ordering:
        grid = _apply_auto_rank(
            grid=grid,
            ordered_parent_segments=ordered_parent_segments,
            segment_order=segment_order,
        )

    return groups, grid, warnings


__all__ = ["plan_double_var_bands"]