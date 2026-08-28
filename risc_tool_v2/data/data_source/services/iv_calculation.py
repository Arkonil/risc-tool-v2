"""Service for calculating Information Value (IV) using Polars."""

import polars as pl

from risc_tool_v2.data.core.utils.logging import get_logger

logger = get_logger(__name__)


def calculate_iv(variable: pl.Series, target: pl.Series) -> float:
    logger.info(
        "Starting IV calculation for variable '%s' against target '%s' (rows=%d)",
        variable.name,
        target.name,
        len(variable),
    )

    df = pl.DataFrame({"variable": variable, "target": target}).drop_nulls()

    if df.height == 0:
        logger.warning("IV for '%s': no non-null records, returning 0.0", variable.name)
        return 0.0

    if df["target"].dtype == pl.Boolean:
        df = df.with_columns(pl.col("target").cast(pl.Int8))

    total_good = (df["target"] == 0).sum()
    total_bad = (df["target"] == 1).sum()

    if total_good == 0 or total_bad == 0:
        logger.warning(
            "IV for '%s': total_good=%d, total_bad=%d, returning 0.0",
            variable.name,
            total_good,
            total_bad,
        )
        return 0.0

    try:
        if df["variable"].dtype.is_numeric():
            logger.debug(
                "Binning numerical variable '%s' into 20 quantiles", variable.name
            )
            df = df.with_columns(pl.col("variable").qcut(20, allow_duplicates=True))

        lf = df.lazy()

        grouped = lf.group_by("variable").agg(
            good_count=(pl.col("target") == 0).sum(),
            bad_count=(pl.col("target") == 1).sum(),
        )

        grouped = grouped.with_columns(
            pct_good=pl.col("good_count") / total_good,
            pct_bad=pl.col("bad_count") / total_bad,
        )

        epsilon = 1e-6
        grouped = grouped.with_columns(
            pct_good=pl
            .when(pl.col("pct_good") < epsilon)
            .then(epsilon)
            .otherwise(pl.col("pct_good")),
            pct_bad=pl
            .when(pl.col("pct_bad") < epsilon)
            .then(epsilon)
            .otherwise(pl.col("pct_bad")),
        )

        grouped = grouped.with_columns(
            woe=(pl.col("pct_good") / pl.col("pct_bad")).log(),
        ).with_columns(iv=(pl.col("pct_good") - pl.col("pct_bad")) * pl.col("woe"))

        iv_total = grouped.collect()["iv"].sum()
        logger.info("Successfully calculated IV for '%s': %f", variable.name, iv_total)

        return float(iv_total)
    except Exception:
        logger.exception("IV calculation failed for '%s'", variable.name)
        return 0.0


__all__ = ["calculate_iv"]
