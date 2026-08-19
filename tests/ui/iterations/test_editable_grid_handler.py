"""Tests for editable grid edit handler (double variable iterations)."""

from risc_tool.data.models.enums import RangeColumn, RSDetCol


class TestEditableGridEditHandler:
    """Tests for editable_grid_edit_handler method."""

    def test_no_change_returns_false(self, iterations_vm, double_var_iteration):
        """Test handler returns False when no changes made."""
        # Populate cache by getting editable grid
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        ))
        assert cached_df is not None

        # Call handler with same data
        result = iterations_vm.editable_grid_edit_handler(
            double_var_iteration.uid, False, cached_df.copy()
        )
        assert result is False

    def test_risk_segment_grid_edit(self, iterations_vm, double_var_iteration):
        """Test handler processes risk segment grid SelectboxColumn changes."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        )).copy()

        # Get parent segment columns (risk segment grid columns)
        parent_segments = list(
            iterations_vm._IterationsViewModel__iterations_repository.get_risk_segment_details(
                double_var_iteration.uid
            ).segments.keys()
        )
        parent_segment_names = [
            iterations_vm._IterationsViewModel__iterations_repository
            .get_risk_segment_details(double_var_iteration.uid)
            .segments[seg]
            .name
            for seg in parent_segments
        ]

        # Edit first group's mapping for first parent segment
        first_group = cached_df.index[0]
        if parent_segment_names:
            # Change the target segment
            current_value = cached_df.at[first_group, parent_segment_names[0]]
            # Find a different segment
            target_segments = [s for s in parent_segment_names if s != current_value]
            if target_segments:
                cached_df.at[first_group, parent_segment_names[0]] = target_segments[0]

                result = iterations_vm.editable_grid_edit_handler(
                    double_var_iteration.uid, False, cached_df
                )
                assert result is True

                # Verify grid was updated
                grid = iterations_vm._IterationsViewModel__iterations_repository.get_risk_segment_grid(
                    double_var_iteration.uid,
                    default=False,
                    details_column=RSDetCol.RISK_SEGMENT,
                )
                assert (
                    grid.at[first_group, parent_segment_names[0]] == target_segments[0]
                )

    def test_numerical_bounds_edit_in_grid(self, iterations_vm, double_var_iteration):
        """Test handler processes numerical bounds changes in grid view."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        )).copy()

        # Edit lower bound for first group
        first_group = cached_df.index[0]
        if RangeColumn.LOWER_BOUND.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 50000.0

            result = iterations_vm.editable_grid_edit_handler(
                double_var_iteration.uid, False, cached_df
            )
            assert result is True

            # Verify controls updated
            controls = (
                iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                    double_var_iteration.uid, default=False
                )
            )
            assert controls.at[first_group, RangeColumn.LOWER_BOUND.value] == 50000.0

    def test_upper_bound_edit_in_grid(self, iterations_vm, double_var_iteration):
        """Test handler processes upper bound changes in grid view."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        )).copy()

        first_group = cached_df.index[0]
        if RangeColumn.UPPER_BOUND.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.UPPER_BOUND.value] = 80000.0

            result = iterations_vm.editable_grid_edit_handler(
                double_var_iteration.uid, False, cached_df
            )
            assert result is True

            controls = (
                iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                    double_var_iteration.uid, default=False
                )
            )
            assert controls.at[first_group, RangeColumn.UPPER_BOUND.value] == 80000.0

    def test_both_bounds_and_grid_edit(self, iterations_vm, double_var_iteration):
        """Test handler processes both bounds and risk segment grid changes."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        )).copy()

        first_group = cached_df.index[0]

        # Edit bounds
        if RangeColumn.LOWER_BOUND.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 50000.0
        if RangeColumn.UPPER_BOUND.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.UPPER_BOUND.value] = 80000.0

        # Edit risk segment grid
        parent_segments = list(
            iterations_vm._IterationsViewModel__iterations_repository.get_risk_segment_details(
                double_var_iteration.uid
            ).segments.keys()
        )
        parent_segment_names = [
            iterations_vm._IterationsViewModel__iterations_repository
            .get_risk_segment_details(double_var_iteration.uid)
            .segments[seg]
            .name
            for seg in parent_segments
        ]

        if parent_segment_names:
            current_value = cached_df.at[first_group, parent_segment_names[0]]
            target_segments = [s for s in parent_segment_names if s != current_value]
            if target_segments:
                cached_df.at[first_group, parent_segment_names[0]] = target_segments[0]

        result = iterations_vm.editable_grid_edit_handler(
            double_var_iteration.uid, False, cached_df
        )
        assert result is True

        # Verify both controls and grid updated
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                double_var_iteration.uid, default=False
            )
        )
        assert controls.at[first_group, RangeColumn.LOWER_BOUND.value] == 50000.0
        assert controls.at[first_group, RangeColumn.UPPER_BOUND.value] == 80000.0

        grid = iterations_vm._IterationsViewModel__iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )
        assert grid.at[first_group, parent_segment_names[0]] == target_segments[0]  # type: ignore

    def test_categorical_categories_edit_in_grid(self, iterations_vm):
        """Test handler processes categorical categories in grid for double var."""
        from risc_tool.data.models.enums import LossRateTypes, VariableType
        from risc_tool.data.models.object_id import RiskSegmentID

        # Create a categorical double var iteration
        root = iterations_vm.add_single_var_iteration(
            name="Root Cat",
            variable_name="employment_status",
            variable_dtype=VariableType.CATEGORICAL,
            selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        child = iterations_vm.add_double_var_iteration(
            name="Child Cat",
            previous_iteration_id=root.uid,
            variable_name="housing_status",
            variable_dtype=VariableType.CATEGORICAL,
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        iterations_vm.get_editable_grid(child.uid, default=False, editable=True)

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            child.uid,
            False,
        )).copy()

        first_group = cached_df.index[0]
        if RangeColumn.CATEGORIES.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.CATEGORIES.value] = ["Own", "Rent"]

            result = iterations_vm.editable_grid_edit_handler(
                child.uid, False, cached_df
            )
            assert result is True

            controls = (
                iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                    child.uid, default=False
                )
            )
            assert "Own" in controls.at[first_group, RangeColumn.CATEGORIES.value]
            assert "Rent" in controls.at[first_group, RangeColumn.CATEGORIES.value]

    def test_default_grid_no_edit(self, iterations_vm, double_var_iteration):
        """Test handler with default grid (should not allow edits via UI)."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=True, editable=False
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            True,
        )).copy()

        first_group = cached_df.index[0]
        if RangeColumn.LOWER_BOUND.value in cached_df.columns:
            cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 99999.0

        # Handler will process but UI disables editing for default
        result = iterations_vm.editable_grid_edit_handler(
            double_var_iteration.uid, True, cached_df
        )
        assert result is True

    def test_non_existent_group_skipped(self, iterations_vm, double_var_iteration):
        """Test handler skips non-existent group indices."""
        iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        cached_df = iterations_vm._IterationsViewModel__editable_grid_cache.get((
            double_var_iteration.uid,
            False,
        )).copy()

        # Add non-existent group
        cached_df.loc[999, RangeColumn.LOWER_BOUND.value] = 100.0

        result = iterations_vm.editable_grid_edit_handler(
            double_var_iteration.uid, False, cached_df
        )
        assert result is True

        # Non-existent group should not be in controls
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                double_var_iteration.uid, default=False
            )
        )
        assert 999 not in controls.index


class TestEditableGridWidget:
    """Tests for editable_grid_widget UI component."""

    def test_get_editable_grid_returns_components(
        self, iterations_vm, double_var_iteration
    ):
        """Test get_editable_grid returns all expected components."""
        components = iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=True
        )

        assert "styler" in components
        assert "lower_bound_pos" in components
        assert "upper_bound_pos" in components
        assert "categories_pos" in components
        assert "risk_segment_grid_col_pos" in components
        assert "grid_options" in components
        assert "show_prev_iter_details" in components

        # Should have numerical bounds positions
        assert components["lower_bound_pos"] is not None
        assert components["upper_bound_pos"] is not None
        assert components["categories_pos"] is None  # Numerical iteration

    def test_get_editable_grid_categorical(self, iterations_vm):
        """Test get_editable_grid for categorical double var iteration."""
        from risc_tool.data.models.enums import LossRateTypes, VariableType
        from risc_tool.data.models.object_id import RiskSegmentID

        root = iterations_vm.add_single_var_iteration(
            name="Root Cat",
            variable_name="employment_status",
            variable_dtype=VariableType.CATEGORICAL,
            selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        child = iterations_vm.add_double_var_iteration(
            name="Child Cat",
            previous_iteration_id=root.uid,
            variable_name="housing_status",
            variable_dtype=VariableType.CATEGORICAL,
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )

        components = iterations_vm.get_editable_grid(
            child.uid, default=False, editable=True
        )

        assert components["categories_pos"] is not None
        assert components["lower_bound_pos"] is None
        assert components["upper_bound_pos"] is None

    def test_show_prev_iter_details_flag(self, iterations_vm, double_var_iteration):
        """Test show_prev_iter_details flag is set correctly."""
        # Enable the metadata flag
        iterations_vm.set_metadata(
            double_var_iteration.uid, show_prev_iter_details=True
        )

        components = iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=False
        )

        # Depth is 2 (child of root), so should show prev iter details
        assert components["show_prev_iter_details"] is True

        # Disable and verify
        iterations_vm.set_metadata(
            double_var_iteration.uid, show_prev_iter_details=False
        )
        components = iterations_vm.get_editable_grid(
            double_var_iteration.uid, default=False, editable=False
        )
        assert components["show_prev_iter_details"] is False
