"""Simulation creator component.

Renders a single-column, top-to-bottom creation flow (Risk Segment Details,
Scalars, Bad Rate Config, IV reference, and remaining iteration inputs). All
state flows through the SimulationViewModel: the UI reads the draft and calls
VM methods to persist temporary changes; only the VM talks to repositories.
"""

import streamlit as st

from risc_tool_v2.data.core.enums import LossRateTypes, VariableType
from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.session import Session
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.data_source.data_explorer.iv_analysis import iv_analysis
from risc_tool_v2.ui.simulation.risk_segment_editor import risk_segment_editor
from risc_tool_v2.ui.simulation.scalar_editor import scalar_editor
from risc_tool_v2.ui.simulation.variable_bad_rate_selector import (
    bad_rate_config_selector,
)


def _sidebar_widgets() -> None:
    session: Session = st.session_state["session"]
    simulation_vm = session.simulation_view_model

    if st.button(
        label="Cancel",
        width="stretch",
        type="secondary",
        icon=":material/arrow_back:",
    ):
        simulation_vm.clear_draft()
        simulation_vm.set_mode("graph")
        st.rerun()


def _name_input(current: str) -> str:
    st.markdown("##### Simulation Name")
    return st.text_input(
        label="Simulation Name",
        value=current,
        label_visibility="collapsed",
        key="sim_name",
        placeholder="Simulation Name",
    )


def _variable_type_selector(current: VariableType) -> VariableType:
    st.markdown("##### Variable Type")
    options = [VariableType.NUMERICAL, VariableType.CATEGORICAL]
    return st.selectbox(
        label="Variable Type",
        options=options,
        index=options.index(current),
        label_visibility="collapsed",
        key="sim_variable_type",
    )


def _loss_rate_type_selector(current: LossRateTypes) -> LossRateTypes:
    st.markdown("##### Loss Rate Type")
    return st.selectbox(
        label="Loss Rate Type",
        options=list(LossRateTypes),
        index=list(LossRateTypes).index(current),
        label_visibility="collapsed",
        key="sim_loss_rate_type",
    )


def _variable_selector(current: str) -> str:
    session: Session = st.session_state["session"]
    columns = session.simulation_view_model.common_columns
    st.markdown("##### Variable")
    return st.selectbox(
        label="Variable",
        options=columns,
        index=columns.index(current) if current in columns else 0,
        label_visibility="collapsed",
        key="sim_variable",
        placeholder="Select variable to band",
    )


def _filter_selector(current: tuple[FilterID, ...]) -> tuple[FilterID, ...]:
    session: Session = st.session_state["session"]
    filters = session.simulation_view_model.filters

    st.markdown("##### Select Filters")
    selected = st.multiselect(
        label="Select Filters",
        options=sorted(filters.keys()),
        default=list(current),
        label_visibility="collapsed",
        format_func=lambda fid: filters[fid].name,
        key="sim_filters",
        placeholder="Select Filters",
    )
    return tuple(selected)


def _other_inputs(draft: SimulationConfigGenerator) -> None:
    """Render the remaining iteration inputs in a grouped form-like container."""
    with st.container(border=True):
        st.markdown("#### Iteration Inputs")

        name = _name_input(draft.name)
        variable = _variable_selector(draft.variable_name)
        variable_type = _variable_type_selector(draft.variable_type)
        loss_rate_type = _loss_rate_type_selector(draft.bad_rate_type)
        filter_ids = _filter_selector(draft.filter_ids)

        c1, c2, c3 = st.columns(3)
        with c1:
            auto_band = st.checkbox(
                "Automatic Banding", value=draft.auto_band, key="sim_auto_band"
            )
        with c2:
            use_scalars = st.checkbox(
                "Use Scalars", value=draft.use_scalars, key="sim_use_scalars"
            )
        with c3:
            remove_outliers = st.checkbox(
                "Remove Outliers",
                value=draft.remove_outliers,
                key="sim_remove_outliers",
            )

        session: Session = st.session_state["session"]
        simulation_vm = session.simulation_view_model
        simulation_vm.update_draft_settings(
            name=name,
            variable_name=variable,
            variable_type=variable_type,
            bad_rate_type=loss_rate_type,
            filter_ids=filter_ids,
            auto_band=auto_band,
            use_scalars=use_scalars,
            remove_outliers=remove_outliers,
        )


def _validate(scg: SimulationConfigGenerator) -> list[str]:
    errors: list[str] = []
    if not scg.name.strip():
        errors.append("Simulation name cannot be empty.")
    if not scg.variable_name.strip():
        errors.append("Please select a variable.")
    selected_br = _get_selected_bad_rate(scg, scg.bad_rate_type)
    if selected_br is None or not selected_br.numerator_col:
        errors.append("Please configure the bad rate numerator column.")
    if scg.bad_rate_type == LossRateTypes.DLR and (
        selected_br is None or not selected_br.denominator_col
    ):
        errors.append("Please configure the bad rate denominator column.")
    if not scg.risk_segment_config.segments:
        errors.append("At least one risk segment is required.")
    return errors


def _get_selected_bad_rate(
    scg: SimulationConfigGenerator, loss_rate_type: LossRateTypes
):
    if loss_rate_type == LossRateTypes.ULR:
        return scg.dev_unit_bad_rate
    return scg.dev_dollar_bad_rate


def simulation_creator() -> None:
    """Render the simulation creation flow; persist draft via the VM."""
    session: Session = st.session_state["session"]
    simulation_vm = session.simulation_view_model

    with st.sidebar:
        _sidebar_widgets()

    st.title("Create New Simulation")

    draft = simulation_vm.draft_scg

    # 1. Risk Segment Details (full width)
    risk_segment_config = risk_segment_editor(draft.risk_segment_config)
    simulation_vm.update_draft_risk_segments(risk_segment_config)
    st.divider()
    draft = simulation_vm.draft_scg

    # 2. Scalars (+ per-segment MAF)
    scalar_config, risk_segment_config = scalar_editor(
        draft.scalar_config, draft.risk_segment_config
    )
    simulation_vm.update_draft_scalars(scalar_config, risk_segment_config)
    st.divider()
    draft = simulation_vm.draft_scg

    # 3. Bad Rate Config (Target + Early)
    selection = bad_rate_config_selector(
        dev_unit_bad_rate=draft.dev_unit_bad_rate,
        dev_dollar_bad_rate=draft.dev_dollar_bad_rate,
        test_unit_bad_rate=draft.test_unit_bad_rate,
        test_dollar_bad_rate=draft.test_dollar_bad_rate,
    )
    simulation_vm.update_draft_bad_rates(
        dev_unit_bad_rate=selection.dev_unit_bad_rate,
        dev_dollar_bad_rate=selection.dev_dollar_bad_rate,
        test_unit_bad_rate=selection.test_unit_bad_rate,
        test_dollar_bad_rate=selection.test_dollar_bad_rate,
    )
    st.divider()
    draft = simulation_vm.draft_scg

    # 4. IV calculation (reference only; does not feed the SCG)
    st.markdown("### Information Value (Reference)")
    iv_analysis()
    st.divider()

    # 5. Other iteration inputs
    _other_inputs(draft)
    draft = simulation_vm.draft_scg

    errors = _validate(draft)
    if errors:
        for err in errors:
            st.error(err, icon=":material/error:")

    col1, _ = st.columns(2)
    with col1:
        if st.button(
            label="Create Simulation",
            type="primary",
            icon=":material/add:",
            width="stretch",
            disabled=bool(errors),
        ):
            simulation_vm.confirm_draft()
            st.rerun()


__all__ = ["simulation_creator"]
