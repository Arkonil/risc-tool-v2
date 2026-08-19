import typing as t
from collections import OrderedDict

import polars as pl

from risc_tool.data.models.enums import DefaultMetricNames, Signature, VariableType
from risc_tool.data.models.exceptions import (
    MissingColumnError,
    SampleDataNotLoadedError,
    VariableNotNumericError,
)
from risc_tool.data.models.json_models import MetricJSON, MetricRepositoryJSON
from risc_tool.data.models.metric import (
    DefaultDollarBadRate,
    DefaultUnitBadRate,
    DefaultVolume,
    DollarBadRate,
    Metric,
    UnitBadRate,
    Volume,
)
from risc_tool.data.models.object_id import DataSourceID, MetricID
from risc_tool.data.models.types import ChangeIDs
from risc_tool.data.repositories.base import BaseRepository
from risc_tool.data.repositories.data import DataRepository
from risc_tool.utils.duplicate_name import create_duplicate_name


class MetricRepository(BaseRepository):
    """Repository for managing default and user-defined metrics.

    Attributes:
        metrics: Ordered mapping of MetricID to all (default and user-defined) metrics.
    """

    @property
    def signature(self) -> Signature:
        """Get the component signature for change tracking.

        Returns:
            Signature.METRIC_REPOSITORY
        """
        return Signature.METRIC_REPOSITORY

    def __init__(self, data_repository: DataRepository) -> None:
        """Initialize the MetricRepository with its data dependency.

        Args:
            data_repository: Repository for data sources and lazyframes.
        """
        super().__init__(dependencies=[data_repository])

        # User defined metrics
        self.__user_defined_metrics: OrderedDict[MetricID, Metric] = OrderedDict()

        # Default metrics configuration
        self._var_dev_unt_bad: str | None = None
        self._var_dev_dlr_bad: str | None = None
        self._var_dev_avg_bal: str | None = None
        self._var_tst_unt_bad: str | None = None
        self._var_tst_dlr_bad: str | None = None
        self._var_tst_avg_bal: str | None = None
        self._current_rate_mob: int = 12
        self._lifetime_rate_mob: int = 36
        self._dev_data_source_ids: list[DataSourceID] = []
        self._tst_data_source_ids: list[DataSourceID] = []

        # Cache
        self.__verified_metrics: dict[tuple[str, tuple[DataSourceID, ...]], Metric] = {}

        self.__dev_unt_bad_rate_metric_cache: dict[
            tuple[str, int, tuple[DataSourceID, ...]], Metric
        ] = {}
        self.__dev_dlr_bad_rate_metric_cache: dict[
            tuple[str, str, int, tuple[DataSourceID, ...]], Metric
        ] = {}
        self.__dev_volume_metric_cache: Metric | None = None

        self.__tst_unt_bad_rate_metric_cache: dict[
            tuple[str, tuple[DataSourceID, ...]], Metric
        ] = {}
        self.__tst_dlr_bad_rate_metric_cache: dict[
            tuple[str, str, tuple[DataSourceID, ...]], Metric
        ] = {}
        self.__tst_volume_metric_cache: Metric | None = None

        # Dependencies
        self.__data_repository: DataRepository = data_repository

    def _update_user_defined_metrics(self):
        """Validate user-defined metrics against the data schema.

        Metrics whose queries fail validation for all their data sources are removed.
        """
        metric_ids_to_remove: list[MetricID] = []

        for metric_id, metric in self.__user_defined_metrics.items():
            valid_data_source_ids: list[DataSourceID] = []

            for ds_id in self.__data_repository.data_sources:
                if ds_id not in metric.data_source_ids:
                    continue

                try:
                    all_columns = self.__data_repository.common_columns([ds_id])
                    all_column_names = [col for col, _ in all_columns]
                    metric.validate_query(all_column_names)
                except (SyntaxError, ValueError):
                    pass
                else:
                    valid_data_source_ids.append(ds_id)

            if valid_data_source_ids:
                metric.data_source_ids = valid_data_source_ids
            else:
                metric_ids_to_remove.append(metric_id)

        for metric_id in metric_ids_to_remove:
            del self.__user_defined_metrics[metric_id]

    def _update_default_metrics(self):
        """Refresh default metric variable assignments and data source selections.

        Clears default variables when no valid data sources exist, otherwise
        validates each configured variable against the common schema.
        """
        if not self.__data_repository.has_valid_sources:
            self._var_dev_unt_bad = None
            self._var_dev_dlr_bad = None
            self._var_dev_avg_bal = None
            self._var_tst_unt_bad = None
            self._var_tst_dlr_bad = None
            self._var_tst_avg_bal = None
            self._dev_data_source_ids = []
            self._tst_data_source_ids = []
            return

        self._dev_data_source_ids = list(
            set(self.__data_repository.data_sources.keys())
            & set(self._dev_data_source_ids)
        )
        self._tst_data_source_ids = list(
            set(self.__data_repository.data_sources.keys())
            & set(self._tst_data_source_ids)
        )

        def _validate_var(
            var_name: str | None, ds_ids: list[DataSourceID]
        ) -> str | None:
            """Validate a variable name against the common columns of the data sources.

            Args:
                var_name: The variable name to validate.
                ds_ids: The data sources to check against.

            Returns:
                The validated variable name, or None if invalid or not numeric.
            """
            if not var_name or not ds_ids:
                return None

            common_columns = self.__data_repository.common_columns(ds_ids)
            if (var_name, VariableType.NUMERICAL) not in common_columns:
                return None

            return var_name

        self._var_dev_unt_bad = _validate_var(
            self._var_dev_unt_bad, self._dev_data_source_ids
        )
        self._var_dev_dlr_bad = _validate_var(
            self._var_dev_dlr_bad, self._dev_data_source_ids
        )
        self._var_dev_avg_bal = _validate_var(
            self._var_dev_avg_bal, self._dev_data_source_ids
        )

        self._var_tst_unt_bad = _validate_var(
            self._var_tst_unt_bad, self._tst_data_source_ids
        )
        self._var_tst_dlr_bad = _validate_var(
            self._var_tst_dlr_bad, self._tst_data_source_ids
        )
        self._var_tst_avg_bal = _validate_var(
            self._var_tst_avg_bal, self._tst_data_source_ids
        )

    def _clear_cache(self):
        """Clear all cached and verified metric objects."""
        self.__verified_metrics.clear()
        self.__dev_unt_bad_rate_metric_cache.clear()
        self.__dev_dlr_bad_rate_metric_cache.clear()
        self.__dev_volume_metric_cache = None
        self.__tst_unt_bad_rate_metric_cache.clear()
        self.__tst_dlr_bad_rate_metric_cache.clear()
        self.__tst_volume_metric_cache = None

    def on_dependency_update(self, change_ids: ChangeIDs):
        """Handle data schema updates by revalidating and caching metrics.

        Args:
            change_ids: The change IDs of the updated dependencies.
        """
        self.logger.info(
            "DataRepository updated, updates user defined and default metrics"
        )
        self._update_user_defined_metrics()
        self._update_default_metrics()
        self._clear_cache()

    def validate_metric_input_column(
        self, column_name: str, data_source_ids: list[DataSourceID]
    ):
        """Validate that a column is numeric and available in the given data sources.

        Args:
            column_name: The column to validate.
            data_source_ids: The data sources to check the column against.

        Raises:
            VariableNotNumericError: If the column is categorical.
            MissingColumnError: If the column is not numeric nor present.
        """
        available_columns = self.__data_repository.common_columns(data_source_ids)

        if (column_name, VariableType.CATEGORICAL) in available_columns:
            raise VariableNotNumericError(column_name, "Categorical")

        if (column_name, VariableType.NUMERICAL) not in available_columns:
            raise MissingColumnError(column_name)

    @property
    def var_dev_unt_bad(self) -> str | None:
        """Development untracked bad rate variable name (or None)."""
        return self._var_dev_unt_bad

    @var_dev_unt_bad.setter
    def var_dev_unt_bad(self, value: str | None):
        """Set the development untracked bad rate variable after validation."""
        if value is None:
            self._var_dev_unt_bad = None
            return
        self.validate_metric_input_column(value, self.dev_data_source_ids)
        self._var_dev_unt_bad = value
        self.notify_subscribers()

    @property
    def var_dev_dlr_bad(self) -> str | None:
        """Development dollar bad rate variable name (or None)."""
        return self._var_dev_dlr_bad

    @var_dev_dlr_bad.setter
    def var_dev_dlr_bad(self, value: str | None):
        """Set the development dollar bad rate variable after validation."""
        if value is None:
            self._var_dev_dlr_bad = None
            return
        self.validate_metric_input_column(value, self.dev_data_source_ids)
        self._var_dev_dlr_bad = value
        self.notify_subscribers()

    @property
    def var_dev_avg_bal(self) -> str | None:
        """Development average balance variable name (or None)."""
        return self._var_dev_avg_bal

    @var_dev_avg_bal.setter
    def var_dev_avg_bal(self, value: str | None):
        """Set the development average balance variable after validation."""
        if value is None:
            self._var_dev_avg_bal = None
            return
        self.validate_metric_input_column(value, self.dev_data_source_ids)
        self._var_dev_avg_bal = value
        self.notify_subscribers()

    @property
    def current_rate_mob(self) -> int:
        """Month-on-book used for current rate metrics."""
        return self._current_rate_mob

    @current_rate_mob.setter
    def current_rate_mob(self, value: int):
        """Set the current rate MOB, which must be a positive integer.

        Raises:
            ValueError: If value is not positive.
        """
        if value <= 0:
            raise ValueError("Current rate MOB must be a positive integer.")
        self._current_rate_mob = value
        self.notify_subscribers()

    @property
    def lifetime_rate_mob(self) -> int:
        """Month-on-book used for lifetime rate metrics."""
        return self._lifetime_rate_mob

    @lifetime_rate_mob.setter
    def lifetime_rate_mob(self, value: int):
        """Set the lifetime rate MOB, which must be a positive integer.

        Raises:
            ValueError: If value is not positive.
        """
        if value <= 0:
            raise ValueError("Lifetime rate MOB must be a positive integer.")
        self._lifetime_rate_mob = value
        self.notify_subscribers()

    @property
    def dev_data_source_ids(self) -> list[DataSourceID]:
        """Data source IDs used for development metrics."""
        return self._dev_data_source_ids

    @dev_data_source_ids.setter
    def dev_data_source_ids(self, value: list[DataSourceID]):
        """Set the development data sources and revalidate affected metrics."""
        self._dev_data_source_ids = value
        self._update_user_defined_metrics()
        self._update_default_metrics()
        self._clear_cache()
        self.notify_subscribers()

    @property
    def var_tst_unt_bad(self) -> str | None:
        """Test untracked bad rate variable name (or None)."""
        return self._var_tst_unt_bad

    @var_tst_unt_bad.setter
    def var_tst_unt_bad(self, value: str | None):
        """Set the test untracked bad rate variable after validation."""
        if value is None:
            self._var_tst_unt_bad = None
            return
        self.validate_metric_input_column(value, self.tst_data_source_ids)
        self._var_tst_unt_bad = value
        self.notify_subscribers()

    @property
    def var_tst_dlr_bad(self) -> str | None:
        """Test dollar bad rate variable name (or None)."""
        return self._var_tst_dlr_bad

    @var_tst_dlr_bad.setter
    def var_tst_dlr_bad(self, value: str | None):
        """Set the test dollar bad rate variable after validation."""
        if value is None:
            self._var_tst_dlr_bad = None
            return
        self.validate_metric_input_column(value, self.tst_data_source_ids)
        self._var_tst_dlr_bad = value
        self.notify_subscribers()

    @property
    def var_tst_avg_bal(self) -> str | None:
        """Test average balance variable name (or None)."""
        return self._var_tst_avg_bal

    @var_tst_avg_bal.setter
    def var_tst_avg_bal(self, value: str | None):
        """Set the test average balance variable after validation."""
        if value is None:
            self._var_tst_avg_bal = None
            return
        self.validate_metric_input_column(value, self.tst_data_source_ids)
        self._var_tst_avg_bal = value
        self.notify_subscribers()

    @property
    def tst_data_source_ids(self) -> list[DataSourceID]:
        """Data source IDs used for test metrics."""
        return self._tst_data_source_ids

    @tst_data_source_ids.setter
    def tst_data_source_ids(self, value: list[DataSourceID]):
        """Set the test data sources and revalidate affected metrics."""
        self._tst_data_source_ids = value
        self._update_user_defined_metrics()
        self._update_default_metrics()
        self._clear_cache()
        self.notify_subscribers()

    def __get_ds_labels(self, ds_ids: list[DataSourceID]) -> str:
        """Return a comma-separated label string for the given data sources.

        Args:
            ds_ids: The data source IDs to resolve.

        Returns:
            A comma-separated string of data source labels.
        """
        labels = [
            self.__data_repository.data_sources[ds_id].label
            for ds_id in ds_ids
            if ds_id in self.__data_repository.data_sources
        ]
        return ", ".join(labels)

    @property
    def dev_unt_bad_rate(self) -> Metric:
        """The development untracked bad rate metric (cached).

        Returns:
            The configured dev UnitBadRate metric, or a DefaultUnitBadRate placeholder
            if no variable is set.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.var_dev_unt_bad is None:
            return DefaultUnitBadRate(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.DEV_UNT_BAD_RATE,
                name=DefaultMetricNames.DEV_UNT_BAD_RATE,
            )

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        key = (
            self.var_dev_unt_bad,
            self.current_rate_mob,
            tuple(sorted(self.dev_data_source_ids)),
        )

        if key in self.__dev_unt_bad_rate_metric_cache:
            return self.__dev_unt_bad_rate_metric_cache[key]

        metric = UnitBadRate(
            self.var_dev_unt_bad,
            self.current_rate_mob,
            self.dev_data_source_ids,
            uid=MetricID.DEV_UNT_BAD_RATE,
            name=DefaultMetricNames.DEV_UNT_BAD_RATE,
        )

        all_cols = self.__data_repository.common_columns(self.dev_data_source_ids)
        metric.validate_query(available_columns=[col for col, _ in all_cols])

        self.__dev_unt_bad_rate_metric_cache[key] = metric
        return metric

    @property
    def dev_dlr_bad_rate(self) -> Metric:
        """The development dollar bad rate metric (cached).

        Returns:
            The configured dev DollarBadRate metric, or a DefaultDollarBadRate
            placeholder if variables are not set.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.var_dev_dlr_bad is None or self.var_dev_avg_bal is None:
            return DefaultDollarBadRate(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.DEV_DLR_BAD_RATE,
                name=DefaultMetricNames.DEV_DLR_BAD_RATE,
            )

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        key = (
            self.var_dev_dlr_bad,
            self.var_dev_avg_bal,
            self.current_rate_mob,
            tuple(sorted(self.dev_data_source_ids)),
        )

        if key in self.__dev_dlr_bad_rate_metric_cache:
            return self.__dev_dlr_bad_rate_metric_cache[key]

        metric = DollarBadRate(
            self.var_dev_dlr_bad,
            self.var_dev_avg_bal,
            self.current_rate_mob,
            self.dev_data_source_ids,
            uid=MetricID.DEV_DLR_BAD_RATE,
            name=DefaultMetricNames.DEV_DLR_BAD_RATE,
        )

        all_cols = self.__data_repository.common_columns(self.dev_data_source_ids)
        metric.validate_query(available_columns=[col for col, _ in all_cols])

        self.__dev_dlr_bad_rate_metric_cache[key] = metric
        return metric

    @property
    def dev_volume(self) -> Metric:
        """The development volume metric (cached).

        Returns:
            The configured dev Volume metric, or a DefaultVolume placeholder if
            no common columns are available.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.__dev_volume_metric_cache is not None:
            return self.__dev_volume_metric_cache

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        available_cols = self.__data_repository.common_columns(self.dev_data_source_ids)
        if not available_cols:
            return DefaultVolume(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.DEV_VOLUME,
                name=DefaultMetricNames.DEV_VOLUME,
            )

        first_column = sorted(available_cols)[0][0]

        metric = Volume(
            first_column,
            self.dev_data_source_ids,
            uid=MetricID.DEV_VOLUME,
            name=f"Volume ({self.__get_ds_labels(self.dev_data_source_ids)})",
        )
        metric.validate_query(available_columns=[col for col, _ in available_cols])

        self.__dev_volume_metric_cache = metric
        return metric

    @property
    def tst_unt_bad_rate(self) -> Metric:
        """The test untracked bad rate metric (cached).

        Returns:
            The configured test UnitBadRate metric, or a DefaultUnitBadRate placeholder
            if no variable is set.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.var_tst_unt_bad is None:
            return DefaultUnitBadRate(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.TST_UNT_BAD_RATE,
                name=DefaultMetricNames.TST_UNT_BAD_RATE,
            )

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        key = (
            self.var_tst_unt_bad,
            tuple(sorted(self.tst_data_source_ids)),
        )

        if key in self.__tst_unt_bad_rate_metric_cache:
            return self.__tst_unt_bad_rate_metric_cache[key]

        metric = UnitBadRate(
            self.var_tst_unt_bad,
            current_rate_mob=12,
            data_source_ids=self.tst_data_source_ids,
            uid=MetricID.TST_UNT_BAD_RATE,
            name=DefaultMetricNames.TST_UNT_BAD_RATE,
        )

        all_cols = self.__data_repository.common_columns(self.tst_data_source_ids)
        metric.validate_query(available_columns=[col for col, _ in all_cols])

        self.__tst_unt_bad_rate_metric_cache[key] = metric
        return metric

    @property
    def tst_dlr_bad_rate(self) -> Metric:
        """The test dollar bad rate metric (cached).

        Returns:
            The configured test DollarBadRate metric, or a DefaultDollarBadRate
            placeholder if variables are not set.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.var_tst_dlr_bad is None or self.var_tst_avg_bal is None:
            return DefaultDollarBadRate(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.TST_DLR_BAD_RATE,
                name=DefaultMetricNames.TST_DLR_BAD_RATE,
            )

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        key = (
            self.var_tst_dlr_bad,
            self.var_tst_avg_bal,
            tuple(sorted(self.tst_data_source_ids)),
        )

        if key in self.__tst_dlr_bad_rate_metric_cache:
            return self.__tst_dlr_bad_rate_metric_cache[key]

        metric = DollarBadRate(
            self.var_tst_dlr_bad,
            self.var_tst_avg_bal,
            current_rate_mob=12,
            data_source_ids=self.tst_data_source_ids,
            uid=MetricID.TST_DLR_BAD_RATE,
            name=DefaultMetricNames.TST_DLR_BAD_RATE,
        )

        all_cols = self.__data_repository.common_columns(self.tst_data_source_ids)
        metric.validate_query(available_columns=[col for col, _ in all_cols])

        self.__tst_dlr_bad_rate_metric_cache[key] = metric
        return metric

    @property
    def tst_volume(self) -> Metric:
        """The test volume metric (cached).

        Returns:
            The configured test Volume metric, or a DefaultVolume placeholder if
            no common columns are available.

        Raises:
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if self.__tst_volume_metric_cache is not None:
            return self.__tst_volume_metric_cache

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        available_cols = self.__data_repository.common_columns(self.tst_data_source_ids)
        if not available_cols:
            return DefaultVolume(
                list(self.__data_repository.data_sources.keys()),
                uid=MetricID.TST_VOLUME,
                name=DefaultMetricNames.TST_VOLUME,
            )

        first_column = sorted(available_cols)[0][0]

        metric = Volume(
            first_column,
            self.tst_data_source_ids,
            uid=MetricID.TST_VOLUME,
            name=f"Volume [Test] ({self.__get_ds_labels(self.tst_data_source_ids)})",
        )
        metric.validate_query(available_columns=[col for col, _ in available_cols])

        self.__tst_volume_metric_cache = metric
        return metric

    def validate_metric(
        self, name: str, query: str, data_source_ids: list[DataSourceID]
    ) -> Metric:
        """Validate and build a user-defined metric without storing it.

        Args:
            name: The metric name.
            query: The metric expression.
            data_source_ids: The data sources the metric applies to.

        Returns:
            A validated Metric model.

        Raises:
            ValueError: If the name is reserved or the expression fails to execute.
            SampleDataNotLoadedError: If no valid data sources are loaded.
        """
        if name in DefaultMetricNames:
            raise ValueError(f"Metric name '{name}' is reserved.")

        key = (query, tuple(sorted(data_source_ids)))

        if key in self.__verified_metrics:
            return self.__verified_metrics[key].duplicate(name=name)

        if not self.__data_repository.has_valid_sources:
            raise SampleDataNotLoadedError()

        new_metric = Metric(
            uid=MetricID.TEMPORARY,
            name=name,
            query=query,
            data_source_ids=data_source_ids,
            is_cumulative=False,
        )

        all_columns = self.__data_repository.common_columns(data_source_ids)
        all_column_names = [col for col, _ in all_columns]
        new_metric.validate_query(available_columns=all_column_names)

        # Execution check
        if new_metric.metric_expr is not None:
            try:
                lf = self.__data_repository.get_lazyframe(
                    data_source_ids, limit_per_source=10
                )
                total_size = lf.select(pl.len()).collect().item(0, 0)
                lf = lf.with_columns(pl.lit(total_size).alias("__TOTAL_SIZE__"))
                lf.select(new_metric.metric_expr).collect()
            except (KeyError, ValueError, TypeError) as e:
                raise ValueError(f"Failed to execute metric expression: {e}")

        self.__verified_metrics[key] = new_metric
        return new_metric

    def create_metric(
        self,
        name: str,
        query: str,
        is_cumulative: bool,
        use_thousand_sep: bool,
        is_percentage: bool,
        decimal_places: int,
        data_source_ids: list[DataSourceID],
    ) -> None:
        """Create and store a new user-defined metric.

        Args:
            name: The metric name.
            query: The metric expression.
            is_cumulative: Whether the metric is cumulative.
            use_thousand_sep: Whether to format with thousand separators.
            is_percentage: Whether to format as a percentage.
            decimal_places: Number of decimal places for formatting.
            data_source_ids: The data sources the metric applies to.
        """
        self.logger.info(
            "Creating user-defined metric '%s' with query '%s'", name, query
        )
        new_metric = self.validate_metric(name, query, data_source_ids)

        new_metric.uid = MetricID(
            self._get_new_id(current_ids=self.__user_defined_metrics.keys())
        )
        new_metric.is_cumulative = is_cumulative
        new_metric.use_thousand_sep = use_thousand_sep
        new_metric.is_percentage = is_percentage
        new_metric.decimal_places = decimal_places

        self.__user_defined_metrics[new_metric.uid] = new_metric
        self.notify_subscribers()

    def modify_metric(
        self,
        metric_id: MetricID,
        name: str,
        query: str,
        is_cumulative: bool,
        use_thousand_sep: bool,
        is_percentage: bool,
        decimal_places: int,
        data_source_ids: list[DataSourceID],
    ) -> None:
        """Replace an existing user-defined metric with a new configuration.

        Args:
            metric_id: The ID of the metric to modify.
            name: The new metric name.
            query: The new metric expression.
            is_cumulative: Whether the metric is cumulative.
            use_thousand_sep: Whether to format with thousand separators.
            is_percentage: Whether to format as a percentage.
            decimal_places: Number of decimal places for formatting.
            data_source_ids: The data sources the metric applies to.

        Raises:
            ValueError: If the metric ID does not exist.
        """
        if metric_id not in self.__user_defined_metrics:
            raise ValueError(f"Metric '{metric_id}' not found.")

        self.logger.info("Modifying metric ID %s to name='%s'", metric_id, name)
        modified_metric = self.validate_metric(name, query, data_source_ids)
        modified_metric.uid = metric_id
        modified_metric.is_cumulative = is_cumulative
        modified_metric.use_thousand_sep = use_thousand_sep
        modified_metric.is_percentage = is_percentage
        modified_metric.decimal_places = decimal_places

        self.__user_defined_metrics[metric_id] = modified_metric
        self.notify_subscribers()

    def remove_metric(self, metric_id: MetricID) -> None:
        """Delete a user-defined metric.

        Args:
            metric_id: The ID of the metric to remove.
        """
        self.logger.warning("Removing metric ID %s", metric_id)
        if metric_id in self.__user_defined_metrics:
            del self.__user_defined_metrics[metric_id]
        self.notify_subscribers()

    def duplicate_metric(self, metric_id: MetricID) -> None:
        """Create a copy of a user-defined metric with a unique name.

        Args:
            metric_id: The ID of the metric to duplicate.
        """
        self.logger.info("Duplicating metric ID %s", metric_id)
        if metric_id not in self.metrics:
            return
        metric_name = self.metrics[metric_id].name
        existing_names = {m.name for m in self.metrics.values()}
        new_name = create_duplicate_name(metric_name, existing_names)

        metric_obj = self.metrics[metric_id].duplicate(
            uid=MetricID(self._get_new_id(current_ids=self.metrics.keys())),
            name=new_name,
        )

        self.__user_defined_metrics[metric_obj.uid] = metric_obj
        self.notify_subscribers()

    @property
    def metrics(self) -> OrderedDict[MetricID, Metric]:
        """All available metrics, with default metrics first then user-defined ones.

        Returns:
            An ordered mapping of MetricID to Metric.
        """
        all_metrics: OrderedDict[MetricID, Metric] = OrderedDict()

        all_metrics[self.dev_volume.uid] = self.dev_volume
        all_metrics[self.dev_unt_bad_rate.uid] = self.dev_unt_bad_rate
        all_metrics[self.dev_dlr_bad_rate.uid] = self.dev_dlr_bad_rate

        all_metrics[self.tst_volume.uid] = self.tst_volume
        all_metrics[self.tst_unt_bad_rate.uid] = self.tst_unt_bad_rate
        all_metrics[self.tst_dlr_bad_rate.uid] = self.tst_dlr_bad_rate

        all_metrics.update(self.__user_defined_metrics)
        return all_metrics

    def to_dict(self):
        """Serialize MetricRepository state to MetricRepositoryJSON Pydantic model."""

        return MetricRepositoryJSON(
            metrics={m.uid: m.to_dict() for m in self.__user_defined_metrics.values()},
            var_dev_unt_bad=self._var_dev_unt_bad,
            var_dev_dlr_bad=self._var_dev_dlr_bad,
            var_dev_avg_bal=self._var_dev_avg_bal,
            var_tst_unt_bad=self._var_tst_unt_bad,
            var_tst_dlr_bad=self._var_tst_dlr_bad,
            var_tst_avg_bal=self._var_tst_avg_bal,
            current_rate_mob=self._current_rate_mob,
            lifetime_rate_mob=self._lifetime_rate_mob,
            dev_data_source_ids=self._dev_data_source_ids,
            tst_data_source_ids=self._tst_data_source_ids,
        )

    @classmethod
    def from_dict(
        cls,
        data: MetricRepositoryJSON,
        data_repository: DataRepository,
        errors: t.Literal["ignore", "raise"],
    ):
        """Reconstruct MetricRepository from MetricRepositoryJSON Pydantic model or dict."""
        repo = cls(data_repository=data_repository)
        invalid_metrics: list[tuple[Metric, Exception]] = []

        for metric_json in data.metrics.values():
            metric_obj = Metric.from_dict(metric_json)
            try:
                if data_repository.has_valid_sources:
                    all_columns = data_repository.common_columns(
                        metric_obj.data_source_ids
                    )
                    all_column_names = [col for col, _ in all_columns]
                    if all_column_names:
                        metric_obj.validate_query(all_column_names)
            except ValueError as error:
                if errors == "raise":
                    invalid_metrics.append((metric_obj, error))

                continue

            repo.__user_defined_metrics[metric_obj.uid] = metric_obj

        repo._var_dev_unt_bad = data.var_dev_unt_bad
        repo._var_dev_dlr_bad = data.var_dev_dlr_bad
        repo._var_dev_avg_bal = data.var_dev_avg_bal
        repo._var_tst_unt_bad = data.var_tst_unt_bad
        repo._var_tst_dlr_bad = data.var_tst_dlr_bad
        repo._var_tst_avg_bal = data.var_tst_avg_bal
        repo._current_rate_mob = data.current_rate_mob
        repo._lifetime_rate_mob = data.lifetime_rate_mob
        repo._dev_data_source_ids = data.dev_data_source_ids
        repo._tst_data_source_ids = data.tst_data_source_ids

        repo._update_user_defined_metrics()
        repo._update_default_metrics()

        return repo, invalid_metrics

    @classmethod
    def validate_json(cls, data_repository: DataRepository, data: MetricRepositoryJSON):
        """Return variables referenced in the JSON that are missing from the data schema."""

        invalid_metrics: dict[MetricID, MetricJSON] = {}
        missing_variables: set[str] = set()

        for metric_json in data.metrics.values():
            available_columns = {
                col
                for col, _ in data_repository.common_columns(
                    metric_json.data_source_ids
                )
            }
            if set(metric_json.used_columns) - available_columns:
                invalid_metrics[metric_json.uid] = metric_json

        available_dev_columns = {
            col for col, _ in data_repository.common_columns(data.dev_data_source_ids)
        }
        for var in (
            data.var_dev_unt_bad,
            data.var_dev_dlr_bad,
            data.var_dev_avg_bal,
        ):
            if var is not None and var not in available_dev_columns:
                missing_variables.add(var)

        available_tst_columns = {
            col for col, _ in data_repository.common_columns(data.tst_data_source_ids)
        }
        for var in (
            data.var_tst_unt_bad,
            data.var_tst_dlr_bad,
            data.var_tst_avg_bal,
        ):
            if var is not None and var not in available_tst_columns:
                missing_variables.add(var)

        return invalid_metrics, sorted(missing_variables)
