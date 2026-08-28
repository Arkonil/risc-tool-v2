# Data Explorer

The Data Explorer provides advanced tools to analyze variable strength and manage data quality before moving into strategy development.

## IV Analysis (Information Value)

**IV Analysis** is used to measure the predictive power of independent variables against the target variable. It helps you identify which variables are most useful for building segments.

- **Weight of Evidence (WoE)**: Calculated for each bin of a variable.
- **Information Value (IV)**: A single statistic representing the overall power of the variable.

**Interpretation Guide:**
- **< 0.02**: Useless for prediction.
- **0.02 to 0.1**: Weak predictive power.
- **0.1 to 0.3**: Medium predictive power.
- **> 0.3**: Strong predictive power.

## Outlier Detection Rules

To prevent extreme values from skewing your risk models, the tool allows you to define **Outlier Detection Rules**. These rules identify anomalous records that can then be tagged or excluded from specific iterations.

### Rule Definition
The tool provides a flexible framework (similar to filters) to define what constitutes an outlier for any given variable:

- **Threshold Types**:
    - **Percentile-based**: Automatically identify values at the extreme ends of the distribution. Available options range from **1%, 5%, 10%, 25%, 50%, 75%, 90%, 95%, and 99%**.
    - **Absolute Values**: Manually specify a "Higher than" or "Lower than" fixed value of your choice.
- **Combined Logic**: Multiple rules can be combined to perform complex tagging:
    - **Multi-variable Tagging**: Identify records that are outliers across several different variables simultaneously.
    - **Dual-end Coverage**: For a particular variable, you can add multiple rules (e.g., both a High-end and Low-end threshold) to remove outliers from both sides of the distribution.

> [!NOTE]
> **Robust Percentile Calculation**
> To ensure that only proper outliers are identified, the tool omits the **most frequent value** while calculating percentiles. This prevents common values (such as zero in a sparsity-heavy column) from biasing the identification of true extremes.

### Visualization and Performance
- **Boxplot Charts**: You can choose to visualize variable distributions using interactive boxplot charts to help define your thresholds.
- **Performance Warning**: Note that rendering interactive charts can significantly **degrade performance**. It is recommended to use these charts selectively when investigating specific distributions.

### Management and Visibility
- **Handling**: Records flagged as outliers can be excluded entirely from specific iterations.
- **Visibility**: View the count of outliers across your dataset variables to gauge the extent of data cleaning required.

> [!TIP]
> Use Outlier Detection to identify data entry errors or extreme cases that do not represent your typical population performance.
