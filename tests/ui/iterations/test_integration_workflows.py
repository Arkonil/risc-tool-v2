"""Integration workflow tests for the iterations feature.

These tests exercise complete user journeys at the ViewModel/repository
level (per TEST_PLAN.md) and are marked with the ``integration`` marker so
they can be run separately from the unit test suite:

    pytest -m integration tests/ui/iterations

Missing features described in TEST_PLAN.md are marked ``xfail`` with a
reason documenting the gap.
"""

import pytest

from risc_tool.data.models.enums import (
    ComparisonOperation,
    LossRateTypes,
    PercentileOptions,
    RangeColumn,
    VariableType,
)
from risc_tool.data.models.types import MetricID, RiskSegmentID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel

pytestmark = pytest.mark.integration

DEV_METRIC_IDS = [
    MetricID.DEV_VOLUME,
    MetricID.DEV_DLR_BAD_RATE,
    MetricID.DEV_UNT_BAD_RATE,
]

DEFAULT_SEGMENT_IDS = (
    RiskSegmentID(0),
    RiskSegmentID(1),
    RiskSegmentID(2),
)


def _single_var(
    iterations_vm,
    name: str,
    variable_name: str,
    variable_dtype=VariableType.NUMERICAL,
    selected_segment_ids=DEFAULT_SEGMENT_IDS,
    loss_rate_type=LossRateTypes.DLR,
    filter_ids=None,
    auto_band=False,
    use_scalar=False,
    remove_outliers=True,
    hv_imp_hr=None,
):
    """Create a single-variable iteration through the ViewModel."""
    return iterations_vm.add_single_var_iteration(
        name=name,
        variable_name=variable_name,
        variable_dtype=variable_dtype,
        selected_segment_ids=list(selected_segment_ids),
        loss_rate_type=loss_rate_type,
        filter_ids=filter_ids or [],
        auto_band=auto_band,
        use_scalar=use_scalar,
        remove_outliers=remove_outliers,
        hv_imp_hr=hv_imp_hr,
    )


def _double_var(
    iterations_vm,
    name: str,
    parent_uid,
    variable_name: str,
    variable_dtype=VariableType.NUMERICAL,
    auto_band=False,
    use_scalar=False,
    remove_outliers=True,
    upgrade_limit=1,
    downgrade_limit=1,
    auto_rank_ordering=True,
):
    """Create a double-variable iteration through the ViewModel."""
    return iterations_vm.add_double_var_iteration(
        name=name,
        previous_iteration_id=parent_uid,
        variable_name=variable_name,
        variable_dtype=variable_dtype,
        auto_band=auto_band,
        use_scalar=use_scalar,
        remove_outliers=remove_outliers,
        upgrade_limit=upgrade_limit,
        downgrade_limit=downgrade_limit,
        auto_rank_ordering=auto_rank_ordering,
    )


def _metric_table(
    iterations_vm,
    iteration_id,
    *,
    default=False,
    filter_ids=None,
    metric_ids=None,
    scalars_enabled=False,
    remove_outliers=True,
    show_total_row=True,
):
    """Build the metric table (Styler) through the ViewModel."""
    return iterations_vm.get_iteration_metric_table(
        iteration_id=iteration_id,
        default=default,
        show_controls=True,
        filter_ids=filter_ids or [],
        metric_ids=metric_ids or DEV_METRIC_IDS,
        scalars_enabled=scalars_enabled,
        remove_outliers=remove_outliers,
        show_total_row=show_total_row,
    )


# ---------------------------------------------------------------------------
# 1. Complete Single Variable Iteration Workflow
# ---------------------------------------------------------------------------


class TestFullSingleVarWorkflow:
    """Full journey for a numerical single-variable iteration."""

    def test_full_single_var_workflow(self, iterations_vm, filter_repository):
        iteration = _single_var(
            iterations_vm,
            name="Credit Score Bands",
            variable_name="credit_score",
            auto_band=True,
            remove_outliers=True,
        )

        # Step 4-5: navigate to View page
        iterations_vm.set_current_status("view", current_iteration_id=iteration.uid)
        view, view_uid = iterations_vm.current_status
        assert view == "view"
        assert view_uid == iteration.uid

        # Step 6: default range table renders with auto-banded groups
        default_styler, errors, _warnings = _metric_table(
            iterations_vm, iteration.uid, default=True
        )
        assert errors == []
        assert default_styler is not None
        assert len(default_styler.data) >= 1
        assert RangeColumn.RISK_SEGMENT.value in default_styler.data.columns

        # Step 7: editable range table renders
        editable_styler, errors, _ = _metric_table(
            iterations_vm, iteration.uid, default=False
        )
        assert errors == []
        assert RangeColumn.LOWER_BOUND.value in editable_styler.data.columns
        assert RangeColumn.UPPER_BOUND.value in editable_styler.data.columns

        # Step 8: edit a group boundary in the editable range table
        cached = iterations_vm._IterationsViewModel__editable_range_cache.get((
            iteration.uid,
            False,
        ))
        assert cached is not None
        edited = cached.copy()
        first_group = edited.index[0]
        edited.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0
        assert (
            iterations_vm.editable_range_edit_handler(iteration.uid, False, edited)
            is True
        )

        # Step 9: metric table updates after the edit
        _updated_styler, errors, _ = _metric_table(
            iterations_vm, iteration.uid, default=False
        )
        assert errors == []

        # Step 10-11: change filter in sidebar, metric table updates
        filter_repository.create_filter("Gold", "credit_score > 700")
        filter_ids = list(filter_repository.get_filters().keys())
        assert len(filter_ids) == 1
        iterations_vm.set_metadata(iteration.uid, current_filter_ids=filter_ids)

        _filtered_styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            filter_ids=filter_ids,
        )
        assert errors == []

        # Step 12-13: toggle Enable Scalars, metric table updates
        iterations_vm.set_metadata(iteration.uid, scalars_enabled=True)
        _scalar_styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            filter_ids=filter_ids,
            scalars_enabled=True,
        )
        assert errors == []

        # Step 14: go back to Graph page, iteration appears in graph
        iterations_vm.set_current_status("graph", selected_iteration_id=iteration.uid)
        view, view_uid = iterations_vm.current_status
        assert view == "graph"
        assert view_uid == iteration.uid
        assert iteration.uid in iterations_vm.iterations


# ---------------------------------------------------------------------------
# 2. Complete Double Variable Iteration Workflow
# ---------------------------------------------------------------------------


class TestFullDoubleVarWorkflow:
    """Full journey for a double-variable iteration."""

    def test_full_double_var_workflow(self, iterations_vm, single_var_iteration):
        parent = single_var_iteration
        child = _double_var(
            iterations_vm,
            name="Income Bands",
            parent_uid=parent.uid,
            variable_name="income",
            auto_band=True,
            remove_outliers=True,
        )

        # Step 6: navigate to View page
        iterations_vm.set_current_status("view", current_iteration_id=child.uid)
        view, view_uid = iterations_vm.current_status
        assert view == "view"
        assert view_uid == child.uid

        # Step 7: default grid renders with risk segment mappings
        default_grid = iterations_vm.get_editable_grid(
            child.uid, default=True, editable=False
        )
        assert "styler" in default_grid
        assert default_grid["styler"].data.shape[1] >= 1

        # Step 8: editable grid renders
        editable_grid = iterations_vm.get_editable_grid(
            child.uid, default=False, editable=True
        )
        assert "styler" in editable_grid
        assert editable_grid["lower_bound_pos"] is not None
        assert editable_grid["upper_bound_pos"] is not None

        # Step 9: edit a risk segment mapping in the editable grid
        cached = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            child.uid,
            False,
        ))
        assert cached is not None
        edited = cached.copy()
        segment_columns = [
            c
            for c in edited.columns
            if c
            not in (
                RangeColumn.LOWER_BOUND.value,
                RangeColumn.UPPER_BOUND.value,
                RangeColumn.CATEGORIES.value,
            )
        ]
        if segment_columns:
            first_group = edited.index[0]
            col = segment_columns[0]
            current_value = edited.at[first_group, col]
            alternatives = [s for s in edited[col].unique() if s != current_value]
            if len(alternatives) > 0:
                edited.at[first_group, col] = alternatives[0]
                assert (
                    iterations_vm.editable_grid_edit_handler(child.uid, False, edited)
                    is True
                )

        # Step 10: metric grids update
        iterations_vm.set_metadata(child.uid, metric_ids=DEV_METRIC_IDS)
        metric_views, errors, _ = iterations_vm.get_metric_grids(
            child.uid,
            default=False,
            show_controls_idx="all",
            show_total_row=True,
            show_total_column=True,
        )
        assert errors == []
        assert len(metric_views) >= 1

        # Step 11-12: toggle Split View, layout metadata changes
        iterations_vm.set_metadata(child.uid, split_view_enabled=False)
        assert (
            iterations_vm.get_iteration_metadata(child.uid).split_view_enabled is False
        )
        iterations_vm.set_metadata(child.uid, split_view_enabled=True)
        assert (
            iterations_vm.get_iteration_metadata(child.uid).split_view_enabled is True
        )

        # Step 13-14: add a new group, verify it appears in the grid
        before_count = len(iterations_vm.get_all_groups(child.uid))
        assert iterations_vm.add_new_group(child.uid) is True
        after_groups = iterations_vm.get_all_groups(child.uid)
        assert len(after_groups) == before_count + 1
        new_group_idx = after_groups.index[-1]
        assert bool(after_groups.loc[new_group_idx, RangeColumn.SELECTED.value])

        # Step 15-16: select/deselect groups, grid filters accordingly
        all_groups = iterations_vm.get_all_groups(child.uid)
        selected_ids = all_groups.index[1:3].to_list()
        assert iterations_vm.select_groups(child.uid, selected_ids) is True
        groups = iterations_vm.get_all_groups(child.uid)
        assert not groups[RangeColumn.SELECTED.value].all()
        assert bool(groups.loc[selected_ids[0], RangeColumn.SELECTED.value])

        # Step 17-18: back to graph, parent-child relationship shown
        iterations_vm.set_current_status("graph", selected_iteration_id=child.uid)
        assert iterations_vm.iteration_graph.get_parent(child.uid) == parent.uid
        assert child.uid in iterations_vm.iteration_graph.get_descendants(parent.uid)


# ---------------------------------------------------------------------------
# 3. Categorical Variable Iteration Workflow
# ---------------------------------------------------------------------------


class TestCategoricalVariableWorkflow:
    """Categorical variables handled correctly throughout the workflow."""

    def test_categorical_variable_workflow(
        self, iterations_vm, categorical_single_var_iteration
    ):
        root = categorical_single_var_iteration

        # Step 2: categorical groups created (one per unique value or grouped)
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                root.uid, default=False
            )
        )
        assert RangeColumn.CATEGORIES.value in controls.columns
        categories_union = set()
        for value in controls[RangeColumn.CATEGORIES.value]:
            categories_union.update(value)
        assert "Employed" in categories_union

        # Step 3: edit categories in editable range table
        cached = iterations_vm._IterationsViewModel__editable_range_cache.get((
            root.uid,
            False,
        ))
        if cached is None:
            _metric_table(iterations_vm, root.uid, default=False)
            cached = iterations_vm._IterationsViewModel__editable_range_cache.get((
                root.uid,
                False,
            ))
        assert cached is not None
        edited = cached.copy()
        first_group = edited.index[0]
        edited.at[first_group, RangeColumn.CATEGORIES.value] = ["Employed"]
        assert (
            iterations_vm.editable_range_edit_handler(root.uid, False, edited) is True
        )

        # Step 4: metric table updates
        _styler, errors, _ = _metric_table(iterations_vm, root.uid, default=False)
        assert errors == []

        # Step 5: double var iteration with categorical variable
        child = _double_var(
            iterations_vm,
            name="Housing Bands",
            parent_uid=root.uid,
            variable_name="housing_status",
            variable_dtype=VariableType.CATEGORICAL,
            remove_outliers=True,
        )

        # Step 6: risk segment grid uses SelectboxColumn (Categories) for mappings
        components = iterations_vm.get_editable_grid(
            child.uid, default=False, editable=True
        )
        assert components["categories_pos"] is not None
        assert components["lower_bound_pos"] is None
        assert components["upper_bound_pos"] is None

        # Step 7: edit mappings
        cached = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            child.uid,
            False,
        ))
        assert cached is not None
        edited = cached.copy()
        segment_columns = [
            c for c in edited.columns if c != RangeColumn.CATEGORIES.value
        ]
        if segment_columns:
            first_group = edited.index[0]
            col = segment_columns[0]
            current_value = edited.at[first_group, col]
            alternatives = [s for s in edited[col].unique() if s != current_value]
            if len(alternatives) > 0:
                edited.at[first_group, col] = alternatives[0]
                assert (
                    iterations_vm.editable_grid_edit_handler(child.uid, False, edited)
                    is True
                )

        # Step 8: metric grids update
        iterations_vm.set_metadata(child.uid, metric_ids=DEV_METRIC_IDS)
        metric_views, errors, _ = iterations_vm.get_metric_grids(
            child.uid,
            default=False,
            show_controls_idx="all",
            show_total_row=True,
            show_total_column=True,
        )
        assert errors == []
        assert len(metric_views) >= 1


# ---------------------------------------------------------------------------
# 4. Iteration Management Workflow
# ---------------------------------------------------------------------------


class TestIterationManagementWorkflow:
    """CRUD operations with proper cascade behavior."""

    def test_iteration_management_workflow(self, iterations_vm, single_var_iteration):
        root = single_var_iteration
        child = _double_var(
            iterations_vm,
            name="Child",
            parent_uid=root.uid,
            variable_name="income",
        )
        grandchild = _double_var(
            iterations_vm,
            name="Grandchild",
            parent_uid=child.uid,
            variable_name="income",
        )

        # Step 2: rename a child iteration
        iterations_vm.rename_iteration(child.uid, "Renamed Child")
        assert iterations_vm.get_iteration_name(child.uid) == "Renamed Child"

        # Step 3: rename reflected in graph selection state
        view, view_uid = iterations_vm.current_status
        assert view == "graph"
        assert view_uid == child.uid

        # Step 4-5: delete a child, parent still exists
        iterations_vm.delete_iteration(grandchild.uid)
        assert grandchild.uid not in iterations_vm.iterations
        assert child.uid in iterations_vm.iterations
        assert root.uid in iterations_vm.iterations

        # Step 6-8: delete root cascades to all descendants
        iterations_vm.delete_iteration(root.uid)
        assert root.uid not in iterations_vm.iterations
        assert child.uid not in iterations_vm.iterations
        assert iterations_vm.iterations == {}


# ---------------------------------------------------------------------------
# 5. Risk Segment Details Synchronization Workflow
# ---------------------------------------------------------------------------


class TestRiskSegmentSyncWorkflow:
    """Sync mechanism for risk segment details against global config."""

    def test_risk_segment_sync_workflow(
        self,
        data_repository,
        filter_repository,
        metric_repository,
        option_repository,
        scalar_repository,
        iterations_repository,
        iterations_vm,
    ):
        from risc_tool.data.models.json_models import SessionJSON
        from risc_tool.data.session import Session

        iteration = _single_var(
            iterations_vm, name="Segments", variable_name="credit_score"
        )
        assert iterations_vm.is_rs_details_same(iteration.uid) == "equal"

        # Simulate a browser refresh: serialize and rebuild the session. The
        # rebuilt iterations hold independent copies of the global segment
        # objects, so editing global config can now drift from the iterations.
        session = Session()
        session.data_repository = data_repository
        session.filter_repository = filter_repository
        session.metric_repository = metric_repository
        session.option_repository = option_repository
        session.scalar_repository = scalar_repository
        session.iterations_repository = iterations_repository
        session.iterations_view_model = iterations_vm

        json_bytes = session.to_dict().model_dump_json().encode("utf-8")
        restored = Session()
        restored.rebuild_from_json(SessionJSON.model_validate_json(json_bytes))
        restored_uid = next(iter(restored.iterations_repository.iterations))

        # Step 2: modify global risk segment styling (colors + MAF)
        restored.option_repository.set_risk_seg_bg_color([RiskSegmentID(0)], "#123456")
        restored.option_repository.set_risk_seg_font_color(
            [RiskSegmentID(0)], "#654321"
        )
        restored.option_repository.set_risk_seg_maf(
            RiskSegmentID(0), 2.5, LossRateTypes.DLR
        )

        # Step 3-4: warning appears (details outdated but core matches)
        assert (
            restored.iterations_repository.is_rs_details_same(restored_uid)
            == "updatable"
        )

        # Step 5-6: Update button syncs iteration details to global
        restored.iterations_repository.update_rs_details(restored_uid)

        # Step 7: warning disappears
        assert (
            restored.iterations_repository.is_rs_details_same(restored_uid) == "equal"
        )
        synced = restored.iterations_repository.get_risk_segment_details(
            restored_uid
        ).segments[RiskSegmentID(0)]
        assert synced.maf_dlr == 2.5
        assert synced.bg_color == "#123456"

    def test_core_unequal_not_updatable(
        self,
        data_repository,
        filter_repository,
        metric_repository,
        option_repository,
        scalar_repository,
        iterations_repository,
        iterations_vm,
    ):
        from risc_tool.data.models.json_models import SessionJSON
        from risc_tool.data.session import Session

        _single_var(iterations_vm, name="Segments", variable_name="credit_score")
        session = Session()
        session.data_repository = data_repository
        session.filter_repository = filter_repository
        session.metric_repository = metric_repository
        session.option_repository = option_repository
        session.scalar_repository = scalar_repository
        session.iterations_repository = iterations_repository
        session.iterations_view_model = iterations_vm

        json_bytes = session.to_dict().model_dump_json().encode("utf-8")
        restored = Session()
        restored.rebuild_from_json(SessionJSON.model_validate_json(json_bytes))
        restored_uid = next(iter(restored.iterations_repository.iterations))

        # Change a core field (segment name) -> core mismatch, not updatable
        restored.option_repository.set_risk_seg_name(RiskSegmentID(0), "CustomSegment")
        assert (
            restored.iterations_repository.is_rs_details_same(restored_uid) == "unequal"
        )
        restored.iterations_repository.update_rs_details(restored_uid)
        assert (
            restored.iterations_repository.is_rs_details_same(restored_uid) == "unequal"
        )


# ---------------------------------------------------------------------------
# 6. Data Source Switching Workflow
# ---------------------------------------------------------------------------


class TestDataSourceSwitchingWorkflow:
    """Switching dev data sources recomputes metrics without data loss."""

    def test_data_source_switching_workflow(self, tmp_path):
        schema = "credit_score,income,average_balance,credit_default_flag\n"
        dev_csv = tmp_path / "dev_data.csv"
        tst_csv = tmp_path / "test_data.csv"
        dev_csv.write_text(
            schema
            + "700,50000,6497.22,1\n"
            + "600,40000,8719.34,0\n"
            + "750,60000,2500.00,1\n"
            + "650,45000,5000.00,0\n",
            encoding="utf-8",
        )
        tst_csv.write_text(
            schema
            + "800,80000,10000.00,0\n"
            + "550,30000,6000.00,1\n"
            + "720,55000,3000.00,1\n"
            + "620,48000,7000.00,0\n"
            + "690,52000,6500.00,1\n",
            encoding="utf-8",
        )

        from risc_tool.data.models.data_source import ReadConfig
        from risc_tool.ui.components.variable_selector_vm import (
            VariableSelectorViewModel,
        )

        data_repo = DataRepository()
        dev_ds = data_repo.add_data_source("Dev Data", dev_csv, ReadConfig())
        tst_ds = data_repo.add_data_source("Test Data", tst_csv, ReadConfig())

        filter_repo = FilterRepository(data_repo)
        metric_repo = MetricRepository(data_repo)
        option_repo = OptionRepository()
        scalar_repo = ScalarRepository()
        iterations_repo = IterationsRepository(
            data_repo, filter_repo, metric_repo, option_repo, scalar_repo
        )
        vm = IterationsViewModel(
            data_repository=data_repo,
            iterations_repository=iterations_repo,
            options_repository=option_repo,
            filter_repository=filter_repo,
            metric_repository=metric_repo,
            scalar_repository=scalar_repo,
        )
        vs_vm = VariableSelectorViewModel(data_repo, metric_repo)

        metric_repo.dev_data_source_ids = [dev_ds.uid]
        metric_repo.var_dev_dlr_bad = "credit_default_flag"
        metric_repo.var_dev_avg_bal = "average_balance"
        metric_repo.var_dev_unt_bad = "credit_default_flag"
        metric_repo.current_rate_mob = 12

        iteration = _single_var(vm, name="Dev Bands", variable_name="credit_score")

        # Step 2: baseline metrics on Dev data
        dev_styler, errors, _ = _metric_table(vm, iteration.uid, default=False)
        assert errors == []

        # Step 3: switch to Test data source
        vs_vm.set_data_source_ids("dev", [tst_ds.uid])
        assert vs_vm.selected_data_source_ids("dev") == [tst_ds.uid]

        tst_styler, errors, _ = _metric_table(vm, iteration.uid, default=False)
        assert errors == []
        assert not dev_styler.data.equals(tst_styler.data)

        # Step 5-6: switch back to Dev, data restores
        vs_vm.set_data_source_ids("dev", [dev_ds.uid])
        restored_styler, errors, _ = _metric_table(vm, iteration.uid, default=False)
        assert errors == []
        assert restored_styler.data.equals(dev_styler.data)


# ---------------------------------------------------------------------------
# 7. Complex Filter Workflow
# ---------------------------------------------------------------------------


class TestComplexFilterWorkflow:
    """Filter combinations and outlier removal update metrics."""

    def test_complex_filter_workflow(self, iterations_vm, filter_repository):
        iteration = _single_var(
            iterations_vm, name="Filtered", variable_name="credit_score"
        )

        # Step 1-2: create complex filter, apply to iteration
        filter_repository.create_filter("Prime", "credit_score > 700")
        filter_repository.create_filter("Affluent", "income > 40000")
        prime_id, affluent_id = list(filter_repository.get_filters().keys())

        # Step 3: verify metrics update
        iterations_vm.set_metadata(iteration.uid, current_filter_ids=[prime_id])
        _prime_styler, errors, _ = _metric_table(
            iterations_vm, iteration.uid, default=False, filter_ids=[prime_id]
        )
        assert errors == []

        # Step 4-5: add outlier removal, verify metrics update
        filter_repository.create_outlier_rule(
            "income", ComparisonOperation.GT, PercentileOptions.PERC_90
        )
        _outlier_styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            filter_ids=[prime_id],
            remove_outliers=True,
        )
        assert errors == []

        # Step 6-8: apply both filters (AND logic)
        iterations_vm.set_metadata(
            iteration.uid, current_filter_ids=[prime_id, affluent_id]
        )
        _both_styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            filter_ids=[prime_id, affluent_id],
            remove_outliers=True,
        )
        assert errors == []

        # Step 9-10: remove one filter, verify metrics update
        iterations_vm.set_metadata(iteration.uid, current_filter_ids=[affluent_id])
        _single_styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            filter_ids=[affluent_id],
            remove_outliers=True,
        )
        assert errors == []


# ---------------------------------------------------------------------------
# 8. Metric Selection Workflow
# ---------------------------------------------------------------------------


class TestMetricSelectionWorkflow:
    """Metric selection persists per iteration."""

    def test_metric_selection_workflow(self, iterations_vm, single_var_iteration):
        iteration = single_var_iteration

        # Step 2: select a single metric
        iterations_vm.set_metadata(iteration.uid, metric_ids=[MetricID.DEV_VOLUME])
        styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            metric_ids=[MetricID.DEV_VOLUME],
        )
        assert errors == []
        columns = styler.data.columns.get_level_values(-1).tolist()
        assert any("Volume" in col for col in columns)

        # Step 3: add bad rate metrics
        iterations_vm.set_metadata(iteration.uid, metric_ids=DEV_METRIC_IDS)
        styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            metric_ids=DEV_METRIC_IDS,
        )
        assert errors == []
        columns = styler.data.columns.get_level_values(-1).tolist()
        assert "Annl. Bad Rate" in " ".join(columns)

        # Step 4-5: deselect a metric, it disappears from tables
        iterations_vm.set_metadata(iteration.uid, metric_ids=[MetricID.DEV_VOLUME])
        styler, errors, _ = _metric_table(
            iterations_vm,
            iteration.uid,
            default=False,
            metric_ids=[MetricID.DEV_VOLUME],
        )
        assert errors == []
        assert "Annl. Bad Rate" not in " ".join(
            styler.data.columns.get_level_values(-1).tolist()
        )

        # Step 6-7: metric selection persists per iteration
        child = _double_var(
            iterations_vm,
            name="Child",
            parent_uid=iteration.uid,
            variable_name="income",
        )
        iterations_vm.set_metadata(child.uid, metric_ids=[MetricID.DEV_VOLUME])
        assert iterations_vm.get_iteration_metadata(iteration.uid).metric_ids == [
            MetricID.DEV_VOLUME
        ]
        assert iterations_vm.get_iteration_metadata(child.uid).metric_ids == [
            MetricID.DEV_VOLUME
        ]


# ---------------------------------------------------------------------------
# 9. Auto-Banding Configuration Workflow
# ---------------------------------------------------------------------------


class TestAutoBandingConfigurationWorkflow:
    """Auto-banding configuration behaviour."""

    def test_auto_banding_creation(self, iterations_vm):
        iteration = _single_var(
            iterations_vm,
            name="Auto Bands",
            variable_name="credit_score",
            auto_band=True,
        )

        # Step 2: bands created based on data distribution
        iteration_obj = iterations_vm.get_iteration(iteration.uid)
        assert len(iteration_obj.default_groups) >= 1
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                iteration.uid, default=True
            )
        )
        assert len(controls) >= 1
        assert controls[RangeColumn.LOWER_BOUND.value].nunique() >= 1

    def test_auto_banding_creation_with_scalars(self, iterations_vm, scalar_repository):
        # Set scalar rates so auto-banding with scalars can run
        scalar_repository.set_current_rate(LossRateTypes.DLR, 0.05)
        scalar_repository.set_lifetime_rate(LossRateTypes.DLR, 0.15)

        iteration = _single_var(
            iterations_vm,
            name="Scaled Bands",
            variable_name="credit_score",
            auto_band=True,
            use_scalar=True,
        )
        assert len(iterations_vm.get_iteration(iteration.uid).default_groups) >= 1

    @pytest.mark.xfail(
        reason=(
            "Runtime re-banding after loss-rate-type change is not implemented "
            "(TEST_PLAN.md workflow 9)."
        ),
        strict=True,
    )
    def test_runtime_loss_rate_type_change_rebands(self, iterations_vm):
        """Changing DLR -> ULR at runtime should recalculate bands."""
        iteration = _single_var(
            iterations_vm, name="Auto Bands", variable_name="credit_score"
        )
        assert iterations_vm.get_iteration(iteration.uid) is not None
        raise AssertionError(
            "No ViewModel API exists to change loss rate type and re-band at runtime."
        )

    @pytest.mark.xfail(
        reason=(
            "Runtime toggle of 'high value implies high risk' band ordering is not "
            "implemented (TEST_PLAN.md workflow 9)."
        ),
        strict=True,
    )
    def test_runtime_hv_imp_hr_toggle(self, iterations_vm):
        iteration = _single_var(
            iterations_vm, name="Auto Bands", variable_name="credit_score"
        )
        assert iterations_vm.get_iteration(iteration.uid) is not None
        raise AssertionError(
            "No ViewModel API exists to toggle high-value-implies-high-risk at runtime."
        )

    @pytest.mark.xfail(
        reason=(
            "Re-enabling auto-banding after manual edits is not implemented "
            "(TEST_PLAN.md workflow 9)."
        ),
        strict=True,
    )
    def test_re_enable_auto_banding_after_manual_edit(self, iterations_vm):
        iteration = _single_var(
            iterations_vm, name="Auto Bands", variable_name="credit_score"
        )
        assert iterations_vm.get_iteration(iteration.uid) is not None
        raise AssertionError(
            "No ViewModel API exists to re-run auto-banding on an existing iteration."
        )


# ---------------------------------------------------------------------------
# 10. Error Handling and Recovery Workflow
# ---------------------------------------------------------------------------


class TestErrorHandlingRecoveryWorkflow:
    """Validation errors display and clear when fixed."""

    def test_invalid_variable_name_error_and_recovery(self, iterations_vm):
        # Step 1: invalid variable name -> error, create disabled
        errors = iterations_vm.validate_iter_create_params(
            variable_name="nonexistent_column",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert any("does not exist" in e for e in errors)

        # Step 3-4: fix variable name -> error clears, create enabled
        fixed_errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert fixed_errors == []

    def test_categorical_unique_limit_error_and_recovery(self, iterations_vm):
        # Step 1: categorical variable exceeding max unique -> error
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.CATEGORICAL,
            auto_band=False,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert any("unique" in e.lower() for e in errors)

        # Step 2: switch to numerical type -> error clears
        fixed_errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert fixed_errors == []

    def test_auto_banding_requires_metric_variables(self, iterations_vm):
        # Step 1: auto-banding without metric variables -> error
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = None
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = None
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert any("metric variables for DLR" in e for e in errors)

        # Step 2: select metric variables -> error clears
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = (
            "credit_default_flag"
        )
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = (
            "average_balance"
        )
        fixed_errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert fixed_errors == []

    def test_auto_banding_requires_scalars(self, iterations_vm):
        # Step 1: auto-banding with scalars but none set -> error
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert any("Scalars" in e for e in errors)

        # Step 2: set scalars -> error clears
        iterations_vm._IterationsViewModel__scalar_repository.set_current_rate(
            LossRateTypes.DLR, 0.05
        )
        iterations_vm._IterationsViewModel__scalar_repository.set_lifetime_rate(
            LossRateTypes.DLR, 0.15
        )
        fixed_errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert fixed_errors == []


# ---------------------------------------------------------------------------
# 11. Session Persistence Workflow
# ---------------------------------------------------------------------------


class TestSessionPersistenceWorkflow:
    """Session state persists across serialization and refresh."""

    def test_session_persistence_workflow(
        self,
        data_repository,
        filter_repository,
        metric_repository,
        option_repository,
        scalar_repository,
        iterations_repository,
        iterations_vm,
        single_var_iteration,
    ):
        from risc_tool.data.session import Session

        # Build a Session wired to the loaded repositories so serialization
        # captures real data sources, filters, and iterations.
        session = Session()
        session.data_repository = data_repository
        session.filter_repository = filter_repository
        session.metric_repository = metric_repository
        session.scalar_repository = scalar_repository
        session.option_repository = option_repository
        session.iterations_repository = iterations_repository
        session.iterations_view_model = iterations_vm

        child = _double_var(
            iterations_vm,
            name="Persistent Child",
            parent_uid=single_var_iteration.uid,
            variable_name="income",
        )

        # Edit ranges, filters, metrics
        iterations_vm.set_metadata(
            single_var_iteration.uid,
            metric_ids=[MetricID.DEV_VOLUME],
            remove_outliers=True,
        )
        filter_repository.create_filter("Gold", "credit_score > 700")

        # Serialize the session (simulates browser refresh / page reload)
        json_bytes = session.to_dict().model_dump_json(indent=2).encode("utf-8")

        from risc_tool.data.models.json_models import SessionJSON

        session_json = SessionJSON.model_validate_json(json_bytes)
        restored = Session()
        restored.rebuild_from_json(session_json)

        # Iterations restored from session
        restored_iterations = restored.iterations_view_model.iterations
        assert single_var_iteration.uid in restored_iterations
        assert child.uid in restored_iterations

        # Metadata restored per iteration
        restored_meta = restored.iterations_view_model.get_iteration_metadata(
            single_var_iteration.uid
        )
        assert restored_meta.metric_ids == [MetricID.DEV_VOLUME]
        assert restored_meta.remove_outliers is True

        # Filters restored
        assert len(restored.filter_repository.filters) == 1
        assert (
            restored.filter_repository.get_filters()[
                next(iter(restored.filter_repository.filters))
            ].name
            == "Gold"
        )


# ---------------------------------------------------------------------------
# 12. Depth Limit Workflow
# ---------------------------------------------------------------------------


class TestDepthLimitWorkflow:
    """Maximum iteration depth enforcement."""

    @pytest.mark.xfail(
        reason=(
            "The max_iteration_depth option is not implemented; can_have_child "
            "returns True for any existing iteration (TEST_PLAN.md workflow 12)."
        ),
        strict=True,
    )
    def test_depth_limit_workflow(self, iterations_vm, single_var_iteration):
        root = single_var_iteration
        child = _double_var(
            iterations_vm,
            name="Depth 2",
            parent_uid=root.uid,
            variable_name="income",
        )
        grandchild = _double_var(
            iterations_vm,
            name="Depth 3",
            parent_uid=child.uid,
            variable_name="income",
        )
        _double_var(
            iterations_vm,
            name="Depth 4",
            parent_uid=grandchild.uid,
            variable_name="income",
        )

        # With default max depth of 2, grandchild creation must be prevented.
        assert iterations_vm.can_have_child(grandchild.uid) is False
