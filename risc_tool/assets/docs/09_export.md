# Export & Implementation

The **Export** page is the final stage of the risk development workflow. It provides multiple ways to save your work, restore previous sessions, and generate code to implement your new risk segmentation in production environments.

The page is divided into three primary categories: **Session Archive**, **Python Code**, and **SAS Code**.

## 1. Session Archive (JSON)

The **Session Archive** is a comprehensive "snapshot" of your entire project. 

### What it contains:
- **Data Configuration**: All column mappings and data source paths.
- **Rules & Logic**: Every metric definition, outlier rule, and filter query.
- **Global Settings**: Risk segment thresholds, color palettes, and scalars.
- **Strategy Tree**: The complete iteration graph, including all manual edits (Custom ranges).

### Use Case:
The downloaded `.json` file can be used later to restore your exact working state on another machine or at a later time. Simply use the **"Restore Session"** option on the home page or data importer to pick up exactly where you left off.

## 2. Implementation Code (Python & SAS)

Once you are satisfied with a risk strategy chain, you can export the logic as production-ready code.

### Selection Logic
The code generator allows you to select a specific **Leaf Node** (the final iteration in a chain). The tool then traverses the tree back to the root and generates code that replicates every level of the segmentation.

### Python Code
The Python export generates a script using **Pandas** and **NumPy**.
- **Data Handling**: Includes code to read your original data sources (CSV/Excel).
- **Processing**: Uses `pd.cut` for numerical ranges and dictionary mapping for categorical groups.
- **Output**: Creates new dataframe columns for each iteration level, ending with your final risk segments.

### SAS Code
The SAS export generates standard **DATA Step** logic.
- **Conditionals**: Uses nested `if-then-else` blocks or `SELECT` statements to assign tiers based on your boundaries.
- **Macros**: Includes optional macro integration for dynamic variable naming.
- **Compatibility**: The generated code is designed to run in standard SAS environments without requiring external dependencies.
