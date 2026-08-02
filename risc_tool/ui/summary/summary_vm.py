"""View Model for the Summary Dashboard feature."""

import typing as t
from uuid import UUID, uuid4

import polars as pl

from risc_tool.data.models.changes import ChangeNotifier
from risc_tool.data.models.enums import Signature, SummaryPageTabName
from risc_tool.data.models.metric import Metric
from risc_tool.data.models.types import ChangeIDs, FilterID, IterationID, MetricID
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.iterations import IterationsRepository
from risc_tool.data.repositories.metric import MetricRepository


class SummaryViewModel(ChangeNotifier):
    """View model encapsulating summary dashboard state and interaction logic."""

    @property
    def signature(self) -> Signature:
        return Signature.SUMMARY_VIEW_MODEL

    def __init__(
        self,
        data_repository: DataRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
        iteration_repository: IterationsRepository,
    ):
        super().__init__(
            dependencies=[
                data_repository,
                filter_repository,
                metric_repository,
                iteration_repository,
            ]
        )

        # Repositories
        self._data_repository: DataRepository = data_repository
        self._filter_repository: FilterRepository = filter_repository
        self._metric_repository: MetricRepository = metric_repository
        self._iteration_repository: IterationsRepository = iteration_repository

        # Page State
        self.tab_names: list[SummaryPageTabName] = [
            SummaryPageTabName.OVERVIEW,
            SummaryPageTabName.COMPARISON,
            SummaryPageTabName.PIVOT,
        ]
        self.current_tab_name: SummaryPageTabName = self.tab_names[0]

        # Overview Tab Data
        self.ov_metric_ids: list[MetricID] = [
            MetricID.DEV_VOLUME,
            MetricID.DEV_DLR_BAD_RATE,
            MetricID.DEV_UNT_BAD_RATE,
        ]
        self.ov_filter_ids: list[FilterID] = []
        self.ov_scalars_enabled = True
        self.ov_remove_outliers = True
        self.ov_selected_iteration_id: IterationID | None = None
        self.ov_selected_iteration_default: bool = False

        # Comparison Tab Data
        self.cv_metric_ids: list[MetricID] = [
            MetricID.DEV_VOLUME,
            MetricID.DEV_DLR_BAD_RATE,
            MetricID.DEV_UNT_BAD_RATE,
        ]
        self.cv_filter_ids: list[FilterID] = []
        self.cv_scalars_enabled = True
        self.cv_remove_outliers = True
        self.cv_selected_iterations: t.OrderedDict[UUID, tuple[IterationID, bool]] = (
            t.OrderedDict()
        )
        self.cv_view_mode: t.Literal["grid", "list"] = "list"

        # Pivot Tab Data
        self.pv_metric_ids: list[MetricID] = []
        self.pv_filter_ids: list[FilterID] = []
        self.pv_remove_outliers = True
        self.pv_row_vars: list[str | tuple[IterationID, bool]] = []
        self.pv_col_vars: list[str | tuple[IterationID, bool]] = []
        self._pv_variables: dict[str | tuple[IterationID, bool], str] = {}

        self.refresh_cache()

    def refresh_cache(self) -> None:
        """Refresh cached variables used by pivot selectors."""
        variables: dict[str | tuple[IterationID, bool], str] = {}

        if self._data_repository.has_valid_sources:
            ds_ids = list(self._data_repository.data_sources.keys())
            lf = self._data_repository.get_lazyframe(data_source_ids=ds_ids)
            for col, _ in self._data_repository.common_columns():
                try:
                    n_uniq = lf.select(pl.col(col).n_unique()).collect().item()
                    if n_uniq <= 10:
                        variables[col] = col
                except (
                    pl.exceptions.PolarsError,
                    AttributeError,
                    KeyError,
                    ValueError,
                ) as e:
                    self.logger.debug(
                        "Could not calculate n_unique for column %s: %s", col, e
                    )

        variables.update(
            self._iteration_repository.iteration_selector_options(
                keep_inactive=False
            ).items()
        )

        self._pv_variables = variables

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle updates from dependent repositories by pruning obsolete references."""
        # Prune Metric IDs
        all_metric_ids = set(self._metric_repository.metrics.keys())
        self.ov_metric_ids = [
            m_id for m_id in self.ov_metric_ids if m_id in all_metric_ids
        ]
        self.cv_metric_ids = [
            m_id for m_id in self.cv_metric_ids if m_id in all_metric_ids
        ]
        self.pv_metric_ids = [
            m_id for m_id in self.pv_metric_ids if m_id in all_metric_ids
        ]

        # Prune Filter IDs
        all_filter_ids = set(self._filter_repository.filters.keys())
        self.ov_filter_ids = [
            f_id for f_id in self.ov_filter_ids if f_id in all_filter_ids
        ]
        self.cv_filter_ids = [
            f_id for f_id in self.cv_filter_ids if f_id in all_filter_ids
        ]
        self.pv_filter_ids = [
            f_id for f_id in self.pv_filter_ids if f_id in all_filter_ids
        ]

        # Prune Iteration IDs
        all_iteration_ids = set(self._iteration_repository.iterations.keys())

        if (
            self.ov_selected_iteration_id is not None
            and self.ov_selected_iteration_id not in all_iteration_ids
        ):
            self.ov_selected_iteration_id = None

        self.cv_selected_iterations = t.OrderedDict([
            (k, v)
            for k, v in self.cv_selected_iterations.items()
            if v[0] in all_iteration_ids
        ])

        common_columns = {c[0] for c in self._data_repository.common_columns()}

        def is_valid_pv_var(var: str | tuple[IterationID, bool]) -> bool:
            if isinstance(var, tuple):
                return var[0] in all_iteration_ids
            return var in common_columns

        self.pv_row_vars = [v for v in self.pv_row_vars if is_valid_pv_var(v)]
        self.pv_col_vars = [v for v in self.pv_col_vars if is_valid_pv_var(v)]

        self.refresh_cache()

    @property
    def data_loaded(self) -> bool:
        """Check if valid data sources are loaded."""
        return self._data_repository.has_valid_sources

    @property
    def sample_loaded(self) -> bool:
        """Check if sample data is loaded (alias for data_loaded)."""
        return self.data_loaded

    def get_metric(self, metric_id: MetricID) -> Metric:
        """Retrieve a metric by ID."""
        return self._metric_repository.metrics[metric_id]

    @property
    def no_iteration(self) -> bool:
        """Check if any iterations exist."""
        return len(self._iteration_repository.iterations) == 0

    # Overview Tab
    def set_overview_metrics(self, metric_ids: list[MetricID]) -> None:
        """Set active metrics for Overview tab."""
        self.ov_metric_ids = metric_ids

    # Comparison Tab
    def set_comparison_metrics(self, metric_ids: list[MetricID]) -> None:
        """Set active metrics for Comparison tab."""
        self.cv_metric_ids = metric_ids

    def remove_iteration_view(self, view_idx: UUID) -> None:
        """Remove an iteration view card from Comparison tab."""
        self.cv_selected_iterations.pop(view_idx, None)

    def add_iteration_view(self, iteration_id: IterationID, default: bool) -> None:
        """Add an iteration view card to Comparison tab."""
        self.cv_selected_iterations.setdefault(uuid4(), (iteration_id, default))

    def edit_iteration_view(
        self, view_idx: UUID, iteration_id: IterationID, default: bool
    ) -> None:
        """Update an existing iteration view card in Comparison tab."""
        self.cv_selected_iterations[view_idx] = (iteration_id, default)

    # Pivot Tab
    def set_pivot_metrics(self, metric_ids: list[MetricID]) -> None:
        """Set active metrics for Pivot tab."""
        self.pv_metric_ids = metric_ids

    @property
    def pivot_variables(self) -> dict[str | tuple[IterationID, bool], str]:
        """Return available pivot variables."""
        return self._pv_variables

    def set_pivot_variables(
        self,
        position: t.Literal["row", "col"],
        variables: list[str | tuple[IterationID, bool]],
    ) -> None:
        """Set pivot row or column variables."""
        if position == "row":
            self.pv_row_vars = variables
        elif position == "col":
            self.pv_col_vars = variables


__all__ = ["SummaryViewModel"]
