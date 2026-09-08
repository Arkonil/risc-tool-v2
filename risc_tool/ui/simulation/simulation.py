import streamlit as st


def simulations_view() -> None:
    pass


simulations_page = st.Page(
    page=simulations_view,
    title="Simulations",
    icon=":material/insights:",
    url_path="/simulations",
)

__all__ = ["simulations_page"]
