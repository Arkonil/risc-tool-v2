"""Enumeration of component signatures for the change tracking system.

Each component in the application (repositories, view models, etc.) has a unique
signature that identifies it in the change notification system. This allows
components to subscribe to changes from specific dependencies.
"""

from enum import StrEnum


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
    DATA_IMPORTER_VIEW_MODEL = "DATA_IMPORTER_VIEW_MODEL"
    DATA_EXPLORER_VIEW_MODEL = "DATA_EXPLORER_VIEW_MODEL"
    VARIABLE_SELECTOR_VIEW_MODEL = "VARIABLE_SELECTOR_VIEW_MODEL"
    METRIC_VIEW_MODEL = "METRIC_VIEW_MODEL"
    FILTER_VIEW_MODEL = "FILTER_VIEW_MODEL"
    CONFIG_VIEW_MODEL = "CONFIG_VIEW_MODEL"
    ITERATION_VIEW_MODEL = "ITERATION_VIEW_MODEL"
    SUMMARY_VIEW_MODEL = "SUMMARY_VIEW_MODEL"
    EXPORT_VIEW_MODEL = "EXPORT_VIEW_MODEL"
    SESSION_ARCHIVE_VIEW_MODEL = "SESSION_ARCHIVE_VIEW_MODEL"
