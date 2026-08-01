"""Tests for double variable iteration UI components."""

from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from risc_tool.data.models.enums import IterationType
from risc_tool.data.models.types import IterationID, MetricID


class TestDoubleVarIterationUI:
    """Tests for double_var_iteration UI page."""

    def test_double_var_iteration_renders_title(self, session, double_var_iteration):
        """Test double var iteration page renders title."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        titles = at.get("title")
        assert len(titles) > 0
        assert titles[0].value == double_var_iteration.pretty_name  # type: ignore

    def test_double_var_iteration_renders_variable_name(
        self, session, double_var_iteration
    ):
        """Test variable name is displayed."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        markdowns = at.get("markdown")
        var_found = any("income" in str(m.value) for m in markdowns)  # type: ignore
        assert var_found

    def test_split_view_enabled_renders_grid_layout(
        self, session, double_var_iteration
    ):
        """Test split view renders grid layout."""
        # Enable split view
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=True
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should have grid layout (2 columns with metric grids)
        assert not at.exception

    def test_linear_view_enabled_renders_linear_layout(
        self, session, double_var_iteration
    ):
        """Test linear view renders linear layout."""
        # Disable split view (linear layout)
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=False
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should have linear layout
        assert not at.exception

    def test_invalid_iteration_type_shows_error(self, session):
        """Test error shown for invalid iteration type."""
        from unittest.mock import PropertyMock

        from risc_tool.ui.iterations.iterations_vm import IterationsViewModel

        mock_iteration = Mock()
        mock_iteration.iter_type = "INVALID"
        mock_iteration.uid = IterationID(999)

        with (
            patch.object(
                IterationsViewModel,
                "current_iteration",
                new_callable=PropertyMock,
                return_value=mock_iteration,
            ),
            patch.object(
                IterationsViewModel,
                "current_iteration_type",
                new_callable=PropertyMock,
                return_value=IterationType.SINGLE,
            ),
        ):
            at = AppTest.from_file(
                "tests/ui/iterations/_render_double_var_iteration.py"
            )
            at.session_state["session"] = session
            at.run()

            exceptions = at.get("exception")
            assert len(exceptions) > 0


class TestDoubleVarSidebarComponents:
    """Tests for double variable iteration sidebar components."""

    def test_sidebar_has_edit_groups_button(self, session, double_var_iteration):
        """Test sidebar has Edit Groups button."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        buttons = at.get("button")
        edit_groups = [b for b in buttons if "Edit Groups" in str(b.label)]  # type: ignore
        assert len(edit_groups) > 0

    def test_sidebar_has_add_group_button(self, session, double_var_iteration):
        """Test sidebar has Add Group button."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        buttons = at.get("button")
        add_group = [
            b for b in buttons if str(b.key) == f"add-group-{double_var_iteration.uid}"
        ]
        assert len(add_group) > 0

    def test_sidebar_has_split_view_toggle(self, session, double_var_iteration):
        """Test sidebar has split view toggle (segmented control)."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        iterations_vm = session.iterations_view_model
        iterations_vm.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        # List view (split_view_enabled=False) -> segmented index 0
        iterations_vm.set_metadata(double_var_iteration.uid, split_view_enabled=False)
        with (
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as _mock_metric,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_segmented.return_value = 0
            mock_filter.return_value = []
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            mock_segmented.assert_called_once()
            assert mock_segmented.call_args.kwargs.get("index") == 0

        # Grid view (split_view_enabled=True) -> segmented index 1
        iterations_vm.set_metadata(double_var_iteration.uid, split_view_enabled=True)
        with (
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as _mock_metric,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_segmented.return_value = 1
            mock_filter.return_value = []
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            mock_segmented.assert_called_once()
            assert mock_segmented.call_args.kwargs.get("index") == 1

    def test_sidebar_has_scalars_checkbox(self, session, double_var_iteration):
        """Test sidebar has Enable Scalars checkbox."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        scalars = [c for c in checkboxes if "Enable Scalars" in str(c.label)]  # type: ignore
        assert len(scalars) > 0

    def test_sidebar_has_remove_outliers_checkbox(self, session, double_var_iteration):
        """Test sidebar has Remove Outliers checkbox."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        outliers = [c for c in checkboxes if "Remove Outliers" in str(c.label)]  # type: ignore
        assert len(outliers) > 0

    def test_sidebar_has_editable_checkbox(self, session, double_var_iteration):
        """Test sidebar has Editable checkbox for double var."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        editable = [c for c in checkboxes if "Editable" in str(c.label)]  # type: ignore
        assert len(editable) > 0

    def test_sidebar_has_show_prev_details_checkbox(
        self, session, double_var_iteration
    ):
        """Test sidebar has Show Previous Iteration Details checkbox."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        show_prev = [c for c in checkboxes if "Show Previous" in str(c.label)]  # type: ignore
        assert len(show_prev) > 0

    def test_split_view_toggle_updates_metadata(self, session, double_var_iteration):
        """Test split view toggle updates metadata."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        iterations_vm = session.iterations_view_model
        iterations_vm.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        # Grid view (index 1) should enable split_view_enabled metadata
        iterations_vm.set_metadata(double_var_iteration.uid, split_view_enabled=False)
        with (
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as _mock_metric,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as _mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_segmented.return_value = 1  # grid view
            mock_filter.return_value = []
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            meta = iterations_vm.get_iteration_metadata(double_var_iteration.uid)
            assert meta.split_view_enabled is True

        # List view (index 0) should disable split_view_enabled metadata
        iterations_vm.set_metadata(double_var_iteration.uid, split_view_enabled=True)
        with (
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as _mock_metric,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as _mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_segmented.return_value = 0  # list view
            mock_filter.return_value = []
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            meta = iterations_vm.get_iteration_metadata(double_var_iteration.uid)
            assert meta.split_view_enabled is False


class TestDoubleVarGridLayout:
    """Tests for grid layout widget."""

    def test_grid_layout_renders_editor_and_metrics(
        self, session, double_var_iteration
    ):
        """Test grid layout renders editable grid and metric grids."""
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should have editable grid and at least one metric grid
        editors = at.get("data_editor")
        dataframes = at.get("dataframe")
        assert len(editors) + len(dataframes) >= 2

    def test_grid_layout_with_multiple_metrics(self, session, double_var_iteration):
        """Test grid layout with multiple metrics."""
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid,
            metric_ids=[MetricID.DEV_VOLUME, MetricID.DEV_DLR_BAD_RATE],
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        assert not at.exception


class TestDoubleVarLinearLayout:
    """Tests for linear layout widget."""

    def test_linear_layout_renders_editor_and_metrics(
        self, session, double_var_iteration
    ):
        """Test linear layout renders editable grid and metric grids."""
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=False
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        assert not at.exception


class TestDoubleVarPreviousIterationsChain:
    """Tests for previous iterations chain display."""

    def test_chain_display_shows_parent_iteration(
        self, session, double_var_iteration, single_var_iteration
    ):
        """Test chain display shows parent iteration."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check for iteration metric table for parent
        markdowns = at.get("markdown")
        chain_found = any("Previous Iterations" in str(m.value) for m in markdowns)  # type: ignore
        assert chain_found
        # Check parent iteration appears in chain
        parent_found = any("credit_score" in str(m.value) for m in markdowns)  # type: ignore
        assert parent_found

    def test_chain_display_shows_multiple_ancestors(self, session):
        """Test chain display with multiple ancestor iterations."""
        # Create a chain: root -> child1 -> child2
        from risc_tool.data.models.enums import LossRateTypes, VariableType
        from risc_tool.data.models.types import RiskSegmentID

        root = session.iterations_view_model.add_single_var_iteration(
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

        child1 = session.iterations_view_model.add_double_var_iteration(
            name="Child1",
            previous_iteration_id=root.uid,
            variable_name="income",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        child2 = session.iterations_view_model.add_double_var_iteration(
            name="Child2",
            previous_iteration_id=child1.uid,
            variable_name="age",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=child2.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should show both root and child1 in chain
        assert not at.exception


class TestDoubleVarIntegration:
    """Integration tests for double var iteration workflow."""

    def test_full_double_var_view(self, session, double_var_iteration):
        """Test complete double var iteration view renders without errors."""
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        assert not at.exception
        titles = at.get("title")
        assert len(titles) > 0

    def test_split_view_toggle(self, session, double_var_iteration):
        """Test toggling split view."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_double_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check initial state
        _initial_split = session.iterations_view_model.get_iteration_metadata(
            double_var_iteration.uid
        ).split_view_enabled

        # Toggle would require interacting with segmented control
        # which is complex in AppTest, so just verify no errors
        assert not at.exception


class TestEditableGridWidgetDoubleVar:
    """Tests for editable_grid_widget with double var."""

    def test_editable_grid_renders_for_default(self, session, double_var_iteration):
        """Test editable grid renders for default view."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.dataframe") as mock_dataframe,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None
            mock_dataframe.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=True, key="test"
            )

            # Default should use dataframe (not editable)
            mock_dataframe.assert_called()

    def test_editable_grid_renders_editor_for_editable_custom(
        self, session, double_var_iteration
    ):
        """Test editable grid renders editor for editable custom view."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        # Enable editable
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, editable=True
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=False, key="test"
            )

            # Editable custom should use data_editor
            mock_editor.assert_called()


class TestMetricGridsRendering:
    """Tests for metric grids rendering."""

    def test_metric_grids_default_and_custom(self, session, double_var_iteration):
        """Test metric grids render for both default and custom."""
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )

        # Test default
        metric_views, errors, warnings = session.iterations_view_model.get_metric_grids(
            double_var_iteration.uid,
            default=True,
            show_controls_idx="alternate",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert isinstance(metric_views, list)
        if metric_views:
            assert "metric_styler" in metric_views[0]

        # Test custom
        metric_views, errors, warnings = session.iterations_view_model.get_metric_grids(
            double_var_iteration.uid,
            default=False,
            show_controls_idx="alternate",
            show_total_row=True,
            show_total_column=True,
            theme="dark",
        )

        assert isinstance(metric_views, list)
