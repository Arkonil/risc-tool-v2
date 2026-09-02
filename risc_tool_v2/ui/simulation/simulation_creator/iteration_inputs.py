"""Iteration Inputs high-level section for the Simulation Creator."""

import streamlit as st

from risc_tool_v2.data.core.uid import FilterID
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.simulation import widgets
from risc_tool_v2.ui.simulation.simulation_creator.base import reconcile, vm


def iteration_inputs_section(draft: SimulationConfigGenerator) -> None:
    """Name, filters, and boolean toggles."""
    sim_vm = vm()

    col1, col2 = st.columns([2, 1])

    with col1:
        name = widgets.name_input(draft.name)
        reconcile(draft.name, name, lambda: sim_vm.update_draft_name(name))

        filter_ids: tuple[FilterID, ...] = widgets.filter_selector(draft.filter_ids)
        reconcile(
            draft.filter_ids,
            filter_ids,
            lambda: sim_vm.update_draft_filter_ids(filter_ids),
        )

    with col2:
        # c1, c2, c3 = st.columns(3)
        # with c1:
        auto_band = widgets.toggle_checkbox(
            "Automatic Banding", draft.auto_band, "sim_auto_band"
        )

        if draft.auto_band:
            # with c2:
            use_scalars = widgets.toggle_checkbox(
                "Use Scalars", draft.use_scalars, "sim_use_scalars"
            )
            # with c3:
            remove_outliers = widgets.toggle_checkbox(
                "Remove Outliers",
                draft.remove_outliers,
                "sim_remove_outliers",
            )
        else:
            use_scalars = draft.use_scalars
            remove_outliers = draft.remove_outliers

    reconcile(
        draft.auto_band,
        auto_band,
        lambda: sim_vm.update_draft_auto_band(auto_band),
    )
    reconcile(
        draft.use_scalars,
        use_scalars,
        lambda: sim_vm.update_draft_use_scalars(use_scalars),
    )
    reconcile(
        draft.remove_outliers,
        remove_outliers,
        lambda: sim_vm.update_draft_remove_outliers(remove_outliers),
    )


__all__ = ["iteration_inputs_section"]
