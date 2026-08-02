"""Pydantic model for iteration UI view state metadata."""

from pydantic import BaseModel, ConfigDict, Field

from risc_tool.data.models.enums import LossRateTypes
from risc_tool.data.models.types import FilterID, MetricID


class IterationMetadata(BaseModel):
    """Stores view state metadata for an iteration (active filters, metrics, modes)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    editable: bool = True
    scalars_enabled: bool = True
    split_view_enabled: bool = True
    show_prev_iter_details: bool = True
    loss_rate_type: LossRateTypes = LossRateTypes.DLR
    initial_filter_ids: list[FilterID] = Field(default_factory=list[FilterID])
    current_filter_ids: list[FilterID] = Field(default_factory=list[FilterID])
    metric_ids: list[MetricID] = Field(default_factory=list[MetricID])
    remove_outliers: bool = True

    def update(
        self,
        editable: bool | None = None,
        scalars_enabled: bool | None = None,
        split_view_enabled: bool | None = None,
        show_prev_iter_details: bool | None = None,
        loss_rate_type: LossRateTypes | None = None,
        initial_filter_ids: list[FilterID] | None = None,
        current_filter_ids: list[FilterID] | None = None,
        metric_ids: list[MetricID] | None = None,
        remove_outliers: bool | None = None,
    ) -> None:
        if editable is not None:
            self.editable = editable
        if scalars_enabled is not None:
            self.scalars_enabled = scalars_enabled
        if split_view_enabled is not None:
            self.split_view_enabled = split_view_enabled
        if show_prev_iter_details is not None:
            self.show_prev_iter_details = show_prev_iter_details
        if loss_rate_type is not None:
            self.loss_rate_type = loss_rate_type
        if initial_filter_ids is not None:
            self.initial_filter_ids = initial_filter_ids
        if current_filter_ids is not None:
            self.current_filter_ids = current_filter_ids
        if metric_ids is not None:
            self.metric_ids = metric_ids
        if remove_outliers is not None:
            self.remove_outliers = remove_outliers

    def with_changes(
        self,
        editable: bool | None = None,
        scalars_enabled: bool | None = None,
        split_view_enabled: bool | None = None,
        show_prev_iter_details: bool | None = None,
        loss_rate_type: LossRateTypes | None = None,
        initial_filter_ids: list[FilterID] | None = None,
        current_filter_ids: list[FilterID] | None = None,
        metric_ids: list[MetricID] | None = None,
        remove_outliers: bool | None = None,
    ) -> "IterationMetadata":
        data = self.model_dump()
        if editable is not None:
            data["editable"] = editable
        if scalars_enabled is not None:
            data["scalars_enabled"] = scalars_enabled
        if split_view_enabled is not None:
            data["split_view_enabled"] = split_view_enabled
        if show_prev_iter_details is not None:
            data["show_prev_iter_details"] = show_prev_iter_details
        if loss_rate_type is not None:
            data["loss_rate_type"] = loss_rate_type
        if initial_filter_ids is not None:
            data["initial_filter_ids"] = initial_filter_ids
        if current_filter_ids is not None:
            data["current_filter_ids"] = current_filter_ids
        if metric_ids is not None:
            data["metric_ids"] = metric_ids
        if remove_outliers is not None:
            data["remove_outliers"] = remove_outliers

        return IterationMetadata.model_validate(data)


__all__ = ["IterationMetadata"]
