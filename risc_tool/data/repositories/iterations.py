import itertools
import typing as t
from collections import OrderedDict

import pandas as pd
import polars as pl

from risc_tool.data.models.config import RiskSegmentConfig
from risc_tool.data.models.enums import (
    Colors,
    LossRateTypes,
    RangeColumn,
    RowIndex,
    RSDetCol,
    Signature,
    VariableType,
)
from risc_tool.data.models.iteration import (
    CategoricalDoubleVarIteration,
    CategoricalGroup,
    CategoricalSingleVarIteration,
    Iteration,
    NumericalDoubleVarIteration,
    NumericalGroup,
    NumericalIterationMixin,
    NumericalSingleVarIteration,
    SingleVarIteration,
)
from risc_tool.data.models.iteration_graph import IterationGraph
from risc_tool.data.models.types import (
    ChangeIDs,
    FilterID,
    GridMetricSummary,
    GroupID,
    IterationID,
    MetricID,
    RiskSegmentID,
)
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.data.repositories.data import DataRepository
from risc_tool.data.repositories.filter import FilterRepository
from risc_tool.data.repositories.metric import MetricRepository
from risc_tool.data.repositories.options import OptionRepository
from risc_tool.data.repositories.scalar import ScalarRepository
from risc_tool.data.services.auto_band import (
    create_auto_categorical_bands,
    create_auto_numeric_bands,
    does_high_value_implies_high_risk,
)


class IterationsRepository(BaseRepository):
    """Repository for managing iterations and calculating risk segments lazily via Polars."""

    @property
    def signature(self) -> Signature:
        return Signature.ITERATION_REPOSITORY

    def __init__(
        self,
        data_repository: DataRepository,
        filter_repository: FilterRepository,
        metric_repository: MetricRepository,
        options_repository: OptionRepository,
        scalar_repository: ScalarRepository,
    ) -> None:
        super().__init__(
            dependencies=[
                data_repository,
                filter_repository,
                metric_repository,
                options_repository,
                scalar_repository,
            ]
        )

        self.iterations: dict[IterationID, Iteration] = {}
        self.graph = IterationGraph()

        self.__data_repository = data_repository
        self.__filter_repository = filter_repository
        self.__metric_repository = metric_repository
        self.__options_repository = options_repository
        self.__scalar_repository = scalar_repository

    def _default_group_ids(
        self, selected_segment_config: RiskSegmentConfig
    ) -> list[GroupID]:
        return [GroupID(seg_id.value) for seg_id in selected_segment_config.segments]

    def _group_display_labels(
        self,
        iteration: Iteration,
        group_ids: list[GroupID],
        *,
        default: bool,
    ) -> list[str]:
        target_groups = iteration.default_groups if default else iteration.groups

        labels: list[str] = []
        for gid in group_ids:
            group = target_groups.get(gid)
            if group is None:
                labels.append("")
                continue

            if isinstance(group, NumericalGroup):
                labels.append(
                    f"({float(group.lower_bound)} - {float(group.upper_bound)}]"
                )
            else:
                labels.append(", ".join(sorted(group.categories)))

        return labels

    def _risk_segment_name_map(
        self, iteration_id: IterationID
    ) -> dict[RiskSegmentID, str]:
        return {
            seg_id: seg.name
            for seg_id, seg in self.get_risk_segment_details(
                iteration_id
            ).segments.items()
        }

    def _create_default_numerical_groups(
        self,
        variable_name: str,
        group_ids: list[GroupID],
    ) -> OrderedDict[GroupID, NumericalGroup]:
        default_groups: OrderedDict[GroupID, NumericalGroup] = OrderedDict()
        group_count = len(group_ids)

        if group_count == 0:
            return default_groups

        quantile_exprs = [
            pl
            .col(variable_name)
            .cast(pl.Float64)
            .quantile(i / group_count, interpolation="linear")
            .alias(f"q{i}")
            for i in range(1, group_count)
        ]

        if quantile_exprs:
            quantile_row = (
                self.__data_repository
                .get_lazyframe()
                .select(quantile_exprs)
                .collect()
                .row(0, named=True)
            )
            quantile_bounds = [
                float(value) if value is not None else float("-inf")
                for value in quantile_row.values()
            ]
        else:
            quantile_bounds = []

        lower_bound = float("-inf")
        for idx, gid in enumerate(group_ids):
            upper_bound = (
                float("inf") if idx == group_count - 1 else float(quantile_bounds[idx])
            )

            default_groups[gid] = NumericalGroup(
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
            lower_bound = upper_bound

        return default_groups

    def _create_default_categorical_groups(
        self,
        variable_name: str,
        group_ids: list[GroupID],
    ) -> OrderedDict[GroupID, CategoricalGroup]:
        default_groups: OrderedDict[GroupID, CategoricalGroup] = OrderedDict()
        group_count = len(group_ids)

        if group_count == 0:
            return default_groups

        unique_values = (
            self.__data_repository
            .get_lazyframe()
            .select(
                pl
                .col(variable_name)
                .cast(pl.String)
                .drop_nulls()
                .unique()
                .sort()
                .alias(variable_name)
            )
            .collect()
            .get_column(variable_name)
            .to_list()
        )

        unique_count = len(unique_values)
        base_size = unique_count // group_count
        remainder = unique_count % group_count

        start = 0
        for idx, gid in enumerate(group_ids):
            chunk_size = base_size + (1 if idx < remainder else 0)
            end = start + chunk_size
            default_groups[gid] = CategoricalGroup(
                categories={str(v) for v in unique_values[start:end]}
            )
            start = end

        return default_groups

    def _set_double_iteration_defaults(
        self,
        iteration: NumericalDoubleVarIteration | CategoricalDoubleVarIteration,
        groups: OrderedDict[GroupID, NumericalGroup]
        | OrderedDict[GroupID, CategoricalGroup],
        grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]],
    ) -> None:
        if isinstance(iteration, NumericalDoubleVarIteration):
            assert all(isinstance(v, NumericalGroup) for v in groups.values())
            typed_groups = t.cast(OrderedDict[GroupID, NumericalGroup], groups)
            iteration.set_default_groups(typed_groups)
        else:
            assert all(isinstance(v, CategoricalGroup) for v in groups.values())
            typed_groups = t.cast(OrderedDict[GroupID, CategoricalGroup], groups)
            iteration.set_default_groups(typed_groups)

        iteration.groups_mask = {gid: True for gid in iteration.default_groups}
        iteration.default_risk_segment_grid = {
            gid: {pseg: tseg for pseg, tseg in row.items()} for gid, row in grid.items()
        }
        iteration.risk_segment_grid = {
            gid: {pseg: tseg for pseg, tseg in row.items()} for gid, row in grid.items()
        }

    def _reindex_double_groups_and_grid(
        self,
        groups: OrderedDict[GroupID, NumericalGroup]
        | OrderedDict[GroupID, CategoricalGroup],
        grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]],
    ) -> tuple[
        OrderedDict[GroupID, NumericalGroup] | OrderedDict[GroupID, CategoricalGroup],
        dict[GroupID, dict[RiskSegmentID, RiskSegmentID]],
    ]:
        reindexed_groups: OrderedDict[
            GroupID,
            NumericalGroup | CategoricalGroup,
        ] = OrderedDict()
        reindexed_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = {}

        for idx, old_gid in enumerate(groups.keys()):
            new_gid = GroupID(idx)
            reindexed_groups[new_gid] = groups[old_gid]
            reindexed_grid[new_gid] = dict(grid[old_gid])

        if reindexed_groups and all(
            isinstance(v, NumericalGroup) for v in reindexed_groups.values()
        ):
            return (
                t.cast(OrderedDict[GroupID, NumericalGroup], reindexed_groups),
                reindexed_grid,
            )

        return (
            t.cast(OrderedDict[GroupID, CategoricalGroup], reindexed_groups),
            reindexed_grid,
        )

    def on_dependency_update(self, change_ids: ChangeIDs) -> None:
        """Handle schema or data updates by validating active variables."""
        if not self.__data_repository.has_valid_sources:
            return

        common_cols = [c[0] for c in self.__data_repository.common_columns()]

        for iteration in self.iterations.values():
            iteration.active = iteration.variable_name in common_cols

    def iteration_selector_options(self, keep_inactive: bool = False):
        """Generate options map for UI iteration selectors."""
        options: dict[tuple[IterationID, bool], str] = {}

        for iter_id, iter_obj in self.iterations.items():
            if iter_obj.active or keep_inactive:
                options[(iter_id, True)] = f"{iter_obj.pretty_name} (Default)"
                options[(iter_id, False)] = f"{iter_obj.pretty_name} (Custom)"

        return options

    def get_iteration(self, iteration_id: IterationID) -> Iteration:
        if iteration_id not in self.iterations:
            raise ValueError(f"Iteration {iteration_id} does not exist.")

        return self.iterations[iteration_id]

    def get_root_iteration(
        self, iteration_id: IterationID
    ) -> SingleVarIteration[NumericalGroup] | SingleVarIteration[CategoricalGroup]:
        root_id = self.graph.get_root_iter_id(iteration_id)
        root_iter = self.get_iteration(root_id)

        if isinstance(root_iter, SingleVarIteration):
            return root_iter

        raise ValueError(
            f"Iteration {root_id} is not a root single-variable iteration."
        )

    def get_risk_segment_details(self, iteration_id: IterationID):
        root_iter = self.get_root_iteration(iteration_id)
        return root_iter.risk_segment_details

    def rename_iteration(self, iteration_id: IterationID, name: str) -> None:
        """Rename an iteration and notify subscribers."""
        iteration = self.get_iteration(iteration_id)
        old_name = iteration.name
        iteration.rename(name)
        self.logger.info(
            "Renamed iteration ID %s from '%s' to '%s'",
            iteration_id,
            old_name,
            iteration.name,
        )
        self.notify_subscribers()

    def delete_iteration(self, iteration_id: IterationID) -> None:
        """Cascade delete an iteration and all descendants."""
        if iteration_id not in self.iterations:
            self.logger.warning(
                "Attempted to delete non-existent iteration ID %s", iteration_id
            )
            return

        self.logger.warning("Deleting iteration ID %s", iteration_id)
        ids_to_delete = [iteration_id] + self.graph.get_descendants(iteration_id)

        for i_id in ids_to_delete:
            self.iterations.pop(i_id, None)
            self.graph.remove_iteration(i_id)

        self.notify_subscribers()

    def add_single_var_iteration(
        self,
        name: str,
        variable_name: str,
        variable_dtype: VariableType,
        selected_segment_ids: list[RiskSegmentID],
        loss_rate_type: LossRateTypes,
        filter_ids: list[FilterID],
        auto_band: bool,
        use_scalar: bool,
        remove_outliers: bool,
        hv_imp_hr: bool | None = None,
    ) -> SingleVarIteration[NumericalGroup] | SingleVarIteration[CategoricalGroup]:
        """Create and store a new SingleVarIteration model."""
        new_id = IterationID(self._get_new_id(current_ids=self.iterations.keys()))

        # Get risk segment options

        selected_segment_config = RiskSegmentConfig(
            segments=self.__options_repository.risk_segments.get_segments(
                selected_segment_ids
            )
        )

        if not selected_segment_config.has_finite_upper_bound_segment():
            raise ValueError(
                "Cannot create single-variable iteration: at least 1 risk segment with a finite upper bound must be selected."
            )

        if variable_dtype == VariableType.NUMERICAL:
            iteration = NumericalSingleVarIteration(
                var_type=VariableType.NUMERICAL,
                uid=new_id,
                name=name,
                variable_name=variable_name,
                risk_segment_details=selected_segment_config,
            )
        else:
            iteration = CategoricalSingleVarIteration(
                var_type=VariableType.CATEGORICAL,
                uid=new_id,
                name=name,
                variable_name=variable_name,
                risk_segment_details=selected_segment_config,
            )

        if auto_band:
            dev_ds_ids = self.__metric_repository.dev_data_source_ids
            lf = self.__data_repository.get_lazyframe(data_source_ids=dev_ds_ids)
            lf = lf.filter(
                self.__filter_repository.get_combined_expression(
                    filter_ids, remove_outliers=remove_outliers
                )
            )

            if loss_rate_type == LossRateTypes.DLR:
                numerator = t.cast(str, self.__metric_repository.var_dev_dlr_bad)
                denominator = t.cast(str, self.__metric_repository.var_dev_avg_bal)
            else:
                numerator = t.cast(str, self.__metric_repository.var_dev_unt_bad)
                denominator = None

            if variable_dtype == VariableType.NUMERICAL:
                assert isinstance(iteration, NumericalSingleVarIteration)
                groups = create_auto_numeric_bands(
                    base_lf=lf,
                    variable=variable_name,
                    risk_segment_config=selected_segment_config,
                    loss_rate_scalar=self.__scalar_repository.get_scalar(
                        loss_rate_type
                    ),
                    numerator=numerator,
                    denominator=denominator,
                    mob=self.__metric_repository.current_rate_mob,
                    use_scalar=use_scalar,
                    hv_imp_hr=hv_imp_hr,
                )

                iteration.set_default_groups(groups)
            else:
                assert isinstance(iteration, CategoricalSingleVarIteration)
                groups = create_auto_categorical_bands(
                    base_lf=lf,
                    variable=variable_name,
                    risk_segment_config=selected_segment_config,
                    loss_rate_scalar=self.__scalar_repository.get_scalar(
                        loss_rate_type
                    ),
                    numerator=numerator,
                    denominator=denominator,
                    mob=self.__metric_repository.current_rate_mob,
                    use_scalar=use_scalar,
                )

                iteration.set_default_groups(groups)

        else:
            group_ids = self._default_group_ids(selected_segment_config)
            if variable_dtype == VariableType.NUMERICAL:
                assert isinstance(iteration, NumericalSingleVarIteration)
                default_groups = self._create_default_numerical_groups(
                    variable_name=variable_name,
                    group_ids=group_ids,
                )
                iteration.set_default_groups(default_groups)
            else:
                assert isinstance(iteration, CategoricalSingleVarIteration)
                default_groups = self._create_default_categorical_groups(
                    variable_name=variable_name,
                    group_ids=group_ids,
                )
                iteration.set_default_groups(default_groups)

        self.iterations[new_id] = iteration

        self.logger.info("Successfully added single variable iteration ID %s", new_id)

        self.notify_subscribers()
        return iteration

    def add_double_var_iteration(
        self,
        name: str,
        previous_iteration_id: IterationID,
        variable_name: str,
        variable_dtype: VariableType,
        loss_rate_type: LossRateTypes,
        filter_ids: list[FilterID],
        auto_band: bool,
        use_scalar: bool,
        remove_outliers: bool,
        upgrade_limit: int | None = None,
        downgrade_limit: int | None = None,
        auto_rank_ordering: bool | None = None,
    ) -> Iteration:
        """Create and store a new DoubleVarIteration model."""
        if previous_iteration_id not in self.iterations:
            raise ValueError(
                f"Invalid previous iteration id: {previous_iteration_id}. Iteration does not exist."
            )

        available_columns = self.__data_repository.common_columns()
        if (variable_name, variable_dtype) not in available_columns:
            raise ValueError(
                f"Variable '{variable_name}' with dtype '{variable_dtype}' does not exist in common columns."
            )

        new_id = IterationID(self._get_new_id(current_ids=self.iterations.keys()))
        parent_iteration = self.get_iteration(previous_iteration_id)
        root_segment_config = self.get_risk_segment_details(previous_iteration_id)
        ordered_parent_segments = list(root_segment_config.segments.keys())

        if variable_dtype == VariableType.NUMERICAL:
            iteration = NumericalDoubleVarIteration(
                var_type=VariableType.NUMERICAL,
                uid=new_id,
                name=name,
                variable_name=variable_name,
            )
        else:
            iteration = CategoricalDoubleVarIteration(
                var_type=VariableType.CATEGORICAL,
                uid=new_id,
                name=name,
                variable_name=variable_name,
            )

        if not auto_band:
            default_group_ids = [GroupID(i) for i in range(10)]
            if variable_dtype == VariableType.NUMERICAL:
                default_groups = self._create_default_numerical_groups(
                    variable_name=variable_name,
                    group_ids=default_group_ids,
                )
            else:
                default_groups = self._create_default_categorical_groups(
                    variable_name=variable_name,
                    group_ids=default_group_ids,
                )

            identity_grid = {
                gid: {seg_id: seg_id for seg_id in ordered_parent_segments}
                for gid in default_groups
            }

            self._set_double_iteration_defaults(
                iteration=iteration,
                groups=default_groups,
                grid=identity_grid,
            )
        else:
            if upgrade_limit is None or downgrade_limit is None:
                raise ValueError(
                    "upgrade_limit and downgrade_limit must be set for auto banding."
                )

            dev_ds_ids = self.__metric_repository.dev_data_source_ids
            data_filter = self.__filter_repository.get_combined_expression(
                filter_ids,
                remove_outliers=remove_outliers,
            )

            chain_ids = self.graph.get_ancestors(previous_iteration_id) + [
                previous_iteration_id
            ]
            with_exprs: list[pl.Expr] = []
            prev_col: str | None = None

            for node_id in chain_ids:
                node_iter = self.get_iteration(node_id)
                alias = f"__RS_NODE_{node_id}__"
                with_exprs.append(
                    node_iter.get_risk_segment_expr(
                        default=False, prev_seg_col=prev_col
                    ).alias(alias)
                )
                prev_col = alias

            parent_col = f"__RS_NODE_{previous_iteration_id}__"

            base_lf = self.__data_repository.get_lazyframe(data_source_ids=dev_ds_ids)
            base_lf = base_lf.filter(data_filter)
            for expr in with_exprs:
                base_lf = base_lf.with_columns(expr)

            transformed_segment_config = RiskSegmentConfig(
                segments=root_segment_config.get_segments(original=False)
            )
            segment_order = list(transformed_segment_config.segments.keys())
            segment_pos = {seg_id: idx for idx, seg_id in enumerate(segment_order)}

            if loss_rate_type == LossRateTypes.DLR:
                numerator = t.cast(str, self.__metric_repository.var_dev_dlr_bad)
                denominator = t.cast(str, self.__metric_repository.var_dev_avg_bal)
            else:
                numerator = t.cast(str, self.__metric_repository.var_dev_unt_bad)
                denominator = None

            parent_segments_present = (
                base_lf
                .select(pl.col(parent_col).drop_nulls().unique().sort())
                .collect()
                .get_column(parent_col)
                .to_list()
            )
            parent_segments_present = [
                RiskSegmentID(int(v))
                for v in parent_segments_present
                if v is not None and RiskSegmentID(int(v)) in segment_pos
            ]

            hv_imp_hr: bool | None = None
            if variable_dtype == VariableType.NUMERICAL:
                assert denominator is not None or loss_rate_type == LossRateTypes.ULR
                hv_imp_hr = does_high_value_implies_high_risk(
                    base_lf=base_lf,
                    variable=variable_name,
                    numerator=numerator,
                    denominator=denominator if denominator is not None else numerator,
                )

                cut_points: set[float] = set()
                for parent_seg in parent_segments_present:
                    pos = segment_pos[parent_seg]
                    start = max(0, pos - upgrade_limit)
                    end = min(len(segment_order), pos + downgrade_limit + 1)
                    allowed_seg_ids = segment_order[start:end]
                    sub_cfg = RiskSegmentConfig(
                        segments=OrderedDict(
                            (sid, transformed_segment_config.segments[sid])
                            for sid in allowed_seg_ids
                        )
                    )

                    seg_lf = base_lf.filter(pl.col(parent_col) == parent_seg.value)
                    seg_groups = create_auto_numeric_bands(
                        base_lf=seg_lf,
                        variable=variable_name,
                        risk_segment_config=sub_cfg,
                        loss_rate_scalar=self.__scalar_repository.get_scalar(
                            loss_rate_type
                        ),
                        numerator=numerator,
                        denominator=denominator,
                        mob=self.__metric_repository.current_rate_mob,
                        use_scalar=use_scalar,
                        hv_imp_hr=hv_imp_hr,
                    )
                    for group in seg_groups.values():
                        cut_points.add(float(group.lower_bound))
                        cut_points.add(float(group.upper_bound))

                sorted_points = sorted(cut_points)
                pair_points = list(itertools.pairwise(sorted_points))
                if not pair_points:
                    pair_points = [(float("-inf"), float("inf"))]

                if hv_imp_hr is False:
                    pair_points = list(reversed(pair_points))

                numerical_groups: OrderedDict[GroupID, NumericalGroup] = OrderedDict()
                for idx, (lower, upper) in enumerate(pair_points):
                    numerical_groups[GroupID(idx)] = NumericalGroup(
                        lower_bound=float(lower),
                        upper_bound=float(upper),
                    )

                t.cast(
                    NumericalDoubleVarIteration,
                    iteration,
                ).set_default_groups(numerical_groups)
            else:
                categorical_groups = create_auto_categorical_bands(
                    base_lf=base_lf,
                    variable=variable_name,
                    risk_segment_config=transformed_segment_config,
                    loss_rate_scalar=self.__scalar_repository.get_scalar(
                        loss_rate_type
                    ),
                    numerator=numerator,
                    denominator=denominator,
                    mob=self.__metric_repository.current_rate_mob,
                    use_scalar=use_scalar,
                )
                t.cast(
                    CategoricalDoubleVarIteration,
                    iteration,
                ).set_default_groups(categorical_groups)

            current_group_col = "__CURR_GROUP__"
            metric = (
                self.__metric_repository.dev_dlr_bad_rate
                if loss_rate_type == LossRateTypes.DLR
                else self.__metric_repository.dev_unt_bad_rate
            )

            metric_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[pl.col(parent_col), pl.col(current_group_col)],
                data_filter=data_filter,
                metrics=[metric],
                with_columns=with_exprs
                + [
                    iteration.get_group_mapping_expr(default=True).alias(
                        current_group_col
                    )
                ],
            )
            metric_df = metric_lf.collect().to_pandas()
            metric_name = metric.pretty_name

            metric_map: dict[tuple[GroupID, RiskSegmentID], float] = {}
            if not metric_df.empty and metric_name in metric_df.columns:
                for _, row in metric_df.iterrows():
                    pseg = row[parent_col]
                    cgrp = row[current_group_col]
                    value = row[metric_name]
                    if pseg is None or cgrp is None or pd.isna(pseg) or pd.isna(cgrp):
                        continue
                    metric_map[(GroupID(int(cgrp)), RiskSegmentID(int(pseg)))] = (
                        float(value) / 100.0
                    )

            risk_segment_grid: dict[GroupID, dict[RiskSegmentID, RiskSegmentID]] = {}
            for gid in iteration.default_groups:
                row_map: dict[RiskSegmentID, RiskSegmentID] = {}
                for parent_seg in ordered_parent_segments:
                    if parent_seg not in segment_pos:
                        row_map[parent_seg] = parent_seg
                        continue

                    metric_value = metric_map.get((gid, parent_seg))
                    if metric_value is None or pd.isna(metric_value):
                        row_map[parent_seg] = parent_seg
                        continue

                    pos = segment_pos[parent_seg]
                    start = max(0, pos - upgrade_limit)
                    end = min(len(segment_order), pos + downgrade_limit + 1)
                    allowed_seg_ids = segment_order[start:end]

                    chosen_seg = allowed_seg_ids[-1]
                    for target_seg in allowed_seg_ids:
                        seg_obj = transformed_segment_config.segments[target_seg]
                        if use_scalar:
                            maf = seg_obj.maf(loss_rate_type)
                            scalar = self.__scalar_repository.get_scalar(loss_rate_type)
                            scaled_metric = metric_value * max(
                                maf * scalar.portfolio_scalar,
                                1.0,
                            )
                        else:
                            scaled_metric = metric_value

                        if scaled_metric < seg_obj.upper_rate:
                            chosen_seg = target_seg
                            break

                    row_map[parent_seg] = chosen_seg

                risk_segment_grid[gid] = row_map

            if isinstance(iteration, NumericalDoubleVarIteration):
                num_groups = iteration.default_groups
                ordered_ids = list(num_groups.keys())
                i = 1
                while i < len(ordered_ids):
                    prev_gid = ordered_ids[i - 1]
                    curr_gid = ordered_ids[i]
                    if risk_segment_grid[curr_gid] != risk_segment_grid[prev_gid]:
                        i += 1
                        continue

                    prev_group = num_groups[prev_gid]
                    curr_group = num_groups[curr_gid]
                    num_groups[prev_gid] = NumericalGroup(
                        lower_bound=min(prev_group.lower_bound, curr_group.lower_bound),
                        upper_bound=max(prev_group.upper_bound, curr_group.upper_bound),
                    )

                    del num_groups[curr_gid]
                    del risk_segment_grid[curr_gid]
                    ordered_ids.pop(i)

                merged_groups, risk_segment_grid = self._reindex_double_groups_and_grid(
                    groups=num_groups,
                    grid=risk_segment_grid,
                )
            else:
                cat_groups = iteration.default_groups
                ordered_ids = list(cat_groups.keys())

                i1 = 0
                while i1 < len(ordered_ids):
                    i2 = i1 + 1
                    while i2 < len(ordered_ids):
                        gid1 = ordered_ids[i1]
                        gid2 = ordered_ids[i2]
                        if risk_segment_grid[gid1] != risk_segment_grid[gid2]:
                            i2 += 1
                            continue

                        cat_groups[gid1] = CategoricalGroup(
                            categories=(
                                cat_groups[gid1].categories
                                | cat_groups[gid2].categories
                            )
                        )
                        del cat_groups[gid2]
                        del risk_segment_grid[gid2]
                        ordered_ids.pop(i2)

                    i1 += 1

                sort_order = sorted(
                    cat_groups.keys(),
                    key=lambda gid: tuple(
                        int(risk_segment_grid[gid][parent_seg])
                        for parent_seg in ordered_parent_segments
                    ),
                )
                sorted_groups: OrderedDict[GroupID, CategoricalGroup] = OrderedDict(
                    (gid, cat_groups[gid]) for gid in sort_order
                )
                sorted_grid = {gid: risk_segment_grid[gid] for gid in sort_order}

                merged_groups, risk_segment_grid = self._reindex_double_groups_and_grid(
                    groups=sorted_groups,
                    grid=sorted_grid,
                )

            if auto_rank_ordering:
                ordered_group_ids = list(risk_segment_grid.keys())

                # cummax by column order per row
                for gid in ordered_group_ids:
                    row_values: list[RiskSegmentID] = []
                    max_seen = -1
                    for parent_seg in ordered_parent_segments:
                        current = int(risk_segment_grid[gid][parent_seg])
                        max_seen = max(max_seen, current)
                        row_values.append(RiskSegmentID(max_seen))

                    risk_segment_grid[gid] = {
                        parent_seg: row_values[idx]
                        for idx, parent_seg in enumerate(ordered_parent_segments)
                    }

                # cummax by row order per column
                for parent_seg in ordered_parent_segments:
                    max_seen = -1
                    for gid in ordered_group_ids:
                        current = int(risk_segment_grid[gid][parent_seg])
                        max_seen = max(max_seen, current)
                        risk_segment_grid[gid][parent_seg] = RiskSegmentID(max_seen)

            self._set_double_iteration_defaults(
                iteration=iteration,
                groups=merged_groups,
                grid=risk_segment_grid,
            )

        if parent_iteration.active is False:
            iteration.active = False

        self.graph.add_child(previous_iteration_id, new_id)
        self.iterations[new_id] = iteration

        self.logger.info(
            "Successfully added double variable iteration ID %s under parent ID %s",
            new_id,
            previous_iteration_id,
        )

        self.notify_subscribers()
        return iteration

    def get_risk_segment_range(
        self, iteration_id: IterationID, show_total_row: bool = False
    ) -> pd.DataFrame:
        """Get Risk Segment label column DataFrame for an iteration."""
        risk_segment_details = self.get_risk_segment_details(iteration_id)

        segments = [seg.name for seg in risk_segment_details.segments.values()]
        indices = list(risk_segment_details.segments.keys())

        risk_segments = pd.DataFrame(
            {RangeColumn.RISK_SEGMENT.value: segments},
            index=indices,
        )

        if show_total_row:
            risk_segments.loc[RowIndex.TOTAL, RangeColumn.RISK_SEGMENT.value] = "Total"

        return risk_segments

    def get_color_range(
        self, iteration_id: IterationID, show_total_row: bool = False
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Get font color and background color DataFrames for an iteration's risk segments."""
        risk_segment_details = self.get_risk_segment_details(iteration_id)

        font_colors = [seg.font_color for seg in risk_segment_details.segments.values()]
        bg_colors = [seg.bg_color for seg in risk_segment_details.segments.values()]
        indices = list(risk_segment_details.segments.keys())

        font_color_df = pd.DataFrame(
            {RSDetCol.FONT_COLOR.value: font_colors}, index=indices
        )
        bg_color_df = pd.DataFrame({RSDetCol.BG_COLOR.value: bg_colors}, index=indices)

        if show_total_row:
            font_color_df.loc[RowIndex.TOTAL, RSDetCol.FONT_COLOR.value] = (
                Colors.F_TABLE_TOTAL_LIGHT.value
            )
            bg_color_df.loc[RowIndex.TOTAL, RSDetCol.BG_COLOR.value] = (
                Colors.B_TABLE_TOTAL_LIGHT.value
            )

        return font_color_df, bg_color_df

    def is_rs_details_same(
        self, iteration_id: IterationID
    ) -> t.Literal["equal", "unequal", "updatable"]:
        current = self.get_risk_segment_details(iteration_id)
        global_segments = self.__options_repository.risk_segments.segments

        if list(current.segments.keys()) != [
            seg_id for seg_id in global_segments if seg_id in current.segments
        ]:
            return "unequal"

        same_core = True
        same_styling = True

        for seg_id, segment in current.segments.items():
            global_segment = global_segments.get(seg_id)
            if global_segment is None:
                return "unequal"

            if (
                segment.name != global_segment.name
                or segment.lower_rate != global_segment.lower_rate
                or segment.upper_rate != global_segment.upper_rate
            ):
                same_core = False

            if (
                segment.maf_dlr != global_segment.maf_dlr
                or segment.maf_ulr != global_segment.maf_ulr
                or segment.font_color != global_segment.font_color
                or segment.bg_color != global_segment.bg_color
            ):
                same_styling = False

        if same_core and same_styling:
            return "equal"
        if same_core:
            return "updatable"
        return "unequal"

    def update_rs_details(self, iteration_id: IterationID) -> None:
        if self.is_rs_details_same(iteration_id) != "updatable":
            return

        root_iter = self.get_root_iteration(iteration_id)
        global_segments = self.__options_repository.risk_segments.segments

        root_iter.update_maf(
            loss_rate_type=LossRateTypes.DLR,
            maf_map={
                seg_id: global_segments[seg_id].maf_dlr
                for seg_id in root_iter.risk_segment_details.segments
                if seg_id in global_segments
            },
        )
        root_iter.update_maf(
            loss_rate_type=LossRateTypes.ULR,
            maf_map={
                seg_id: global_segments[seg_id].maf_ulr
                for seg_id in root_iter.risk_segment_details.segments
                if seg_id in global_segments
            },
        )
        root_iter.update_color(
            color_type=RSDetCol.BG_COLOR,
            color_map={
                seg_id: global_segments[seg_id].bg_color
                for seg_id in root_iter.risk_segment_details.segments
                if seg_id in global_segments
            },
        )
        root_iter.update_color(
            color_type=RSDetCol.FONT_COLOR,
            color_map={
                seg_id: global_segments[seg_id].font_color
                for seg_id in root_iter.risk_segment_details.segments
                if seg_id in global_segments
            },
        )

        self.notify_subscribers()

    def get_all_groups(self, iteration_id: IterationID) -> pd.DataFrame:
        iteration = self.get_iteration(iteration_id)

        all_group_ids = list(iteration.groups.keys())
        groups_df = pd.DataFrame(index=all_group_ids)

        if isinstance(
            iteration, (NumericalDoubleVarIteration, CategoricalDoubleVarIteration)
        ):
            groups_df[RangeColumn.SELECTED.value] = [
                iteration.groups_mask.get(gid, False) for gid in all_group_ids
            ]

        if isinstance(iteration, NumericalIterationMixin):
            groups_df[RangeColumn.LOWER_BOUND.value] = [
                iteration.groups[gid].lower_bound for gid in all_group_ids
            ]
            groups_df[RangeColumn.UPPER_BOUND.value] = [
                iteration.groups[gid].upper_bound for gid in all_group_ids
            ]
        else:
            groups_df[RangeColumn.CATEGORIES.value] = [
                sorted(iteration.groups[gid].categories) for gid in all_group_ids
            ]

        return groups_df

    def select_groups(
        self, iteration_id: IterationID, selected_indices: list[GroupID]
    ) -> None:
        iteration = self.get_iteration(iteration_id)
        if not isinstance(
            iteration,
            (NumericalDoubleVarIteration, CategoricalDoubleVarIteration),
        ):
            return

        selected_set = {gid for gid in selected_indices if gid in iteration.groups}
        if not selected_set:
            return

        new_mask = {gid: gid in selected_set for gid in iteration.groups}
        if new_mask == iteration.groups_mask:
            return

        iteration.groups_mask = new_mask
        self.notify_subscribers()

    def add_new_group(self, iteration_id: IterationID) -> None:
        iteration = self.get_iteration(iteration_id)
        if not isinstance(
            iteration,
            (NumericalDoubleVarIteration, CategoricalDoubleVarIteration),
        ):
            return

        new_gid = GroupID(max((int(gid) for gid in iteration.groups), default=-1) + 1)

        if isinstance(iteration, NumericalDoubleVarIteration):
            iteration.groups[new_gid] = NumericalGroup(lower_bound=0.0, upper_bound=0.0)
            iteration.default_groups[new_gid] = NumericalGroup(
                lower_bound=0.0,
                upper_bound=0.0,
            )
        else:
            iteration.groups[new_gid] = CategoricalGroup(categories=set())
            iteration.default_groups[new_gid] = CategoricalGroup(categories=set())

        segment_ids = list(self.get_risk_segment_details(iteration_id).segments.keys())
        last_default_row = next(
            reversed(iteration.default_risk_segment_grid.values()), None
        )
        last_custom_row = next(reversed(iteration.risk_segment_grid.values()), None)
        identity_row = {seg_id: seg_id for seg_id in segment_ids}

        iteration.default_risk_segment_grid[new_gid] = dict(
            last_default_row or identity_row
        )
        iteration.risk_segment_grid[new_gid] = dict(last_custom_row or identity_row)
        iteration.groups_mask[new_gid] = True

        self.notify_subscribers()

    def get_controls(self, iteration_id: IterationID, default: bool) -> pd.DataFrame:
        """Get group boundary controls DataFrame for an iteration."""
        iteration = self.get_iteration(iteration_id)

        if isinstance(iteration, NumericalIterationMixin):
            numerical_groups: OrderedDict[GroupID, NumericalGroup] = (
                iteration.default_groups if default else iteration.groups
            )
            if isinstance(iteration, NumericalDoubleVarIteration) and not default:
                numerical_groups = OrderedDict(
                    (gid, group)
                    for gid, group in numerical_groups.items()
                    if iteration.groups_mask.get(gid, False)
                )

            indices = list(numerical_groups.keys())
            lower_bounds = [g.lower_bound for g in numerical_groups.values()]
            upper_bounds = [g.upper_bound for g in numerical_groups.values()]
            control_df = pd.DataFrame(
                {
                    RangeColumn.LOWER_BOUND.value: lower_bounds,
                    RangeColumn.UPPER_BOUND.value: upper_bounds,
                },
                index=indices,
            )
        else:
            categorical_groups: OrderedDict[GroupID, CategoricalGroup] = (
                iteration.default_groups if default else iteration.groups
            )
            if isinstance(iteration, CategoricalDoubleVarIteration) and not default:
                categorical_groups = OrderedDict(
                    (gid, group)
                    for gid, group in categorical_groups.items()
                    if iteration.groups_mask.get(gid, False)
                )

            indices = list(categorical_groups.keys())
            categories = [sorted(g.categories) for g in categorical_groups.values()]
            control_df = pd.DataFrame(
                {RangeColumn.CATEGORIES.value: categories},
                index=indices,
            )

        return control_df

    def set_controls(self, iteration_id: IterationID, groups: pd.DataFrame) -> None:
        """Set group boundaries or categories from an edited DataFrame."""
        iteration = self.get_iteration(iteration_id)

        lower_bounds = groups.get(
            RangeColumn.LOWER_BOUND.value, pd.Series(index=groups.index)
        )
        upper_bounds = groups.get(
            RangeColumn.UPPER_BOUND.value, pd.Series(index=groups.index)
        )
        categories_col = groups.get(
            RangeColumn.CATEGORIES.value, pd.Series(index=groups.index)
        )

        for group_id in groups.index:
            if group_id not in iteration.groups:
                continue

            cat_val: t.Any = categories_col.get(group_id, set())
            if isinstance(cat_val, (list, tuple, set)):
                cats: set[str] = {str(c) for c in cat_val}  # type: ignore
            else:
                cats: set[str] = set()

            iteration.set_group(
                group_id=group_id,
                lower_bound=float(lower_bounds.get(group_id, float("-inf"))),
                upper_bound=float(upper_bounds.get(group_id, float("inf"))),
                categories=cats,
            )

        self.notify_subscribers()

    def get_risk_segment_grid(
        self,
        iteration_id: IterationID,
        default: bool,
        details_column: RSDetCol,
    ) -> pd.DataFrame:
        iteration = self.get_iteration(iteration_id)
        if not isinstance(
            iteration,
            (NumericalDoubleVarIteration, CategoricalDoubleVarIteration),
        ):
            raise TypeError(
                f"Iteration {iteration_id} is not a double variable iteration."
            )

        target_grid = (
            iteration.default_risk_segment_grid
            if default
            else iteration.risk_segment_grid
        )
        target_rows = list(target_grid.keys())
        if not default:
            target_rows = [
                gid for gid in target_rows if iteration.groups_mask.get(gid, False)
            ]

        details = self.get_risk_segment_details(iteration_id).segments
        column_name_map = {seg_id: seg.name for seg_id, seg in details.items()}

        if details_column == RSDetCol.RISK_SEGMENT:
            value_map = {seg_id: seg.name for seg_id, seg in details.items()}
        elif details_column == RSDetCol.FONT_COLOR:
            value_map = {seg_id: seg.font_color for seg_id, seg in details.items()}
        elif details_column == RSDetCol.BG_COLOR:
            value_map = {seg_id: seg.bg_color for seg_id, seg in details.items()}
        else:
            raise ValueError(
                f"Unsupported risk-segment detail column: {details_column}"
            )

        rows: list[dict[str, str]] = []
        for gid in target_rows:
            row = target_grid.get(gid, {})
            rows.append({
                column_name_map[parent_seg]: value_map.get(target_seg, "")
                for parent_seg, target_seg in row.items()
                if parent_seg in column_name_map
            })

        return pd.DataFrame(rows, index=target_rows)

    def set_risk_segment_grid(
        self,
        iteration_id: IterationID,
        risk_segment_grid: pd.DataFrame,
    ) -> None:
        iteration = self.get_iteration(iteration_id)
        if not isinstance(
            iteration,
            (NumericalDoubleVarIteration, CategoricalDoubleVarIteration),
        ):
            raise TypeError(
                f"Iteration {iteration_id} is not a double variable iteration."
            )

        segment_name_map = self._risk_segment_name_map(iteration_id)
        inverse_segment_name_map = {
            name: seg_id for seg_id, name in segment_name_map.items()
        }

        changed = False
        for group_id in risk_segment_grid.index:
            if group_id not in iteration.risk_segment_grid:
                continue

            for parent_segment_name in risk_segment_grid.columns:
                parent_seg_id = inverse_segment_name_map.get(str(parent_segment_name))
                target_seg_id = inverse_segment_name_map.get(
                    str(risk_segment_grid.at[group_id, parent_segment_name])
                )
                if parent_seg_id is None or target_seg_id is None:
                    continue

                if (
                    iteration.risk_segment_grid[group_id].get(parent_seg_id)
                    == target_seg_id
                ):
                    continue

                iteration.set_risk_segment_grid_cell(
                    group_id, parent_seg_id, target_seg_id
                )
                changed = True

        if changed:
            self.notify_subscribers()

    def get_metric_range(
        self,
        iteration_id: IterationID,
        default: bool,
        filter_ids: list[FilterID],
        metric_ids: list[MetricID],
        scalars_enabled: bool,
        remove_outliers: bool,
        show_total_row: bool,
    ) -> tuple[pd.DataFrame, list[str], list[str]]:
        """Calculate summarized and cumulative metrics grouped by iteration risk segments."""
        ancestors = self.graph.get_ancestors(iteration_id)
        node_chain = ancestors + [iteration_id]

        all_warnings: list[str] = []
        all_errors: list[str] = []

        if not self.__data_repository.has_valid_sources:
            all_errors.append("Data sources are not loaded.")

        for node_id in node_chain:
            iter_obj = self.get_iteration(node_id)
            _def = default if node_id == iteration_id else False
            w, e, _ = iter_obj.validate_groups(default=_def)
            all_warnings.extend(w)
            all_errors.extend(e)

        if all_errors:
            empty_df = pd.DataFrame()
            return empty_df, all_errors, all_warnings

        with_exprs: list[pl.Expr] = []
        prev_col: str | None = None

        for node_id in node_chain:
            iter_obj = self.get_iteration(node_id)
            _def = default if node_id == iteration_id else False
            col_alias = f"__RS_NODE_{node_id}__"

            expr = iter_obj.get_risk_segment_expr(
                default=_def, prev_seg_col=prev_col
            ).alias(col_alias)

            with_exprs.append(expr)
            prev_col = col_alias

        target_rs_col = f"__RS_NODE_{iteration_id}__"

        data_filter = self.__filter_repository.get_combined_expression(
            filter_ids, remove_outliers=remove_outliers
        )

        all_metrics = self.__metric_repository.metrics
        valid_metrics = [
            all_metrics[m_id] for m_id in metric_ids if m_id in all_metrics
        ]

        summarized_metrics = [m for m in valid_metrics if not m.is_cumulative]
        cumulative_metrics = [m for m in valid_metrics if m.is_cumulative]

        risk_segment_details = self.get_risk_segment_details(iteration_id)
        ordered_seg_ids = [s_id for s_id in risk_segment_details.segments]

        metric_dfs: list[pd.DataFrame] = []

        if summarized_metrics:
            s_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[pl.col(target_rs_col)],
                data_filter=data_filter,
                metrics=summarized_metrics,
                with_columns=with_exprs,
            )
            s_df = s_lf.collect().to_pandas()
            if not s_df.empty and target_rs_col in s_df.columns:
                s_df = s_df.set_index(target_rs_col)
            metric_dfs.append(s_df)

        if cumulative_metrics:
            c_lf = self.__data_repository.get_cumulative_metrics(
                groupby_variable=target_rs_col,
                ordered_groups=ordered_seg_ids,
                data_filter=data_filter,
                metrics=cumulative_metrics,
                with_columns=with_exprs,
            )
            c_df = c_lf.collect().to_pandas()
            if not c_df.empty and target_rs_col in c_df.columns:
                c_df = c_df.set_index(target_rs_col)
            metric_dfs.append(c_df)

        if metric_dfs:
            metric_df = pd.concat(metric_dfs, axis=1)
            metric_df = metric_df.reindex(ordered_seg_ids)
            present_cols = [
                m.pretty_name
                for m in valid_metrics
                if m.pretty_name in metric_df.columns
            ]
            metric_df = metric_df[present_cols]
        else:
            metric_df = pd.DataFrame(index=ordered_seg_ids)

        if show_total_row:
            tot_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[],
                data_filter=data_filter,
                metrics=valid_metrics,
                with_columns=with_exprs,
            )
            tot_df = tot_lf.collect().to_pandas()
            tot_df.index = [RowIndex.TOTAL]
            metric_df = pd.concat([metric_df, tot_df], axis=0)

        if scalars_enabled:
            maf_dlr_dict: dict[int, float] = {
                k: v.maf_dlr for k, v in risk_segment_details.segments.items()
            }
            maf_ulr_dict: dict[int, float] = {
                k: v.maf_ulr for k, v in risk_segment_details.segments.items()
            }
            if show_total_row:
                maf_dlr_dict[RowIndex.TOTAL] = 1.0
                maf_ulr_dict[RowIndex.TOTAL] = 1.0

            maf_dlr_series = (
                pd.Series(maf_dlr_dict).reindex(metric_df.index).fillna(1.0)
            )
            maf_ulr_series = (
                pd.Series(maf_ulr_dict).reindex(metric_df.index).fillna(1.0)
            )

            if MetricID.DEV_DLR_BAD_RATE in metric_ids:
                m_obj = all_metrics.get(MetricID.DEV_DLR_BAD_RATE)
                if m_obj and m_obj.pretty_name in metric_df.columns:
                    scalar = self.__scalar_repository.get_scalar(LossRateTypes.DLR)
                    sf = scalar.portfolio_scalar
                    factors = (maf_dlr_series * sf).clip(lower=1.0)
                    metric_df[m_obj.pretty_name] *= factors

            if MetricID.DEV_UNT_BAD_RATE in metric_ids:
                m_obj = all_metrics.get(MetricID.DEV_UNT_BAD_RATE)
                if m_obj and m_obj.pretty_name in metric_df.columns:
                    scalar = self.__scalar_repository.get_scalar(LossRateTypes.ULR)
                    sf = scalar.portfolio_scalar
                    factors = (maf_ulr_series * sf).clip(lower=1.0)
                    metric_df[m_obj.pretty_name] *= factors

        for metric_id in metric_ids:
            if metric_id in all_metrics:
                metric = all_metrics[metric_id]
                m_name = metric.pretty_name
                if m_name in metric_df.columns:
                    metric_df[m_name] = metric_df[m_name].map(metric.format)

        return metric_df, all_errors, all_warnings

    def get_metric_grids(
        self,
        iteration_id: IterationID,
        default: bool,
        filter_ids: list[FilterID],
        metric_ids: list[MetricID],
        scalars_enabled: bool,
        remove_outliers: bool,
        show_total_row: bool,
        show_total_column: bool,
    ) -> tuple[list[GridMetricSummary], list[str], list[str]]:
        iteration = self.get_iteration(iteration_id)
        parent_iteration_id = self.graph.get_parent(iteration_id)

        if (
            not isinstance(
                iteration,
                (NumericalDoubleVarIteration, CategoricalDoubleVarIteration),
            )
            or parent_iteration_id is None
        ):
            raise ValueError(
                f"Iteration {iteration_id} is not a double variable iteration."
            )

        ancestors = self.graph.get_ancestors(parent_iteration_id)
        node_chain = ancestors + [parent_iteration_id]

        warnings: list[str] = []
        errors: list[str] = []
        for node_id in node_chain:
            node_iter = self.get_iteration(node_id)
            node_warnings, node_errors, _ = node_iter.validate_groups(default=False)
            warnings.extend(node_warnings)
            errors.extend(node_errors)

        child_warnings, child_errors, _ = iteration.validate_groups(default=default)
        warnings.extend(child_warnings)
        errors.extend(child_errors)

        if errors:
            return [], errors, warnings

        with_exprs: list[pl.Expr] = []
        prev_col: str | None = None
        for node_id in node_chain:
            node_iter = self.get_iteration(node_id)
            alias = f"__RS_NODE_{node_id}__"
            with_exprs.append(
                node_iter.get_risk_segment_expr(
                    default=False, prev_seg_col=prev_col
                ).alias(alias)
            )
            prev_col = alias

        parent_col = f"__RS_NODE_{parent_iteration_id}__"
        current_group_col = "__CURR_GROUP__"
        with_exprs.append(
            iteration.get_group_mapping_expr(default=default).alias(current_group_col)
        )

        data_filter = self.__filter_repository.get_combined_expression(
            filter_ids,
            remove_outliers=remove_outliers,
        )
        all_metrics = self.__metric_repository.metrics
        valid_metrics = [
            all_metrics[m_id] for m_id in metric_ids if m_id in all_metrics
        ]
        if not valid_metrics:
            return [], warnings, errors

        metric_lf = self.__data_repository.get_summarized_metrics(
            groupby_variables=[pl.col(current_group_col), pl.col(parent_col)],
            data_filter=data_filter,
            metrics=valid_metrics,
            with_columns=with_exprs,
        )
        metric_df = metric_lf.collect().to_pandas()

        if show_total_column:
            total_col_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[
                    pl.col(current_group_col),
                    pl.lit(RowIndex.TOTAL).alias(parent_col),
                ],
                data_filter=data_filter,
                metrics=valid_metrics,
                with_columns=with_exprs,
            )
            metric_df = pd.concat(
                [metric_df, total_col_lf.collect().to_pandas()], axis=0
            )

        if show_total_row:
            total_row_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[
                    pl.lit(RowIndex.TOTAL).alias(current_group_col),
                    pl.col(parent_col),
                ],
                data_filter=data_filter,
                metrics=valid_metrics,
                with_columns=with_exprs,
            )
            metric_df = pd.concat(
                [metric_df, total_row_lf.collect().to_pandas()], axis=0
            )

        if show_total_row and show_total_column:
            total_lf = self.__data_repository.get_summarized_metrics(
                groupby_variables=[
                    pl.lit(RowIndex.TOTAL).alias(current_group_col),
                    pl.lit(RowIndex.TOTAL).alias(parent_col),
                ],
                data_filter=data_filter,
                metrics=valid_metrics,
                with_columns=with_exprs,
            )
            metric_df = pd.concat([metric_df, total_lf.collect().to_pandas()], axis=0)

        if metric_df.empty:
            return [], errors, warnings

        metric_df = metric_df.set_index([current_group_col, parent_col])

        active_group_ids = list(self.get_controls(iteration_id, default).index)
        ordered_parent_segments = list(
            self.get_risk_segment_details(iteration_id).segments.keys()
        )
        row_index: list[GroupID | RowIndex] = list(active_group_ids)
        col_index: list[RiskSegmentID | RowIndex] = list(ordered_parent_segments)
        if show_total_row:
            row_index.append(RowIndex.TOTAL)
        if show_total_column:
            col_index.append(RowIndex.TOTAL)

        metric_df = metric_df.reindex(
            pd.MultiIndex.from_product([row_index, col_index])
        )

        if scalars_enabled and (
            MetricID.DEV_DLR_BAD_RATE in metric_ids
            or MetricID.DEV_UNT_BAD_RATE in metric_ids
        ):
            target_grid = (
                iteration.default_risk_segment_grid
                if default
                else iteration.risk_segment_grid
            )
            scalar_rows: dict[
                tuple[GroupID | RowIndex, RiskSegmentID | RowIndex], tuple[float, float]
            ] = {}
            for gid in active_group_ids:
                row = target_grid.get(gid, {})
                for parent_seg_id in ordered_parent_segments:
                    mapped_seg_id = row.get(parent_seg_id, parent_seg_id)
                    seg = self.get_risk_segment_details(iteration_id).segments.get(
                        mapped_seg_id
                    )
                    if seg is None:
                        continue
                    scalar_rows[(gid, parent_seg_id)] = (seg.maf_dlr, seg.maf_ulr)

            if show_total_row:
                for parent_seg_id in ordered_parent_segments:
                    seg = self.get_risk_segment_details(iteration_id).segments[
                        parent_seg_id
                    ]
                    scalar_rows[(RowIndex.TOTAL, parent_seg_id)] = (
                        seg.maf_dlr,
                        seg.maf_ulr,
                    )

            if show_total_column:
                for gid in active_group_ids:
                    scalar_rows[(gid, RowIndex.TOTAL)] = (1.0, 1.0)
            if show_total_row and show_total_column:
                scalar_rows[(RowIndex.TOTAL, RowIndex.TOTAL)] = (1.0, 1.0)

            scalar_index = metric_df.index
            maf_dlr_series = (
                pd
                .Series(
                    {idx: values[0] for idx, values in scalar_rows.items()},
                    index=scalar_index,
                    dtype=float,
                )
                .reindex(scalar_index)
                .fillna(1.0)
            )
            maf_ulr_series = (
                pd
                .Series(
                    {idx: values[1] for idx, values in scalar_rows.items()},
                    index=scalar_index,
                    dtype=float,
                )
                .reindex(scalar_index)
                .fillna(1.0)
            )

            if MetricID.DEV_DLR_BAD_RATE in metric_ids:
                metric = all_metrics[MetricID.DEV_DLR_BAD_RATE]
                if metric.pretty_name in metric_df.columns:
                    scalar = self.__scalar_repository.get_scalar(LossRateTypes.DLR)
                    metric_df[metric.pretty_name] *= (
                        maf_dlr_series * scalar.portfolio_scalar
                    ).clip(lower=1.0)

            if MetricID.DEV_UNT_BAD_RATE in metric_ids:
                metric = all_metrics[MetricID.DEV_UNT_BAD_RATE]
                if metric.pretty_name in metric_df.columns:
                    scalar = self.__scalar_repository.get_scalar(LossRateTypes.ULR)
                    metric_df[metric.pretty_name] *= (
                        maf_ulr_series * scalar.portfolio_scalar
                    ).clip(lower=1.0)

        column_name_map = self._risk_segment_name_map(iteration_id)
        metric_outputs: list[GridMetricSummary] = []
        for metric in valid_metrics:
            metric_name = metric.pretty_name
            if metric_name not in metric_df.columns:
                continue

            formatted_series = metric_df[metric_name].map(metric.format)
            grid_df = formatted_series.unstack(level=1)
            grid_df = grid_df.rename(
                columns=lambda value: (
                    "Total"
                    if value == RowIndex.TOTAL
                    else column_name_map.get(t.cast(RiskSegmentID, value), value)
                )
            )

            ordered_columns = [
                column_name_map[seg_id] for seg_id in ordered_parent_segments
            ]
            if show_total_column:
                ordered_columns.append("Total")
            grid_df = grid_df.reindex(columns=ordered_columns)

            metric_outputs.append(
                GridMetricSummary(
                    metric_grid=grid_df,
                    metric_name=metric_name,
                    data_source_names=[
                        self.__data_repository.data_sources[ds_id].label
                        for ds_id in metric.data_source_ids
                        if ds_id in self.__data_repository.data_sources
                    ],
                )
            )

        return metric_outputs, errors, warnings


__all__ = ["IterationsRepository"]
