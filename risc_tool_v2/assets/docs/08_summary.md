# Summary & Analytics

The **Summary** page is the final analytical layer of the Risk Tier Tool. It allows you to step back from individual development steps and analyze your strategy's overall performance, compare different iterations side-by-side, and perform multi-dimensional aggregations.

The page is organized into three specialized tabs: **Overview**, **Comparison**, and **Pivot**.

## 1. Overview Tab
The **Overview** tab is designed for a focused deep-dive into a single iteration.

### Display
- **Iteration Selector**: Choose the specific iteration from your development tree.
- **Version Toggle**: Select whether to view the **Default** (algorithm-generated) or **Custom** (manually edited) version of that iteration.
- **Performance Table**: Displays all selected metrics for the chosen iteration's risk segments.

### Why use it?
Use the Overview tab when you need to validate the final performance of a specific strategy branch before export, or when you want to see how a target population performs under different banding settings.

## 2. Comparison Tab
The **Comparison** tab allows you to build a custom dashboard to compare multiple iterations or versions side-by-side.

### Management
- **Add View**: Use the "Add New Iteration" section at the bottom to choose an iteration and append it to your dashboard.
- **Removing Views**: Each compared table has a **Delete** (trash icon) button to remove it from the current view.
- **Side-by-Side Switching**: Each table has its own iteration/version selector, allowing you to quickly swap nodes for instant comparison.

### Layout Options
You can control how the dashboard is rendered via the sidebar:
- **List Mode**: Tables are stacked vertically, ideal for detailed line-by-line reading.
- **Grid Mode**: Tables are tiled in a 2-column layout, perfect for comparing 4-6 iterations at a glance on larger screens.

## 3. Pivot Tab
The **Pivot** tab provides a multi-dimensional perspective, allowing you to intersect multiple variables to identify hidden pockets of risk or performance.

### Capabilities
- **Variable Selection**: Use the **Row Variables** and **Column Variables** multiselectors to define the dimensions of your aggregation.
- **Metric Inclusion**: Choose one or more metrics to populate the cells of the pivot table.
- **Dynamic Reordering**: If multiple variables are selected for rows or columns, **draggable sorting lists** appear in the sidebar. You can drag and drop these items to change the hierarchy of the aggregation (e.g., nesting "Score" inside "Income" vs. vice-versa).

> [!NOTE]
> The Pivot tab uses a custom HTML renderer to support complex multi-level headers and clean table styling, ensuring readability even with deep nesting.

## Global Analytical Options
All three tabs share a set of sidebar controls that align the entire analytical view:

- **Metric Selector & Reordering**: Select which performance metrics to display and drag to define their column order.
- **Filter Selector**: Apply search/masking rules globally to the current tab to see how your strategies perform on specific sub-populations.
- **Remove Outliers**: Toggle whether to include or exclude records flagged as outliers in the **Data Explorer**.
- **Enable Scalars**: Toggle between observed bad rates and lifetime (annualized) projected rates.
