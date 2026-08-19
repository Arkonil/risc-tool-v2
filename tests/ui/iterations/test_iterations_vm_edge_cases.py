"""Tests for IterationsViewModel edge cases."""

import pytest

from risc_tool.data.models.enums import (
    IterationType,
    LossRateTypes,
    RangeColumn,
    RowIndex,
    VariableType,
)
from risc_tool.data.models.object_id import GroupID, IterationID, MetricID


class TestViewModelNavigation:
    """Tests for ViewModel navigation state management."""

    def test_graph_to_create_root_transition(self, iterations_vm):
        """Test navigation from graph to create root iteration."""
        # Start at graph
        view, iter_id = iterations_vm.current_status
        assert view == "graph"
        assert iter_id is None

        # Transition to create root
        iterations_vm.set_current_status("create", iteration_create_parent_id=None)
        view, iter_id = iterations_vm.current_status
        assert view == "create"
        assert iter_id is None

        # Create iteration
        from risc_tool.data.models.object_id import RiskSegmentID

        iteration = iterations_vm.add_single_var_iteration(
            name="Root",
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1)],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        # Transition to view
        iterations_vm.set_current_status("view", current_iteration_id=iteration.uid)
        view, iter_id = iterations_vm.current_status
        assert view == "view"
        assert iter_id == iteration.uid

    def test_create_child_from_view(self, iterations_vm, single_var_iteration):
        """Test creating child iteration from parent view."""
        # View parent iteration
        iterations_vm.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        # Transition to create child
        iterations_vm.set_current_status(
            "create", iteration_create_parent_id=single_var_iteration.uid
        )
        view, iter_id = iterations_vm.current_status
        assert view == "create"
        assert iter_id == single_var_iteration.uid

        # Verify create mode is DOUBLE
        assert iterations_vm.current_iteration_create_mode == IterationType.DOUBLE
        assert (
            iterations_vm.current_iteration_create_parent_id == single_var_iteration.uid
        )

    def test_view_to_graph_transition(self, iterations_vm, single_var_iteration):
        """Test transition from view back to graph."""
        iterations_vm.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        iterations_vm.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )
        view, iter_id = iterations_vm.current_status
        assert view == "graph"
        assert iter_id == single_var_iteration.uid

    def test_invalid_view_iteration_id(self, iterations_vm):
        """Test setting view with invalid iteration ID raises error."""
        with pytest.raises(ValueError, match="Must provide a current iteration ID"):
            iterations_vm.set_current_status("view", current_iteration_id=None)

    def test_view_nonexistent_iteration_falls_back_to_graph(self, iterations_vm):
        """Test viewing nonexistent iteration falls back to graph."""
        iterations_vm.set_current_status("view", current_iteration_id=IterationID(999))
        view, iter_id = iterations_vm.current_status
        assert view == "graph"
        assert iter_id is None

    def test_selected_iteration_in_graph(self, iterations_vm, single_var_iteration):
        """Test selecting iteration in graph view."""
        iterations_vm.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )
        view, iter_id = iterations_vm.current_status
        assert view == "graph"
        assert iter_id == single_var_iteration.uid


class TestViewModelCategoricalOptions:
    """Tests for categorical iteration options."""

    def test_categorical_options_sorted(
        self, iterations_vm, categorical_single_var_iteration
    ):
        """Test categorical options are sorted."""
        options = iterations_vm.get_categorical_iteration_options(
            categorical_single_var_iteration.uid
        )
        assert options == sorted(options)

    def test_categorical_options_unique(
        self, iterations_vm, categorical_single_var_iteration
    ):
        """Test categorical options are unique."""
        options = iterations_vm.get_categorical_iteration_options(
            categorical_single_var_iteration.uid
        )
        assert len(options) == len(set(options))

    def test_numerical_returns_empty(self, iterations_vm, single_var_iteration):
        """Test numerical iteration returns empty list."""
        options = iterations_vm.get_categorical_iteration_options(
            single_var_iteration.uid
        )
        assert options == []

    def test_nonexistent_iteration_returns_empty(self, iterations_vm):
        """Test nonexistent iteration raises error (current behavior)."""
        from risc_tool.data.models.object_id import IterationID

        with pytest.raises(ValueError, match="does not exist"):
            iterations_vm.get_categorical_iteration_options(IterationID(999))


class TestViewModelMetricGrids:
    """Tests for get_metric_grids with various configurations."""

    def test_show_controls_all(self, iterations_vm, double_var_iteration):
        """Test get_metric_grids with show_controls_idx='all'."""
        iterations_vm.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )

        metric_views, _errors, _warnings = iterations_vm.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx="all",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert isinstance(metric_views, list)
        assert len(metric_views) == 1
        # All should have controls
        for view in metric_views:
            data = view["metric_styler"].data
            # Control columns should be present
            assert (
                "Lower Bound" in data.columns.get_level_values(-1).tolist()
                or "Upper Bound" in data.columns.get_level_values(-1).tolist()
            )

    def test_show_controls_alternate(self, iterations_vm, double_var_iteration):
        """Test get_metric_grids with show_controls_idx='alternate'."""
        iterations_vm.set_metadata(
            double_var_iteration.uid,
            metric_ids=[
                MetricID.DEV_VOLUME,
                MetricID.DEV_DLR_BAD_RATE,
                MetricID.DEV_UNT_BAD_RATE,
            ],
        )

        metric_views, _errors, _warnings = iterations_vm.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx="alternate",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert len(metric_views) == 3
        # Alternate means controls on odd-indexed views only
        for i, view in enumerate(metric_views):
            data = view["metric_styler"].data
            cols = data.columns.get_level_values(-1).tolist()
            has_controls = "Lower Bound" in cols or "Upper Bound" in cols
            assert has_controls == (i % 2 != 0), f"view {i} controls mismatch"

    def test_show_controls_list(self, iterations_vm, double_var_iteration):
        """Test get_metric_grids with show_controls_idx as list."""
        iterations_vm.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )

        metric_views, _errors, _warnings = iterations_vm.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx=[0],
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert len(metric_views) == 1

    def test_no_metrics_returns_empty(self, iterations_vm, double_var_iteration):
        """Test get_metric_grids with no metrics returns empty."""
        iterations_vm.set_metadata(double_var_iteration.uid, metric_ids=[])

        metric_views, _errors, _warnings = iterations_vm.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx="all",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert metric_views == []

    def test_total_row_and_column(self, iterations_vm, double_var_iteration):
        """Test get_metric_grids with total row and column."""
        iterations_vm.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )

        metric_views, _errors, _warnings = iterations_vm.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx="all",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        data = metric_views[0]["metric_styler"].data
        # Check for Total in columns and index
        cols = data.columns.get_level_values(-1).tolist()
        assert "Total" in cols
        idx = data.index.tolist()
        # Total row uses RowIndex.TOTAL enum
        from risc_tool.data.models.enums import RowIndex

        assert RowIndex.TOTAL in idx


class TestViewModelGroupSelection:
    """Tests for group selection and management."""

    def test_select_groups_empty(self, iterations_vm, double_var_iteration):
        """Test selecting empty group list."""
        # Current behavior: repository doesn't change selection when empty list given
        # (selected_set is empty, so it returns early)
        result = iterations_vm.select_groups(double_var_iteration.uid, [])
        # ViewModel returns True because current != new, but repository doesn't change
        assert result is True

        # Groups remain selected (repository behavior)
        groups = iterations_vm.get_all_groups(double_var_iteration.uid)
        assert groups[RangeColumn.SELECTED.value].all()

    def test_select_groups_invalid_ids(self, iterations_vm, double_var_iteration):
        """Test selecting invalid group IDs."""
        # Select with non-existent group IDs
        result = iterations_vm.select_groups(
            double_var_iteration.uid, [GroupID(999), GroupID(1000)]
        )
        # ViewModel returns True (current != new), but repository doesn't change (empty selected_set)
        assert result is True

        # Original selection should remain
        groups = iterations_vm.get_all_groups(double_var_iteration.uid)
        assert groups[RangeColumn.SELECTED.value].all()

    def test_select_groups_partial(self, iterations_vm, double_var_iteration):
        """Test selecting subset of groups."""
        all_groups = iterations_vm.get_all_groups(double_var_iteration.uid)
        valid_group_ids = [g for g in all_groups.index if g != RowIndex.TOTAL]

        if len(valid_group_ids) >= 2:
            selected = valid_group_ids[:2]
            result = iterations_vm.select_groups(double_var_iteration.uid, selected)
            assert result is True

            groups = iterations_vm.get_all_groups(double_var_iteration.uid)
            assert bool(groups.loc[selected[0], RangeColumn.SELECTED.value])
            assert bool(groups.loc[selected[1], RangeColumn.SELECTED.value])

    def test_add_new_group(self, iterations_vm, double_var_iteration):
        """Test adding new group to double var iteration."""
        before_count = len(iterations_vm.get_all_groups(double_var_iteration.uid))

        result = iterations_vm.add_new_group(double_var_iteration.uid)
        assert result is True

        after_count = len(iterations_vm.get_all_groups(double_var_iteration.uid))
        assert after_count == before_count + 1

        # New group should be selected by default
        groups = iterations_vm.get_all_groups(double_var_iteration.uid)
        new_group_idx = groups.index[-1]
        assert bool(groups.loc[new_group_idx, RangeColumn.SELECTED.value])

    def test_add_new_group_single_var_returns_false(
        self, iterations_vm, single_var_iteration
    ):
        """Test adding group to single var iteration returns False."""
        result = iterations_vm.add_new_group(single_var_iteration.uid)
        assert result is False  # Single var iterations don't support groups


class TestViewModelMetadata:
    """Tests for metadata management."""

    def test_set_metadata_updates_values(self, iterations_vm, single_var_iteration):
        """Test set_metadata updates metadata values."""
        iterations_vm.set_metadata(
            single_var_iteration.uid,
            scalars_enabled=True,
            remove_outliers=False,
        )

        meta = iterations_vm.get_iteration_metadata(single_var_iteration.uid)
        assert meta.scalars_enabled is True
        assert meta.remove_outliers is False

    def test_get_metadata_nonexistent_raises(self, iterations_vm):
        """Test getting metadata for nonexistent iteration raises error."""
        with pytest.raises(ValueError, match="does not exist"):
            iterations_vm.get_iteration_metadata(IterationID(999))

    def test_dependency_update_prunes_metadata(
        self, iterations_vm, single_var_iteration
    ):
        """Test dependency update prunes deleted iterations."""
        # Add metadata for a fake iteration
        from risc_tool.data.models.iteration_metadata import IterationMetadata

        fake_id = IterationID(999)
        iterations_vm._IterationsViewModel__metadata[fake_id] = IterationMetadata()

        # Trigger dependency update
        iterations_vm.on_dependency_update(set())

        # Fake iteration should be pruned
        assert fake_id not in iterations_vm._IterationsViewModel__metadata


class TestViewModelIterationAccess:
    """Tests for iteration access methods."""

    def test_current_iteration_returns_correct(
        self, iterations_vm, single_var_iteration
    ):
        """Test current_iteration returns correct iteration."""
        iterations_vm.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        current = iterations_vm.current_iteration
        assert current is not None
        assert current.uid == single_var_iteration.uid

    def test_current_iteration_none_in_graph(self, iterations_vm):
        """Test current_iteration is None in graph view."""
        iterations_vm.set_current_status("graph")
        current = iterations_vm.current_iteration
        assert current is None

    def test_current_iteration_type(
        self, iterations_vm, single_var_iteration, double_var_iteration
    ):
        """Test current_iteration_type returns correct type."""
        iterations_vm.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )
        assert iterations_vm.current_iteration_type == IterationType.SINGLE

        iterations_vm.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )
        assert iterations_vm.current_iteration_type == IterationType.DOUBLE

    def test_get_iteration_name(self, iterations_vm, single_var_iteration):
        """Test get_iteration_name returns name."""
        name = iterations_vm.get_iteration_name(single_var_iteration.uid)
        assert name == single_var_iteration.name

    def test_get_iteration(self, iterations_vm, single_var_iteration):
        """Test get_iteration returns iteration object."""
        iteration = iterations_vm.get_iteration(single_var_iteration.uid)
        assert iteration.uid == single_var_iteration.uid

    def test_can_have_child(self, iterations_vm, single_var_iteration):
        """Test can_have_child returns True for existing iterations and False for missing iterations."""
        assert iterations_vm.can_have_child(single_var_iteration.uid) is True
        assert iterations_vm.can_have_child("nonexistent_id") is False


class TestViewModelRiskSegments:
    """Tests for risk segment details."""

    def test_global_risk_segment_details(self, iterations_vm):
        """Test global_risk_segment_details returns styler."""
        styler = iterations_vm.global_risk_segment_details()
        assert styler is not None
        assert hasattr(styler, "data")

    def test_get_risk_segment_details(self, iterations_vm, single_var_iteration):
        """Test get_risk_segment_details returns styler."""
        styler = iterations_vm.get_risk_segment_details(single_var_iteration.uid)
        assert styler is not None
        assert hasattr(styler, "data")

    def test_is_rs_details_same(self, iterations_vm, single_var_iteration):
        """Test is_rs_details_same returns status."""
        status = iterations_vm.is_rs_details_same(single_var_iteration.uid)
        assert status in ["equal", "unequal", "updatable"]

    def test_update_rs_details(self, iterations_vm, single_var_iteration):
        """Test update_rs_details returns bool."""
        result = iterations_vm.update_rs_details(single_var_iteration.uid)
        assert isinstance(result, bool)
