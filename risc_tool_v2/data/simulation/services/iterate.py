"""Iteration band-table evaluation: per-band metrics over a simulation output's groups.

The table always includes the parent simulation's dev bad rate column, computed
from the same dev bad rate the simulation itself used; when scalars are enabled
it is scaled per segment by ``max(maf * portfolio_scalar, 1.0)``. Additional
user metrics are evaluated with frames scoped to each metric's own selected data
sources (all sources when none are selected), mirroring the rule that metrics
(and simulations) are defined only for their selected data sources.
"""

from collections import OrderedDict

import polars as pl

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import DataSourceID, FilterID, MetricID, RiskSegmentID
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
    SimulationConfigGenerator,
    SimulationOutput,
)

_Column = tuple[str, Metric]
_Values = dict[RiskSegmentID, dict[str, float | None]]


class BandTableResult:
    """Result of an iteration band-table evaluation.

    Attributes:
        columns: Ordered ``(column name, metric)`` pairs in display order.
        segments: Risk segments in band order (from the iterator's groups).
        values: Per-segment raw values keyed by segment ID then column name.
        warnings: Non-fatal issues (e.g. metrics skipped as invalid).
        errors: Fatal errors that prevented evaluation altogether.
    """

    def __init__(
        self,
        columns: list[_Column] | None = None,
        segments: OrderedDict[RiskSegmentID, RiskSegment] | None = None,
        values: _Values | None = None,
        warnings: list[str] | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.columns: list[_Column] = columns if columns is not None else []
        self.segments: OrderedDict[RiskSegmentID, RiskSegment] = (
            segments if segments is not None else OrderedDict()
        )
        self.values: _Values = values if values is not None else {}
        self.warnings: list[str] = warnings if warnings is not None else []
        self.errors: list[str] = errors if errors is not None else []


def _segment_assignment_expr(
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


def _scalar_factor(segment: RiskSegment, scalar: LossRateScalar) -> float:
    """Return this segment's risk scalar factor: max(maf * portfolio_scalar, 1.0)."""
    return max(segment.maf(scalar.loss_rate_type) * scalar.portfolio_scalar, 1.0)


def _dev_bad_rate_column(
    scg: SimulationConfigGenerator,
) -> tuple[str, Metric, tuple[DataSourceID, ...]]:
    """Return (name, metric, data_source_ids) for the simulation's dev bad rate.

    Raises:
        ValueError: When no dev bad rate is configured for the bad rate type.
    """
    if scg.bad_rate_type == LossRateTypes.ULR:
        bad_rate_config = scg.dev_unit_bad_rate
    else:
        bad_rate_config = scg.dev_dollar_bad_rate

    if bad_rate_config is None:
        raise ValueError(f"No dev bad rate configured for {scg.bad_rate_type.value}")

    symbol = "$" if scg.bad_rate_type == LossRateTypes.DLR else "#"
    metric = bad_rate_config.to_metric(
        uid=MetricID.TEMPORARY,
        name=f"Dev {symbol} Bad Rate",
    )
    return metric.name, metric, tuple(bad_rate_config.data_source_ids)


def _evaluate_groups(
    *,
    data_repository: DataRepository,
    filter_repository: FilterRepository,
    metric: Metric,
    data_source_ids: tuple[DataSourceID, ...],
    filter_ids: tuple[FilterID, ...],
    remove_outliers: bool,
    group_expr: pl.Expr,
) -> dict[str, float | None]:
    """Aggregate one metric per segment and return seg-id -> value."""
    ds_ids: list[DataSourceID] = list(data_source_ids) or list(
        data_repository.data_sources.keys()
    )
    lf = data_repository.get_lazyframe(data_source_ids=ds_ids)
    data_filter = filter_repository.get_combined_expression(
        list(filter_ids), remove_outliers=remove_outliers
    )
    lf = lf.filter(data_filter)

    metric_expr = metric.metric_expr
    if metric_expr is None:
        raise ValueError(f"Metric '{metric.name}' has no compiled expression.")

    result_df = lf.group_by(group_expr).agg(metric_expr.alias("__value")).collect()

    values: dict[str, float | None] = {}
    for row in result_df.iter_rows():
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
) -> BandTableResult:
    """Evaluate the per-band metric table for an iteration.

    Args:
        data_repository: Data source access.
        filter_repository: Filter expression resolution.
        metric_repository: Registered user metrics.
        scg: The iteration's simulation config generator (bad rates, scalars, segments).
        so: The iteration's simulation output (groups/variable).
        metric_ids: User metrics to include alongside the dev bad rate.
        filter_ids: Filters applied to every column.
        scalars_enabled: Whether to scale the dev bad rate by risk scalar factor.
        remove_outliers: Whether to drop outlier rows.

    Returns:
        A :class:`BandTableResult` with per-segment values and warning/error lists.
    """
    result = BandTableResult()

    if not so.groups:
        result.errors.append("No groups produced for this output.")
        return result

    risk_segment_config: RiskSegmentConfig = scg.risk_segment_config
    segments: OrderedDict[RiskSegmentID, RiskSegment] = OrderedDict()
    for seg_id in so.groups:
        seg = risk_segment_config.segments.get(seg_id)
        if seg is not None:
            segments[seg_id] = seg
    result.segments = segments

    group_expr = _segment_assignment_expr(so.groups, so.variable_name)

    scalar = scg.scalar_config.get_scalar(scg.bad_rate_type)

    bad_rate_name: str | None = None
    bad_rate_sources: tuple[DataSourceID, ...] = ()

    try:
        bad_rate_name, bad_rate_metric, bad_rate_sources = _dev_bad_rate_column(scg)
    except ValueError as exc:
        result.errors.append(str(exc))
    else:
        if _validate_metric_for_sources(bad_rate_metric, data_repository):
            result.columns.append((bad_rate_name, bad_rate_metric))
        else:
            result.warnings.append(
                "Dev bad rate column is unavailable for the selected dev sources."
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
    # The dev bad rate column is unscaled unless scalars are enabled.
    for column_name, metric in result.columns:
        is_bad_rate = column_name == bad_rate_name if bad_rate_name else False
        sources = bad_rate_sources if is_bad_rate else tuple(metric.data_source_ids)

        column_values = _evaluate_groups(
            data_repository=data_repository,
            filter_repository=filter_repository,
            metric=metric,
            data_source_ids=sources,
            filter_ids=filter_ids,
            remove_outliers=remove_outliers,
            group_expr=group_expr,
        )

        for seg_id in segments:
            raw = column_values.get(str(seg_id))
            if is_bad_rate and raw is not None and scalars_enabled:
                factor = _scalar_factor(segments[seg_id], scalar)
                raw = float(raw) * factor
            result.values.setdefault(seg_id, {})[column_name] = raw

    return result


__all__ = ["BandTableResult", "evaluate_band_table"]
