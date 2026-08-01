"""Tests for single variable iteration UI components."""

from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from risc_tool.data.models.enums import IterationType
from risc_tool.data.models.types import IterationID


class TestSingleVarIterationUI:
    """Tests for single_var_iteration UI page."""

    def test_single_var_iteration_renders_title(self, session, single_var_iteration):
        """Test single var iteration page renders title."""
        # Set up session state
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check title is rendered
        assert len(at.get("title")) > 0
        assert at.get("title")[0].value == single_var_iteration.pretty_name  # type: ignore

    def test_single_var_iteration_renders_variable_name(
        self, session, single_var_iteration
    ):
        """Test variable name is displayed."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check variable name in markdown
        markdowns = at.get("markdown")
        var_found = any("credit_score" in str(m.value) for m in markdowns)  # type: ignore
        assert var_found

    def test_single_var_iteration_renders_default_range(
        self, session, single_var_iteration
    ):
        """Test default range table is rendered."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check for data_editor or dataframe (range grid)
        editors = at.get("data_editor")
        dataframes = at.get("dataframe")
        assert len(editors) + len(dataframes) >= 2  # Default + Editable

    def test_single_var_iteration_renders_editable_range(
        self, session, single_var_iteration
    ):
        """Test editable range table is rendered."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should have at least 2 data editors/dataframes
        # Note: In AppTest, st.data_editor elements surface as dataframe elements
        editors = at.get("data_editor")
        dataframes = at.get("dataframe")
        assert len(editors) + len(dataframes) >= 2

    def test_invalid_iteration_type_shows_error(self, session):
        """Test error shown for invalid iteration type."""
        from unittest.mock import PropertyMock

        from risc_tool.ui.iterations.iterations_vm import IterationsViewModel

        # Create a mock iteration with wrong type
        mock_iteration = Mock()
        mock_iteration.iter_type = "INVALID"
        mock_iteration.uid = IterationID(999)

        # Patch the class-level property so the AppTest thread sees it too
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
                return_value=IterationType.DOUBLE,
            ),
        ):
            at = AppTest.from_file(
                "tests/ui/iterations/_render_single_var_iteration.py"
            )
            at.session_state["session"] = session
            at.run()

            # Should show exception
            exceptions = at.get("exception")
            assert len(exceptions) > 0


class TestSingleVarSidebarComponents:
    """Tests for single variable iteration sidebar components."""

    def test_sidebar_has_variable_selector_button(self, session, single_var_iteration):
        """Test sidebar has Set Variables button."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Check sidebar has button
        buttons = at.get("button")
        sidebar_buttons = [b for b in buttons if "Set Variables" in str(b.label)]  # type: ignore
        assert len(sidebar_buttons) > 0

    def test_sidebar_has_metric_selector(self, session, single_var_iteration):
        """Test sidebar has metric selector."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Metric selector renders as a button with the "Set Metrics" label
        buttons = at.get("button")
        metric_buttons = [
            b
            for b in buttons
            if "Set Metrics" in str(b.label) or str(b.key) == "metric_selector_button_0"  # type: ignore
        ]
        assert len(metric_buttons) > 0

    def test_sidebar_has_filter_selector(self, session, single_var_iteration):
        """Test sidebar has filter selector."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Filter selector renders as multiselect
        multiselects = at.get("multiselect")
        assert len(multiselects) > 0

    def test_sidebar_has_scalars_checkbox(self, session, single_var_iteration):
        """Test sidebar has Enable Scalars checkbox."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        scalars_checkbox = [c for c in checkboxes if "Enable Scalars" in str(c.label)]  # type: ignore
        assert len(scalars_checkbox) > 0

    def test_sidebar_has_remove_outliers_checkbox(self, session, single_var_iteration):
        """Test sidebar has Remove Outliers checkbox."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        outliers_checkbox = [c for c in checkboxes if "Remove Outliers" in str(c.label)]  # type: ignore
        assert len(outliers_checkbox) > 0

    def test_filter_change_triggers_rerun(
        self, session, single_var_iteration, filter_repository
    ):
        """Test filter selection change updates metadata and triggers rerun."""
        # Wire the data-backed filter repository into the session so the
        # sidebar's filter_selector sees the same filters as the VM.
        session.filter_repository = filter_repository
        filter_repository.create_filter("Gold", "credit_score > 700")
        filter_ids = list(filter_repository.get_filters().keys())
        assert len(filter_ids) > 0

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # The filter_selector component should be present as a multiselect
        multiselects = at.get("multiselect")
        filter_multiselect = [m for m in multiselects if "Filter" in str(m.label)]  # type: ignore
        assert len(filter_multiselect) > 0

        # Selecting a filter should update metadata
        filter_multiselect[0].set_value(filter_ids).run()  # type: ignore
        meta = session.iterations_view_model.get_iteration_metadata(
            single_var_iteration.uid
        )
        assert set(meta.current_filter_ids) == set(filter_ids)

    def test_scalars_checkbox_change_updates_metadata(
        self, session, single_var_iteration
    ):
        """Test scalars checkbox updates metadata."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        scalars_checkbox = [c for c in checkboxes if "Enable Scalars" in str(c.label)][  # type: ignore
            0
        ]

        # Toggle checkbox
        original_value = scalars_checkbox.value  # type: ignore
        scalars_checkbox.set_value(not original_value).run()  # type: ignore

        # Metadata should be updated
        meta = session.iterations_view_model.get_iteration_metadata(
            single_var_iteration.uid
        )
        assert meta.scalars_enabled != original_value

    def test_remove_outliers_checkbox_change_updates_metadata(
        self, session, single_var_iteration
    ):
        """Test remove outliers checkbox updates metadata."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        checkboxes = at.get("checkbox")
        outliers_checkbox = [
            c
            for c in checkboxes
            if "Remove Outliers" in str(c.label)  # type: ignore
        ][0]

        original_value = outliers_checkbox.value  # type: ignore
        outliers_checkbox.set_value(not original_value).run()  # type: ignore

        meta = session.iterations_view_model.get_iteration_metadata(
            single_var_iteration.uid
        )
        assert meta.remove_outliers != original_value


class TestSingleVarNavigation:
    """Tests for navigation in single var iteration."""

    def test_navigation_widgets_render(self, session, single_var_iteration):
        """Test navigation widgets are rendered."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Back button should always be present in view mode
        buttons = at.get("button")
        back_buttons = [b for b in buttons if "Back" in str(b.label)]  # type: ignore
        assert len(back_buttons) > 0


class TestSingleVarIterationIntegration:
    """Integration tests for single var iteration workflow."""

    def test_full_single_var_view(self, session, single_var_iteration):
        """Test complete single var iteration view renders without errors."""
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should run without exceptions
        assert not at.exception

        # Should have title
        titles = at.get("title")
        assert len(titles) > 0

        # Should have data editors for range tables
        editors = at.get("data_editor")
        dataframes = at.get("dataframe")
        assert len(editors) + len(dataframes) >= 2


class TestSingleVarIterationWithMetrics:
    """Tests with metrics configured."""

    def test_with_metrics_renders_metric_columns(self, session, single_var_iteration):
        """Test metric columns appear when metrics are configured."""
        # Add a metric to metadata
        from risc_tool.data.models.types import MetricID

        session.iterations_view_model.set_metadata(
            single_var_iteration.uid, metric_ids=[MetricID.DEV_VOLUME]
        )
        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_single_var_iteration.py")
        at.session_state["session"] = session
        at.run()

        # Should still render without errors
        assert not at.exception
        editors = at.get("data_editor")
        dataframes = at.get("dataframe")
        assert len(editors) + len(dataframes) >= 2


class TestIterationMetricTableComponent:
    """Tests for iteration_metric_table component directly."""

    def test_component_renders_with_valid_params(self, session, single_var_iteration):
        """Test iteration_metric_table component renders."""
        from risc_tool.ui.components.iteration_metric_table import (
            iteration_metric_table,
        )

        # Mock streamlit components
        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None

            iteration_metric_table(
                iteration_id=single_var_iteration.uid,
                default=True,
                show_controls=True,
                filter_ids=[],
                metric_ids=[],
                scalars_enabled=False,
                remove_outliers=False,
                editable=True,
                key="test-key",
            )

            mock_editor.assert_called_once()

    def test_component_editable_false_shows_dataframe(
        self, session, single_var_iteration
    ):
        """Test component still renders the table when editable=False."""
        from risc_tool.ui.components.iteration_metric_table import (
            iteration_metric_table,
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None

            iteration_metric_table(
                iteration_id=single_var_iteration.uid,
                default=True,
                show_controls=True,
                filter_ids=[],
                metric_ids=[],
                scalars_enabled=False,
                remove_outliers=False,
                editable=False,
                key="test-key",
            )

            mock_editor.assert_called_once()

    def test_component_shows_errors_when_editable(self, session, single_var_iteration):
        """Test component shows error widget when editable."""
        from risc_tool.ui.components.iteration_metric_table import (
            iteration_metric_table,
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch(
                "risc_tool.ui.components.iteration_metric_table.error_and_warning_widget"
            ) as mock_error,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None
            mock_error.return_value = None

            iteration_metric_table(
                iteration_id=single_var_iteration.uid,
                default=True,
                show_controls=True,
                filter_ids=[],
                metric_ids=[],
                scalars_enabled=False,
                remove_outliers=False,
                editable=True,
                key="test-key",
            )

            mock_error.assert_called_once()
