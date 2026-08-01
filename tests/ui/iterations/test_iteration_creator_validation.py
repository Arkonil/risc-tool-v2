"""Tests for iteration creator validation logic."""

from unittest.mock import MagicMock, patch

from risc_tool.data.models.enums import LossRateTypes, VariableType
from risc_tool.data.models.types import RiskSegmentID
from risc_tool.ui.iterations.iteration_creator import (
    variable_selector,
    iteration_name_input,
    variable_type_selector,
    loss_rate_type_selector,
    filter_selector,
    risk_segment_details_selector,
    upgrade_downgrade_selector,
)


class TestValidateIterCreateParams:
    """Tests for validate_iter_create_params method."""

    def test_no_data_loaded_error(self, iterations_vm):
        """Test error when data sources are not loaded."""
        # Create a fresh VM without data
        from risc_tool.data.repositories.data import DataRepository
        from risc_tool.data.repositories.filter import FilterRepository
        from risc_tool.data.repositories.iterations import IterationsRepository
        from risc_tool.data.repositories.metric import MetricRepository
        from risc_tool.data.repositories.options import OptionRepository
        from risc_tool.data.repositories.scalar import ScalarRepository
        from risc_tool.ui.iterations.iterations_vm import IterationsViewModel
        
        empty_data_repo = DataRepository()
        empty_filter_repo = FilterRepository(empty_data_repo)
        empty_metric_repo = MetricRepository(empty_data_repo)
        empty_option_repo = OptionRepository()
        empty_scalar_repo = ScalarRepository()
        empty_iter_repo = IterationsRepository(
            empty_data_repo, empty_filter_repo, empty_metric_repo, 
            empty_option_repo, empty_scalar_repo
        )
        
        vm = IterationsViewModel(
            empty_data_repo, empty_iter_repo, empty_option_repo,
            empty_filter_repo, empty_metric_repo, empty_scalar_repo
        )
        
        errors = vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert "Data sources are not loaded." in errors

    def test_variable_not_in_schema_error(self, iterations_vm):
        """Test error when variable doesn't exist in schema."""
        errors = iterations_vm.validate_iter_create_params(
            variable_name="nonexistent_variable",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert any("does not exist in the data schema" in e for e in errors)

    def test_numerical_type_on_string_variable_error(self, iterations_vm):
        """Test error when numerical type selected for string/categorical variable."""
        # employment_status is categorical in the data
        errors = iterations_vm.validate_iter_create_params(
            variable_name="employment_status",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert any("cannot be treated as a numerical variable" in e for e in errors)

    def test_categorical_unique_exceeds_max(self, iterations_vm):
        """Test error when categorical variable has too many unique values."""
        # Temporarily lower the max to trigger error
        options_repo = iterations_vm._IterationsViewModel__options_repository
        original_max = options_repo.max_categorical_unique
        options_repo._OptionRepository__options_config.max_categorical_unique = 2
        
        try:
            errors = iterations_vm.validate_iter_create_params(
                variable_name="employment_status",
                variable_dtype=VariableType.CATEGORICAL,
                auto_band=True,
                loss_rate_type=LossRateTypes.DLR,
                use_scalars=True,
            )
            assert any("exceeds the maximum allowed for categorical variables" in e for e in errors)
        finally:
            options_repo._OptionRepository__options_config.max_categorical_unique = original_max

    def test_auto_band_dlr_without_metric_variables(self, iterations_vm):
        """Test error when auto-banding DLR but metric variables not selected."""
        # Don't set the metric variables
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = None
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = None
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert any("Required metric variables for DLR are not selected" in e for e in errors)

    def test_auto_band_ulr_without_metric_variables(self, iterations_vm):
        """Test error when auto-banding ULR but metric variables not selected."""
        iterations_vm._IterationsViewModel__metric_repository.var_dev_unt_bad = None
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.ULR,
            use_scalars=False,
        )
        assert any("Required metric variables for ULR are not selected" in e for e in errors)

    def test_auto_band_with_scalars_dlr_no_scalar_set(self, iterations_vm):
        """Test error when using scalars for DLR but no scalar configured."""
        # Reset metric variables
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = "credit_default_flag"
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = "average_balance"
        # Don't set scalar
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert any("Scalars for" in e and "$ Bad" in e for e in errors)

    def test_auto_band_with_scalars_ulr_no_scalar_set(self, iterations_vm):
        """Test error when using scalars for ULR but no scalar configured."""
        iterations_vm._IterationsViewModel__metric_repository.var_dev_unt_bad = "credit_default_flag"
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.ULR,
            use_scalars=True,
        )
        assert any("Scalars for" in e and "# Bad" in e for e in errors)

    def test_valid_single_var_params(self, iterations_vm):
        """Test valid parameters for single variable iteration."""
        # Set up required metric variables
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = "credit_default_flag"
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = "average_balance"
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert errors == []

    def test_valid_single_var_params_with_scalars(self, iterations_vm):
        """Test valid parameters with scalars configured."""
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = "credit_default_flag"
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = "average_balance"
        
        # Set scalar
        iterations_vm._IterationsViewModel__scalar_repository.set_current_rate(
            LossRateTypes.DLR, 0.04
        )
        iterations_vm._IterationsViewModel__scalar_repository.set_lifetime_rate(
            LossRateTypes.DLR, 0.06
        )
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=True,
        )
        assert errors == []

    def test_valid_categorical_params(self, iterations_vm):
        """Test valid parameters for categorical variable."""
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = "credit_default_flag"
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = "average_balance"
        
        errors = iterations_vm.validate_iter_create_params(
            variable_name="employment_status",
            variable_dtype=VariableType.CATEGORICAL,
            auto_band=True,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert errors == []

    def test_valid_no_auto_band(self, iterations_vm):
        """Test valid parameters without auto-banding."""
        errors = iterations_vm.validate_iter_create_params(
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            loss_rate_type=LossRateTypes.DLR,
            use_scalars=False,
        )
        assert errors == []


class TestIterationCreatorUIComponents:
    """Tests for iteration creator UI component functions."""

    def test_variable_selector_returns_selected(self, session):
        """Test variable selector returns selected variable."""
        with patch('streamlit.selectbox') as mock_selectbox, \
             patch('streamlit.markdown') as mock_markdown, \
             patch('streamlit.session_state', {'session': session}):
            mock_selectbox.return_value = "credit_score"
            result = variable_selector()
            assert result == "credit_score"
            mock_selectbox.assert_called_once()

    def test_iteration_name_input_returns_input(self, session):
        """Test iteration name input returns entered name."""
        with patch('streamlit.text_input') as mock_text_input:
            mock_text_input.return_value = "My Iteration"
            result = iteration_name_input()
            assert result == "My Iteration"

    def test_variable_type_selector_returns_type(self, session):
        """Test variable type selector returns selected type."""
        with patch('streamlit.selectbox') as mock_selectbox:
            mock_selectbox.return_value = VariableType.NUMERICAL
            result = variable_type_selector()
            assert result == VariableType.NUMERICAL

    def test_loss_rate_type_selector_returns_type(self, session):
        """Test loss rate type selector returns selected type."""
        with patch('streamlit.selectbox') as mock_selectbox:
            mock_selectbox.return_value = LossRateTypes.DLR
            result = loss_rate_type_selector()
            assert result == LossRateTypes.DLR

    def test_upgrade_downgrade_selector_returns_values(self, session):
        """Test upgrade/downgrade selector returns tuple."""
        with patch('streamlit.checkbox') as mock_checkbox, \
             patch('streamlit.columns') as mock_columns:
            
            mock_checkbox.return_value = True
            
            # Two st.columns(2) calls: titles pair, inputs pair.
            # First columns call -> [upgrade_cont_t, downgrade_cont_t]
            # Second columns call -> [upgrade_cont_i, downgrade_cont_i]
            title_cols = [MagicMock(), MagicMock()]
            input_cols = [MagicMock(), MagicMock()]
            input_cols[0].number_input.return_value = 1  # upgrade_limit
            input_cols[1].number_input.return_value = 2  # downgrade_limit
            mock_columns.side_effect = [title_cols, input_cols]
            
            result = upgrade_downgrade_selector()
            assert result == (True, 1, 2)

    def test_filter_selector_returns_selected(self, session):
        """Test filter selector returns selected filters."""
        with patch('streamlit.multiselect') as mock_multiselect, \
             patch('streamlit.markdown') as mock_markdown, \
             patch('streamlit.session_state', {'session': session}):
            mock_multiselect.return_value = []
            result = filter_selector()
            assert result == []

    def test_risk_segment_details_selector_single_var(self, session):
        """Test risk segment selector for single var iteration."""
        session.iterations_view_model.set_current_status("create", iteration_create_parent_id=None)
        
        with patch('streamlit.data_editor') as mock_editor, \
             patch('streamlit.markdown') as mock_markdown, \
             patch('streamlit.column_config.CheckboxColumn') as mock_checkbox_col, \
             patch('streamlit.column_config.TextColumn') as mock_text_col, \
             patch('streamlit.session_state', {'session': session}):
            # Mock the return value with selected segments
            import pandas as pd
            mock_df = pd.DataFrame({
                'Selected': [True, False, True],
                'Risk Segment': ['Low', 'Medium', 'High'],
                'Lower Bad Rate': [0.0, 0.1, 0.3],
                'Upper Bad Rate': [0.1, 0.3, 1.0],
            })
            mock_editor.return_value = mock_df
            
            result = risk_segment_details_selector()
            # Should return indices where selected is True
            assert result == [0, 2]


class TestIterationCreatorWorkflow:
    """Integration tests for iteration creator workflow."""

    def test_create_single_var_iteration_button_disabled_on_errors(self, iterations_vm, session):
        """Test create button is disabled when validation errors exist."""
        # Unset metric variables - should cause errors
        iterations_vm.set_current_status("create", iteration_create_parent_id=None)
        metric_repo = iterations_vm._IterationsViewModel__metric_repository
        original_dlr_bad = metric_repo.var_dev_dlr_bad
        original_avg_bal = metric_repo.var_dev_avg_bal
        metric_repo.var_dev_dlr_bad = None
        metric_repo.var_dev_avg_bal = None
        
        try:
            errors = iterations_vm.validate_iter_create_params(
                variable_name="credit_score",
                variable_dtype=VariableType.NUMERICAL,
                auto_band=True,
                loss_rate_type=LossRateTypes.DLR,
                use_scalars=False,
            )
            
            # Button should be disabled when errors exist
            assert bool(errors) == True
        finally:
            metric_repo.var_dev_dlr_bad = original_dlr_bad
            metric_repo.var_dev_avg_bal = original_avg_bal

    def test_create_single_var_iteration_success(self, iterations_vm):
        """Test successful single var iteration creation."""
        # Set up required metric variables
        iterations_vm._IterationsViewModel__metric_repository.var_dev_dlr_bad = "credit_default_flag"
        iterations_vm._IterationsViewModel__metric_repository.var_dev_avg_bal = "average_balance"
        
        iteration = iterations_vm.add_single_var_iteration(
            name="Test Iteration",
            variable_name="credit_score",
            variable_dtype=VariableType.NUMERICAL,
            selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1)],
            loss_rate_type=LossRateTypes.DLR,
            filter_ids=[],
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )
        
        assert iteration is not None
        assert iteration.name == "Test Iteration"
        assert iteration.variable_name == "credit_score"
        assert iteration.iter_type.value == "single"

    def test_create_double_var_iteration_success(self, iterations_vm, single_var_iteration):
        """Test successful double var iteration creation."""
        iteration = iterations_vm.add_double_var_iteration(
            name="Child Iteration",
            previous_iteration_id=single_var_iteration.uid,
            variable_name="income",
            variable_dtype=VariableType.NUMERICAL,
            auto_band=False,
            use_scalar=False,
            remove_outliers=False,
        )
        
        assert iteration is not None
        assert iteration.name == "Child Iteration"
        assert iteration.variable_name == "income"
        assert iteration.iter_type.value == "double"