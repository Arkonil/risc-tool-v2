# Data Importer

The Data Importer is the starting point of your project. It allows you to bring your raw data into the tool and prepare it for analysis.

## Supported Formats

The tool supports the following file formats:
- **CSV**: Comma-separated or custom delimiter files.
- **Excel**: `.xlsx` and `.xls` workbooks.

## Importing Multiple Datasets

The tool supports importing multiple datasets simultaneously. This is particularly useful for comparing performance across different populations or time periods within a single project.

### Custom Labels
For each dataset, you can assign a custom label to distinguish them in reports and filters. Common examples include:
- **Development**, **OOT1**, **OOT2**
- **Train**, **Test**, **Validation**

These labels act as a way to identify and group data from different sources (details on Metric Evaluation and Reporting).

### Data Appending Logic
When multiple datasets are provided, the tool **appends (concatenates)** them in the exact order they appear in the data source list. All subsequent calculations and metric evaluations are performed on this combined dataset.

> [!IMPORTANT]
> **Column Names are Case-Sensitive.**
> The tool aligns data based on exact column names. If the same information is present as "Score" in one file and "score" in another, they will be treated as separate variables. Always ensure consistent naming across your files.

#### Missing Columns
If a column exists in one dataset but is missing in another, the tool populates it with **`pd.NA`**. This allows for the flexible use of datasets with slightly different schemas while maintaining a unified analysis.

> [!NOTE]
> The internal column order within individual source files does not matter, as the tool reads and aligns them by name.

## Managing Datasets

The Data Importer provides a streamlined interface to manage your source files:

- **Adding Datasets**: Use the "Add Data Source" button to add new files and configure their import parameters (e.g., Header Row, Sheet Name, Delimiter) and custom labels.
- **Editing Datasets**: To change the file path, label, or import parameters of an existing dataset, first make the changes in the input fields, then click on the **Refresh** button.
- **Removing Datasets**: Click the  **Remove** button to exclude a dataset from the project. This will trigger a recalculation of the unified data and any metrics that depends solely on this source will be deleted.

## Data Preview and Tab View

After datasets are added, the **Data Preview** section allows you to inspect the raw data structure:

- **Tabbed Navigation**: Each dataset is displayed in its own tab, labeled with your custom name.
- **Immediate Feedback**: The preview updates instantly when you change import settings (like header row, delimiter, or sheet name) and click **Refresh**, allowing you to verify the data structure before proceeding.
- **Lazy Loading**: To ensure performance, the preview only loads the first few hundred rows of each dataset (exact number depends on the input field **sample row count**), providing a representative sample without overwhelming the UI.

## Variable Selector

After importing your data, you must use the **Variable Selector** to define the performance metrics and bad rates that will drive risk segmentation. This component maps your raw columns to standardized KPIs used throughout the application.

### Data Source Selection
The Variable Selector allows you to isolate specific datasets for different types of performance monitoring:
- **Target Bad Rate Sources**: Select the "Development" or historical sources where performance has matured (sufficient Months on Book).
- **Early Bad Rate Sources**: Select recent or "Out-of-Time" (OOT) sources to monitor leading indicators of delinquency before they reach full maturity.

Selecting specific sources is critical as it ensures that "Early" immature data does not dilute the calculations for your "Target" performance benchmarks.

### Metric Definitions

#### Target Bad Rates (Development Portfolio)
These metrics establish the ground truth for segmenting risk and building your strategy.

- **# Annl. Bad Rate (Unit Bad Rate)**:
    - **Logic**: `(# Bad Count / # Accounts) * (12 / MOB)`
    - **Significance**: Measures the frequency of default events. Annualizing this rate allows for consistent comparison between portfolios with different performance window lengths.
- **$ Annl. Bad Rate (Dollar Bad Rate)**:
    - **Logic**: `($ Bad Amount / $ Avg Balance) * (12 / MOB)`
    - **Significance**: Measures the financial loss exposure. By using average balance as the denominator, it provides a more accurate view of risk for portfolios with high balance volatility.

#### Performance Adjustments (MOB)
- **MOB (Months on Book)**: The observation window (in months) for the Target population. This is used as the base for annualization.
- **Lifetime MOB**: The total expected duration of the asset. This allows the tool to project the lifetime loss impact based on the observed annualized performance.

#### Early Bad Rates (Leading Indicators)
Provides a real-time pulse on the quality of recent originations that have not yet reached full maturity.

- **# Early Delq. Rate**: Calculated as `# Bad Count / # Accounts`.
- **\$ Early Delq. Rate**: Calculated as `$ Bad Amount / $ Avg Balance`.
- **Significance**: These are "snapshot" metrics used to flag sudden risk shifts in newer cohorts. They are typically compared against historical early performance benchmarks.

### Calculation Workflow
1. **Source Isolation**: The tool filters the combined dataset to include only records from the sources selected for the specific metric category.
2. **Column Aggregation**: The values in the mapped columns are summed across the selected population.
3. **Ratio Derivation**: The numerator (e.g., Bad Count) is divided by the denominator (e.g., Accounts).
4. **Annualization**: Target metrics are multiplied by the factor `(12 / MOB)` to produce the final reported rates.

## Handling Missing Values

To ensure calculation stability across different sources, the tool automatically handles missing values during the import process:
- All null values are converted to a consistent **`pd.NA`** format.
- Numeric columns are converted to nullable integer or float types.
- Categorical columns are handled as standard string/category types.

This normalization allows you to use `__MISSING__` or `.isna()` in your metric and filter expressions without worrying about underlying data source discrepancies.