"""UI dialog/form for creating new single or double variable iterations."""

import typing as t

import streamlit as st

from risc_tool.data.models.enums import (
    IterationType,
    LossRateTypes,
    RSDetCol,
    VariableType,
)
from risc_tool.data.models.iteration_metadata import IterationMetadata
from risc_tool.data.models.object_id import FilterID, IterationID, RiskSegmentID
from risc_tool.data.session import Session
from risc_tool.ui.components.error_warnings import error_and_warning_widget
from risc_tool.ui.components.variable_selector import variable_selector_dialog
from risc_tool.ui.iterations.navigation import navigation_widgets


def sidebar_widgets() -> None:
    """Render sidebar widgets with a button to open the variable selector dialog."""
    st.button(
        label="Set Variables",
        width="stretch",
        icon=":material/data_table:",
        help="Select variables for calculations",
        type="primary",
        on_click=variable_selector_dialog,
    )


def variable_selector() -> str:
    """Render a dropdown to select the variable to iterate on.

    Returns:
        The selected variable name.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    label = "##### Select Variable"

    st.markdown(label)
    variable_name = st.selectbox(
        label=label,
        options=iterations_vm.common_columns,
        label_visibility="collapsed",
    )

    return variable_name


def iteration_name_input() -> str:
    """Render a text input for the iteration name.

    Returns:
        The entered iteration name.
    """
    label = "##### Iteration Name"

    st.markdown(label)
    iteration_name = st.text_input(label="Iteration Name", label_visibility="collapsed")

    return iteration_name


def variable_type_selector() -> VariableType:
    """Render a dropdown to select the variable type.

    Returns:
        The selected VariableType.
    """
    label = "##### Variable Type"

    st.markdown(label)
    variable_dtype = st.selectbox(
        label="Variable Type",
        options=[VariableType.NUMERICAL, VariableType.CATEGORICAL],
        index=0,
        label_visibility="collapsed",
    )

    return variable_dtype


def loss_rate_type_selector() -> LossRateTypes:
    """Render a dropdown to select the loss rate type.

    Returns:
        The selected LossRateTypes.
    """
    label = "##### Loss Rate Type"

    st.markdown(label)
    loss_rate_type = st.selectbox(
        label=label,
        options=LossRateTypes,
        index=0,
        label_visibility="collapsed",
    )

    return LossRateTypes(loss_rate_type)


def upgrade_downgrade_selector() -> tuple[bool, int, int]:
    """Render inputs for auto rank ordering and upgrade/downgrade limits.

    Returns:
        A tuple of (auto_rank_ordering, upgrade_limit, downgrade_limit).
    """
    auto_rank_ordering = st.checkbox("Auto Rank Ordering", value=True)
    upgrade_cont_t, downgrade_cont_t = st.columns(2)
    upgrade_cont_i, downgrade_cont_i = st.columns(2)

    upgrade_cont_t.markdown(
        "##### Upgrade Limit",
        help="Upgrade Current RT to a one with lower risk. Example RT2 -> RT1.",
    )
    upgrade_limit = upgrade_cont_i.number_input(
        label="Upgrade Limit",
        min_value=0,
        step=1,
        format="%d",
        label_visibility="collapsed",
        key="upgrade_limit",
        value=0,
    )

    downgrade_cont_t.markdown(
        "##### Downgrade Limit",
        help="Downgrade Current RT to a one with lower risk. Example RT2 -> RT4.",
    )
    downgrade_limit = downgrade_cont_i.number_input(
        label="Downgrade Limit",
        min_value=0,
        step=1,
        format="%d",
        label_visibility="collapsed",
        key="downgrade_limit",
        value=1,
    )

    return auto_rank_ordering, upgrade_limit, downgrade_limit


def filter_selector():
    """Render a multiselect widget for choosing filters.

    Returns:
        The selected filter IDs.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    label = "##### Select Filters"

    st.markdown(label)

    if iterations_vm.current_iteration_create_parent_id:
        default_value = iterations_vm.get_iteration_metadata(
            iterations_vm.current_iteration_create_parent_id
        ).initial_filter_ids
    else:
        default_value = None

    filters = iterations_vm.get_filters()
    disabled = iterations_vm.current_iteration_create_mode == IterationType.DOUBLE

    filter_ids = st.multiselect(
        label=label,
        options=sorted(filters.keys()),
        label_visibility="collapsed",
        format_func=lambda filter_id: filters[filter_id].name,
        disabled=disabled,
        default=default_value,
    )

    return filter_ids


def risk_segment_details_selector() -> list[RiskSegmentID]:
    """Render an editable table of risk segment details for selection.

    Returns:
        The list of selected RiskSegmentIDs.
    """
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model
    is_single = iterations_vm.current_iteration_create_mode == IterationType.SINGLE

    if is_single:
        previous_node_id = None
        rs_details = iterations_vm.global_risk_segment_details()
    else:
        previous_node_id = t.cast(
            IterationID, iterations_vm.current_iteration_create_parent_id
        )
        rs_details = iterations_vm.get_risk_segment_details(previous_node_id)

    column_config = {
        RSDetCol.SELECTED.value: st.column_config.CheckboxColumn(
            label=RSDetCol.SELECTED,
            disabled=not is_single,
        ),
        RSDetCol.RISK_SEGMENT.value: st.column_config.TextColumn(
            label=RSDetCol.RISK_SEGMENT,
            disabled=True,
        ),
        RSDetCol.LOWER_RATE.value: st.column_config.TextColumn(
            label=RSDetCol.LOWER_RATE,
            disabled=True,
            alignment="right",
        ),
        RSDetCol.UPPER_RATE.value: st.column_config.TextColumn(
            label=RSDetCol.UPPER_RATE,
            disabled=True,
            alignment="right",
        ),
    }

    if iterations_vm.current_iteration_create_mode == IterationType.SINGLE:
        st.markdown("##### Select Risk Segments")
    else:
        st.markdown("##### Selected Risk Segments *(from Root Node)*")

    edited_rs_details = st.data_editor(
        data=rs_details,
        column_order=[
            RSDetCol.SELECTED,
            RSDetCol.RISK_SEGMENT,
            RSDetCol.LOWER_RATE,
            RSDetCol.UPPER_RATE,
        ],
        column_config=column_config,
        width="stretch",
        hide_index=True,
    )

    selected_risk_segments = edited_rs_details[RSDetCol.SELECTED]
    return selected_risk_segments.loc[selected_risk_segments].index.tolist()


def iteration_creator() -> None:
    """Render the iteration creation form page."""
    session: Session = st.session_state["session"]
    iterations_vm = session.iterations_view_model

    with st.sidebar:
        sidebar_widgets()

    navigation_widgets()

    st.title("Create New Iteration")

    col1, col2 = st.columns([3, 4])

    with col1:
        variable_name = variable_selector()
        iteration_name = iteration_name_input()
        variable_dtype = variable_type_selector()

        col11, col12 = st.columns(2)

        auto_band = col11.checkbox("Automatic Banding", value=True)
        auto_rank_ordering, upgrade_limit, downgrade_limit = True, 1, 1

        if auto_band:
            use_scalars = col12.checkbox("Use Scalars", value=True)

            if iterations_vm.current_iteration_create_mode == IterationType.SINGLE:
                loss_rate_type = loss_rate_type_selector()
            else:
                loss_rate_type = iterations_vm.get_iteration_metadata(
                    t.cast(
                        IterationID, iterations_vm.current_iteration_create_parent_id
                    )
                ).loss_rate_type
                auto_rank_ordering, upgrade_limit, downgrade_limit = (
                    upgrade_downgrade_selector()
                )

        else:
            use_scalars = False
            loss_rate_type = IterationMetadata().loss_rate_type

        filter_ids: list[FilterID] = filter_selector()

        remove_outliers = st.checkbox("Remove Outliers", value=True)

    # Right Column Controls
    with col2:
        selected_segment_ids = risk_segment_details_selector()

    is_single = iterations_vm.current_iteration_create_mode == IterationType.SINGLE

    errors = iterations_vm.validate_iter_create_params(
        variable_name,
        variable_dtype,
        auto_band,
        loss_rate_type,
        use_scalars,
        selected_segment_ids=selected_segment_ids if is_single else None,
    )

    if errors:
        error_and_warning_widget(errors=errors, warnings=[])

    if iterations_vm.current_iteration_create_mode == IterationType.SINGLE:
        button_label = "Create Root Iteration"
    else:
        button_label = "Create Child Iteration"

    if st.button(
        label=button_label,
        type="primary",
        disabled=bool(errors),
        icon=":material/add:",
    ):
        variable_schema = iterations_vm.get_variable_schema(variable_name)
        if variable_schema is not None and not variable_schema.is_numeric():
            variable_dtype = VariableType.CATEGORICAL

        if iterations_vm.current_iteration_create_mode == IterationType.SINGLE:
            iteration = iterations_vm.add_single_var_iteration(
                name=iteration_name,
                variable_name=variable_name,
                variable_dtype=variable_dtype,
                selected_segment_ids=selected_segment_ids,
                loss_rate_type=loss_rate_type,
                filter_ids=filter_ids,
                auto_band=auto_band,
                use_scalar=use_scalars,
                remove_outliers=remove_outliers,
            )

            iterations_vm.set_current_status("view", iteration.uid)
            st.rerun()

        else:
            previous_node_id = t.cast(
                IterationID, iterations_vm.current_iteration_create_parent_id
            )

            iteration = iterations_vm.add_double_var_iteration(
                name=iteration_name,
                previous_iteration_id=previous_node_id,
                variable_name=variable_name,
                variable_dtype=variable_dtype,
                auto_band=auto_band,
                use_scalar=use_scalars,
                remove_outliers=remove_outliers,
                upgrade_limit=upgrade_limit if auto_band else None,
                downgrade_limit=downgrade_limit if auto_band else None,
                auto_rank_ordering=auto_rank_ordering if auto_band else None,
            )

            iterations_vm.set_current_status("view", iteration.uid)
            st.rerun()


__all__ = ["iteration_creator"]
