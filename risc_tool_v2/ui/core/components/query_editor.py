from code_editor import code_editor  # type: ignore


def query_editor(current_query: str, column_completions: list[dict[str, str | int]]):
    """Render a code editor with Python syntax highlighting and autocomplete completions."""
    code_editor_output = code_editor(
        code=current_query,
        lang="python",
        completions=column_completions,
        replace_completer=True,
        keybindings="vscode",
        props={
            "minLines": 13,
            "fontSize": 16,
            "enableSnippets": False,
            "debounceChangePeriod": 100,
        },
        options={
            "showLineNumbers": True,
        },
        response_mode="debounce",
    )

    return code_editor_output


__all__ = ["query_editor"]
