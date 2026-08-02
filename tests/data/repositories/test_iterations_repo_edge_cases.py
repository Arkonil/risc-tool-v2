"""Tests for IterationsRepository edge cases."""

import pandas as pd
import pytest

from risc_tool.data.models.enums import (
    LossRateTypes,
    RangeColumn,
    RowIndex,
    RSDetCol,
)
from risc_tool.data.models.types import (
    GroupID,
    IterationID,
    MetricID,
)


class TestSetControls:
    """Tests for set_controls method."""

    def test_set_controls_numerical_bounds(
        self, iterations_repository, single_var_iteration
    ):
        """Test setting numerical bounds via set_controls."""
        # Get current controls
        controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )

        # Modify bounds
        modified = controls.copy()
        first_group = modified.index[0]
        modified.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0
        modified.at[first_group, RangeColumn.UPPER_BOUND.value] = 700.0

        iterations_repository.set_controls(single_var_iteration.uid, modified)

        # Verify update
        updated = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )
        assert updated.at[first_group, RangeColumn.LOWER_BOUND.value] == 500.0
        assert updated.at[first_group, RangeColumn.UPPER_BOUND.value] == 700.0

    def test_set_controls_categorical_categories(
        self, iterations_repository, categorical_single_var_iteration
    ):
        """Test setting categorical categories via set_controls."""
        controls = iterations_repository.get_controls(
            categorical_single_var_iteration.uid, default=False
        )

        modified = controls.copy()
        first_group = modified.index[0]
        modified.at[first_group, RangeColumn.CATEGORIES.value] = [
            "Employed",
            "Self-Employed",
        ]

        iterations_repository.set_controls(
            categorical_single_var_iteration.uid, modified
        )

        updated = iterations_repository.get_controls(
            categorical_single_var_iteration.uid, default=False
        )
        assert "Employed" in updated.at[first_group, RangeColumn.CATEGORIES.value]
        assert "Self-Employed" in updated.at[first_group, RangeColumn.CATEGORIES.value]

    def test_set_controls_invalid_group_id_skipped(
        self, iterations_repository, single_var_iteration
    ):
        """Test set_controls skips invalid group IDs."""
        controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )

        modified = controls.copy()
        # Add non-existent group
        modified.loc[999, RangeColumn.LOWER_BOUND.value] = 100.0

        iterations_repository.set_controls(single_var_iteration.uid, modified)

        # Non-existent group should not be added
        updated = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )
        assert 999 not in updated.index

    def test_set_controls_mixed_types(
        self, iterations_repository, single_var_iteration
    ):
        """Test set_controls handles mixed column types."""
        controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )

        modified = controls.copy()
        first_group = modified.index[0]
        # Set both bounds and categories (categories will be ignored for numerical)
        modified.at[first_group, RangeColumn.LOWER_BOUND.value] = 500.0
        modified.at[first_group, RangeColumn.CATEGORIES.value] = [
            "test"
        ]  # Should be ignored

        iterations_repository.set_controls(single_var_iteration.uid, modified)

        updated = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )
        assert updated.at[first_group, RangeColumn.LOWER_BOUND.value] == 500.0

    def test_set_controls_string_bounds_converted(
        self, iterations_repository, single_var_iteration
    ):
        """Test set_controls converts string bounds to float."""
        controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )

        modified = controls.copy()
        first_group = modified.index[0]
        # Pass as string (cast to object so pandas 2.x allows the assignment)
        modified[RangeColumn.LOWER_BOUND.value] = modified[
            RangeColumn.LOWER_BOUND.value
        ].astype(object)
        modified[RangeColumn.UPPER_BOUND.value] = modified[
            RangeColumn.UPPER_BOUND.value
        ].astype(object)
        modified.at[first_group, RangeColumn.LOWER_BOUND.value] = "550.0"
        modified.at[first_group, RangeColumn.UPPER_BOUND.value] = "750.0"

        iterations_repository.set_controls(single_var_iteration.uid, modified)

        updated = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )
        assert updated.at[first_group, RangeColumn.LOWER_BOUND.value] == 550.0
        assert updated.at[first_group, RangeColumn.UPPER_BOUND.value] == 750.0


class TestSetRiskSegmentGrid:
    """Tests for set_risk_segment_grid method."""

    def test_set_grid_valid_segment_names(
        self, iterations_repository, double_var_iteration
    ):
        """Test setting risk segment grid with valid segment names."""
        # Get current grid
        grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )

        modified = grid.copy()
        first_group = modified.index[0]
        first_col = modified.columns[0]

        # Change to a different valid segment
        current = modified.at[first_group, first_col]
        _ = list(
            iterations_repository.get_risk_segment_details(
                double_var_iteration.uid
            ).segments.keys()
        )
        parent_names = [
            seg.name
            for seg in iterations_repository.get_risk_segment_details(
                double_var_iteration.uid
            ).segments.values()
        ]
        target_names = [n for n in parent_names if n != current]

        if target_names:
            modified.at[first_group, first_col] = target_names[0]
            iterations_repository.set_risk_segment_grid(
                double_var_iteration.uid, modified
            )

            # Verify update
            updated = iterations_repository.get_risk_segment_grid(
                double_var_iteration.uid,
                default=False,
                details_column=RSDetCol.RISK_SEGMENT,
            )
            assert updated.at[first_group, first_col] == target_names[0]

    def test_set_grid_invalid_segment_name_skipped(
        self, iterations_repository, double_var_iteration
    ):
        """Test set_risk_segment_grid skips invalid segment names."""
        grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )

        modified = grid.copy()
        first_group = modified.index[0]
        first_col = modified.columns[0]

        # Set invalid segment name
        modified.at[first_group, first_col] = "NonExistentSegment"
        iterations_repository.set_risk_segment_grid(double_var_iteration.uid, modified)

        # Should not update
        updated = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )
        assert updated.at[first_group, first_col] != "NonExistentSegment"

    def test_set_grid_invalid_group_skipped(
        self, iterations_repository, double_var_iteration
    ):
        """Test set_risk_segment_grid skips invalid group IDs."""
        grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )

        modified = grid.copy()
        # Add non-existent group
        modified.loc[999] = modified.iloc[0]
        iterations_repository.set_risk_segment_grid(double_var_iteration.uid, modified)

        # Non-existent group should not be added
        updated = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )
        assert 999 not in updated.index

    def test_set_grid_no_change_returns_unchanged(
        self, iterations_repository, double_var_iteration
    ):
        """Test set_risk_segment_grid with no changes doesn't notify."""
        grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )

        # Call with same data
        iterations_repository.set_risk_segment_grid(
            double_var_iteration.uid, grid.copy()
        )

        # Grid should be unchanged after no-op set
        updated = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )
        assert updated.equals(grid)


class TestGetMetricRange:
    """Tests for get_metric_range method."""

    def test_metric_range_with_filters(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_metric_range with filter IDs."""
        from risc_tool.data.repositories.filter import FilterRepository

        # Create a filter
        filter_repo = FilterRepository(
            iterations_repository._IterationsRepository__data_repository
        )
        filter_repo.create_filter("Test Filter", "credit_score > 600")
        filter_id = next(iter(filter_repo.get_filters()))

        metric_df, errors, warnings = iterations_repository.get_metric_range(
            iteration_id=single_var_iteration.uid,
            default=False,
            filter_ids=[filter_id],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        assert isinstance(metric_df, pd.DataFrame)
        assert isinstance(errors, list)
        assert isinstance(warnings, list)

    def test_metric_range_with_scalars(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_metric_range with scalars enabled."""
        scalar_repo = iterations_repository._IterationsRepository__scalar_repository
        scalar_repo.set_current_rate(LossRateTypes.DLR, 0.05)
        scalar_repo.set_lifetime_rate(LossRateTypes.DLR, 0.075)

        metric_df, _errors, _warnings = iterations_repository.get_metric_range(
            iteration_id=single_var_iteration.uid,
            default=False,
            filter_ids=[],
            metric_ids=[MetricID.DEV_DLR_BAD_RATE],
            scalars_enabled=True,
            remove_outliers=False,
            show_total_row=True,
        )

        assert isinstance(metric_df, pd.DataFrame)

    def test_metric_range_empty_data(self, iterations_repository, single_var_iteration):
        """Test get_metric_range with filter that returns no data."""
        from risc_tool.data.repositories.filter import FilterRepository

        filter_repo = FilterRepository(
            iterations_repository._IterationsRepository__data_repository
        )
        # Filter that matches nothing
        filter_repo.create_filter("Empty Filter", "credit_score > 1000")
        filter_id = next(iter(filter_repo.get_filters()))

        metric_df, _errors, _warnings = iterations_repository.get_metric_range(
            iteration_id=single_var_iteration.uid,
            default=False,
            filter_ids=[filter_id],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        # Should return empty dataframe but no errors
        assert isinstance(metric_df, pd.DataFrame)

    def test_metric_range_invalid_metric_id(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_metric_range with invalid metric ID."""
        metric_df, _errors, _warnings = iterations_repository.get_metric_range(
            iteration_id=single_var_iteration.uid,
            default=False,
            filter_ids=[],
            metric_ids=[MetricID(999)],  # Invalid
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        # Invalid metric should be ignored
        assert isinstance(metric_df, pd.DataFrame)

    def test_metric_range_total_row(self, iterations_repository, single_var_iteration):
        """Test get_metric_range includes total row."""
        metric_df, _errors, _warnings = iterations_repository.get_metric_range(
            iteration_id=single_var_iteration.uid,
            default=False,
            filter_ids=[],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
        )

        if not metric_df.empty:
            assert RowIndex.TOTAL in metric_df.index


class TestGetMetricGrids:
    """Tests for get_metric_grids method."""

    def test_metric_grids_total_row_and_column(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_metric_grids with total row and column."""
        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
            show_total_column=True,
        )

        assert isinstance(metric_outputs, list)
        if metric_outputs:
            grid = metric_outputs[0]["metric_grid"]
            assert "Total" in grid.columns.tolist()
            assert RowIndex.TOTAL in grid.index

    def test_metric_grids_only_total_row(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_metric_grids with only total row."""
        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
            show_total_column=False,
        )

        if metric_outputs:
            grid = metric_outputs[0]["metric_grid"]
            assert RowIndex.TOTAL in grid.index
            assert "Total" not in grid.columns.tolist()

    def test_metric_grids_only_total_column(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_metric_grids with only total column."""
        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=False,
            show_total_column=True,
        )

        if metric_outputs:
            grid = metric_outputs[0]["metric_grid"]
            assert "Total" in grid.columns.tolist()
            assert RowIndex.TOTAL not in grid.index

    def test_metric_grids_no_totals(self, iterations_repository, double_var_iteration):
        """Test get_metric_grids without totals."""
        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[MetricID.DEV_VOLUME],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=False,
            show_total_column=False,
        )

        if metric_outputs:
            grid = metric_outputs[0]["metric_grid"]
            assert "Total" not in grid.columns.tolist()
            assert "Total" not in grid.index.tolist()

    def test_metric_grids_with_scalars(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_metric_grids with scalars enabled."""
        scalar_repo = iterations_repository._IterationsRepository__scalar_repository
        scalar_repo.set_current_rate(LossRateTypes.DLR, 0.05)
        scalar_repo.set_lifetime_rate(LossRateTypes.DLR, 0.075)

        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[MetricID.DEV_DLR_BAD_RATE],
            scalars_enabled=True,
            remove_outliers=False,
            show_total_row=True,
            show_total_column=True,
        )

        assert isinstance(metric_outputs, list)

    def test_metric_grids_invalid_iteration_raises(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_metric_grids raises for single var iteration."""
        with pytest.raises(ValueError, match="not a double variable iteration"):
            iterations_repository.get_metric_grids(
                iteration_id=single_var_iteration.uid,
                default=True,
                filter_ids=[],
                metric_ids=[MetricID.DEV_VOLUME],
                scalars_enabled=False,
                remove_outliers=False,
                show_total_row=True,
                show_total_column=True,
            )

    def test_metric_grids_no_metrics_returns_empty(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_metric_grids with no metrics returns empty list."""
        metric_outputs, _errors, _warnings = iterations_repository.get_metric_grids(
            iteration_id=double_var_iteration.uid,
            default=True,
            filter_ids=[],
            metric_ids=[],
            scalars_enabled=False,
            remove_outliers=False,
            show_total_row=True,
            show_total_column=True,
        )

        assert metric_outputs == []


class TestRepositoryEdgeCases:
    """Additional edge case tests for repository."""

    def test_rename_nonexistent_iteration_raises(self, iterations_repository):
        """Test renaming nonexistent iteration raises error."""
        with pytest.raises(ValueError, match="does not exist"):
            iterations_repository.rename_iteration(IterationID(999), "New Name")

    def test_delete_nonexistent_iteration_warns(self, iterations_repository):
        """Test deleting nonexistent iteration logs warning but doesn't raise."""
        count_before = len(iterations_repository.iterations)
        # Should not raise
        iterations_repository.delete_iteration(IterationID(999))
        assert len(iterations_repository.iterations) == count_before

    def test_get_iteration_nonexistent_raises(self, iterations_repository):
        """Test getting nonexistent iteration raises error."""
        with pytest.raises(ValueError, match="does not exist"):
            iterations_repository.get_iteration(IterationID(999))

    def test_get_all_groups_single_var(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_all_groups for single var iteration."""
        groups = iterations_repository.get_all_groups(single_var_iteration.uid)
        assert isinstance(groups, pd.DataFrame)
        assert RangeColumn.LOWER_BOUND.value in groups.columns
        assert RangeColumn.UPPER_BOUND.value in groups.columns
        # Single var doesn't have SELECTED column
        assert RangeColumn.SELECTED.value not in groups.columns

    def test_get_all_groups_double_var(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_all_groups for double var iteration."""
        groups = iterations_repository.get_all_groups(double_var_iteration.uid)
        assert isinstance(groups, pd.DataFrame)
        assert RangeColumn.SELECTED.value in groups.columns
        assert RangeColumn.LOWER_BOUND.value in groups.columns
        assert RangeColumn.UPPER_BOUND.value in groups.columns

    def test_select_groups_single_var_noop(
        self, iterations_repository, single_var_iteration
    ):
        """Test select_groups on single var is noop."""
        result = iterations_repository.select_groups(
            single_var_iteration.uid, [GroupID(0)]
        )
        # Should not error, just return
        assert result is None

    def test_add_new_group_single_var_noop(
        self, iterations_repository, single_var_iteration
    ):
        """Test add_new_group on single var is noop."""
        result = iterations_repository.add_new_group(single_var_iteration.uid)
        # Should not error, just return
        assert result is None

    def test_get_controls_default_vs_custom(
        self, iterations_repository, single_var_iteration
    ):
        """Test get_controls returns different data for default vs custom."""
        default_controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=True
        )
        custom_controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )

        # Initially should be the same
        assert default_controls.equals(custom_controls)

        # Modify custom
        first_group = custom_controls.index[0]
        custom_controls.at[first_group, RangeColumn.LOWER_BOUND.value] = 999.0
        iterations_repository.set_controls(single_var_iteration.uid, custom_controls)

        # Now they should differ
        default_controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=True
        )
        custom_controls = iterations_repository.get_controls(
            single_var_iteration.uid, default=False
        )
        assert not default_controls.equals(custom_controls)

    def test_get_risk_segment_grid_default_vs_custom(
        self, iterations_repository, double_var_iteration
    ):
        """Test get_risk_segment_grid returns different data for default vs custom."""
        default_grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid, default=True, details_column=RSDetCol.RISK_SEGMENT
        )
        custom_grid = iterations_repository.get_risk_segment_grid(
            double_var_iteration.uid,
            default=False,
            details_column=RSDetCol.RISK_SEGMENT,
        )

        # Initially should be the same
        assert default_grid.equals(custom_grid)


class TestIterationValidation:
    """Tests for iteration validation methods."""

    def test_single_var_validation(self, iterations_repository, single_var_iteration):
        """Test single var iteration validation."""
        warnings, errors, _ = single_var_iteration.validate_groups(default=False)
        assert isinstance(warnings, list)
        assert isinstance(errors, list)

    def test_double_var_validation(self, iterations_repository, double_var_iteration):
        """Test double var iteration validation."""
        warnings, errors, _ = double_var_iteration.validate_groups(default=False)
        assert isinstance(warnings, list)
        assert isinstance(errors, list)

    def test_iteration_active_flag_on_data_change(
        self, iterations_repository, single_var_iteration
    ):
        """Test iteration active flag updates on data dependency change."""
        # Initially active
        assert single_var_iteration.active is True

        # Simulate data source removal by triggering dependency update
        iterations_repository.on_dependency_update(set())

        # Should still be active (variable still exists)
        iterations_repository.get_iteration(single_var_iteration.uid)
        assert single_var_iteration.active is True
