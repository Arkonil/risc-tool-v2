# Home Page

The **Home** page is your entry point into the Risk Tier Tool. It allows you to either start fresh or resume a previous strategy development session.

## Options Available

### 1. New Project (Start Fresh)
- **Action**: Choosing this option redirects you directly to the **Data Importer** page.
- **Use Case**: Use this if you are starting a new risk development project from scratch and intend to define all data sources, metrics, and tiers manually.

### 2. Restore Session (Import JSON)
- **Action**: This option allows you to upload a previously exported `.json` project file.
- **Persistence**: It imports every configuration from your earlier session, including data mappings, manual iteration edits (custom ranges), complex metric formulas, and outlier rules.

## The Import Engine (Safety & Integrity)

The tool places a high emphasis on session integrity. Before a project is imported, it undergoes a rigorous **Validation Pass**.

### Integrity Analysis
The tool analyzes the entire JSON file before allowing the import to guarantee there are no anomalies. This includes checking:
- **Schema Validation**: Ensuring the JSON structure has not been corrupted.
- **Dependency Tracking**: Verifying that every iteration node correctly references its parent and that all metrics exist.

### Self-Healing Pathing
If the tool detects that a data source path in your JSON is no longer valid (e.g., if you moved the source CSV file or changed its name):
1.  **Rectification Prompt**: The app provides a dedicated interface showing the "Old Config" vs. a "New Config" selector.
2.  **Manual Update**: You can point the tool to the new file location within the app to rectify the path.
3.  **Recursive Check**: The tool then re-validates that the new file contains the columns required by your saved metrics and filters.

### Import Anyway (Warning Mode)
If certain filters or metrics can no longer be computed (e.g., a required column is missing from the updated data source), the tool will flag these as **Invalid Items**. You then have the choice to **"Import Anyway"** (to recover the remaining logic) or cancel the import to fix the data source.