from risc_tool_v2.data.data_source.models.data_source import ReadConfig
from risc_tool_v2.data.data_source.repositories.data_repository import DataRepository


def test_data_repository_crud(sample_csv):
    repo = DataRepository()
    ds = repo.add_data_source("Source 1", sample_csv, ReadConfig())

    assert ds.uid in repo.data_sources
    assert repo.has_valid_sources

    cols = repo.common_columns()
    assert len(cols) > 0

    # Test update
    updated_ds = repo.update_data_source(ds.uid, label="Updated Source")
    assert updated_ds.label == "Updated Source"
    assert updated_ds.uid in repo.data_sources

    # Test delete
    repo.delete_data_source(updated_ds.uid)
    assert not repo.has_valid_sources
