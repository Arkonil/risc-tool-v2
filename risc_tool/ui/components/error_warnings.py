"""Error and warning display widget for UI components."""

import streamlit as st


def error_and_warning_widget(errors: list[str], warnings: list[str]) -> None:
    """Render errors and warnings expander."""
    if errors or warnings:
        severe = len(errors) > 0
        counts = []
        if errors:
            counts.append(f"{len(errors)} Errors")
        if warnings:
            counts.append(f"{len(warnings)} Warnings")

        count_label = " and ".join(counts)

        with st.expander(count_label, expanded=severe):
            if errors:
                message = "Errors: \n\n" + "\n\n".join(f"- {msg}" for msg in errors)
                st.error(message, icon=":material/error:")

            if warnings:
                message = "Warnings: \n\n" + "\n\n".join(f"- {msg}" for msg in warnings)
                st.warning(message, icon=":material/warning:")


__all__ = ["error_and_warning_widget"]
