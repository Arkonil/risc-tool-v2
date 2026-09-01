"""Enumeration of component signatures and options for the change tracking system.

Each component in the application (repositories, view models, etc.) has a unique
signature that identifies it in the change notification system. This allows
components to subscribe to changes from specific dependencies.
"""

import re
from enum import StrEnum, auto


class Signature(StrEnum):
    """Unique identifiers for components in the change tracking system.

    These signatures are used by the ChangeTracker/ChangeNotifier system to
    identify which component triggered a change notification and to manage
    dependency subscriptions.
    """

    # base
    CHANGE_TRACKER = "CHANGE_TRACKER"
    CHANGE_NOTIFIER = "CHANGE_NOTIFIER"
    BASE_REPOSITORY = "BASE_REPOSITORY"

    # Repositories
    DATA_REPOSITORY = "DATA_REPOSITORY"
    METRIC_REPOSITORY = "METRIC_REPOSITORY"
    FILTER_REPOSITORY = "FILTER_REPOSITORY"
    SIMULATION_REPOSITORY = "SIMULATION_REPOSITORY"

    # ViewModels
    DATA_IMPORTER_VIEW_MODEL = "DATA_IMPORTER_VIEW_MODEL"
    DATA_EXPLORER_VIEW_MODEL = "DATA_EXPLORER_VIEW_MODEL"
    METRIC_VIEW_MODEL = "METRIC_VIEW_MODEL"
    FILTER_VIEW_MODEL = "FILTER_VIEW_MODEL"
    SIMULATION_VIEW_MODEL = "SIMULATION_VIEW_MODEL"


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
        """Return the opposite comparison operation."""
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
    """Percentile thresholds available for outlier rule comparison bases."""

    @staticmethod
    def _generate_next_value_(
        name: str, start: int, count: int, last_values: list[str]
    ) -> str:
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
        """Format a percentile option value or raw value as a human-readable string."""
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


class MetricTemplates(StrEnum):
    """Predefined metric templates available in the metric editor."""

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


__all__ = [
    "ComparisonOperation",
    "DataExplorerTabName",
    "LossRateTypes",
    "MetricTemplates",
    "PercentileOptions",
    "Signature",
    "VariableType",
]
