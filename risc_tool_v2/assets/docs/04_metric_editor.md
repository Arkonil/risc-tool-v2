# Metric Editor

The Metric Editor allows you to define custom KPIs and performance indicators using a Python-based syntax. These metrics are used to evaluate risk segments and portfolio performance across your projects.

> [!IMPORTANT]
> **Scalar Constraint**: Whatever query you write, the end result must be a **scalar value** (a single number). If an expression returns a list or a column, the tool will trigger a validation error.

## Workflow: Creating a Metric

1.  **Add/Select Metric**: Click **"Create Metric"** in the sidebar or select an existing one to edit.
2.  **Assign Data Sources**: Choose which datasets the metric should be calculated on. Each metric is calculated **only** on the specified sources; other data is ignored.
3.  **Define Name**: Provide a unique name. Duplicate names are not allowed and will block the creation of the metric.
4.  **Write Query**: Use the Code Editor or Template Builder to define the logic.
5.  **Verify**: Click **"Verify"** to test the syntax and calculation on a data sample. Invalid metrics cannot be saved; the tool will show specific error messages to guide your corrections.
6.  **Save**: Once verified, save the metric to add it to your project list.

## Metric Syntax Guide

The editor supports a subset of Python and Pandas syntax tailored for risk analysis.

### Binary Operators
Operators can involve scalars (fixed numbers) and columns (Series). 
- **Broadcasting Logic**: 
    - `Scalar <op> Scalar`: Returns a scalar.
    - `Scalar <op> Column`: Broadcasts the scalar and returns a column.
    - `Column <op> Column`: Performs element-wise calculation and returns a column.
- **Allowed Operators**: `+`, `-`, `*`, `/`, `**` (Power), `%` (Modulo), `//` (Floor Division).

### Element-wise Functions
Functions perform row-by-row operations across multiple arguments. If any argument is a column, the result is a column.
- **`sum(*args)`**: Row-wise sum. E.g., `sum(col1, col2)` returns a column where each row is the sum of `col1` and `col2`.
- **`mean(*args)`, `median(*args)`, `min(*args)`, `max(*args)`, `std(*args)`**: Row-wise statistical calculations across multiple columns/scalars.

### Column Methods (Aggregation Methods)
Methods are called directly on a column using the dot notation (e.g., `column.sum()`). They aggregate data across the entire selected population and **always return a scalar**. This is the most common way to reach a scalar result.

| Method | Description | Pandas Docs |
| :--- | :--- | :--- |
| `all()` | Returns whether all elements are True. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.all.html) |
| `any()` | Returns whether any element is True. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.any.html) |
| `autocorr()` | Computes the lag-N autocorrelation. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.autocorr.html) |
| `corr()` | Computes correlation with another series. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.corr.html) |
| `count()` | Returns number of non-NA/null observations. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.count.html) |
| `cov()` | Computes covariance with another series. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.cov.html) |
| `kurt()` / `kurtosis()` | Returns unbiased kurtosis. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.kurt.html) |
| `max()` | Returns the maximum value in the column. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.max.html) |
| `mean()` | Returns the mean value. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.mean.html) |
| `median()` | Returns the median value. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.median.html) |
| `min()` | Returns the minimum value. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.min.html) |
| `mode()` | Returns the most frequent value. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.mode.html) |
| `prod()` | Returns the product of all values. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.prod.html) |
| `quantile(q)` | Returns the value at a given quantile (0 to 1). | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.quantile.html) |
| `sem()` | Returns unbiased standard error of the mean. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.sem.html) |
| `skew()` | Returns unbiased skewness. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.skew.html) |
| `std()` | Returns unbiased standard deviation. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.std.html) |
| `sum()` | Returns the sum of all values. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.sum.html) |
| `var()` | Returns unbiased variance. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.var.html) |
| `nunique()` | Returns the number of unique elements. | [Reference](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.Series.nunique.html) |

### Special Keywords & Attributes
- **`__MISSING__`**: Represents a null or missing value (`NaN`).
- **`__TOTAL_SIZE__`**: Returns the size of the **filtered population** (dataset filtered by global filters and selected data sources, but not yet segmented by risk tiers).
- **`<column>.size`**: Returns the size of the **segmented group** (the subset of filtered data belonging to the specific segment or bin currently being calculated).

> [!NOTE]
> **Key Difference**: `__TOTAL_SIZE__` is a constant across all rows of an iteration table. `<column>.size` varies based on how many records fall into each specific risk segment. Use `__TOTAL_SIZE__` for overall portfolio penetration and `.size` for segment-specific density.

## Query Examples

Here are some practical examples of common risk metrics defined using the Code Editor:

### 1. Portfolio Penetration (Normalized Volume)
Calculates the density of the current segment relative to the entire filtered population.
```python
`Application_ID`.size / __TOTAL_SIZE__
```

### 2. Dollar-Weighted Average Score
Calculates a risk score weighted by financial exposure.
```python
(`Risk_Score` * `Exposure`).sum() / `Exposure`.sum()
```

### 3. Loss Severity (LGD - Loss Given Default)
Calculates the average loss amount restricted to default events.
```python
`Net_Loss`.sum() / `Default_Flag`.sum()
```

### 4. Tail Risk (95th Percentile)
Identifies the threshold for extreme values in a distribution.
```python
`Utilization_Rate`.quantile(0.95)
```

## Metric Formatting
Customize the display of your scalars using the following options:
- **Is Percentage**: Multiplies the resulting scalar by 100 during calculation and appends a `%` symbol for display.
- **Use Thousand Separator**: Adds commas to large numbers (e.g., `1,234.56`).
- **Decimal Places**: Sets the precision (e.g., `2` for `0.00`).

## Cumulative Metrics
Cumulative metrics aggregate data points across segments sequentially before applying the final calculation.
- **Logic**: In a 1D table with rows [X, Y, Z], the cumulative calculation for row Y will include data from both X and Y.
- **Restriction**: Cumulative metrics can only be used in **1D Iteration-Metric Tables**. They are not supported in 2D Cross-Tabular grids.
- **Use Case**: Determining cumulative capture rates or cumulative bad rate thresholds across ordered risk tiers.

## Metric Templates
Templates provide pre-defined logic for some standard KPIs:
- **Volume**: Returns the count of records in a segment (`col.size`).
- **Approval Rate**: `Approved_Units / Total_Decisioned_Units`.
- **Overall Approval Rate**: `Approved_Units / __TOTAL_SIZE__` (Penetration relative to total filtered population).
- **$ Bad Rate**: Financial risk calculation (`sum of bad exposure / sum of total exposure`).
- **# Bad Rate**: Frequency risk calculation (`sum of bad count / col.size`).

## Managing Metrics
The **Metrics List View** allows you to manage your library:
- **Edit**: Modify query, formatting, or data sources for custom metrics.
- **Duplicate**: Quickly create a new metric using an existing one as a starting point.
- **Delete**: Remove custom metrics. Default metrics are protected and cannot be deleted or edited, but they can be duplicated. To edit one of the default metrics, modify the mappings in the **Variable Selector** section within the Data Importer section.
