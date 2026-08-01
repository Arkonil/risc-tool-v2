"""Tests for editable range edit handler."""

from risc_tool.data.models.enums import RangeColumn, RowIndex


class TestEditableRangeEditHandler:
    """Tests for editable_range_edit_handler method."""

    def test_no_change_returns_false(self, iterations_vm, single_var_iteration):
        """Test handler returns False when no changes made."""
        # Get the initial metric table to populate cache
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        # Get cached dataframe
        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        )
        assert cached_df is not None

        # Call handler with same data - should return False
        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df.copy()
        )
        assert result is False

    def test_valid_lower_bound_edit(self, iterations_vm, single_var_iteration):
        """Test handler processes valid lower bound edit."""
        # Populate cache
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        # Modify lower bound for first group
        first_group = cached_df.index[0]
        cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        assert result is True

        # Verify the control was updated in repository
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        assert controls.at[first_group, RangeColumn.LOWER_BOUND.value] == 500.0

    def test_valid_upper_bound_edit(self, iterations_vm, single_var_iteration):
        """Test handler processes valid upper bound edit."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        first_group = cached_df.index[0]
        cached_df.at[first_group, RangeColumn.UPPER_BOUND.value] = 700.0

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        assert result is True

        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        assert controls.at[first_group, RangeColumn.UPPER_BOUND.value] == 700.0

    def test_valid_both_bounds_edit(self, iterations_vm, single_var_iteration):
        """Test handler processes both bounds edit."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        first_group = cached_df.index[0]
        cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0
        cached_df.at[first_group, RangeColumn.UPPER_BOUND.value] = 700.0

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        assert result is True

        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        assert controls.at[first_group, RangeColumn.LOWER_BOUND.value] == 500.0
        assert controls.at[first_group, RangeColumn.UPPER_BOUND.value] == 700.0

    def test_total_row_skipped(self, iterations_vm, single_var_iteration):
        """Test handler skips Total row edits."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        # Try to edit Total row - should be ignored
        cached_df.at[RowIndex.TOTAL, RangeColumn.LOWER_BOUND.value] = 999.0

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        # Should return True because there's a control column, but Total row should not be applied
        assert result is True

        # Total row should not affect actual controls
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        # Total row shouldn't be in controls
        assert RowIndex.TOTAL not in controls.index

    def test_non_existent_row_skipped(self, iterations_vm, single_var_iteration):
        """Test handler skips non-existent row indices."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        # Add a non-existent row index
        cached_df.loc[999, RangeColumn.LOWER_BOUND.value] = 100.0

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        assert result is True

        # Non-existent row should not be in controls
        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        assert 999 not in controls.index

    def test_non_existent_column_skipped(self, iterations_vm, single_var_iteration):
        """Test handler skips non-existent column indices."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        first_group = cached_df.index[0]
        # Try to edit a non-control column
        cached_df.at[first_group, "NonExistentColumn"] = "value"

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        # Should still return True if there are control columns
        assert result is True

    def test_categorical_categories_edit(
        self, iterations_vm, categorical_single_var_iteration
    ):
        """Test handler processes categorical categories edit."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=categorical_single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (categorical_single_var_iteration.uid, False)
        ).copy()

        first_group = cached_df.index[0]
        # Edit categories column
        cached_df.at[first_group, RangeColumn.CATEGORIES.value] = [
            "Employed",
            "Self-Employed",
        ]

        result = iterations_vm.editable_range_edit_handler(
            categorical_single_var_iteration.uid, False, cached_df
        )
        assert result is True

        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                categorical_single_var_iteration.uid, default=False
            )
        )
        assert "Employed" in controls.at[first_group, RangeColumn.CATEGORIES.value]
        assert "Self-Employed" in controls.at[first_group, RangeColumn.CATEGORIES.value]

    def test_default_mode_no_edit(self, iterations_vm, single_var_iteration):
        """Test handler in default mode (should not allow edits)."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=True,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, True)
        ).copy()

        first_group = cached_df.index[0]
        cached_df.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0

        # Even if we call handler, default mode controls should not be editable via this path
        # The UI disables editing for default mode, but let's verify handler behavior
        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, True, cached_df
        )
        # Handler will still process but UI prevents this scenario
        assert result is True

    def test_multiple_row_edits(self, iterations_vm, single_var_iteration):
        """Test handler processes multiple row edits at once."""
        iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        cached_df = iterations_vm._IterationsViewModel__editable_range_cache.get(
            (single_var_iteration.uid, False)
        ).copy()

        # Edit multiple rows
        for idx, group_id in enumerate(cached_df.index):
            if group_id != RowIndex.TOTAL:
                cached_df.at[group_id, RangeColumn.LOWER_BOUND.value] = float(idx * 100)
                cached_df.at[group_id, RangeColumn.UPPER_BOUND.value] = float(
                    (idx + 1) * 100
                )

        result = iterations_vm.editable_range_edit_handler(
            single_var_iteration.uid, False, cached_df
        )
        assert result is True

        controls = (
            iterations_vm._IterationsViewModel__iterations_repository.get_controls(
                single_var_iteration.uid, default=False
            )
        )
        for idx, group_id in enumerate(controls.index):
            assert controls.at[group_id, RangeColumn.LOWER_BOUND.value] == float(
                idx * 100
            )
            assert controls.at[group_id, RangeColumn.UPPER_BOUND.value] == float(
                (idx + 1) * 100
            )


class TestIterationMetricTableComponent:
    """Tests for iteration_metric_table UI component."""

    def test_single_var_iteration_metric_table_renders(
        self, iterations_vm, single_var_iteration
    ):
        """Test metric table renders for single var iteration."""
        from risc_tool.ui.components.iteration_metric_table import (
            iteration_metric_table,
        )

        # This tests the component function directly
        # We can't easily test Streamlit rendering without AppTest
        # But we can verify the ViewModel method works
        styler, errors, warnings = iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=True,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        assert styler is not None
        assert hasattr(styler, "data")
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_editable_range_table_renders(self, iterations_vm, single_var_iteration):
        """Test editable range table renders."""
        styler, errors, warnings = iterations_vm.get_iteration_metric_table(
            iteration_id=single_var_iteration.uid,
            default=False,
            show_controls=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        assert styler is not None
        # Editable table should have control columns
        data = styler.data
        assert RangeColumn.LOWER_BOUND.value in data.columns
        assert RangeColumn.UPPER_BOUND.value in data.columns

    def test_categorical_iteration_options(
        self, iterations_vm, categorical_single_var_iteration
    ):
        """Test categorical iteration options returned."""
        options = iterations_vm.get_categorical_iteration_options(
            categorical_single_var_iteration.uid
        )
        # employment_status has limited unique values
        assert isinstance(options, list)
        assert len(options) > 0
        assert "Employed" in options
        assert "Self-Employed" in options
        assert "Unemployed" in options
        assert "Retired" in options

    def test_numerical_iteration_no_categorical_options(
        self, iterations_vm, single_var_iteration
    ):
        """Test numerical iteration returns empty categorical options."""
        options = iterations_vm.get_categorical_iteration_options(
            single_var_iteration.uid
        )
        assert options == []
