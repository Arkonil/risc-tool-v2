"""Auto-banding calculation services for numeric and categorical variables."""

from collections import OrderedDict

import polars as pl

from risc_tool.data.models.config import LossRateScalar, RiskSegmentConfig
from risc_tool.data.models.enums import LossRateTypes
from risc_tool.data.models.iteration import CategoricalGroup, NumericalGroup
from risc_tool.data.models.types import GroupID


def does_high_value_implies_high_risk(
    base_lf: pl.LazyFrame,
    variable: str,
    numerator: str,
    denominator: str,
) -> bool:
    """Determine whether higher values of a variable correlate with higher risk."""
    df = (
        base_lf
        .group_by(pl.col(variable))
        .agg(
            (pl.col(numerator).sum() / pl.col(denominator).sum())
            .fill_nan(0)
            .alias("ratio"),
        )
        .sort(variable)
        .with_columns(
            (pl.col("ratio") / pl.col("ratio").sum().fill_nan(1.0)).alias(
                "normalized_ratio"
            )
        )
        .with_columns(
            (pl.col(variable) * pl.col("normalized_ratio")).alias("m1"),
            (pl.col(variable) ** 2 * pl.col("normalized_ratio")).alias("m2"),
            (pl.col(variable) ** 3 * pl.col("normalized_ratio")).alias("m3"),
        )
        .sum()
        .select(
            (pl.col("m3") - 3 * pl.col("m2") * pl.col("m1") + 2 * pl.col("m1") ** 3)
            .lt(0)
            .alias("u3")
        )
        .collect()
    )

    if df.is_empty() or df.item(0, "u3") is None:
        return True
    return bool(df.item(0, "u3"))


def create_auto_numeric_bands(
    base_lf: pl.LazyFrame,
    variable: str,
    risk_segment_config: RiskSegmentConfig,
    loss_rate_scalar: LossRateScalar,
    numerator: str,
    denominator: str | None = None,
    mob: int = 12,
    use_scalar: bool = True,
    hv_imp_hr: bool | None = None,
) -> OrderedDict[GroupID, NumericalGroup]:
    """Create optimal numerical band boundaries for risk segments."""
    # Implementation goes here
    schema = base_lf.collect_schema()

    variable_schema = schema.get(variable)
    numerator_schema = schema.get(numerator)
    denominator_schema = schema.get(denominator) if denominator is not None else None

    if variable_schema is None:
        raise ValueError(
            f"Variable '{variable}' not found in the base LazyFrame schema"
        )

    if not variable_schema.is_numeric():
        raise ValueError(
            f"Variable '{variable}' must be numeric for numerical band creation"
        )

    if numerator_schema is None:
        raise ValueError(
            f"Numerators '{numerator}' not found in the base LazyFrame schema"
        )

    if denominator is not None and denominator_schema is None:
        raise ValueError(
            f"Denominators '{denominator}' not found in the base LazyFrame schema"
        )

    if loss_rate_scalar.loss_rate_type == LossRateTypes.DLR and denominator is None:
        raise ValueError("Denominators must be provided for DLR loss rate type")

    if mob <= 0:
        raise ValueError("Months on book (mob) must be a positive integer")

    variable_expr = pl.col(variable)
    numerator_expr = pl.col(numerator).sum()
    denominator_expr = (
        pl.col(denominator).sum() if denominator is not None else pl.len()
    )

    if hv_imp_hr is None:
        hv_imp_hr = does_high_value_implies_high_risk(
            base_lf=base_lf.group_by(variable_expr.alias("variable")).agg(
                numerator_expr.alias("numerator"),
                denominator_expr.alias("denominator"),
            ),
            variable="variable",
            numerator="numerator",
            denominator="denominator",
        )

    if not hv_imp_hr:
        base_lf = base_lf.with_columns((-variable_expr).alias(variable))

    group_lf = (
        base_lf
        .group_by(variable_expr)
        .agg(
            numerator_expr.alias("numerator"),
            denominator_expr.alias("denominator"),
            ((numerator_expr / denominator_expr) * (12 / mob)).alias("ratio"),
        )
        .sort(variable_expr)
    )

    last_cutoff = float("-inf")
    groups: OrderedDict[GroupID, NumericalGroup] = OrderedDict()

    for risk_seg_id, risk_seg in risk_segment_config.get_segments(
        original=False
    ).items():
        if risk_seg.upper_rate == float("inf"):
            groups[GroupID(risk_seg_id)] = NumericalGroup(
                lower_bound=last_cutoff,
                upper_bound=risk_seg.upper_rate,
            )
            break

        if use_scalar:
            risk_scalar_factor = (
                risk_seg.maf(loss_rate_scalar.loss_rate_type)
                * loss_rate_scalar.portfolio_scalar
            )
        else:
            risk_scalar_factor = 1.0

        result_df = (
            group_lf
            .with_columns(
                (pl.col("ratio") * risk_scalar_factor < risk_seg.upper_rate)
                .cast(pl.Int8)
                .cum_min()
                .cast(pl.Boolean)
                .alias("mask")
            )
            .filter(pl.col("mask"))
            .select(variable_expr)
            .collect()
            .to_series()
            .cast(pl.Float64)
        )

        if result_df.len() == 0:
            groups[GroupID(risk_seg_id)] = NumericalGroup(
                lower_bound=last_cutoff,
                upper_bound=last_cutoff,
            )
            continue

        max_value = max(result_df.to_list())

        groups[GroupID(risk_seg_id)] = NumericalGroup(
            lower_bound=last_cutoff,
            upper_bound=max_value,
        )
        last_cutoff = max_value

        group_lf = group_lf.filter(variable_expr > last_cutoff)

    if not hv_imp_hr:
        delta = 1.0

        for group_id in groups:
            group = groups[group_id]

            groups[group_id] = NumericalGroup(
                lower_bound=-group.upper_bound - delta,
                upper_bound=-group.lower_bound - delta,
            )

    return groups


def create_auto_categorical_bands(
    base_lf: pl.LazyFrame,
    variable: str,
    risk_segment_config: RiskSegmentConfig,
    loss_rate_scalar: LossRateScalar,
    numerator: str,
    denominator: str | None = None,
    mob: int = 12,
    use_scalar: bool = True,
) -> OrderedDict[GroupID, CategoricalGroup]:
    """Create optimal categorical groups for risk segments."""
    # Implementation goes here
    schema = base_lf.collect_schema()

    variable_schema = schema.get(variable)
    numerator_schema = schema.get(numerator)
    denominator_schema = schema.get(denominator) if denominator is not None else None

    if variable_schema is None:
        raise ValueError(
            f"Variable '{variable}' not found in the base LazyFrame schema"
        )

    if variable_schema.is_numeric():
        raise ValueError(
            f"Variable '{variable}' must be categorical for categorical band creation"
        )

    if numerator_schema is None:
        raise ValueError(
            f"Numerators '{numerator}' not found in the base LazyFrame schema"
        )

    if denominator is not None and denominator_schema is None:
        raise ValueError(
            f"Denominators '{denominator}' not found in the base LazyFrame schema"
        )

    if loss_rate_scalar.loss_rate_type == LossRateTypes.DLR and denominator is None:
        raise ValueError("Denominators must be provided for DLR loss rate type")

    if mob <= 0:
        raise ValueError("Months on book (mob) must be a positive integer")

    variable_expr = pl.col(variable)
    numerator_expr = pl.col(numerator).sum()
    denominator_expr = (
        pl.col(denominator).sum() if denominator is not None else pl.len()
    )

    group_lf = (
        base_lf
        .group_by(variable_expr)
        .agg(
            numerator_expr.alias("numerator"),
            denominator_expr.alias("denominator"),
            ((numerator_expr / denominator_expr) * (12 / mob)).alias("ratio"),
        )
        .sort(pl.col("ratio"))
    )

    groups: OrderedDict[GroupID, CategoricalGroup] = OrderedDict()

    found_categories: set[str] = set()

    for risk_seg_id, risk_seg in risk_segment_config.get_segments(
        original=False
    ).items():
        if risk_seg.upper_rate == float("inf"):
            groups[GroupID(risk_seg_id)] = CategoricalGroup(
                categories=set(group_lf.select(variable_expr).collect().to_series())
            )
            break

        if use_scalar:
            risk_scalar_factor = (
                risk_seg.maf(loss_rate_scalar.loss_rate_type)
                * loss_rate_scalar.portfolio_scalar
            )
        else:
            risk_scalar_factor = 1.0

        categories: set[str] = set(
            group_lf
            .filter((pl.col("ratio") * risk_scalar_factor) < risk_seg.upper_rate)
            .select(variable_expr)
            .unique(variable_expr)
            .cast(pl.Utf8)
            .collect()
            .to_series()
            .to_list()
        )

        groups[GroupID(risk_seg_id)] = CategoricalGroup(categories=categories)
        found_categories.update(categories)

        group_lf = group_lf.filter(~variable_expr.cast(pl.Utf8).is_in(found_categories))

    return groups


__all__ = [
    "does_high_value_implies_high_risk",
    "create_auto_numeric_bands",
    "create_auto_categorical_bands",
]
