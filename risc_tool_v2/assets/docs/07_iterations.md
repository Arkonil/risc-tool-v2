# Iterations & Scenarios

Iterations are the core logical engine—the **main crux**—of the Risk Tier Development Tool. They allow you to transform raw data into actionable risk segments by bucketing numerical or categorical variables into distinct tiers.

## The Strategy Tree (Iteration Graph)

The tool uses a graph-based structure to help you build and visualize your risk strategy.
- **Single Variable (Root Node)**: The starting point of any strategy. It creates initial risk buckets using a single variable across the entire population.
- **Double Variable (Child Node)**: A refinement step created from an existing iteration. It allows you to "double-click" into a specific segment and further sub-segment it using a second (or third, etc.) variable.

### Navigation
- **Graph to View**: Click on any node in the graph to view its detailed performance tables.
- **Back to Graph**: Use the **"Back"** button in the top navigation bar to return to the bird's-eye view.
- **Traversing Chains**: Use **"Previous"** and **"Next"** buttons to move through a specific chain of iterations (e.g., from a Root node to its sub-segments).

## Creating an Iteration

When creating a new iteration, you define the parameters for the segmentation algorithm.

### 1. General Configuration
- **Iteration Name**: Assign a custom name for easy identification in reports (e.g., "Bureau Score - Prime Optimization").
- **Variable**: Select the independent variable to be bucketed.
- **Variable Type**: Choose **Numerical** (e.g., Credit Score) or **Categorical** (e.g., Employment Type).
    - **Inference Logic**: 
        - If a **Categorical** column is selected as **Numerical**, the app will automatically default to Categorical treatment.
        - If a **Numerical** column is selected, you can choose to treat it as **Numerical** (for range-based bucketing) or **Categorical** (to group unique numeric values).

### 2. Optimization & Banding
The tool provides two ways to create buckets:
- **Automatic Banding (Optimized)**: The tool uses a specialized algorithm to create clusters based on your **Risk Segment Details** (defined in the Config page). It attempts to align buckets with target bad rates.
- **Generic Banding**: If Automatic Banding is disabled, the tool creates simple percentile-based buckets (for numerical) or individual groups (for categorical).

> [!TIP]
> **Using Scalars**: While using Optimized Banding, you can enable **"Use Scalars"**. This multiplies the observed bad rates by their segment-specific scalar factors during the optimization pass, ensuring buckets accurately reflect ultimate lifetime risk.

### 3. Metric & Variable Validation
You can choose to optimize based on **$ Bad Rate** or **# Bad Rate**.
- **Validation**: The tool validates that the required variables (Bad Amount/Count and Volume/Average Balance) are mapped. 
- **Quick Fix**: If variables are missing, use the **"Set Variables"** button in the sidebar to map them without leaving the creation page.

### 4. Constraints & Outliers
- **Filters**: Select one or more filters. The optimization algorithm will only run on the population that satisfies the combined "AND" mask.
- **Remove Outliers**: Toggle this to exclude records defined as outliers in the **Data Explorer** from the optimization process. This ensures extreme values don't skew your risk tiers.

### 5. Double Variable Specifics
Double Var iterations have additional constraints and behaviors to ensure logical consistency with their parents:
- **Parent Inheritance**: Children always use the **manually edited** version of their parent's risk segmentation as their foundation, ensuring that any manual adjustments made at the root level are preserved in the sub-segments.
- **Fixed Filters**: Children inherit and "lock" the filters used by their parent iteration to maintain population consistency.
- **Upgrade/Downgrade Limits**: These restrict how much a segment's tier can shift relative to its parent. 
    - *Upgrade Limit*: Max tiers a segment can move "up" (RT3 -> RT1).
    - *Downgrade Limit*: Max tiers a segment can move "down" (RT3 -> RT5).
- **Auto Rank Ordering**: Ensures the resulting buckets maintain a monotonic relationship with the target metric.

## The Iteration Interface

Once created, the iteration page provides a detailed breakdown of results.

### Sidebar Controls
The sidebar is your command center for fine-tuning the view:
- **Metric Selector & Reordering**: Choose which performance metrics to display and drag them to reorder the columns in your tables.
- **Filter Selector**: Re-apply different filters to see how the current segmentation performs on different subsets of data.
- **Enable Scalars**: Toggle whether to display annualized (lifetime) or raw bad rates.
- **Editable**: (Double Var only) Enable this to manually reassess specific cells in the grid.
- **Show Previous Iteration Details**: Shows the parent node's metrics alongside the current ones for context.

### Comparison Tables & Grids

The layout of the iteration page varies significantly depending on the type of iteration.

#### Single Variable Iteration View
This view displays exactly two comparison tables:
1.  **Default Range**: Shows the **raw output** of the banding algorithm.
2.  **Editable Range**: A workspace where you can **manually override** boundaries or tier assignments.

#### Double Variable (Grid) View
The Double Var page is more complex, providing a multi-dimensional perspective:
1.  **Segmentation Grid**: A matrix showing the interaction between the parent tiers and the second variable's tiers.
2.  **Metric Grids**: For every selected metric, a dedicated grid is displayed, showing values across the intersection of both variables.
3.  **Default vs. Editable Sections**: The complete set of grids above is repeated—once for the **Default** segmentation and once for the **User Edited** segmentation.

### Strategy Chain Persistence (1D Tables)
At the bottom of every iteration page, the tool displays a **1D Table for each iteration in the current chain** (from the root node down to the current node). 
- **Structure**: These tables provide a summary where rows represent the **Risk Segments** and columns represent all selected **Metrics**. This allows you to track performance across the entire development path simultaneously.

### Double Variable Layout (Split View)
For complex double-variable strategies, you can toggle the **Split View**:
- **List View**: A detailed table showing every intersecting segment line-by-line.
- **Grid View**: A cross-tabulated matrix (Pivot) showing the interaction between the parent variable tiers and the second variable tiers. This is ideal for identifying specific "pockets" of risk or opportunity.
