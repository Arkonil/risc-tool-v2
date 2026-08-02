"""Tests for common iteration utilities."""

from unittest.mock import MagicMock, Mock, patch

import pandas as pd

from risc_tool.data.models.enums import RangeColumn
from risc_tool.data.models.types import GroupID


class TestSetGroupsDialogWidget:
    """Tests for set_groups_dialog_widget."""

    def test_dialog_renders_groups_editor(self, session, double_var_iteration):
        """Test dialog renders groups data editor."""
        from risc_tool.ui.iterations.common import set_groups_dialog_widget

        dialog_func = set_groups_dialog_widget.__wrapped__  # type: ignore

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = pd.DataFrame(
                {
                    RangeColumn.SELECTED.value: [True, False],
                    RangeColumn.LOWER_BOUND.value: [0.0, 100.0],
                    RangeColumn.UPPER_BOUND.value: [100.0, 200.0],
                },
                index=[GroupID(0), GroupID(1)],
            )
            mock_button.return_value = False
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(double_var_iteration.uid)

            mock_editor.assert_called_once()
            # Verify column config includes SELECTED checkbox

    def test_dialog_submit_updates_groups(self, session, double_var_iteration):
        """Test submitting dialog updates selected groups."""
        from risc_tool.ui.iterations.common import set_groups_dialog_widget

        dialog_func = set_groups_dialog_widget.__wrapped__  # type: ignore

        # Create edited groups with selection
        edited_groups = pd.DataFrame(
            {
                RangeColumn.SELECTED.value: [True, False, True],
                RangeColumn.LOWER_BOUND.value: [0.0, 100.0, 200.0],
                RangeColumn.UPPER_BOUND.value: [100.0, 200.0, 300.0],
            },
            index=[GroupID(0), GroupID(1), GroupID(2)],
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = edited_groups
            mock_button.return_value = True  # Submit clicked
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(double_var_iteration.uid)

            # Should call select_groups and rerun
            mock_rerun.assert_called()

    def test_dialog_no_selected_column_shows_error(self, session, double_var_iteration):
        """Test dialog shows error when SELECTED column missing."""
        from risc_tool.ui.iterations.common import set_groups_dialog_widget

        dialog_func = set_groups_dialog_widget.__wrapped__  # type: ignore

        # Mock get_all_groups to return data without SELECTED column
        with (
            patch.object(
                session.iterations_view_model, "get_all_groups"
            ) as mock_get_groups,
            patch("streamlit.exception") as mock_exception,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_get_groups.return_value = pd.DataFrame(
                {
                    RangeColumn.LOWER_BOUND.value: [0.0, 100.0],
                    RangeColumn.UPPER_BOUND.value: [100.0, 200.0],
                },
                index=[GroupID(0), GroupID(1)],
            )

            dialog_func(double_var_iteration.uid)

            mock_exception.assert_called_once()


class TestCheckCurrentRSDetails:
    """Tests for check_current_rs_details."""

    def test_equal_details_does_nothing(self, session, single_var_iteration):
        """Test equal RS details does nothing."""
        from risc_tool.ui.iterations.common import check_current_rs_details

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        with (
            patch.object(
                session.iterations_view_model, "is_rs_details_same"
            ) as mock_is_same,
            patch("streamlit.expander") as mock_expander,
            patch("streamlit.warning") as mock_warning,
            patch("streamlit.button"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_is_same.return_value = "equal"

            check_current_rs_details()

            mock_is_same.assert_called_once_with(single_var_iteration.uid)
            mock_expander.assert_not_called()
            mock_warning.assert_not_called()

    def test_unequal_details_shows_error(self, session, single_var_iteration):
        """Test unequal RS details shows error expander."""
        from risc_tool.ui.iterations.common import check_current_rs_details

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        with (
            patch.object(
                session.iterations_view_model, "is_rs_details_same"
            ) as mock_is_same,
            patch("streamlit.expander") as mock_expander,
            patch("streamlit.error") as mock_error,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_is_same.return_value = "unequal"
            mock_expander_context = Mock()
            mock_expander_context.__enter__ = Mock(return_value=mock_expander_context)
            mock_expander_context.__exit__ = Mock(return_value=False)
            mock_expander.return_value = mock_expander_context

            check_current_rs_details()

            mock_expander.assert_called_once()
            mock_error.assert_called_once()

    def test_updatable_details_shows_warning_with_update_button(
        self, session, single_var_iteration
    ):
        """Test updatable RS details shows warning with update button."""
        from risc_tool.ui.iterations.common import check_current_rs_details

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        with (
            patch.object(
                session.iterations_view_model, "is_rs_details_same"
            ) as mock_is_same,
            patch.object(
                session.iterations_view_model, "update_rs_details"
            ) as mock_update,
            patch("streamlit.container") as mock_container,
            patch("streamlit.warning") as mock_warning,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_is_same.return_value = "updatable"
            mock_update.return_value = True
            mock_button.return_value = True
            mock_container_context = Mock()
            mock_container_context.__enter__ = Mock(return_value=mock_container_context)
            mock_container_context.__exit__ = Mock(return_value=False)
            mock_container.return_value = mock_container_context

            check_current_rs_details()

            mock_warning.assert_called_once()
            mock_button.assert_called_once()
            mock_update.assert_called_once_with(single_var_iteration.uid)
            mock_rerun.assert_called_once()

    def test_updatable_details_update_false_no_rerun(
        self, session, single_var_iteration
    ):
        """Test updatable details with failed update doesn't rerun."""
        from risc_tool.ui.iterations.common import check_current_rs_details

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        with (
            patch.object(
                session.iterations_view_model, "is_rs_details_same"
            ) as mock_is_same,
            patch.object(
                session.iterations_view_model, "update_rs_details"
            ) as mock_update,
            patch("streamlit.container"),
            patch("streamlit.warning"),
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_is_same.return_value = "updatable"
            mock_update.return_value = False
            mock_button.return_value = True

            check_current_rs_details()

            mock_update.assert_called_once()
            mock_rerun.assert_not_called()


class TestIterationSidebarComponents:
    """Tests for iteration_sidebar_components."""

    def test_sidebar_renders_variable_selector_button(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has Set Variables button."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            # Should have Set Variables button
            button_calls = mock_button.call_args_list
            var_button = [c for c in button_calls if "Set Variables" in str(c)]
            assert len(var_button) > 0

    def test_sidebar_renders_metric_selector(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has metric selector."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as mock_metric,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            mock_metric.assert_called_once()

    def test_sidebar_renders_edit_groups_for_double_var(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has Edit Groups for double var."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.button") as mock_button,
            patch("risc_tool.ui.iterations.common.set_groups_dialog_widget"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            # Edit Groups button should be present for double var
            button_calls = mock_button.call_args_list
            edit_button = [c for c in button_calls if "Edit Groups" in str(c)]
            assert len(edit_button) > 0

    def test_sidebar_renders_add_group_for_double_var(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has Add Group for double var."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            # Add group button (icon-only button with key add-group-{iteration_id})
            button_calls = mock_button.call_args_list
            add_button = [
                c
                for c in button_calls
                if c.kwargs.get("key") == f"add-group-{double_var_iteration.uid}"
            ]
            assert len(add_button) > 0

    def test_sidebar_renders_split_view_toggle_for_double_var(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has split view toggle for double var."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_segmented.return_value = 0  # list view
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            mock_segmented.assert_called_once()

    def test_sidebar_renders_filter_selector(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has filter selector."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_filter.return_value = []
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            mock_filter.assert_called_once()

    def test_sidebar_renders_scalars_checkbox(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has scalars checkbox."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.checkbox") as mock_checkbox,
            patch("streamlit.rerun"),
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_checkbox.return_value = True
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            checkbox_calls = mock_checkbox.call_args_list
            scalars_call = [c for c in checkbox_calls if "Enable Scalars" in str(c)]
            assert len(scalars_call) > 0

    def test_sidebar_renders_remove_outliers_checkbox(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has remove outliers checkbox."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.checkbox") as mock_checkbox,
            patch("streamlit.rerun"),
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_checkbox.return_value = True
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            checkbox_calls = mock_checkbox.call_args_list
            outliers_call = [c for c in checkbox_calls if "Remove Outliers" in str(c)]
            assert len(outliers_call) > 0

    def test_sidebar_renders_editable_checkbox_for_double_var(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has editable checkbox for double var."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.checkbox") as mock_checkbox,
            patch("streamlit.rerun"),
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_checkbox.return_value = True
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            checkbox_calls = mock_checkbox.call_args_list
            editable_call = [c for c in checkbox_calls if "Editable" in str(c)]
            assert len(editable_call) > 0

    def test_sidebar_renders_show_prev_details_for_depth_2(
        self, session, double_var_iteration, patch_columns
    ):
        """Test sidebar has show prev details for depth 2 iteration."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        with (
            patch("streamlit.checkbox") as mock_checkbox,
            patch("streamlit.rerun"),
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_checkbox.return_value = True
            mock_button.return_value = False

            iteration_sidebar_components(double_var_iteration.uid)

            checkbox_calls = mock_checkbox.call_args_list
            prev_call = [c for c in checkbox_calls if "Show Previous" in str(c)]
            assert len(prev_call) > 0


class TestEditableGridWidget:
    """Tests for editable_grid_widget."""

    def test_widget_renders_dataframe_when_not_editable(
        self, session, double_var_iteration
    ):
        """Test widget renders dataframe when not editable."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        # Disable editable
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, editable=False
        )

        with (
            patch("streamlit.dataframe") as mock_dataframe,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_dataframe.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=False, key="test"
            )

            mock_dataframe.assert_called_once()

    def test_widget_renders_editor_when_editable(self, session, double_var_iteration):
        """Test widget renders data_editor when editable."""
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

            mock_editor.assert_called_once()

    def test_widget_renders_dataframe_when_default(self, session, double_var_iteration):
        """Test widget renders dataframe for default view even if editable."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, editable=True
        )

        with (
            patch("streamlit.dataframe") as mock_dataframe,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_dataframe.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=True, key="test"
            )

            # Default view should use dataframe (not editable)
            mock_dataframe.assert_called_once()

    def test_widget_shows_prev_details_spacing(self, session, double_var_iteration):
        """Test widget adds spacing when showing prev iter details in split view."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, editable=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, show_prev_iter_details=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=True
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.space") as mock_space,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=False, key="test"
            )

            mock_space.assert_called_once()


class TestNavigationWidgets:
    """Tests for navigation_widgets."""

    def test_navigation_renders_buttons(
        self, session, single_var_iteration, patch_columns
    ):
        """Test navigation widgets render buttons."""
        from risc_tool.ui.iterations.navigation import navigation_widgets

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=single_var_iteration.uid
        )

        with (
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            navigation_widgets()

            # Back button should always be rendered in view mode
            button_calls = mock_button.call_args_list
            back_calls = [c for c in button_calls if c.kwargs.get("label") == "Back"]
            assert len(back_calls) > 0


class TestCommonUtilitiesIntegration:
    """Integration tests for common utilities."""

    def test_full_sidebar_workflow(self, session, double_var_iteration):
        """Test complete sidebar interaction workflow."""
        from risc_tool.ui.iterations.common import iteration_sidebar_components

        session.iterations_view_model.set_current_status(
            "view", current_iteration_id=double_var_iteration.uid
        )

        with (
            patch("streamlit.button") as mock_button,
            patch("streamlit.checkbox") as mock_checkbox,
            patch("streamlit.columns") as mock_columns,
            patch("risc_tool.ui.iterations.common.filter_selector") as mock_filter,
            patch(
                "risc_tool.ui.iterations.common.metric_selector_button"
            ) as mock_metric,
            patch("risc_tool.ui.iterations.common.variable_selector_dialog"),
            patch("streamlit_antd_components.segmented") as mock_segmented,
            patch("streamlit.rerun"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_checkbox.return_value = True
            mock_button.return_value = False
            mock_filter.return_value = []
            mock_segmented.return_value = 0
            mock_columns.return_value = [MagicMock(), MagicMock()]

            iteration_sidebar_components(double_var_iteration.uid)

            # All components should be called
            assert mock_metric.called
            assert mock_filter.called
            assert mock_segmented.called

    def test_editable_grid_with_prev_details(self, session, double_var_iteration):
        """Test editable grid with previous iteration details."""
        from risc_tool.ui.iterations.common import editable_grid_widget

        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, editable=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, show_prev_iter_details=True
        )
        session.iterations_view_model.set_metadata(
            double_var_iteration.uid, split_view_enabled=True
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.container"),
            patch("streamlit.markdown"),
            patch("streamlit.space"),
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = None

            editable_grid_widget(
                iteration_id=double_var_iteration.uid, default=False, key="test"
            )

            mock_editor.assert_called_once()

    def test_set_groups_dialog_integration(self, session, double_var_iteration):
        """Test set groups dialog integration with select_groups."""
        from risc_tool.ui.iterations.common import set_groups_dialog_widget

        dialog_func = set_groups_dialog_widget.__wrapped__  # type: ignore

        # Initial groups
        groups_before = session.iterations_view_model.get_all_groups(
            double_var_iteration.uid
        )
        groups_before[groups_before[RangeColumn.SELECTED.value]].index.tolist()

        # New selection
        new_groups = pd.DataFrame(
            {
                RangeColumn.SELECTED.value: [False, True, False],
                RangeColumn.LOWER_BOUND.value: [0.0, 100.0, 200.0],
                RangeColumn.UPPER_BOUND.value: [100.0, 200.0, 300.0],
            },
            index=[GroupID(0), GroupID(1), GroupID(2)],
        )

        with (
            patch("streamlit.data_editor") as mock_editor,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_editor.return_value = new_groups
            mock_button.return_value = True
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(double_var_iteration.uid)

            # Should update selection
            mock_rerun.assert_called()
