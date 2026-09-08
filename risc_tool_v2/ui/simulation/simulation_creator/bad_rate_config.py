"""Bad Rate Config high-level section for the Simulation Creator."""

import streamlit as st

from risc_tool_v2.data.core.enums import LossRateTypes
from risc_tool_v2.data.simulation.models.simulation_config import (
    SimulationConfigGenerator,
)
from risc_tool_v2.ui.simulation import widgets
from risc_tool_v2.ui.simulation.simulation_creator.base import reconcile, vm


def bad_rate_config_section(draft: SimulationConfigGenerator) -> None:
    """Target (dev) and Early (test) bad rate configuration."""
    sim_vm = vm()
    with st.container(border=False):
        st.subheader("Bad Rate Config")

        col1, col2 = st.columns([1, 1])

        # --- Target Bad Rates (dev) ---
        with col1.container(border=True):
            st.markdown("#### Target Bad Rates", text_alignment="center")

            dev_unit = draft.dev_unit_bad_rate
            dev_dollar = draft.dev_dollar_bad_rate
            dev_ids = dev_unit.data_source_ids if dev_unit is not None else ()

            selected_ids = widgets.data_source_selector("sim_dev_data_sources", dev_ids)
            reconcile(
                dev_ids,
                selected_ids,
                lambda: sim_vm.update_draft_bad_rate_data_sources("dev", selected_ids),
            )

            dev_unt_num = dev_unit.numerator_col if dev_unit is not None else None
            unt_bad = widgets.unit_bad_rate_row(
                "# Bad Rate", "sim_dev_unt", dev_unt_num, selected_ids
            )
            reconcile(
                dev_unt_num,
                unt_bad,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="dev",
                    loss_rate_type=LossRateTypes.ULR,
                    field="numerator_col",
                    value=unt_bad,
                ),
            )

            dev_dlr_num = dev_dollar.numerator_col if dev_dollar is not None else None
            dev_dlr_den = dev_dollar.denominator_col if dev_dollar is not None else None
            dlr_bad, avg_bal = widgets.dollar_bad_rate_row(
                "$ Bad Rate", "sim_dev_dlr", dev_dlr_num, dev_dlr_den, selected_ids
            )
            reconcile(
                dev_dlr_num,
                dlr_bad,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="dev",
                    loss_rate_type=LossRateTypes.DLR,
                    field="numerator_col",
                    value=dlr_bad,
                ),
            )
            reconcile(
                dev_dlr_den,
                avg_bal,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="dev",
                    loss_rate_type=LossRateTypes.DLR,
                    field="denominator_col",
                    value=avg_bal,
                ),
            )

        # --- Early Bad Rates (test) ---
        with col2.container(border=True):
            st.markdown("#### Early Bad Rates", text_alignment="center")

            test_unit = draft.test_unit_bad_rate
            test_dollar = draft.test_dollar_bad_rate
            test_ids = test_unit.data_source_ids if test_unit is not None else ()

            test_selected_ids = widgets.data_source_selector(
                "sim_test_data_sources", test_ids
            )
            reconcile(
                test_ids,
                test_selected_ids,
                lambda: sim_vm.update_draft_bad_rate_data_sources(
                    "test", test_selected_ids
                ),
            )

            test_unt_num = test_unit.numerator_col if test_unit is not None else None
            test_unt_bad = widgets.unit_bad_rate_row(
                "# Bad Rate", "sim_test_unt", test_unt_num, test_selected_ids
            )
            reconcile(
                test_unt_num,
                test_unt_bad,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="test",
                    loss_rate_type=LossRateTypes.ULR,
                    field="numerator_col",
                    value=test_unt_bad,
                ),
            )

            test_dlr_num = (
                test_dollar.numerator_col if test_dollar is not None else None
            )
            test_dlr_den = (
                test_dollar.denominator_col if test_dollar is not None else None
            )
            test_dlr_bad, test_avg_bal = widgets.dollar_bad_rate_row(
                "$ Bad Rate",
                "sim_test_dlr",
                test_dlr_num,
                test_dlr_den,
                test_selected_ids,
            )
            reconcile(
                test_dlr_num,
                test_dlr_bad,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="test",
                    loss_rate_type=LossRateTypes.DLR,
                    field="numerator_col",
                    value=test_dlr_bad,
                ),
            )
            reconcile(
                test_dlr_den,
                test_avg_bal,
                lambda: sim_vm.update_draft_bad_rate_column(
                    which="test",
                    loss_rate_type=LossRateTypes.DLR,
                    field="denominator_col",
                    value=test_avg_bal,
                ),
            )

        with col1:
            dev_mob = dev_unit.current_rate_mob if dev_unit is not None else 12
            mob = widgets.mob_selector("sim_dev_mob", dev_mob)
            reconcile(dev_mob, mob, lambda: sim_vm.update_draft_mob(mob))

        with col2:
            lifetime_mob = draft.lifetime_rate_mob
            life_mob = widgets.mob_selector(
                "sim_dev_lifetime_mob", lifetime_mob, label="Lifetime MOB"
            )
            reconcile(
                lifetime_mob,
                life_mob,
                lambda: sim_vm.update_draft_lifetime_mob(life_mob),
            )

        st.info(
            """
            Final annualized bad rates are calculated as:
            ```'Bad Rate %' * (12 / MOB)```
            """,
            icon=":material/info:",
        )


__all__ = ["bad_rate_config_section"]
