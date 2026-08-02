"""View Model for the Summary Dashboard feature."""

import typing as t
from uuid import UUID, uuid4

import pandas as pd
import polars as pl

from risc_tool.data.models.changes import ChangeNotifier
from risc_tool.data.models.enums import RowIndex, Signature, SummaryPageTabName
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
    def _valid_pivot_metrics(self, metric_ids: list[MetricID]) -> list[MetricID]:
        """Filter metric IDs to those usable in the pivot table."""
        all_metrics = self._metric_repository.metrics
        return [
            m_id
            for m_id in metric_ids
            if m_id in all_metrics and not all_metrics[m_id].is_cumulative
        ]

    def set_pivot_metrics(self, metric_ids: list[MetricID]) -> None:
        """Set active metrics for Pivot tab, keeping only valid ones."""
        self.pv_metric_ids = self._valid_pivot_metrics(metric_ids)

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

    def get_pivot_expr_and_with_cols(
        self, variable: str | tuple[IterationID, bool]
    ) -> tuple[pl.Expr, list[pl.Expr]] | None:
        """Resolve a pivot variable into a Polars grouping expression and derived column expressions."""
        if variable not in self.pivot_variables:
            return None

        alias = self.pivot_variables[variable]

        if isinstance(variable, str):
            return pl.col(variable).alias(alias), []

        iter_id, default = variable
        if iter_id not in self._iteration_repository.iterations:
            return None

        try:
            node_chain = self._iteration_repository.graph.get_ancestors(iter_id) + [
                iter_id
            ]
            with_exprs: list[pl.Expr] = []
            prev_col: str | None = None

            for node_id in node_chain:
                iter_obj = self._iteration_repository.get_iteration(node_id)
                _def = default if node_id == iter_id else False
                col_alias = f"__RS_NODE_{node_id}__"

                expr = iter_obj.get_risk_segment_expr(
                    default=_def, prev_seg_col=prev_col
                ).alias(col_alias)

                with_exprs.append(expr)
                prev_col = col_alias

            target_rs_col = f"__RS_NODE_{iter_id}__"
            risk_segment_details = self._iteration_repository.get_risk_segment_details(
                iter_id
            )

            seg_label_map = {
                int(seg_id): seg.name
                for seg_id, seg in risk_segment_details.segments.items()
            }

            mapped_expr = (
                pl
                .col(target_rs_col)
                .replace_strict(seg_label_map, default=None)
                .alias(alias)
            )
            with_exprs.append(mapped_expr)

            return pl.col(alias), with_exprs
        except (KeyError, ValueError, AttributeError) as e:
            self.logger.debug(
                "Could not resolve risk segment expression for iteration %s: %s",
                iter_id,
                e,
            )
            return None

    def get_pivot_tables(self) -> list[pd.DataFrame]:
        """Calculate and return multi-dimensional pivot tables for active pivot metrics."""
        if not self.pv_metric_ids or not self.pv_row_vars:
            return []

        metrics = [
            self._metric_repository.metrics[m_id]
            for m_id in self._valid_pivot_metrics(self.pv_metric_ids)
        ]

        if not metrics:
            return []

        row_resolutions = [
            self.get_pivot_expr_and_with_cols(var) for var in self.pv_row_vars
        ]
        col_resolutions = [
            self.get_pivot_expr_and_with_cols(var) for var in self.pv_col_vars
        ]

        row_resolutions = [res for res in row_resolutions if res is not None]
        col_resolutions = [res for res in col_resolutions if res is not None]

        if not row_resolutions:
            return []

        row_exprs = [res[0] for res in row_resolutions]
        col_exprs = [res[0] for res in col_resolutions]

        all_with_cols: list[pl.Expr] = []
        for res in row_resolutions + col_resolutions:
            all_with_cols.extend(res[1])

        row_names = [str(expr.meta.output_name()) for expr in row_exprs]
        col_names = [str(expr.meta.output_name()) for expr in col_exprs]
        names = row_names + col_names

        r_N = len(row_exprs)
        c_N = len(col_exprs)

        data_filter = self._filter_repository.get_combined_expression(
            self.pv_filter_ids, remove_outliers=self.pv_remove_outliers
        )

        all_summary_lf_idx: list[tuple[int, int]] = []
        all_summary_lfs: list[pl.LazyFrame] = []

        for r_i in range(r_N + 1):
            for c_i in range(c_N + 1):
                all_summary_lf_idx.append((r_i, c_i))

                r_group = row_exprs[:r_i]
                c_group = col_exprs[:c_i]

                lf = self._data_repository.get_summarized_metrics(
                    groupby_variables=r_group + c_group,
                    data_filter=data_filter,
                    metrics=metrics,
                    with_columns=all_with_cols,
                )

                all_summary_lfs.append(lf)

        all_summary_pdfs: list[pl.DataFrame] = pl.collect_all(
            all_summary_lfs, engine="streaming"
        )
        all_summary_dfs: list[pd.DataFrame] = []

        for (r_i, c_i), pdf in zip(all_summary_lf_idx, all_summary_pdfs):
            df = pdf.to_pandas()

            if df.empty:
                continue

            r_group = row_exprs[:r_i]
            c_group = col_exprs[:c_i]

            if r_i + c_i == 0:
                idx = pd.MultiIndex.from_tuples(
                    [(RowIndex.TOTAL,) * (r_N + c_N)],
                    names=names,
                )
            elif r_i + c_i == 1:
                group_cols = [str(e.meta.output_name()) for e in r_group + c_group]
                series = df[group_cols[0]]
                idx = pd.MultiIndex.from_product(
                    [series] + [[RowIndex.TOTAL]] * (r_N + c_N - 1),
                ).swaplevel(0, 0 if r_i == 1 else r_N)
                idx.names = names
                df = df.drop(columns=group_cols)
            else:
                group_cols = [str(e.meta.output_name()) for e in r_group + c_group]
                tuples = [tuple(x) for x in df[group_cols].to_numpy()]
                idx = pd.MultiIndex.from_tuples(
                    [
                        (
                            *t[:r_i],
                            *([RowIndex.TOTAL] * (r_N - r_i)),
                            *t[r_i:],
                            *([RowIndex.TOTAL] * (c_N - c_i)),
                        )
                        for t in tuples
                    ],
                    names=names,
                )
                df = df.drop(columns=group_cols)

            df.index = idx
            all_summary_dfs.append(df)

        if not all_summary_dfs:
            return []

        long_df = pd.concat(all_summary_dfs, axis=0)
        long_df = long_df[~long_df.index.duplicated(keep="last")]

        def sort_key(t_val: t.Any) -> tuple[tuple[bool, str], ...]:
            values: tuple[object, ...]
            if isinstance(t_val, tuple):
                values = t.cast(tuple[object, ...], t_val)
            else:
                values = (t.cast(object, t_val),)

            ordered_items: list[tuple[bool, str]] = []
            for value in values:
                ordered_items.append((value == RowIndex.TOTAL, str(value)))

            return tuple(ordered_items)

        pivot_dfs: list[pd.DataFrame] = []

        for m in metrics:
            metric_series = long_df[m.pretty_name].map(m.format)

            if c_N > 0:
                pivot_df = metric_series.unstack(level=col_names)
            else:
                pivot_df = pd.DataFrame(metric_series, columns=[m.pretty_name])

            ordered_index = sorted(pivot_df.index.tolist(), key=sort_key)
            pivot_df = pivot_df.loc[ordered_index]

            if c_N > 0:
                ordered_cols = sorted(pivot_df.columns.tolist(), key=sort_key)
                pivot_df = pivot_df[ordered_cols]

            def replace_total(tup: object) -> object:
                if not isinstance(tup, tuple):
                    return "Total" if tup == RowIndex.TOTAL else tup

                tuple_values = t.cast(tuple[object, ...], tup)
                replaced_items: list[object] = []

                for t_val in tuple_values:
                    replacement: object = "Total" if t_val == RowIndex.TOTAL else t_val
                    replaced_items.append(replacement)

                return tuple(replaced_items)

            pivot_df.index = pivot_df.index.map(replace_total)
            pivot_df.columns = pivot_df.columns.map(replace_total)

            pivot_dfs.append(pivot_df)

        return pivot_dfs


__all__ = ["SummaryViewModel"]
