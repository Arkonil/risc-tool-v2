import re
import textwrap

TAB = "    "


def wrap_text(
    text: str,
    width: int = 70,
    *,
    initial_indent: str = "",
    subsequent_indent: str = "",
    expand_tabs: bool = True,
    tabsize: int = 8,
    replace_whitespace: bool = True,
    fix_sentence_endings: bool = False,
    break_long_words: bool = True,
    break_on_hyphens: bool = True,
    drop_whitespace: bool = True,
    max_lines: int | None = None,
    placeholder: str = " [...]",
) -> list[str]:
    """Wraps text to a specified width, preserving content within double quotes."""
    # Find all quoted sections
    quoted_sections: list[str] = re.findall(r"\"(.*?)\"", text)

    # Replace quoted sections with placeholders to avoid wrapping them
    quote_placeholder_map: dict[str, str] = {}
    for i, quoted_text in enumerate(quoted_sections):
        placeholder = f"__QUOTE_PLACEHOLDER_{i}__"
        quote_placeholder_map[placeholder] = quoted_text
        text = text.replace(f'"{quoted_text}"', placeholder, 1)

    # Wrap the remaining text (non-quoted parts)
    wrapped_text = textwrap.fill(
        text,
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        expand_tabs=expand_tabs,
        tabsize=tabsize,
        replace_whitespace=replace_whitespace,
        fix_sentence_endings=fix_sentence_endings,
        break_long_words=break_long_words,
        break_on_hyphens=break_on_hyphens,
        drop_whitespace=drop_whitespace,
        max_lines=max_lines,
        placeholder=placeholder,
    )

    # Restore the quoted sections
    for placeholder, original_quoted_text in quote_placeholder_map.items():
        wrapped_text = wrapped_text.replace(placeholder, f'"{original_quoted_text}"')

    return wrapped_text.splitlines()


__all__ = ["wrap_text", "TAB"]
