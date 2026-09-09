"""Iteration band-table evaluation: per-band metrics over a simulation output's groups.

The table includes the requested built-in bad rate columns (dev/test x
unit/dollar, resolved from the simulation's SCG and selectable even when
unconfigured) plus the selected user metrics. When scalars are enabled the dev
(annualized) bad rate columns are scaled per segment by
``max(maf * portfolio_scalar, 1.0)``; the test (early) bad rates are never
scaled. Each column is evaluated with a frame scoped to that metric's own
selected data sources (all sources when none are selected), mirroring the rule
that metrics (and simulations) are defined only for their selected data sources.
"""

import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import (
    DataSourceID,
    FilterID,
    MetricID,
    RiskSegmentID,
)
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.models.metric import Metric
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository
from risc_tool_v2.data.simulation.models.groups import (
    CategoricalGroup,
    NumericalGroup,
)
from risc_tool_v2.data.simulation.models.risk_segment import (
    RiskSegment,
    RiskSegmentConfig,
)
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar
from risc_tool_v2.data.simulation.models.simulation_config import (
    BadRateConfig,
    SimulationConfigGenerator,
    SimulationOutput,
)

_Column = tuple[str, Metric]
_Values = dict[RiskSegmentID, dict[str, float | None]]
RiskSegmentGrid = dict[RiskSegmentID, dict[RiskSegmentID, RiskSegmentID]]
_BuiltinBadRateColumn = tuple[str, Metric, tuple[DataSourceID, ...], bool]

# The four built-in bad rate metrics an iteration can display, keyed by their
# reserved MetricID sentinel. Undefined SCG bad rate configs still resolve to a
# default BadRateConfig, so every option is selectable whether or not the
# simulation configured its columns.
_BUILTIN_BAD_RATES: dict[MetricID, tuple[str, str]] = {
    MetricID.DEV_UNT_BAD_RATE: ("dev_unit_bad_rate", "Dev # Bad Rate"),
    MetricID.DEV_DLR_BAD_RATE: ("dev_dollar_bad_rate", "Dev $ Bad Rate"),
    MetricID.TST_UNT_BAD_RATE: ("test_unit_bad_rate", "Test # Bad Rate"),
    MetricID.TST_DLR_BAD_RATE: ("test_dollar_bad_rate", "Test $ Bad Rate"),
}


class BandTableResult:
    """Result of an iteration band-table evaluation.

    Attributes:
        columns: Ordered ``(column name, metric)`` pairs in display order.
        segments: Risk segments in band order (from the iterator's groups).
        values: Per-segment raw values keyed by segment ID then column name.
        total: When a total row is requested, per-column aggregate over all
            rows keyed by column name.
        warnings: Non-fatal issues (e.g. metrics skipped as invalid).
        errors: Fatal errors that prevented evaluation altogether.
    """

    def __init__(
        self,
        columns: list[_Column] | None = None,
        segments: OrderedDict[RiskSegmentID, RiskSegment] | None = None,
        values: _Values | None = None,
        total: dict[str, float | None] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.columns: list[_Column] = columns if columns is not None else []
        self.segments: OrderedDict[RiskSegmentID, RiskSegment] = (
            segments if segments is not None else OrderedDict()
        )
        self.values: _Values = values if values is not None else {}
        self.total: dict[str, float | None] = total if total is not None else {}
        self.warnings: list[str] = warnings if warnings is not None else []
        self.errors: list[str] = errors if errors is not None else []


def segment_assignment_expr(
    groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
    variable_name: str,
) -> pl.Expr:
    """Build a Polars expression mapping rows to their segment id (as str)."""
    expr: pl.Expr | None = None
    for seg_id, group in groups.items():
        cond = group.predicate(variable_name)
        if expr is None:
            expr = pl.when(cond).then(pl.lit(str(seg_id)))
        else:
            expr = expr.when(cond).then(pl.lit(str(seg_id)))
    if expr is None:
        raise ValueError("Cannot evaluate a band table with no groups.")
    return expr.otherwise(pl.lit(None)).alias("__iteration_segment")


def double_var_assignment_expr(
    *,
    groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
    variable_name: str,
    prev_col: str,
    grid: RiskSegmentGrid,
) -> pl.Expr:
    """Build a Polars expression assigning rows to target band ids (as str) via a grid.

    Each row is mapped to a target band by combining the current group the
    value falls into with the previous (parent) band column. Unmapped cells
    produce None.
    """
    expr: pl.Expr | None = None
    for gid, group in groups.items():
        row_map = grid.get(gid, {})
        for parent_seg_id, target_seg_id in row_map.items():
            cond = group.predicate(variable_name) & (
                pl.col(prev_col) == str(parent_seg_id)
            )
            if expr is None:
                expr = pl.when(cond).then(pl.lit(str(target_seg_id)))
            else:
                expr = expr.when(cond).then(pl.lit(str(target_seg_id)))
    if expr is None:
        raise ValueError("Cannot evaluate a double-variable band table with no grid.")
    return expr.otherwise(pl.lit(None)).alias("__iteration_segment")


def _scalar_factor(segment: RiskSegment, scalar: LossRateScalar) -> float:
    """Return this segment's risk scalar factor: max(maf * portfolio_scalar, 1.0)."""
    return max(segment.maf(scalar.loss_rate_type) * scalar.portfolio_scalar, 1.0)


def _default_bad_rate_config(
    scg: SimulationConfigGenerator, field: str
) -> BadRateConfig:
    """Return an SCG bad rate config, or an undefined default when absent.

    The returned config backs a built-in metric even when the simulation has
    not configured that bad rate; such metrics evaluate to empty cells.
    """
    config = getattr(scg, field)
    if config is not None:
        return config
    loss_rate_type = (
        LossRateTypes.ULR
        if field.endswith("_unit_bad_rate")
        else LossRateTypes.DLR
    )
    return BadRateConfig(
        loss_rate_type=loss_rate_type,
        data_source_ids=(),
        is_annualized=field.startswith("dev_"),
    )


def builtin_bad_rate_columns(
    scg: SimulationConfigGenerator,
    metric_ids: tuple[MetricID, ...],
) -> list[_BuiltinBadRateColumn]:
    """Resolve requested built-in bad rate sentinels to evaluatable columns.

    Returns a list of ``(name, metric, data_source_ids, is_dev)`` tuples in
    selection order. User metric ids and unknown ids are ignored.
    """
    columns: list[_BuiltinBadRateColumn] = []
    for metric_id in metric_ids:
        spec = _BUILTIN_BAD_RATES.get(metric_id)
        if spec is None:
            continue
        field, name = spec
        config = _default_bad_rate_config(scg, field)
        metric = config.to_metric(uid=MetricID.TEMPORARY, name=name)
        columns.append(
            (name, metric, tuple(config.data_source_ids), field.startswith("dev_"))
        )
    return columns


def builtin_bad_rate_metric_options(
    scg: SimulationConfigGenerator,
) -> dict[MetricID, tuple[str, Metric]]:
    """Return the four built-in bad rate metrics for an SCG keyed by sentinel.

    The metrics carry their sentinel uid so the metric selector can offer them
    alongside user-defined metrics; unconfigured rates yield undefined metrics
    whose cells evaluate to empty.
    """
    options: dict[MetricID, tuple[str, Metric]] = {}
    for metric_id, (field, name) in _BUILTIN_BAD_RATES.items():
        config = _default_bad_rate_config(scg, field)
        options[metric_id] = (name, config.to_metric(uid=metric_id, name=name))
    return options


def _evaluate_aggregate(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric: Metric,
    data_source_ids: tuple[DataSourceID, ...],
    filter_ids: tuple[FilterID, ...],
    remove_outliers: bool,
    metric_expr: pl.Expr,
    group_keys: list[pl.Expr] | None = None,
    chain_exprs: list[pl.Expr] | None = None,
) -> list[tuple[t.Any, ...]]:
    """Aggregate one metric, optionally grouped by the given key expressions.

    Args:
        data_repository: Data source access.
        filter_repository: Filter expression resolution.
        metric: The metric to aggregate.
        data_source_ids: Sources the metric is scoped to.
        filter_ids: Filters applied to the frame.
        remove_outliers: Whether to drop outlier rows.
        metric_expr: The compiled metric expression.
        group_keys: Optional grouping expressions; empty/None aggregates over
            all rows into a single value.
        chain_exprs: Optional dependent expressions (ancestor band columns) that
            must be applied sequentially before grouping.

    Returns:
        A list of result rows. Each row is ``(*key_values, value)`` when
        grouping is used, or ``(value,)`` for an ungrouped aggregate.
    """
    ds_ids: list[DataSourceID] = list(data_source_ids) or list(
        data_repository.data_sources.keys()
    )
    lf = data_repository.get_lazyframe(data_source_ids=ds_ids)
    data_filter = filter_repository.get_combined_expression(
        list(filter_ids), remove_outliers=remove_outliers
    )
    lf = lf.filter(data_filter)
    if chain_exprs:
        lf = _apply_chain_exprs(lf, chain_exprs)

    if group_keys:
        result_df = lf.group_by(*group_keys).agg(metric_expr.alias("__value")).collect()
        return list(result_df.iter_rows())

    result_df = lf.select(metric_expr.alias("__value")).collect()
    if result_df.is_empty():
        return [(None,)]
    return list(result_df.iter_rows())


def _evaluate_groups(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric: Metric,
    data_source_ids: tuple[DataSourceID, ...],
    filter_ids: tuple[FilterID, ...],
    remove_outliers: bool,
    group_expr: pl.Expr,
    chain_exprs: list[pl.Expr] | None = None,
) -> dict[str, float | None]:
    """Aggregate one metric per segment and return seg-id -> value.

    Args:
        data_repository: Data source access.
        filter_repository: Filter expression resolution.
        metric: The metric to aggregate.
        data_source_ids: Sources the metric is scoped to.
        filter_ids: Filters applied to the frame.
        remove_outliers: Whether to drop outlier rows.
        group_expr: Expression producing the segment id per row.
        chain_exprs: Optional dependent expressions (ancestor band columns) that
            must be applied sequentially before grouping.
    """
    metric_expr = metric.metric_expr
    if metric_expr is None:
        raise ValueError(f"Metric '{metric.name}' has no compiled expression.")

    rows = _evaluate_aggregate(
        data_repository=data_repository,
        filter_repository=filter_repository,
        metric=metric,
        data_source_ids=data_source_ids,
        filter_ids=filter_ids,
        remove_outliers=remove_outliers,
        metric_expr=metric_expr,
        group_keys=[group_expr],
        chain_exprs=chain_exprs,
    )

    values: dict[str, float | None] = {}
    for row in rows:
        seg_str = row[0]
        if seg_str is None:
            continue
        values[str(seg_str)] = row[1]
    return values


def _validate_metric_for_sources(
    metric: Metric,
    data_repository: DataRepository,
) -> bool:
    """Return True if the metric resolves against its selected sources' columns."""
    ds_ids: list[DataSourceID] = list(metric.data_source_ids) or list(
        data_repository.data_sources.keys()
    )
    available_columns = [col for col, _ in data_repository.common_columns(ds_ids)]
    try:
        metric.validate_query(available_columns=available_columns)
    except (ValueError, TypeError):
        return False
    return True


def evaluate_band_table(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric_repository: MetricRepository,
    scg: SimulationConfigGenerator,
    so: SimulationOutput,
    metric_ids: tuple[MetricID, ...] = (),
    filter_ids: tuple[FilterID, ...] = (),
    scalars_enabled: bool = True,
    remove_outliers: bool = True,
    groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] | None = None,
    variable_name: str | None = None,
    assignment_expr: pl.Expr | None = None,
    segments: OrderedDict[RiskSegmentID, RiskSegment] | None = None,
    chain_exprs: list[pl.Expr] | None = None,
    show_total_row: bool = False,
) -> BandTableResult:
    """Evaluate the per-band metric table for an iteration.

    By default the bands resolve from ``so.groups``/``so.variable_name``. For
    editable variants and double-variable iterations the caller may instead
    pass explicit ``groups``/``variable_name`` and, for a double-variable
    band table (where rows map through a chain of parent bands), a fully
    composed ``assignment_expr`` and the ``segments``/``columns`` that result.

    Args:
        data_repository: Data source access.
        filter_repository: Filter expression resolution.
        metric_repository: Registered user metrics.
        scg: The iteration's simulation config generator (bad rates, scalars, segments).
        so: The iteration's simulation output (groups/variable).
        metric_ids: Built-in bad rate sentinels and user metrics to include.
        filter_ids: Filters applied to every column.
        scalars_enabled: Whether to scale the dev (annualized) bad rate columns.
        remove_outliers: Whether to drop outlier rows.
        groups: Explicit working bands, overriding ``so.groups`` when provided.
        variable_name: Explicit banded variable, overriding ``so.variable_name``.
        assignment_expr: Explicit row-to-band assignment expression, overriding
            the one derived from ``groups``/``variable_name``.
        segments: Explicit segments in row order, overriding those derived from
            the groups' keys.
        chain_exprs: Dependent band assignment expressions (ancestors along the
            iteration chain) applied sequentially before grouping; used for
            double-variable band tables whose row assignment references an
            ancestor band column.
        show_total_row: Whether to compute a total aggregate over all rows.

    Returns:
        A :class:`BandTableResult` with per-segment values and warning/error lists.
    """
    result = BandTableResult()

    effective_groups = groups if groups is not None else so.groups
    effective_variable = variable_name if variable_name is not None else so.variable_name

    if not effective_groups:
        result.errors.append("No groups produced for this output.")
        return result

    risk_segment_config: RiskSegmentConfig = scg.risk_segment_config
    if segments is not None:
        result.segments = segments
    else:
        result.segments = OrderedDict()
        for seg_id in effective_groups:
            seg = risk_segment_config.segments.get(seg_id)
            if seg is not None:
                result.segments[seg_id] = seg

    group_expr = (
        assignment_expr
        if assignment_expr is not None
        else segment_assignment_expr(effective_groups, effective_variable)
    )

    scalar = scg.scalar_config.get_scalar(scg.bad_rate_type)

    bad_rate_columns: list[_BuiltinBadRateColumn] = builtin_bad_rate_columns(
        scg, metric_ids
    )
    dev_bad_rate_names = {name for name, _, _, is_dev in bad_rate_columns if is_dev}
    bad_rate_sources_by_name = {
        name: sources for name, _, sources, _ in bad_rate_columns
    }

    for name, bad_rate_metric, _sources, _is_dev in bad_rate_columns:
        if _validate_metric_for_sources(bad_rate_metric, data_repository):
            result.columns.append((name, bad_rate_metric))
        else:
            result.warnings.append(
                f"{name} column is unavailable for its selected data sources."
            )

    # Collect the user metrics in selection order, validating each against its
    # own sources; invalid ones are dropped with a warning.
    metrics: list[Metric] = []
    for metric_id in metric_ids:
        metric = metric_repository.metrics.get(metric_id)
        if metric is None:
            result.warnings.append(f"Metric {metric_id} no longer exists.")
            continue
        if not _validate_metric_for_sources(metric, data_repository):
            result.warnings.append(
                f"Metric '{metric.name}' is undefined for its selected data sources."
            )
            continue
        result.columns.append((metric.name, metric))
        metrics.append(metric)

    if result.errors:
        return result

    # Evaluate each column with a frame scoped to that metric's data sources.
    # Dev (annualized) bad rate columns are scaled when scalars are enabled;
    # test (early) bad rates and user metrics are never scaled.
    for column_name, metric in result.columns:
        is_dev_bad_rate = column_name in dev_bad_rate_names
        sources = bad_rate_sources_by_name.get(column_name, tuple(metric.data_source_ids))

        column_values = _evaluate_groups(
            data_repository=data_repository,
            filter_repository=filter_repository,
            metric=metric,
            data_source_ids=sources,
            filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            group_expr=group_expr,
            chain_exprs=chain_exprs,
        )

        for seg_id in result.segments:
            raw = column_values.get(str(seg_id))
            if is_dev_bad_rate and raw is not None and scalars_enabled:
                factor = _scalar_factor(result.segments[seg_id], scalar)
                raw = float(raw) * factor
            result.values.setdefault(seg_id, {})[column_name] = raw

        if show_total_row:
            metric_expr = metric.metric_expr
            total_rows = (
                _evaluate_aggregate(
                    data_repository=data_repository,
                    filter_repository=filter_repository,
                    metric=metric,
                    data_source_ids=sources,
                    filter_ids=filter_ids,
                    remove_outliers=remove_outliers,
                    metric_expr=metric_expr,
                    chain_exprs=chain_exprs,
                )
                if metric_expr is not None
                else [(None,)]
            )
            total_raw = total_rows[0][0] if total_rows else None
            result.total[column_name] = total_raw

    return result


class MetricGridResult:
    """Result of a double-variable metric grid evaluation.

    Attributes:
        columns: Ordered ``(column name, metric)`` pairs in display order.
        row_groups: Child (row) bands in band order.
        parent_segments: Parent (column) bands in band order.
        values: Per-cell values keyed by ``(row_gid, parent_seg_id)`` then
            column name.
        total_row: When a total row is requested, per-column values keyed by
            parent band id.
        total_column: When a total column is requested, per-column values keyed
            by row band id.
        corner_total: When both totals are requested, per-column aggregate over
            all rows.
        warnings: Non-fatal issues (e.g. metrics skipped as invalid).
        errors: Fatal errors that prevented evaluation altogether.
    """

    def __init__(
        self,
        columns: list[_Column] | None = None,
        row_groups: (
            OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] | None
        ) = None,
        parent_segments: OrderedDict[RiskSegmentID, RiskSegment] | None = None,
        values: dict[tuple[RiskSegmentID, RiskSegmentID], dict[str, float | None]]
        | None = None,
        total_row: dict[str, dict[RiskSegmentID, float | None]] | None = None,
        total_column: dict[str, dict[RiskSegmentID, float | None]] | None = None,
        corner_total: dict[str, float | None] | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.columns: list[_Column] = columns if columns is not None else []
        self.row_groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup] = (
            row_groups if row_groups is not None else OrderedDict()
        )
        self.parent_segments: OrderedDict[RiskSegmentID, RiskSegment] = (
            parent_segments if parent_segments is not None else OrderedDict()
        )
        self.values: dict[tuple[RiskSegmentID, RiskSegmentID], dict[str, float | None]] = (
            values if values is not None else {}
        )
        self.total_row: dict[str, dict[RiskSegmentID, float | None]] = (
            total_row if total_row is not None else {}
        )
        self.total_column: dict[str, dict[RiskSegmentID, float | None]] = (
            total_column if total_column is not None else {}
        )
        self.corner_total: dict[str, float | None] = (
            corner_total if corner_total is not None else {}
        )
        self.warnings: list[str] = warnings if warnings is not None else []
        self.errors: list[str] = errors if errors is not None else []

    def cell(self, row_gid: RiskSegmentID, parent_seg_id: RiskSegmentID, column: str) -> float | None:
        """Return the raw value for one grid cell.

        Args:
            row_gid: The row (child) band id.
            parent_seg_id: The parent (column) band id.
            column: The column name.

        Returns:
            The cell's raw value, or None when the cell has no value.
        """
        return self.values.get((row_gid, parent_seg_id), {}).get(column)


def _apply_chain_exprs(lf: pl.LazyFrame, exprs: list[pl.Expr]) -> pl.LazyFrame:
    """Apply a sequence of dependent band assignment expressions left to right."""
    for expr in exprs:
        lf = lf.with_columns(expr)
    return lf


def evaluate_metric_grid(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric_repository: MetricRepository,
    scg: SimulationConfigGenerator,
    variable_name: str,
    row_groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
    parent_segments: OrderedDict[RiskSegmentID, RiskSegment],
    parent_chain_exprs: list[pl.Expr],
    parent_col: str,
metric_ids: tuple[MetricID, ...] = (),
    filter_ids: tuple[FilterID, ...] = (),
    scalars_enabled: bool = True,
    remove_outliers: bool = True,
    grid: RiskSegmentGrid | None = None,
    show_total_row: bool = False,
    show_total_column: bool = False,
) -> MetricGridResult:
    """Evaluate the double-variable metric grid for an iteration.

    Each grid cell aggregates a column's metric over the rows falling into one
    ``(row group, parent band)`` pair. The dev bad rate column is scaled per
    cell by the target band's risk scalar factor (the cell's grid mapping is
    used to pick the target band; unmapped cells use the parent band itself).

    Args:
        data_repository: Data source access.
        filter_repository: Filter expression resolution.
        metric_repository: Registered user metrics.
        scg: The iteration's simulation config generator (bad rates, scalars, segments).
        variable_name: The child (row) variable being banded.
        row_groups: Child bands in row order.
        parent_segments: Parent (column) bands in band order.
        parent_chain_exprs: Dependent expressions computing the parent band
            column from base columns (they must be applied sequentially).
        parent_col: The alias of the parent band column within the frame.
        metric_ids: Built-in bad rate sentinels and user metrics to include.
        filter_ids: Filters applied to every column.
        scalars_enabled: Whether to scale the dev (annualized) bad rate columns.
        remove_outliers: Whether to drop outlier rows.
        grid: Cell to target band mapping used for scalar resolution; when None,
            each cell is treated as its parent band.
        show_total_row: Whether to compute a total row (per parent band) and,
            when ``show_total_column`` is also set, the corner total.
        show_total_column: Whether to compute a total column (per row group).

    Returns:
        A :class:`MetricGridResult` with per-cell values and warning/error lists.
    """
    result = MetricGridResult(
        row_groups=row_groups,
        parent_segments=parent_segments,
    )

    if not row_groups:
        result.errors.append("No groups produced for this output.")
        return result
    if not parent_segments:
        result.errors.append("No parent segments available for this grid.")
        return result

    row_expr = segment_assignment_expr(row_groups, variable_name)
    scalar = scg.scalar_config.get_scalar(scg.bad_rate_type)

    bad_rate_columns: list[_BuiltinBadRateColumn] = builtin_bad_rate_columns(
        scg, metric_ids
    )
    dev_bad_rate_names = {name for name, _, _, is_dev in bad_rate_columns if is_dev}
    bad_rate_sources_by_name = {
        name: sources for name, _, sources, _ in bad_rate_columns
    }

    for name, bad_rate_metric, _sources, _is_dev in bad_rate_columns:
        if _validate_metric_for_sources(bad_rate_metric, data_repository):
            result.columns.append((name, bad_rate_metric))
        else:
            result.warnings.append(
                f"{name} column is unavailable for its selected data sources."
            )

    metrics: list[Metric] = []
    for metric_id in metric_ids:
        metric = metric_repository.metrics.get(metric_id)
        if metric is None:
            result.warnings.append(f"Metric {metric_id} no longer exists.")
            continue
        if not _validate_metric_for_sources(metric, data_repository):
            result.warnings.append(
                f"Metric '{metric.name}' is undefined for its selected data sources."
            )
            continue
        result.columns.append((metric.name, metric))
        metrics.append(metric)

    if result.errors:
        return result

    for column_name, metric in result.columns:
        is_dev_bad_rate = column_name in dev_bad_rate_names
        sources = bad_rate_sources_by_name.get(column_name, tuple(metric.data_source_ids))

        try:
            metric_expr = metric.metric_expr
            if metric_expr is None:
                raise ValueError(f"Metric '{metric.name}' has no compiled expression.")
            cell_values = _evaluate_grid_cells(
                data_repository=data_repository,
                filter_repository=filter_repository,
                metric=metric,
                data_source_ids=sources,
                filter_ids=filter_ids,
                remove_outliers=remove_outliers,
                row_expr=row_expr,
                parent_chain_exprs=parent_chain_exprs,
                parent_col=parent_col,
            )
            column_totals = _evaluate_grid_totals(
                data_repository=data_repository,
                filter_repository=filter_repository,
                metric=metric,
                data_source_ids=sources,
                filter_ids=filter_ids,
                remove_outliers=remove_outliers,
                metric_expr=metric_expr,
                row_expr=row_expr,
                parent_chain_exprs=parent_chain_exprs,
                parent_col=parent_col,
                row_groups=row_groups,
                parent_segments=parent_segments,
                show_total_row=show_total_row,
                show_total_column=show_total_column,
            )
        except pl.exceptions.PolarsError as exc:
            result.warnings.append(
                f"Metric '{metric.name}' cannot be resolved for the iteration grid: {exc}"
            )
            continue

        total_row_values = column_totals.total_row
        total_column_values = column_totals.total_column
        corner_value = column_totals.corner_total

        for row_gid in row_groups:
            for parent_seg_id in parent_segments:
                raw = cell_values.get((str(row_gid), str(parent_seg_id)))
                if is_dev_bad_rate and raw is not None and scalars_enabled:
                    target_seg_id = (
                        grid.get(row_gid, {}).get(parent_seg_id, parent_seg_id)
                        if grid
                        else parent_seg_id
                    )
                    target_seg = parent_segments.get(target_seg_id)
                    if target_seg is not None:
                        raw = float(raw) * _scalar_factor(target_seg, scalar)
                result.values.setdefault((row_gid, parent_seg_id), {})[
                    column_name
                ] = raw

        if is_dev_bad_rate and scalars_enabled:
            # Total row keeps each parent band's own scalar; the total column
            # and corner total carry no scalar (factor 1.0), matching v1.
            for parent_seg_id, raw in total_row_values.items():
                if raw is None:
                    continue
                seg = parent_segments.get(parent_seg_id)
                if seg is not None:
                    total_row_values[parent_seg_id] = (
                        float(raw) * _scalar_factor(seg, scalar)
                    )
        if total_row_values:
            result.total_row[column_name] = total_row_values
        if total_column_values:
            result.total_column[column_name] = total_column_values
        if show_total_row and show_total_column:
            result.corner_total[column_name] = corner_value

    return result


def _evaluate_grid_cells(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric: Metric,
    data_source_ids: tuple[DataSourceID, ...],
    filter_ids: tuple[FilterID, ...],
    remove_outliers: bool,
    row_expr: pl.Expr,
    parent_chain_exprs: list[pl.Expr],
    parent_col: str,
) -> dict[tuple[str, str], float | None]:
    """Aggregate one metric per (row_group, parent_band) cell."""
    metric_expr = metric.metric_expr
    if metric_expr is None:
        raise ValueError(f"Metric '{metric.name}' has no compiled expression.")

    rows = _evaluate_aggregate(
        data_repository=data_repository,
        filter_repository=filter_repository,
        metric=metric,
        data_source_ids=data_source_ids,
        filter_ids=filter_ids,
        remove_outliers=remove_outliers,
        metric_expr=metric_expr,
        group_keys=[pl.col(parent_col), row_expr],
        chain_exprs=parent_chain_exprs,
    )

    values: dict[tuple[str, str], float | None] = {}
    for row in rows:
        parent_seg = row[0]
        row_gid = row[1]
        if parent_seg is None or row_gid is None:
            continue
        values[(str(row_gid), str(parent_seg))] = row[2]
    return values


class _GridTotals(t.NamedTuple):
    """Per-column grid totals: row (per parent band), column (per row group)."""

    total_row: dict[RiskSegmentID, float | None]
    total_column: dict[RiskSegmentID, float | None]
    corner_total: float | None


def _evaluate_grid_totals(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric: Metric,
    data_source_ids: tuple[DataSourceID, ...],
    filter_ids: tuple[FilterID, ...],
    remove_outliers: bool,
    metric_expr: pl.Expr,
    row_expr: pl.Expr,
    parent_chain_exprs: list[pl.Expr],
    parent_col: str,
    row_groups: OrderedDict[RiskSegmentID, NumericalGroup | CategoricalGroup],
    parent_segments: OrderedDict[RiskSegmentID, RiskSegment],
    show_total_row: bool,
    show_total_column: bool,
) -> _GridTotals:
    """Aggregate one metric's grid totals (row/column/corner)."""
    parent_str_to_id = {str(sid): sid for sid in parent_segments}
    row_str_to_id = {str(gid): gid for gid in row_groups}

    total_row: dict[RiskSegmentID, float | None] = {}
    total_column: dict[RiskSegmentID, float | None] = {}
    corner_total: float | None = None

    if show_total_row:
        rows = _evaluate_aggregate(
            data_repository=data_repository,
            filter_repository=filter_repository,
            metric=metric,
            data_source_ids=data_source_ids,
            filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            metric_expr=metric_expr,
            group_keys=[pl.col(parent_col)],
            chain_exprs=parent_chain_exprs,
        )
        for row in rows:
            parent_str = row[0]
            if parent_str is None:
                continue
            parent_id = parent_str_to_id.get(parent_str)
            if parent_id is not None:
                total_row[parent_id] = row[1]

    if show_total_column:
        rows = _evaluate_aggregate(
            data_repository=data_repository,
            filter_repository=filter_repository,
            metric=metric,
            data_source_ids=data_source_ids,
            filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            metric_expr=metric_expr,
            group_keys=[row_expr],
            chain_exprs=parent_chain_exprs,
        )
        for row in rows:
            row_str = row[0]
            if row_str is None:
                continue
            row_id = row_str_to_id.get(row_str)
            if row_id is not None:
                total_column[row_id] = row[1]

    if show_total_row and show_total_column:
        rows = _evaluate_aggregate(
            data_repository=data_repository,
            filter_repository=filter_repository,
            metric=metric,
            data_source_ids=data_source_ids,
            filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            metric_expr=metric_expr,
            chain_exprs=parent_chain_exprs,
        )
        corner_total = rows[0][0] if rows else None

    return _GridTotals(
        total_row=total_row,
        total_column=total_column,
        corner_total=corner_total,
    )


__all__ = [
    "BandTableResult",
    "MetricGridResult",
    "double_var_assignment_expr",
    "evaluate_band_table",
    "evaluate_metric_grid",
    "segment_assignment_expr",
]
