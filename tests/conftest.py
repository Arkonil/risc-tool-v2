import pandas as pd
import pytest

from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository
from risc_tool_v2.data.filter.repositories.filter_repository import FilterRepository
from risc_tool_v2.data.metric.repositories.metric_repository import MetricRepository


@pytest.fixture
def sample_csv(tmp_path):
    csv_file = tmp_path / "sample_data.csv"
    df = pd.DataFrame({
        "credit_score": [650, 700, 750, 620, 800, 580, 710, 690, 740, 600],
        "income": [
            50000,
            60000,
            75000,
            45000,
            90000,
            35000,
            65000,
            58000,
            72000,
            40000,
        ],
        "unt_bad": [0, 0, 0, 1, 0, 1, 0, 0, 0, 1],
        "dlr_bad": [0.0, 0.0, 0.0, 500.0, 0.0, 1200.0, 0.0, 0.0, 0.0, 800.0],
        "avg_bal": [
            1000.0,
            2000.0,
            1500.0,
            1200.0,
            3000.0,
            1800.0,
            2200.0,
            1600.0,
            2500.0,
            1400.0,
        ],
        "status": [
            "Approved",
            "Approved",
            "Approved",
            "Declined",
            "Approved",
            "Declined",
            "Approved",
            "Approved",
            "Approved",
            "Declined",
        ],
    })
    df.to_csv(csv_file, index=False)
    return csv_file


@pytest.fixture
def data_repository(sample_csv):
    repo = DataRepository()
    repo.add_data_source(
        label="Dev Data",
        filepath=sample_csv,
        read_config=ReadConfig(read_mode="CSV", delimiter=",", header_row=0),
    )
    return repo


@pytest.fixture
def filter_repository(data_repository):
    return FilterRepository(data_repository=data_repository)


@pytest.fixture
def metric_repository(data_repository):
    return MetricRepository(data_repository=data_repository)
