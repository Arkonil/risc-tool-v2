import pathlib
import re

docs_dir = pathlib.Path("risc_tool/assets/docs")

# Pattern to match the horizontal rule and the navigation links
# It looks for '---' followed by optional whitespace, then markdown links
pattern = re.compile(r"---\s*\n\s*\n\[.*?\n?", re.DOTALL)

for md_file in docs_dir.glob("*.md"):
    content = md_file.read_text(encoding="utf-8")

    # We want to remove the LAST occurrence of '---' and everything after it
    # if it matches the navigation pattern.

    parts = content.split("---")
    if len(parts) > 1:
        # Check the last part for navigation links
        last_part = parts[-1]
        if "[" in last_part and "]" in last_part and "(" in last_part:
            # Join all parts except the last one with '---'
            new_content = "---".join(parts[:-1]) + "---\n"
            md_file.write_text(new_content, encoding="utf-8")
            print(f"Scrubbed {md_file.name}")
        else:
            print(f"Skipped {md_file.name} (No nav links found in last section)")
    else:
        print(f"Skipped {md_file.name} (No hr found)")
