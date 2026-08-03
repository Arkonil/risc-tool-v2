"""Streamlit UI page for application configuration and scalar management."""

import typing as t

import streamlit as st

from risc_tool.data.models.enums import LossRateTypes, RSDetCol, ScalarTableColumn
from risc_tool.data.session import Session


def get_session() -> Session:
    """Retrieve Session instance from Streamlit session state."""
    if "session" not in st.session_state:
        st.session_state["session"] = Session()
    return st.session_state["session"]


def color_selector(
    color_type: t.Literal["font", "background"],
    selected_indices: list[int],
    current_color: str | None,
    disabled: bool,
) -> None:
    """Render color picker widget and assignment button."""
    session = get_session()
    config_vm = session.config_view_model

    col1, col2 = st.columns([1, 4])

    with col1:
        chosen_color = st.color_picker(
            label=f"{color_type.capitalize()} Color",
            label_visibility="collapsed",
            value=current_color,
        )

    callback = (
        config_vm.set_risk_seg_font_color
        if color_type == "font"
        else config_vm.set_risk_seg_bg_color
    )

    with col2:
        st.button(
            label=f"Use {color_type.capitalize()} Color",
            width="stretch",
            type="secondary",
            icon=":material/palette:",
            disabled=disabled,
            on_click=callback,
            kwargs={
                "segment_ids": selected_indices,
                "color": chosen_color,
            },
            key=f"btn_apply_color_{color_type}",
        )


def risk_seg_details_selector() -> None:
    """Render Risk Segment Details configuration editor and controls."""
    session = get_session()
    config_vm = session.config_view_model

    styler = config_vm.risk_segment_details_styler

    column_config = {
        RSDetCol.SELECTED.value: st.column_config.CheckboxColumn(
            label=RSDetCol.SELECTED.value,
            default=False,
        ),
        RSDetCol.RISK_SEGMENT.value: st.column_config.TextColumn(
            label=RSDetCol.RISK_SEGMENT.value,
        ),
        RSDetCol.LOWER_RATE.value: st.column_config.NumberColumn(
            label=RSDetCol.LOWER_RATE.value,
            format="%.2f %%",
            disabled=True,
        ),
        RSDetCol.UPPER_RATE.value: st.column_config.NumberColumn(
            label=RSDetCol.UPPER_RATE.value,
            format="%.2f %%",
            min_value=0.0,
            max_value=100.0,
        ),
        RSDetCol.BG_COLOR.value: st.column_config.TextColumn(
            label=RSDetCol.BG_COLOR.value,
            disabled=True,
        ),
        RSDetCol.FONT_COLOR.value: st.column_config.TextColumn(
            label=RSDetCol.FONT_COLOR.value,
            disabled=True,
        ),
    }

    col11, col12 = st.columns([4, 1], vertical_alignment="bottom")
    col21, col22 = st.columns([4, 1])

    col11.subheader("Risk Segment Details")

    with col21:
        edited_df = st.data_editor(
            styler,
            width="stretch",
            column_order=[
                RSDetCol.SELECTED.value,
                RSDetCol.RISK_SEGMENT.value,
                RSDetCol.LOWER_RATE.value,
                RSDetCol.UPPER_RATE.value,
                RSDetCol.FONT_COLOR.value,
                RSDetCol.BG_COLOR.value,
            ],
            column_config=column_config,
            hide_index=True,
            key="risk_seg_data_editor",
        )

        selected_mask = edited_df[RSDetCol.SELECTED.value]
        selected_indices = edited_df.index[selected_mask].tolist()
        has_selection = len(selected_indices) > 0

    col12.write("#### Controls")

    with col22:
        st.button(
            label="Add Row",
            width="stretch",
            type="secondary",
            icon=":material/add:",
            on_click=config_vm.add_risk_seg_row,
            key="btn_add_risk_seg_row",
        )

        st.button(
            label="Delete Selected",
            width="stretch",
            type="secondary",
            icon=":material/delete:",
            disabled=not has_selection,
            on_click=config_vm.delete_selected_risk_seg_rows,
            args=(selected_indices,),
            key="btn_delete_risk_seg_rows",
        )

        first_selected_font = (
            str(edited_df.loc[selected_indices[0], RSDetCol.FONT_COLOR.value])
            if has_selection
            else None
        )
        first_selected_bg = (
            str(edited_df.loc[selected_indices[0], RSDetCol.BG_COLOR.value])
            if has_selection
            else None
        )

        color_selector(
            color_type="font",
            selected_indices=selected_indices,
            current_color=first_selected_font,
            disabled=not has_selection,
        )

        color_selector(
            color_type="background",
            selected_indices=selected_indices,
            current_color=first_selected_bg,
            disabled=not has_selection,
        )

        st.button(
            label="Reset Defaults",
            width="stretch",
            type="secondary",
            icon=":material/restart_alt:",
            on_click=config_vm.set_risk_seg_default_values,
            key="btn_reset_risk_seg",
        )

    st.info(
        f"The value :blue-badge[**`None`**] in the column "
        f":blue-badge[**`{RSDetCol.UPPER_RATE.value}`**] "
        f"represents _+Infinity_.",
        icon=":material/info:",
    )

    # Validation & Edits
    validation_errors = config_vm.validate_risk_segments(edited_df)
    if validation_errors:
        for err in validation_errors:
            st.error(err, icon=":material/error:")
        return

    if config_vm.process_risk_segment_edits(edited_df):
        st.rerun()


def annualization_factor_editor(loss_rate_type: LossRateTypes) -> None:
    """Render annualization rate configuration editor."""
    session = get_session()
    config_vm = session.config_view_model

    scalar = config_vm.get_scalar(loss_rate_type)
    df = config_vm.get_annualization_df(loss_rate_type)

    col1, col2 = st.columns([3, 1])

    with col1:
        edited_df = st.data_editor(
            df,
            column_config={
                "Loss Rate Description": st.column_config.TextColumn(
                    label="Loss Rate Description",
                    disabled=True,
                ),
                "MOB": st.column_config.TextColumn(
                    label="MOB",
                    disabled=True,
                ),
                "Loss Rates": st.column_config.NumberColumn(
                    label=f"{'$' if loss_rate_type == LossRateTypes.DLR else '#'} Bad Rate",
                    required=True,
                    format="%.2f %%",
                    min_value=0.0,
                    max_value=100.0,
                ),
            },
            hide_index=True,
            width="stretch",
            key=f"annual_factor_editor_{loss_rate_type.value}",
        )

    with col2:
        symbol = "$" if loss_rate_type == LossRateTypes.DLR else "#"
        st.metric(
            label=f"{symbol} Portfolio Scalar",
            value=f"{scalar.portfolio_scalar:.2f}",
            border=True,
        )

    if config_vm.process_annualization_edits(loss_rate_type, edited_df):
        st.rerun()


def risk_scalar_factor_editor(loss_rate_type: LossRateTypes) -> None:
    """Render Risk Scalar Factor editor per risk segment."""
    session = get_session()
    config_vm = session.config_view_model

    styler = config_vm.get_risk_scalar_factor_styler(loss_rate_type)

    edited_df = st.data_editor(
        styler,
        column_config={
            ScalarTableColumn.RISK_SEGMENT.value: st.column_config.TextColumn(
                label=ScalarTableColumn.RISK_SEGMENT.value,
                disabled=True,
            ),
            ScalarTableColumn.MAF.value: st.column_config.NumberColumn(
                label=ScalarTableColumn.MAF.value,
                format="%.1f %%",
                min_value=0.0,
            ),
            ScalarTableColumn.RISK_SCALAR_FACTOR.value: st.column_config.NumberColumn(
                label=ScalarTableColumn.RISK_SCALAR_FACTOR.value,
                format="%.2f",
                disabled=True,
            ),
        },
        hide_index=True,
        width="stretch",
        key=f"rsf_editor_{loss_rate_type.value}",
    )

    if config_vm.process_maf_edits(loss_rate_type, edited_df):
        st.rerun()


def scalar_editor(loss_rate_type: LossRateTypes) -> None:
    """Render scalar calculation section for a specific loss rate type."""
    symbol = "$" if loss_rate_type == LossRateTypes.DLR else "#"
    st.subheader(f"{symbol} Bad Rate")
    annualization_factor_editor(loss_rate_type)
    risk_scalar_factor_editor(loss_rate_type)


def scalar_calculation() -> None:
    """Render Scalar Calculation dashboard section."""
    st.subheader("Scalar Calculation")

    dlr_col, ulr_col = st.columns(2)

    with dlr_col:
        scalar_editor(LossRateTypes.ULR)

    with ulr_col:
        scalar_editor(LossRateTypes.DLR)

    st.info(
        ":blue-badge[`Risk Scalar Factor`] is calculated as "
        ":blue-badge[`max(portfolio_scalar * maturity_adjustment_factor, 1)`], "
        "as the loss rate at :blue-badge[`n + 1`] th MOB will be more than or equal to "
        "the loss rate of :blue-badge[`n`] th MOB.",
        icon=":material/info:",
    )


def render_config_page() -> None:
    """Main entry point for rendering the Configuration UI page."""
    st.title("Configuration")

    risk_seg_details_selector()
    st.divider()
    scalar_calculation()


config_page = st.Page(
    page=render_config_page,
    title="Configuration",
    icon=":material/settings:",
    url_path="/config",
)


__all__ = ["config_page", "render_config_page"]
