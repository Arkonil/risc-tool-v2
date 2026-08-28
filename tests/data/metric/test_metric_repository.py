def test_metric_repository_crud(metric_repository, data_repository):
    ds_ids = list(data_repository.data_sources.keys())
    metric_repository.create_metric(
        name="Bad Rate",
        query="unt_bad.sum() / unt_bad.size",
        is_cumulative=False,
        use_thousand_sep=False,
        is_percentage=True,
        decimal_places=2,
        data_source_ids=ds_ids,
    )

    metrics = metric_repository.metrics
    assert len(metrics) == 1
    mid = next(iter(metrics.keys()))

    # Modify
    metric_repository.modify_metric(
        metric_id=mid,
        name="Bad Rate Mod",
        query="unt_bad.sum() / unt_bad.size",
        is_cumulative=False,
        use_thousand_sep=False,
        is_percentage=True,
        decimal_places=4,
        data_source_ids=ds_ids,
    )

    new_metrics = metric_repository.metrics
    assert len(new_metrics) == 1
    new_mid = next(iter(new_metrics.keys()))
    assert new_mid != mid

    # Delete
    metric_repository.remove_metric(new_mid)
    assert len(metric_repository.metrics) == 0
