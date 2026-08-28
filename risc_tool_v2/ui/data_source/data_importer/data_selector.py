"""UI components for data source selection and configuration in the Data Importer."""

import pathlib
import typing as t

import streamlit as st

from risc_tool_v2.data.core.uid import DataSourceID
from risc_tool_v2.data.core.utils.logging import get_logger
from risc_tool_v2.data.data_source.models.data_source import ReadConfig, ReadMode
from risc_tool_v2.data.session import Session
from risc_tool_v2.ui.data_source.data_importer.data_importer_vm import (
    DataSourceViewModel,
)

logger = get_logger(__name__)


def data_label_input_widget(key: str, label: str = "") -> str:
    widget_label = "##### Data Label:"
    st.markdown(widget_label)
    return st.text_input(
        label=widget_label,
        label_visibility="collapsed",
        value=label,
        key=f"{widget_label}-{key}",
    )


def filepath_input_widget(
    key: str,
    filepath: pathlib.Path | None = None,
    disabled: bool = False,
) -> pathlib.Path | None:
    widget_label = "##### File Path:"
    default_value = str(filepath) if filepath is not None else ""

    st.markdown(widget_label)
    path_text = st.text_input(
        label=widget_label,
        label_visibility="collapsed",
        value=default_value,
        key=f"{widget_label}-{key}",
        disabled=disabled,
    )

    if not path_text:
        return None

    return pathlib.Path(path_text)


def read_mode_input_widget(
    key: str,
    read_mode: ReadMode = "CSV",
    disabled: bool = False,
) -> ReadMode:
    widget_label = "##### Read Mode:"
    options: list[ReadMode] = ["CSV"]
    st.markdown(widget_label)
    return st.selectbox(
        label=widget_label,
        options=options,
        label_visibility="collapsed",
        index=options.index(read_mode),
        key=f"{widget_label}-{key}",
        disabled=disabled,
    )


def delimiter_input_widget(key: str, delimiter: str, disabled: bool = False) -> str:
    widget_label = "##### Delimiter:"
    delimiters = [
        {"name": "comma", "value": ","},
        {"name": "semicolon", "value": ";"},
        {"name": "pipe", "value": "|"},
        {"name": "whitespace", "value": "\\s+"},
    ]

    for i, d in enumerate(delimiters):
        if d["value"] == delimiter:
            current_index = i
            break
    else:
        current_index = 0

    def format_delimiter(delimiter: dict[str, str]) -> str:
        return f"{delimiter['name'].capitalize()} ({delimiter['value']})"

    st.markdown(widget_label)
    selected_option = st.selectbox(
        label=widget_label,
        options=delimiters,
        format_func=format_delimiter,
        label_visibility="collapsed",
        index=current_index,
        key=f"{widget_label}-{key}",
        disabled=disabled,
    )

    return selected_option["value"]


def header_row_input_widget(key: str, header_row: int, disabled: bool = False):
    widget_label = "##### Header Row:"
    st.markdown(widget_label)
    return st.number_input(
        label=widget_label,
        min_value=0,
        max_value=1_048_575,
        value=header_row,
        label_visibility="collapsed",
        key=f"{widget_label}-{key}",
        disabled=disabled,
    )


def sample_row_count_input_widget(
    key: str,
    sample_row_count: int,
    disabled: bool = False,
):
    widget_label = "##### Sample Row Count:"
    st.markdown(widget_label)
    return st.number_input(
        label=widget_label,
        min_value=100,
        value=sample_row_count,
        step=100,
        label_visibility="collapsed",
        key=f"{widget_label}-{key}",
        disabled=disabled,
    )


def file_selector(
    data_source_vm: DataSourceViewModel,
    import_button_label: t.Literal["Add", "Refresh"],
    delete_btn_disabled: bool = False,
):
    session: Session = st.session_state["session"]
    data_importer_view_model = session.data_importer_view_model

    data_source = data_source_vm.data_source
    data_source_uid = data_source.uid
    label = data_source.label
    filepath = data_source.filepath
    read_config = data_source.read_config

    key = f"file_selector-{data_source_uid}"

    with st.container(border=True):
        if data_source_uid == DataSourceID.EMPTY:
            st.subheader("New Data Source")
        else:
            st.subheader(f"Data Source #{data_source_uid}")

        col1, col2 = st.columns([0.75, 0.25])
        with col1:
            label = data_label_input_widget(key, label)
        with col2:
            read_mode = read_mode_input_widget(key, read_config.read_mode)

        filepath = filepath_input_widget(key, filepath)

        col1, col2, col3 = st.columns(3)
        with col1:
            delimiter = delimiter_input_widget(key, read_config.delimiter)
        with col2:
            header_row = header_row_input_widget(key, read_config.header_row)
        with col3:
            sample_row_count = sample_row_count_input_widget(
                key, read_config.sample_row_count
            )

        st.space()

        status_container, import_button_container, delete_button_container = st.columns(
            [0.8, 0.15, 0.05], vertical_alignment="top"
        )

        def import_button_clicked():
            logger.info("User initiated import for data source ID %s", data_source_uid)
            data_importer_view_model.update_data_source(
                data_source_id=data_source_uid,
                filepath=filepath,
                label=label,
                read_config=ReadConfig(
                    read_mode=read_mode,
                    delimiter=delimiter,
                    header_row=header_row,
                    sample_row_count=sample_row_count,
                ),
            )

        def delete_button_clicked():
            logger.info("User deleted data source ID %s", data_source_uid)
            data_importer_view_model.delete_data_source(data_source_uid)

        import_button_container.button(
            label=import_button_label,
            type="secondary" if import_button_label == "Add" else "primary",
            width="stretch",
            key=f"import_button-{key}",
            on_click=import_button_clicked,
            icon=":material/add:"
            if import_button_label == "Add"
            else ":material/refresh:",
        )

        delete_button_container.button(
            label="",
            icon=":material/delete:",
            type="primary",
            width="stretch",
            disabled=delete_btn_disabled,
            key=f"delete_button-{key}",
            on_click=delete_button_clicked,
        )

        if data_source_vm.import_status["status"] == "error":
            status_container.error(
                data_source_vm.import_status["message"].replace("\n", "\n\n"),
                icon=":material/error:",
            )
        elif data_source_vm.import_status["status"] == "success":
            status_container.success(
                data_source_vm.import_status["message"], icon=":material/done_all:"
            )
        elif data_source_vm.import_status["status"] == "loading":
            status_container.info(
                data_source_vm.import_status["message"], icon=":material/info:"
            )


def data_selector():
    session: Session = st.session_state["session"]
    data_importer_view_model = session.data_importer_view_model

    existing_count = 0

    for dsv in data_importer_view_model.data_source_views.values():
        file_selector(dsv, import_button_label="Refresh", delete_btn_disabled=False)
        existing_count += 1

    if data_importer_view_model.showing_empty_data_source:
        file_selector(
            data_importer_view_model.empty_data_source_view,
            import_button_label="Add",
            delete_btn_disabled=(existing_count == 0),
        )
    else:
        with st.container(horizontal_alignment="right", width="stretch"):
            st.button(
                label="Add Data Source",
                type="primary",
                width="content",
                icon=":material/add:",
                on_click=data_importer_view_model.show_empty_data_source,
            )


__all__ = ["data_selector"]
