"""UI components for Outlier Rules management in the Data Explorer.

Provides interactive widgets for creating, viewing, and modifying outlier
rules, including boxplot visualization and quantile tables.
"""

import altair as alt
import streamlit as st

from risc_tool.data.models.enums import (
    ComparisonOperation,
    PercentileOptions,
    VariableType,
)
from risc_tool.data.models.types import FilterID
from risc_tool.data.session import Session
from risc_tool.utils.logging import get_logger

logger = get_logger(__name__)


def show_boxplot(variable: str):
    """Render an interactive boxplot with hoverable percentile markers.

    Args:
        variable: The name of the numerical variable to visualize.
    """
    session: Session = st.session_state["session"]
    de_view_model = session.data_explorer_view_model

    df, perc_df = de_view_model.get_boxplot_data(
        variable_name=variable,
    )

    if df is None or perc_df is None:
        logger.error("Failed to generate boxplot for '%s': data was None", variable)
        st.error(f"Error generating boxplot for variable {variable}.")
        return

    hover = alt.selection_point(
        on="mouseover",
        nearest=True,
        fields=["Percentile"],
        empty=False,
    )

    boxplot = (
        alt.Chart(df)
        .mark_boxplot(
            orient="horizontal",
            size=20,
            color="#44c1ca",
            outliers=alt.MarkConfig(size=10, opacity=1),
        )
        .encode(x=alt.X("Value:Q", title="", scale=alt.Scale(zero=False)))
    )

    anchors = (
        alt.Chart(perc_df)
        .mark_point(size=300, opacity=0)
        .encode(
            x="Value:Q", tooltip=["Percentile:N", alt.Tooltip("Value:Q", format=".2f")]
        )
        .add_params(hover)
    )

    arrows = (
        alt.Chart(perc_df)
        .mark_text(text="▼", size=16, baseline="bottom", dy=0)
        .encode(
            x="Value:Q",
            color=alt.condition(hover, alt.value("red"), alt.value("gray")),
        )
    )

    text_above = (
        alt.Chart(perc_df)
        .mark_text(
            align="center",
            baseline="bottom",
            dy=-10,
            fontWeight="bold",
            size=12,
        )
        .encode(
            x="Value:Q",
            text="Percentile:N",
            color=alt.condition(hover, alt.value("red"), alt.value("white")),
        )
    )

    text_below = (
        alt.Chart(perc_df)
        .mark_text(
            align="center",
            baseline="top",
            dy=10,
            fontWeight="bold",
            size=12,
        )
        .encode(
            x="Value:Q",
            text="Value_Str:N",
            color=alt.condition(hover, alt.value("red"), alt.value("white")),
        )
    )

    st.altair_chart(
        boxplot + anchors + arrows + text_above + text_below,
        width="stretch",
        height=150,
    )


def show_quantile_table(variable: str, quantiles: list[float]):
    """Render a table of quantile values for a numerical variable.

    Args:
        variable: The name of the numerical variable to analyze.
        quantiles: List of quantile thresholds (e.g., [0.25, 0.5, 0.75]).
    """
    session: Session = st.session_state["session"]
    de_view_model = session.data_explorer_view_model

    df = de_view_model.get_quantile_table(
        variable_name=variable,
        quantiles=quantiles,
    )

    if df is None or df.empty:
        logger.error("Failed to generate quantile table for '%s'", variable)
        st.error(f"Error generating quantile table for variable {variable}.")
        return

    headers = df.columns

    st.dataframe(
        data=df,
        height=70,
        column_config={
            header: st.column_config.NumberColumn(alignment="center", format="%,.2f")
            for header in headers
        },
    )


def outlier_rule_input(
    outlier_id: FilterID,
    variable_name: str,
    comparison_op: ComparisonOperation,
    comparison_base: PercentileOptions | str,
    key: str = "new",
    errors: Exception | None = None,
    frequency: int = 0,
    show_dist_as_chart: bool = True,
):
    """Render an outlier rule editor card with variable selector and save/delete actions.

    Args:
        outlier_id: The FilterID of the rule, or FilterID.TEMPORARY for a new rule.
        variable_name: Currently selected variable name.
        comparison_op: Currently selected comparison operator.
        comparison_base: Currently selected percentile or threshold value.
        key: Unique widget key suffix for Streamlit state management.
        errors: Optional exception to display as an error message.
        frequency: Count of outlier rows found by this rule.
        show_dist_as_chart: If True, shows a boxplot; otherwise shows a quantile table.
    """
    session: Session = st.session_state["session"]
    de_view_model = session.data_explorer_view_model

    all_variables = [
        col
        for col, dtype in de_view_model.common_columns
        if dtype == VariableType.NUMERICAL
    ]

    with st.container(border=True):
        col1, col2, col3 = st.columns([6, 2, 3])

        new_variable_name = col1.selectbox(
            label="Select Variable",
            options=all_variables,
            index=all_variables.index(variable_name)
            if variable_name in all_variables
            else 0,
            key=f"outlier-variable-name-selector-{key}",
        )

        new_comparison_op = col2.selectbox(
            label="Comparison Operation",
            options=list(ComparisonOperation),
            index=list(ComparisonOperation).index(comparison_op),
            key=f"outlier-comparison-op-selector-{key}",
        )

        if isinstance(comparison_base, PercentileOptions):
            comparison_base_options = list(PercentileOptions)
            comparison_base_index = comparison_base_options.index(comparison_base)
        else:
            comparison_base_options = [comparison_base] + list(PercentileOptions)
            comparison_base_index = 0

        new_comparison_base = col3.selectbox(
            label="Comparison Base",
            options=comparison_base_options,
            index=comparison_base_index,
            format_func=PercentileOptions.format_perc,
            key=f"outlier-comparison-base-selector-{key}",
        )

        try:
            new_comparison_base = PercentileOptions(new_comparison_base)
        except ValueError:
            pass

        with st.container(horizontal=True):
            if errors:
                st.error(str(errors), width="stretch", icon=":material/error:")
            elif outlier_id != FilterID.TEMPORARY:
                st.metric(
                    label="Outlier Count",
                    value=f"{frequency:,}",
                    delta=None,
                    width="content",
                    format="localized",
                    border=True,
                )

            if not errors:
                try:
                    if show_dist_as_chart:
                        show_boxplot(new_variable_name)
                    else:
                        show_quantile_table(
                            new_variable_name,
                            [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99],
                        )
                except Exception as e:
                    logger.exception(
                        "Error rendering distribution for '%s'", new_variable_name
                    )
                    st.error(f"Error rendering distribution: {e}")

            save_button_disabled = (variable_name, comparison_op, comparison_base) == (
                new_variable_name,
                new_comparison_op,
                new_comparison_base,
            ) and (outlier_id != FilterID.TEMPORARY)

            with st.container(width=200):
                if st.button(
                    label="Rule Saved" if save_button_disabled else "Save Rule",
                    type="primary",
                    key=f"outlier-save-button-{key}",
                    disabled=save_button_disabled,
                    width="stretch",
                    icon=":material/download_done:"
                    if save_button_disabled
                    else ":material/save:",
                ):
                    logger.info("User saved outlier rule for '%s'", new_variable_name)
                    de_view_model.save_outlier(
                        outlier_id,
                        new_variable_name,
                        new_comparison_op,
                        new_comparison_base,
                    )
                    st.rerun()

                if outlier_id != FilterID.TEMPORARY:
                    if st.button(
                        label="Delete Rule",
                        type="primary",
                        key=f"outlier-delete-button-{key}",
                        icon=":material/delete:",
                        width="stretch",
                    ):
                        logger.info("User deleted outlier rule ID %s", outlier_id)
                        de_view_model.delete_outlier_rule(outlier_id)
                        st.rerun()


def outlier_rules():
    """Render the Outlier Rules section of the Data Explorer page.

    Displays existing outlier rules with their editors, a summary of total
    outlier count, and a form to add new outlier rules. Supports toggling
    between boxplot chart and quantile table display modes.
    """
    session: Session = st.session_state["session"]
    de_view_model = session.data_explorer_view_model

    show_dist_as_chart = st.sidebar.checkbox(
        label="Show Distribution as Chart",
        value=False,
        key="show_dist_as_chart",
    )

    if de_view_model.current_outlier_rules:
        # Sum frequencies of outlier rules
        total_outliers = de_view_model.total_outlier_count
        st.write(f"Total Outlier Count: {total_outliers:,}")

    for outlier_rule in de_view_model.current_outlier_rules:
        try:
            comparison_base = PercentileOptions(outlier_rule.comparison_base)
        except ValueError:
            comparison_base = str(outlier_rule.comparison_base)

        outlier_rule_input(
            outlier_id=outlier_rule.uid,
            variable_name=outlier_rule.variable_name,
            comparison_op=outlier_rule.comparison_op,
            comparison_base=comparison_base,
            key=str(outlier_rule.uid),
            errors=de_view_model.ol_errors.get(outlier_rule.uid),
            frequency=outlier_rule.frequency,
            show_dist_as_chart=show_dist_as_chart,
        )

    if de_view_model.current_outlier_rules:
        st.divider()
        st.subheader("Add New Outlier Rule")

    common_columns = de_view_model.common_columns
    first_numeric_column = next(
        (col for col, dtype in common_columns if dtype == VariableType.NUMERICAL), None
    )

    outlier_rule_input(
        outlier_id=FilterID.TEMPORARY,
        variable_name=first_numeric_column if first_numeric_column else "",
        comparison_op=ComparisonOperation.GT,
        comparison_base=PercentileOptions.PERC_99,
        errors=de_view_model.ol_errors.get(FilterID.TEMPORARY),
        show_dist_as_chart=show_dist_as_chart,
    )


__all__ = ["outlier_rules"]
