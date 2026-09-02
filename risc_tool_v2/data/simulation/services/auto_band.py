"""Auto-banding calculation services for numeric and categorical variables."""

import math
from collections import OrderedDict
from decimal import Decimal

import polars as pl

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.core.uid import GroupID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.simulation.models.groups import CategoricalGroup, NumericalGroup
from risc_tool_v2.data.simulation.models.risk_segment import RiskSegmentConfig
from risc_tool_v2.data.simulation.models.scalar import LossRateScalar

logger = get_logger(__name__)


def _cummin_mask(expr: pl.Expr) -> pl.Expr:
    """Create a cumulative minimum mask for a given expression."""
    return expr.cast(pl.Int8).cum_min().cast(pl.Boolean)


def _delta_from_min_difference(minimum_difference: float | None) -> float:
    if (
        (minimum_difference is None)
        or (minimum_difference <= 0)
        or not math.isfinite(minimum_difference)
    ):
        return 1.0

    difference = Decimal(str(minimum_difference)).normalize()

    if difference >= 1:
        return float(10 ** math.floor(math.log10(float(difference))))

    decimal_places = difference.as_tuple().exponent
    assert isinstance(decimal_places, int), "Decimal places must be an integer"

    return float(Decimal(1).scaleb(decimal_places))


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

    group_df = (
        base_lf
        .group_by(variable_expr.alias("variable"))
        .agg(
            numerator_expr.alias("numerator"),
            denominator_expr.alias("denominator"),
        )
        .sort(pl.col("variable"))
        .with_row_index("__row_id")
        .collect()
    )

    groups: OrderedDict[GroupID, NumericalGroup] = OrderedDict()

    minimum_difference = (
        group_df
        .get_column("variable")
        .cast(pl.Float64)
        .sort()
        .diff()
        .abs()
        .drop_nulls()
        .min()
    )
    if isinstance(minimum_difference, (int, float, Decimal)):
        minimum_difference = (
            float(minimum_difference) if minimum_difference is not None else None
        )
        delta = _delta_from_min_difference(minimum_difference)
    else:
        delta = 1.0

    annualization_factor = 12 / mob

    if group_df.is_empty():
        for risk_seg_id, risk_seg in risk_segment_config.get_segments(
            normalize=True
        ).items():
            groups[GroupID(risk_seg_id)] = NumericalGroup(
                lower_bound=0.0,
                upper_bound=0.0,
            )
        return groups

    transformed_variable = not hv_imp_hr
    current_lower_bound = float(group_df.item(0, "variable")) - delta
    last_value = current_lower_bound
    transformed_variable_max = float(group_df.item(-1, "variable"))

    for risk_seg_id, risk_seg in risk_segment_config.get_segments(
        normalize=True
    ).items():
        if use_scalar:
            risk_scalar_factor = (
                risk_seg.maf(loss_rate_scalar.loss_rate_type)
                * loss_rate_scalar.portfolio_scalar
            )
        else:
            risk_scalar_factor = 1.0

        mask_state = group_df.select(
            "__row_id", pl.lit(None, dtype=pl.Boolean).alias("__mask_state")
        )
        mtc_temp = group_df

        for _ in range(100):
            if mtc_temp.is_empty():
                break

            forward = mtc_temp.with_columns(
                _cummin_mask(
                    (pl.col("numerator") / pl.col("denominator")) * annualization_factor
                    < risk_seg.upper_rate / risk_scalar_factor
                ).alias("__mask")
            )
            mask_state = (
                mask_state
                .join(
                    forward.select("__row_id", "__mask"),
                    on="__row_id",
                    how="left",
                )
                .with_columns(
                    pl
                    .when(pl.col("__mask") == False)
                    .then(pl.lit(False))
                    .otherwise(pl.col("__mask_state"))
                    .alias("__mask_state")
                )
                .drop("__mask")
            )
            mtc_temp = forward.filter(pl.col("__mask")).drop("__mask")

            if mtc_temp.is_empty():
                break

            backward = (
                mtc_temp
                .reverse()
                .with_columns(
                    pl.col("numerator").cum_sum().alias("__cum_numerator"),
                    pl.col("denominator").cum_sum().alias("__cum_denominator"),
                )
                .reverse()
                .with_columns(
                    _cummin_mask(
                        (pl.col("__cum_numerator") / pl.col("__cum_denominator"))
                        * annualization_factor
                        < risk_seg.upper_rate / risk_scalar_factor
                    ).alias("__mask")
                )
                .drop("__cum_numerator", "__cum_denominator")
            )
            mask_state = (
                mask_state
                .join(
                    backward.select("__row_id", "__mask"),
                    on="__row_id",
                    how="left",
                )
                .with_columns(
                    pl
                    .when(pl.col("__mask").fill_null(False))
                    .then(pl.lit(True))
                    .otherwise(pl.col("__mask_state"))
                    .alias("__mask_state")
                )
                .drop("__mask")
            )

            mtc_temp = backward.filter(~pl.col("__mask")).drop("__mask")

        selected = group_df.join(mask_state, on="__row_id", how="left").filter(
            pl.col("__mask_state") == True
        )
        if not selected.is_empty():
            last_value = float(selected.select(pl.col("variable").max()).item())

        groups[GroupID(risk_seg_id)] = NumericalGroup(
            lower_bound=current_lower_bound,
            upper_bound=last_value,
        )
        group_df = (
            group_df
            .join(mask_state, on="__row_id", how="left")
            .filter((pl.col("__mask_state") != True) | pl.col("__mask_state").is_null())
            .drop("__mask_state")
        )
        current_lower_bound = last_value

    last_group_id = next(reversed(groups), None)
    if last_group_id is not None:
        last_group = groups[last_group_id]
        if last_group.upper_bound < transformed_variable_max:
            groups[last_group_id] = NumericalGroup(
                lower_bound=last_group.lower_bound,
                upper_bound=transformed_variable_max,
            )

    if transformed_variable:
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

    group_df = (
        base_lf
        .group_by(variable_expr)
        .agg(
            numerator_expr.alias("numerator"),
            denominator_expr.alias("denominator"),
            ((numerator_expr / denominator_expr) * (12 / mob)).alias("ratio"),
        )
        .collect()
    )

    groups: OrderedDict[GroupID, CategoricalGroup] = OrderedDict()

    for risk_seg_id, risk_seg in risk_segment_config.get_segments(
        normalize=True
    ).items():
        if use_scalar:
            risk_scalar_factor = (
                risk_seg.maf(loss_rate_scalar.loss_rate_type)
                * loss_rate_scalar.portfolio_scalar
            )
        else:
            risk_scalar_factor = 1.0

        categories: frozenset[str] = frozenset(
            group_df
            .filter((pl.col("ratio") * risk_scalar_factor) < risk_seg.upper_rate)
            .get_column(variable)
            .unique()
            .cast(pl.String)
            .to_list()
        )

        groups[GroupID(risk_seg_id)] = CategoricalGroup(categories=categories)
        group_df = group_df.filter(~pl.col(variable).cast(pl.String).is_in(categories))

    last_group_id = next(reversed(groups), None)
    if last_group_id is not None:
        last_group = groups[last_group_id]
        remaining_categories: set[str] = set(
            group_df.get_column(variable).unique().cast(pl.String).to_list()
        )
        groups[last_group_id] = CategoricalGroup(
            categories=last_group.categories | remaining_categories
        )

    return groups


__all__ = [
    "create_auto_categorical_bands",
    "create_auto_numeric_bands",
    "does_high_value_implies_high_risk",
]
