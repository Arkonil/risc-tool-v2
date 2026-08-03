"""Enumeration of component signatures for the change tracking system.

Each component in the application (repositories, view models, etc.) has a unique
signature that identifies it in the change notification system. This allows
components to subscribe to changes from specific dependencies.
"""

import re
from enum import IntEnum, StrEnum, auto


class RowIndex(IntEnum):
    """Sentinel row index used for summary/total rows in tables.

    Attributes:
        TOTAL: Large integer sentinel identifying the total row.
    """

    TOTAL = 9999


class Colors(StrEnum):
    """Color palette constants for table total rows.

    Attributes:
        F_TABLE_TOTAL_LIGHT: Font color for totals in light theme.
        B_TABLE_TOTAL_LIGHT: Background color for totals in light theme.
        F_TABLE_TOTAL_DARK: Font color for totals in dark theme.
        B_TABLE_TOTAL_DARK: Background color for totals in dark theme.
    """

    F_TABLE_TOTAL_LIGHT = "#7D8088"
    B_TABLE_TOTAL_LIGHT = "#F8F9FB"
    F_TABLE_TOTAL_DARK = "#A0A1A4"
    B_TABLE_TOTAL_DARK = "#1A1C24"


class IterationType(StrEnum):
    """Type of iteration: single-variable or double-variable.

    Attributes:
        SINGLE: Iteration over a single variable.
        DOUBLE: Iteration over two variables (grid layout).
    """

    SINGLE = "single"
    DOUBLE = "double"


class Signature(StrEnum):
    """Unique identifiers for components in the change tracking system.

    These signatures are used by the ChangeTracker/ChangeNotifier system to
    identify which component triggered a change notification and to manage
    dependency subscriptions.

    Attributes:
        CHANGE_TRACKER: Base class for components that track changes.
        CHANGE_NOTIFIER: Base class for components that notify subscribers of changes.
        BASE_REPOSITORY: Base repository class.
        DATA_REPOSITORY: Repository for managing data sources.
        METRIC_REPOSITORY: Repository for managing metrics.
        FILTER_REPOSITORY: Repository for managing filters.
        SCALAR_REPOSITORY: Repository for managing scalar values.
        OPTION_REPOSITORY: Repository for managing options.
        ITERATION_REPOSITORY: Repository for managing iterations.
        DATA_IMPORTER_VIEW_MODEL: View model for the data importer UI.
        DATA_EXPLORER_VIEW_MODEL: View model for the data explorer UI.
        VARIABLE_SELECTOR_VIEW_MODEL: View model for variable selection.
        METRIC_VIEW_MODEL: View model for metrics.
        FILTER_VIEW_MODEL: View model for filters.
        CONFIG_VIEW_MODEL: View model for configuration.
        ITERATION_VIEW_MODEL: View model for iterations.
        SUMMARY_VIEW_MODEL: View model for summary.
        EXPORT_VIEW_MODEL: View model for export.
        SESSION_ARCHIVE_VIEW_MODEL: View model for session archive.
    """

    # base
    CHANGE_TRACKER = "CHANGE_TRACKER"
    CHANGE_NOTIFIER = "CHANGE_NOTIFIER"
    BASE_REPOSITORY = "BASE_REPOSITORY"

    # Repositories
    DATA_REPOSITORY = "DATA_REPOSITORY"
    METRIC_REPOSITORY = "METRIC_REPOSITORY"
    FILTER_REPOSITORY = "FILTER_REPOSITORY"
    SCALAR_REPOSITORY = "SCALAR_REPOSITORY"
    OPTION_REPOSITORY = "OPTION_REPOSITORY"
    ITERATION_REPOSITORY = "ITERATION_REPOSITORY"

    # ViewModels
    HOME_VIEW_MODEL = "HOME_VIEW_MODEL"
    DATA_IMPORTER_VIEW_MODEL = "DATA_IMPORTER_VIEW_MODEL"
    DATA_EXPLORER_VIEW_MODEL = "DATA_EXPLORER_VIEW_MODEL"
    VARIABLE_SELECTOR_VIEW_MODEL = "VARIABLE_SELECTOR_VIEW_MODEL"
    METRIC_VIEW_MODEL = "METRIC_VIEW_MODEL"
    FILTER_VIEW_MODEL = "FILTER_VIEW_MODEL"
    CONFIG_VIEW_MODEL = "CONFIG_VIEW_MODEL"
    ITERATION_VIEW_MODEL = "ITERATION_VIEW_MODEL"
    SUMMARY_VIEW_MODEL = "SUMMARY_VIEW_MODEL"
    EXPORT_VIEW_MODEL = "EXPORT_VIEW_MODEL"
    DOCS_VIEW_MODEL = "DOCS_VIEW_MODEL"


class VariableType(StrEnum):
    """Enumeration of variable types for data exploration and analysis.

    Attributes:
        NUMERICAL: Numeric continuous/discrete variables.
        CATEGORICAL: Qualitative, string, or boolean variables.
    """

    NUMERICAL = "Numerical"
    CATEGORICAL = "Categorical"


class DataExplorerTabName(StrEnum):
    """Enumeration of tab names for the Data Explorer page."""

    IV_ANALYSIS = "IV Analysis"
    OUTLIER_RULES = "Outlier Rules"


class ComparisonOperation(StrEnum):
    """Comparison operators used for filter and outlier rule expressions.

    Attributes:
        GT: Greater-than operator (>).
        GE: Greater-than-or-equal operator (>=).
        LT: Less-than operator (<).
        LE: Less-than-or-equal operator (<=).
    """

    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="

    @property
    def complement(self) -> "ComparisonOperation":
        """Return the opposite comparison operation.

        Returns:
            The ComparisonOperation that negates the current operator
            (e.g. the complement of GT is LE).
        """
        if self == ComparisonOperation.GT:
            return ComparisonOperation.LE
        elif self == ComparisonOperation.GE:
            return ComparisonOperation.LT
        elif self == ComparisonOperation.LT:
            return ComparisonOperation.GE
        elif self == ComparisonOperation.LE:
            return ComparisonOperation.GT
        else:
            raise ValueError(f"Invalid comparison operation: {self}")


class PercentileOptions(StrEnum):
    """Percentile thresholds available for outlier rule comparison bases.

    Members are generated from their names, e.g. PERC_95 produces the value
    "PERC_95".
    """

    @staticmethod
    def _generate_next_value_(
        name: str, start: int, count: int, last_values: list[str]
    ) -> str:
        """Generate the enum value directly from the member name.

        Args:
            name: The name of the member being defined.
            start: The start value passed to enum() (unused).
            count: The ordinal count of the member being created (unused).
            last_values: Previously generated member values (unused).

        Returns:
            The member name itself, used as the enum value.
        """
        return name

    PERC_1 = auto()
    PERC_5 = auto()
    PERC_10 = auto()
    PERC_25 = auto()
    PERC_50 = auto()
    PERC_75 = auto()
    PERC_90 = auto()
    PERC_95 = auto()
    PERC_99 = auto()

    @classmethod
    def format_perc(cls, value: str) -> str:
        """Format a percentile option value or raw value as a human-readable string.

        Args:
            value: The string value to format. May be a PercentileOptions value
                (e.g. "PERC_95") or any other string (e.g. a raw numeric threshold).

        Returns:
            A formatted label such as "95th Percentile", a comma-formatted
            number, or the original value if it cannot be parsed.
        """
        try:
            instance = cls(value)
            m = re.match(r"PERC_(\d+)", instance.value)

            if not m:
                raise ValueError(f"{instance} is not of pattern `PERC_(\\d+)`")

            perc_value = int(m.group(1))

            match instance.value[-1]:
                case "1":
                    return f"{perc_value}st Percentile"
                case "2":
                    return f"{perc_value}nd Percentile"
                case "3":
                    return f"{perc_value}rd Percentile"
                case _:
                    return f"{perc_value}th Percentile"
        except ValueError:
            try:
                return f"{float(value):,}"
            except ValueError:
                return value


class DefaultMetricNames(StrEnum):
    """Default metric names for development and test metrics.

    Attributes:
        DEV_VOLUME: Development volume metric name.
        DEV_UNT_BAD_RATE: Development annualized unit bad rate name.
        DEV_DLR_BAD_RATE: Development annualized dollar bad rate name.
        TST_VOLUME: Test volume metric name.
        TST_UNT_BAD_RATE: Test early unit delinquency rate name.
        TST_DLR_BAD_RATE: Test early dollar delinquency rate name.
    """

    DEV_VOLUME = "Volume"
    DEV_UNT_BAD_RATE = "# Annl. Bad Rate"
    DEV_DLR_BAD_RATE = "$ Annl. Bad Rate"
    TST_VOLUME = "Volume (Test)"
    TST_UNT_BAD_RATE = "# Early Delq. Rate"
    TST_DLR_BAD_RATE = "$ Early Delq. Rate"


class MetricTemplates(StrEnum):
    """Predefined metric templates available in the metric editor.

    Attributes:
        VOLUME: Loan/account volume metric.
        APPROVAL_RATE: Approval rate metric.
        OVERALL_APPROVAL_RATE: Overall approval rate metric.
        DLR_BAD_RATE: Dollar bad rate metric.
        UNT_BAD_RATE: Unit bad rate metric.
    """

    VOLUME = "Volume"
    APPROVAL_RATE = "Approval Rate"
    OVERALL_APPROVAL_RATE = "Overall Approval Rate"
    DLR_BAD_RATE = "$ Bad Rate"
    UNT_BAD_RATE = "# Bad Rate"


class LossRateTypes(StrEnum):
    """Types of loss rates used in risk calculations.

    Attributes:
        DLR: Dollar bad rate ($).
        ULR: Unit bad rate (#).
    """

    DLR = "$ Bad Rate"
    ULR = "# Bad Rate"


class RSDetCol(StrEnum):
    """Column names for the risk segment details editor table.

    Attributes:
        SELECTED: Whether the row is selected.
        ORIG_INDEX: Original row index.
        RISK_SEGMENT: Risk segment name.
        LOWER_RATE: Lower bad rate bound.
        UPPER_RATE: Upper bad rate bound.
        BG_COLOR: Background color.
        FONT_COLOR: Font color.
        MAF_ULR: Maturity adjustment factor for unit bad rate.
        MAF_DLR: Maturity adjustment factor for dollar bad rate.
    """

    SELECTED = "Selected"
    ORIG_INDEX = "Original Index"
    RISK_SEGMENT = "Risk Segment"
    LOWER_RATE = "Lower Bad Rate"
    UPPER_RATE = "Upper Bad Rate"
    BG_COLOR = "Background Color"
    FONT_COLOR = "Font Color"
    MAF_ULR = "Maturity Adjustment Factor (ULR)"
    MAF_DLR = "Maturity Adjustment Factor (DLR)"


class ScalarTableColumn(StrEnum):
    """Column names for the risk scalar factor table.

    Attributes:
        RISK_SEGMENT: Risk segment name.
        MAF: Maturity adjustment factor.
        RISK_SCALAR_FACTOR: Computed risk scalar factor.
    """

    RISK_SEGMENT = "Risk Segment"
    MAF = "Maturity Adjustment Factor"
    RISK_SCALAR_FACTOR = "Risk Scalar Factor"


class RangeColumn(StrEnum):
    """Column names for the iteration group range editor table.

    Attributes:
        SELECTED: Whether the group is selected.
        RISK_SEGMENT: Associated risk segment.
        GROUPS: Group label.
        LOWER_BOUND: Lower bound of the range.
        UPPER_BOUND: Upper bound of the range.
        CATEGORIES: Categories for categorical groups.
    """

    SELECTED = RSDetCol.SELECTED
    RISK_SEGMENT = RSDetCol.RISK_SEGMENT
    GROUPS = "Groups"
    LOWER_BOUND = "Lower Bound"
    UPPER_BOUND = "Upper Bound"
    CATEGORIES = "Categories"


class GridColumn(StrEnum):
    """Column names for the double-variable iteration grid.

    Attributes:
        PREV_RISK_SEGMENT: Previous (development) risk segment column.
        CURR_RISK_SEGMENT: Current (test) risk segment column.
        GROUP_INDEX: Grid group index column.
    """

    PREV_RISK_SEGMENT = f"Previous {RSDetCol.RISK_SEGMENT}"
    CURR_RISK_SEGMENT = f"Current {RSDetCol.RISK_SEGMENT}"
    GROUP_INDEX = "Group Index"


class SummaryPageTabName(StrEnum):
    """Tab names for the summary page.

    Attributes:
        OVERVIEW: Overview tab.
        COMPARISON: Comparison tab.
        PIVOT: Pivot tab.
    """

    OVERVIEW = "Overview"
    COMPARISON = "Comparison"
    PIVOT = "Pivot"


class ExportTabName(StrEnum):
    """Tab names for the export page.

    Attributes:
        SESSION_ARCHIVE: Session archive download tab.
        PYTHON_CODE: Python code generation tab.
        SAS_CODE: SAS code generation tab.
    """

    SESSION_ARCHIVE = "Session Archive"
    PYTHON_CODE = "Python Code"
    SAS_CODE = "SAS Code"
