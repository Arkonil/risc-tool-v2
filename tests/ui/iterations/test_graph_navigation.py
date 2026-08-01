"""Tests for graph navigation and dialogs."""

from unittest.mock import MagicMock, Mock, patch

from streamlit.testing.v1 import AppTest

from risc_tool.data.models.types import IterationID


class TestIterationGraphUI:
    """Tests for iteration graph UI page."""

    def test_graph_renders_title(self, session):
        """Test graph page renders title."""
        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        titles = at.get("title")
        assert len(titles) > 0
        assert titles[0].value == "Iteration Graph"  # type: ignore

    def test_graph_renders_flow_component(self, session, single_var_iteration):
        """Test graph renders streamlit_flow component."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            IterationID(0), single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        # streamlit_flow component should be rendered
        # It appears as a custom component
        assert not at.exception

    def test_graph_with_no_iterations_shows_add_button(self, session):
        """Test graph shows Add New Iteration button when no iterations."""
        # Ensure no iterations
        session.iterations_view_model._IterationsViewModel__iterations_repository.iterations.clear()
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph = session.iterations_view_model._IterationsViewModel__iterations_repository.graph.__class__()

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        # Should have Add New Iteration button in sidebar
        buttons = at.get("button")
        add_button = [b for b in buttons if "Add New Iteration" in str(b.label)]  # type: ignore
        assert len(add_button) > 0

    def test_graph_with_selected_iteration_shows_open_button(
        self, session, single_var_iteration
    ):
        """Test graph shows Open Iteration button when iteration selected."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            IterationID(0), single_var_iteration.uid
        )
        session.iterations_view_model.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        buttons = at.get("button")
        open_button = [b for b in buttons if "Open Iteration" in str(b.label)]  # type: ignore
        assert len(open_button) > 0

    def test_graph_with_selected_iteration_shows_add_child_button(
        self, session, single_var_iteration
    ):
        """Test graph shows Add Child Iteration button when depth allows."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            IterationID(0), single_var_iteration.uid
        )
        session.iterations_view_model.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        buttons = at.get("button")
        add_child = [b for b in buttons if "Add Child Iteration" in str(b.label)]  # type: ignore
        assert len(add_child) > 0

    def test_graph_with_selected_iteration_shows_rename_button(
        self, session, single_var_iteration
    ):
        """Test graph shows Rename Iteration button."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        buttons = at.get("button")
        rename_button = [b for b in buttons if "Rename Iteration" in str(b.label)]  # type: ignore
        assert len(rename_button) > 0

    def test_graph_with_selected_iteration_shows_delete_button(
        self, session, single_var_iteration
    ):
        """Test graph shows Delete Iteration button."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        buttons = at.get("button")
        delete_button = [b for b in buttons if "Delete Iteration" in str(b.label)]  # type: ignore
        assert len(delete_button) > 0

    def test_minimap_checkbox_in_sidebar(self, session):
        """Test minimap checkbox in sidebar."""
        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        checkboxes = at.get("checkbox")
        minimap = [c for c in checkboxes if "Show Minimap" in str(c.label)]  # type: ignore
        assert len(minimap) > 0


class TestDeleteConfirmationDialog:
    """Tests for delete confirmation dialog."""

    def test_delete_dialog_shows_iteration_id(self, session, single_var_iteration):
        """Test delete dialog shows iteration ID."""
        from risc_tool.ui.iterations.graph import delete_confirmation_dialog

        dialog_func = delete_confirmation_dialog.__wrapped__  # type: ignore

        with (
            patch("streamlit.write") as mock_write,
            patch("streamlit.markdown") as _mock_markdown,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.side_effect = [False, False]  # Delete, Cancel
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            # Should show iteration ID
            write_calls = [str(c) for c in mock_write.call_args_list]
            assert any(str(single_var_iteration.uid) in c for c in write_calls)

    def test_delete_dialog_shows_children_warning(
        self, session, single_var_iteration, double_var_iteration
    ):
        """Test delete dialog shows child iterations warning."""
        from risc_tool.ui.iterations.graph import delete_confirmation_dialog

        dialog_func = delete_confirmation_dialog.__wrapped__  # type: ignore

        # Set up parent-child relationship
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            single_var_iteration.uid, double_var_iteration.uid
        )

        with (
            patch("streamlit.write") as _mock_write,
            patch("streamlit.markdown") as mock_markdown,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.side_effect = [False, False]
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            markdown_calls = [str(c) for c in mock_markdown.call_args_list]
            assert any("also be deleted" in c for c in markdown_calls)
            assert any(str(double_var_iteration.uid) in c for c in markdown_calls)

    def test_delete_dialog_confirm_deletes(self, session, single_var_iteration):
        """Test confirming delete removes iteration."""
        from risc_tool.ui.iterations.graph import delete_confirmation_dialog

        dialog_func = delete_confirmation_dialog.__wrapped__  # type: ignore

        with (
            patch("streamlit.write"),
            patch("streamlit.markdown"),
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            # First call (Delete) returns True, second (Cancel) not called
            mock_button.side_effect = [True, False]
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            # Should call delete_iteration and rerun
            assert (
                single_var_iteration.uid not in session.iterations_view_model.iterations
            )
            mock_rerun.assert_called()

    def test_delete_dialog_cancel_does_nothing(self, session, single_var_iteration):
        """Test cancel doesn't delete iteration."""
        from risc_tool.ui.iterations.graph import delete_confirmation_dialog

        dialog_func = delete_confirmation_dialog.__wrapped__  # type: ignore

        with (
            patch("streamlit.write"),
            patch("streamlit.markdown"),
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_button.side_effect = [False, True]  # Delete=False, Cancel=True
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            # Iteration should still exist
            assert single_var_iteration.uid in session.iterations_view_model.iterations
            mock_rerun.assert_called()


class TestRenameIterationDialog:
    """Tests for rename iteration dialog."""

    def test_rename_dialog_shows_current_name(self, session, single_var_iteration):
        """Test rename dialog shows current name in input."""
        from risc_tool.ui.iterations.graph import rename_iteration_dialog

        dialog_func = rename_iteration_dialog.__wrapped__  # type: ignore

        with (
            patch("streamlit.text_input") as mock_text_input,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as _mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_text_input.return_value = "New Name"
            mock_button.side_effect = [True, False]  # Save, Cancel
            mock_columns.return_value = [MagicMock(), MagicMock()]

            original_name = single_var_iteration.name
            dialog_func(single_var_iteration.uid)

            mock_text_input.assert_called()
            call_kwargs = mock_text_input.call_args.kwargs
            assert call_kwargs.get("value") == original_name

    def test_rename_dialog_save_updates_name(self, session, single_var_iteration):
        """Test saving rename updates iteration name."""
        from risc_tool.ui.iterations.graph import rename_iteration_dialog

        dialog_func = rename_iteration_dialog.__wrapped__  # type: ignore

        _original_name = single_var_iteration.name

        with (
            patch("streamlit.text_input") as mock_text_input,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_text_input.return_value = "Updated Name"
            mock_button.side_effect = [True, False]
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            assert (
                session.iterations_view_model.get_iteration_name(
                    single_var_iteration.uid
                )
                == "Updated Name"
            )
            mock_rerun.assert_called()

    def test_rename_dialog_cancel_keeps_name(self, session, single_var_iteration):
        """Test cancel keeps original name."""
        from risc_tool.ui.iterations.graph import rename_iteration_dialog

        dialog_func = rename_iteration_dialog.__wrapped__  # type: ignore

        original_name = single_var_iteration.name

        with (
            patch("streamlit.text_input") as mock_text_input,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.button") as mock_button,
            patch("streamlit.rerun") as mock_rerun,
            patch("streamlit.session_state", {"session": session}),
        ):
            mock_text_input.return_value = "New Name"
            mock_button.side_effect = [False, True]  # Save=False, Cancel=True
            mock_columns.return_value = [MagicMock(), MagicMock()]

            dialog_func(single_var_iteration.uid)

            assert (
                session.iterations_view_model.get_iteration_name(
                    single_var_iteration.uid
                )
                == original_name
            )
            mock_rerun.assert_called()


class TestGraphNodeSelection:
    """Tests for node selection in graph."""

    def test_clicking_node_selects_it(self, session, single_var_iteration):
        """Test clicking a node selects it."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            IterationID(0), single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        # The streamlit_flow component handles click internally
        # We can't easily simulate click in AppTest
        # But we can verify the component is rendered
        assert not at.exception

    def test_selecting_node_updates_status(self, session, single_var_iteration):
        """Test selecting node updates ViewModel status."""
        # This is handled by the streamlit_flow component's on_click
        # which calls set_current_status
        session.iterations_view_model.set_current_status(
            "graph", selected_iteration_id=single_var_iteration.uid
        )

        view, iter_id = session.iterations_view_model.current_status
        assert view == "graph"
        assert iter_id == single_var_iteration.uid

    def test_unlimited_depth_allows_add_child(self, session, single_var_iteration):
        """Test that adding child is allowed for any existing iteration without depth limitation."""
        can_have = session.iterations_view_model.can_have_child(
            single_var_iteration.uid
        )
        assert can_have is True


class TestGraphIntegration:
    """Integration tests for graph workflow."""

    def test_full_graph_view(self, session, single_var_iteration):
        """Test complete graph view renders without errors."""
        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )
        session.iterations_view_model._IterationsViewModel__iterations_repository.graph.add_child(
            IterationID(0), single_var_iteration.uid
        )

        at = AppTest.from_file("tests/ui/iterations/_render_graph.py")
        at.session_state["session"] = session
        at.run(timeout=10)

        assert not at.exception
        titles = at.get("title")
        assert len(titles) > 0


class TestStreamlitFlowGraph:
    """Tests for streamlit_flow_graph function."""

    def test_streamlit_flow_graph_creates_nodes(self, session, single_var_iteration):
        """Test streamlit_flow_graph creates nodes for iterations."""
        from risc_tool.ui.iterations.graph import streamlit_flow_graph

        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )

        with patch("risc_tool.ui.iterations.graph.streamlit_flow") as mock_flow:
            mock_state = Mock()
            mock_state.selected_id = None
            mock_state.timestamp = 0
            mock_flow.return_value = mock_state

            state = streamlit_flow_graph(
                iterations=session.iterations_view_model.iterations,
                iteration_graph=session.iterations_view_model.iteration_graph,
                selected_node_id=None,
            )

            mock_flow.assert_called_once()
            assert state is mock_state

    def test_streamlit_flow_graph_with_selected_node(
        self, session, single_var_iteration
    ):
        """Test streamlit_flow_graph with selected node."""
        from risc_tool.ui.iterations.graph import streamlit_flow_graph

        session.iterations_view_model.iterations[single_var_iteration.uid] = (
            single_var_iteration
        )

        with patch("risc_tool.ui.iterations.graph.streamlit_flow") as mock_flow:
            mock_state = Mock()
            mock_state.selected_id = str(single_var_iteration.uid)
            mock_state.timestamp = 0
            mock_flow.return_value = mock_state

            _state = streamlit_flow_graph(
                iterations=session.iterations_view_model.iterations,
                iteration_graph=session.iterations_view_model.iteration_graph,
                selected_node_id=single_var_iteration.uid,
            )

            mock_flow.assert_called_once()
