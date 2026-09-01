"""Shared fixtures for all tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from risc_tool.data.models.data_source import ReadConfig
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.data.session import Session
from risc_tool.ui.iterations.iterations_vm import IterationsViewModel


@pytest.fixture
def test_data_path():
    """Path to test data directory."""
    return Path(__file__).parent / "test_data"


@pytest.fixture
def train_data_path(test_data_path):
    """Path to training data CSV."""
    return test_data_path / "train_data.csv"


@pytest.fixture
def val_data_path(test_data_path):
    """Path to validation data CSV."""
    return test_data_path / "val_data.csv"


@pytest.fixture
def test_data_path_csv(test_data_path):
    """Path to test data CSV."""
    return test_data_path / "test_data.csv"


@pytest.fixture
def data_repository(train_data_path):
    """Create a DataRepository with test data loaded."""
    repo = DataRepository()
    repo.add_data_source("Dev Data", train_data_path, ReadConfig())
    return repo


@pytest.fixture
def filter_repository(data_repository):
    """Create a FilterRepository."""
    return FilterRepository(data_repository)


@pytest.fixture
def metric_repository(data_repository):
    """Create a MetricRepository."""
    return MetricRepository(data_repository)


@pytest.fixture
def option_repository():
    """Create an OptionRepository."""
    return OptionRepository()


@pytest.fixture
def scalar_repository():
    """Create a ScalarRepository."""
    return ScalarRepository()


@pytest.fixture
def iterations_repository(
    data_repository,
    filter_repository,
    metric_repository,
    option_repository,
    scalar_repository,
):
    """Create an IterationsRepository."""
    return IterationsRepository(
        data_repository,
        filter_repository,
        metric_repository,
        option_repository,
        scalar_repository,
    )


@pytest.fixture
def iterations_vm(
    data_repository,
    iterations_repository,
    option_repository,
    filter_repository,
    metric_repository,
    scalar_repository,
):
    """Create an IterationsViewModel with all dependencies."""
    return IterationsViewModel(
        data_repository=data_repository,
        iterations_repository=iterations_repository,
        options_repository=option_repository,
        filter_repository=filter_repository,
        metric_repository=metric_repository,
        scalar_repository=scalar_repository,
    )


@pytest.fixture
def session(iterations_vm):
    """Create a Session with the iterations view model."""
    session = Session()
    session.iterations_view_model = iterations_vm
    return session


@pytest.fixture
def single_var_iteration(iterations_vm):
    """Create a single variable iteration for testing."""
    from risc_tool.data.models.enums import LossRateTypes, VariableType
    from risc_tool.data.models.uid import RiskSegmentID

    return iterations_vm.add_single_var_iteration(
        name="Test Single Var",
        variable_name="credit_score",
        variable_dtype=VariableType.NUMERICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )


@pytest.fixture
def double_var_iteration(iterations_vm, single_var_iteration):
    """Create a double variable iteration for testing."""
    from risc_tool.data.models.enums import VariableType

    return iterations_vm.add_double_var_iteration(
        name="Test Double Var",
        previous_iteration_id=single_var_iteration.uid,
        variable_name="income",
        variable_dtype=VariableType.NUMERICAL,
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )


@pytest.fixture
def categorical_single_var_iteration(iterations_vm):
    """Create a categorical single variable iteration for testing."""
    from risc_tool.data.models.enums import LossRateTypes, VariableType
    from risc_tool.data.models.uid import RiskSegmentID

    return iterations_vm.add_single_var_iteration(
        name="Test Categorical",
        variable_name="employment_status",
        variable_dtype=VariableType.CATEGORICAL,
        selected_segment_ids=[RiskSegmentID(0), RiskSegmentID(1), RiskSegmentID(2)],
        loss_rate_type=LossRateTypes.DLR,
        filter_ids=[],
        auto_band=False,
        use_scalar=False,
        remove_outliers=False,
    )


def _make_context_columns(n: int) -> list[MagicMock]:
    """Create column mocks that support the context manager protocol."""
    return [MagicMock() for _ in range(n)]


@pytest.fixture
def patch_columns():
    """Patch streamlit.columns to return context-manager columns.

    Yields a helper that sets the number of columns returned by st.columns.
    """
    with patch("streamlit.columns") as mock_columns:
        mock_columns.return_value = _make_context_columns(2)

        def set_count(n: int) -> None:
            mock_columns.return_value = _make_context_columns(n)

        yield set_count
