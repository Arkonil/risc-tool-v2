# Filter Editor

The Filter Editor allows you to isolate specific segments of your data for detailed analysis. By defining logical rules, you can create data "masks" that include or exclude records based on their attributes.

> [!IMPORTANT]
> **Boolean Constraint**: Filter expressions must evaluate to a **boolean series** (True/False for every record). Only records where the expression evaluates to `True` are included in the analysis.

## Workflow: Creating a Filter

1.  **Create Filter**: Click **"Create Filter"** in the sidebar to start a new definition.
2.  **Define Name**: Provide a unique and descriptive name (e.g., "Prime Borrowers"). Duplicate names are not allowed within the project.
3.  **Write Query**: Use the Code Editor to define the logical expression.
4.  **Verify**: Click **"Verify"** to test the query against the loaded data. The tool ensures the query is valid Python/Pandas syntax and returns a boolean mask of the correct length.
5.  **Save**: Once verified, the filter is added to your project library.

## Using Multiple Filters
When working on reports or iterations, you can select **multiple filters simultaneously**. 
- **Application**: All selected filters are combined using a logical **"AND"** operation.
- **Result**: Only records that satisfy **all** selected filters will be included in the final dataset for that specific report or iteration.

## Syntax Guide

Filters use a standard Pandas-eval syntax, providing high flexibility for complex logical structures.

### Comparison Operators
These operators compare column values against scalars or other columns.
- `==` (Equal), `!=` (Not Equal)
- `<` (Less than), `<=` (Less than or equal)
- `>` (Greater than), `>=` (Greater than or equal)

### Logical Operators
Compose complex conditions by combining simple comparisons.
- `and` / `&`: Both conditions must be True.
- `or` / `|`: At least one condition must be True.
- `not` / `~`: Invert the condition.

### Membership Checks
Check if a value exists within a pre-defined set of options.
- **`in`**: `` `Region` in ('North', 'East') ``
- **`not in`**: `` `Segment` not in ('Default', 'Fraud') ``
- **Equality with List**: `` `Status` == ['Approved', 'Pending'] ``

### Handling Null/Missing Values
Identify and handle missing data using built-in methods.
- **`.isna()`**: `` `Income`.isna() `` (True if value is null).
- **`~...isna()`**: `` ~`Region`.isna() `` (True if value is NOT null).

## Handling Columns with Spaces
Always use backticks (`` ` ``) for column names that contain spaces or special characters to ensure correct parsing.
```python
`Credit Score` >= 700
```

## Query Examples

### 1. Simple Range Filter
Includes records within a specific numeric range.
```python
`Age` >= 18 and `Age` <= 35
```

### 2. Categorical Exclusion
Excludes specific products or statuses.
```python
`Product_Type` != 'Venture' and `Loan_Status` == 'Active'
```

### 3. Complex Nested Logic
Combines multiple conditions with precedence.
```python
(`Risk_Score` > 50 or `Income` > 50000) and `State` in ('NY', 'CA', 'TX')
```

### 4. Data Cleanup
Ensures only valid IDs are included.
```python
~`Credit_Link_ID`.isna()
```

## Managing Filters
The **Filter List View** allows you to manage your definitions:
- **Edit**: Update the query or name of existing filters.
- **Duplicate**: Create a copy of a filter to serve as a template for a new one.
- **Delete**: Permanently remove a filter from the project.
