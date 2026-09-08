"""Import JSON Session Archive page for Home feature."""

import streamlit as st
from pydantic import ValidationError

from risc_tool.data.models.asset_path import AssetPath
from risc_tool.data.models.data_source import DataSource, ReadConfig
from risc_tool.data.session import Session
from risc_tool.ui.data_importer.data_importer import data_importer_page
from risc_tool.ui.data_importer.data_selector import (
    delimiter_input_widget,
    filepath_input_widget,
    header_row_input_widget,
    read_mode_input_widget,
    sample_row_count_input_widget,
)


def file_selector(data_source: DataSource, disabled: bool) -> DataSource | None:
    """Render read config inputs for a data source.

    Args:
        data_source: The data source to edit.
        disabled: Whether the inputs are read-only.

    Returns:
        An updated DataSource with the edited config, or None if no filepath is set.
    """
    key = f"file_selector-{data_source.uid}-disabled_{disabled}"

    with st.container(border=True, width="stretch", key=key):
        col1, col2 = st.columns([0.75, 0.25])
        with col1:
            filepath = filepath_input_widget(
                key, data_source.filepath, disabled=disabled
            )
        with col2:
            read_mode = read_mode_input_widget(
                key, data_source.read_config.read_mode, disabled=disabled
            )

        col1, col2, col3 = st.columns(3)
        with col1:
            delimiter = delimiter_input_widget(
                key, data_source.read_config.delimiter, disabled=disabled
            )

        with col2:
            header_row = header_row_input_widget(
                key, data_source.read_config.header_row, disabled=disabled
            )

        with col3:
            sample_row_count = sample_row_count_input_widget(
                key, data_source.read_config.sample_row_count, disabled=disabled
            )

    if filepath is None:
        return None

    return DataSource(
        uid=data_source.uid,
        filepath=filepath,
        label=data_source.label,
        read_config=ReadConfig(
            read_mode=read_mode,
            delimiter=delimiter,
            header_row=header_row,
            sample_row_count=sample_row_count,
        ),
    )


def import_json_page() -> None:
    """Render Session JSON import view."""
    session: Session = st.session_state["session"]
    home_vm = session.home_view_model

    if st.button(
        label="Back",
        icon=":material/arrow_back_ios:",
        type="primary",
    ):
        home_vm.set_home_page_view("welcome")
        st.rerun()

    st.title("Import Session JSON File")

    uploaded_file = st.file_uploader(
        label="Upload JSON File",
        type=[".json"],
        help="This file should contain exported session archive data from a previous session.",
        label_visibility="collapsed",
        accept_multiple_files=False,
        key="json-file-uploader",
    )

    if uploaded_file is None:
        if home_vm.uploaded_file is None:
            return
        else:
            file_obj = home_vm.uploaded_file
    else:
        file_obj = uploaded_file
        home_vm.uploaded_file = file_obj
        # home_vm.uploaded_json_str = file_obj.read().decode("utf-8")

    with st.container(horizontal=True, vertical_alignment="center"):
        st.success(
            f"File uploaded successfully. File name: `{file_obj.name}`",
            icon=":material/check_circle:",
        )

        def clear_uploaded_file():
            """Clear the uploaded file and reset the uploader widget."""
            home_vm.clear_uploaded_file()
            del st.session_state["json-file-uploader"]

        with st.container(border=True, width="content"):
            st.button(
                label="",
                icon=":material/close:",
                type="primary",
                on_click=clear_uploaded_file,
                help="Clear the Uploaded file",
            )

    try:
        raw_session_json, validated_session_json = home_vm.get_jsons()
    except ValidationError as error:
        st.exception(error)
        return
    except ValueError:
        return

    st.success("Session JSON validated successfully!", icon=":material/check_circle:")

    data_source_edits = home_vm.get_data_source_corrections()

    if data_source_edits:
        all_sources_valid = True

        st.divider()

        st.markdown("## Data Source Correction")
        st.markdown(
            "*Following data sources found in the `.json` file are invalid. Please update the read config to complete the import.*"
        )

        for ds_uid, ds_error in data_source_edits.items():
            st.space()

            raw_ds = raw_session_json.data_repository.data_sources[ds_uid]
            validated_ds = validated_session_json.data_repository.data_sources[ds_uid]

            st.markdown(f"#### Data Source #{raw_ds.uid} - {raw_ds.label}")

            col1, col2, col3 = st.columns(
                spec=[0.485, 0.03, 0.485],
                vertical_alignment="center",
            )

            with col1:
                st.markdown("##### Config from `.json` file:")
                file_selector(raw_ds, disabled=True)

            with col2:
                st.image(AssetPath.ARROW_RIGHT, width=50)

            with col3:
                st.markdown("##### Edited Config:")
                updated_ds = file_selector(validated_ds, disabled=False)

            with st.container(horizontal=True, vertical_alignment="center"):
                if ds_error is not None or updated_ds is None:
                    st.error(ds_error, icon=":material/error:")
                    all_sources_valid = False
                else:
                    st.success(
                        f"Validated Data Source: {updated_ds.filepath}",
                        icon=":material/check_circle:",
                    )

                if (
                    st.button(
                        label="Validate",
                        type="primary",
                        key=f"validate-button-{raw_ds.uid}",
                        help="Validate the data source",
                        icon=":material/check_circle:",
                        disabled=updated_ds is None,
                    )
                    and updated_ds is not None
                ):
                    home_vm.validate_data_source(updated_ds)
                    st.rerun()

        if not all_sources_valid:
            return

    (
        invalid_filters,
        invalid_metrics,
        invalid_iterations,
        missing_data_explorer_variables,
        missing_summary_variables,
    ) = home_vm.validate_columns()

    import_button_label = "Import"
    import_button_icon = ":material/done_all:"

    if (
        invalid_filters
        or invalid_metrics
        or invalid_iterations
        or missing_data_explorer_variables
        or missing_summary_variables
    ):
        st.divider()
        st.markdown("## Invalid Items:")
        st.markdown(
            "*Following items cannot be imported from the selected data sources.*"
        )

        import_button_label = "Import Anyway"
        import_button_icon = ":material/warning:"

    if invalid_filters:
        st.markdown("### Filters:")
        for filter_obj in invalid_filters.values():
            with st.container(border=True):
                st.markdown(f"#### Filter #{filter_obj.uid} - {filter_obj.name}")
                st.code(filter_obj.query)
                st.error(
                    "Some columns are not available in the data sources.",
                    icon=":material/error:",
                )

    if invalid_metrics:
        st.markdown("### Metrics:")
        for metric_obj in invalid_metrics.values():
            with st.container(border=True):
                st.markdown(f"#### Metric #{metric_obj.uid} - {metric_obj.name}")
                st.code(metric_obj.query)
                st.error(
                    "Some columns are not available in the data sources.",
                    icon=":material/error:",
                )

    if invalid_iterations:
        st.markdown("### Iterations:")
        for iteration_id in invalid_iterations:
            with st.container(border=True):
                st.markdown(f"#### Iteration #{iteration_id}")
                st.error(
                    "Some columns are not available in the data sources.",
                    icon=":material/error:",
                )

    if missing_data_explorer_variables:
        with st.container(border=True):
            st.error(
                f"Missing variables (used in Data Explorer) in the data sources: {', '.join(missing_data_explorer_variables)}",
                icon=":material/error:",
            )

    if missing_summary_variables:
        with st.container(border=True):
            st.error(
                f"Missing variables (used in Summary) in the data sources: {', '.join(missing_summary_variables)}",
                icon=":material/error:",
            )

    st.divider()

    if st.button(label=import_button_label, icon=import_button_icon, type="primary"):
        session.rebuild_from_json(validated_session_json)

        st.switch_page(data_importer_page)


__all__ = ["import_json_page"]
