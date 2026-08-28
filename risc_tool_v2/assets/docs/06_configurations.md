# Configuration Settings

The Configuration page serves as the global brain for your project. It defines the risk tiers, their visual representation, and the mathematical scalars used to project current performance into lifetime loss expectations.

## Risk Segment Details

This section allows you to define the risk segments (tiers) used throughout the application. These segments are used to categorize records based on their loss rates.

### Default Setup
By default, the tool is initialized with 10 tiers (1A through 5B) covering a range from 0% to +Infinity. Each tier comes with a predefined background and font color for easier identification in iteration tables.

### Editable Attributes
You can customize the following for each segment:
- **Risk Segment Name**: A unique identifier for the tier (e.g., "RT 1A", "Risk Tier 1A").
- **Upper Rate (%)**: The ceiling threshold for this segment.
    - *Note: The Lower Rate is automatically derived from the Upper Rate of the previous segment.*
    - *Note: The value **`None`** (empty) represents **+Infinity**.*
    - *Note: If two adjacent rows have the same Upper Rate, the application will implicitly use the midpoint between the lower limit and the upper limit as the upper limit for the lower risk tier. For more than 2 adjacent rows with the same Upper Rate, the application will divide the range between the lower limit and the upper limit into equal intervals.*
- **Font & Background Colors**: Custom hex colors for UI rendering.

### Editing Workflow
1.  **Direct Editing**: You can edit Segment Names and Upper Rates directly within the table editor.
2.  **Color Selection**: 
    - Select one or more rows using the **Selected** checkboxes.
    - Use the **Font Color** or **Background Color** pickers to choose a color.
    - Click **"Use Color"** to apply the choice to all selected rows.
3.  **Add/Delete**: Use the **"Add Row"** button to create new tiers or **"Delete Selected Rows"** to remove them.
4.  **Reset**: Revert all segments and colors to the project defaults.

> [!WARNING]
> **Name Uniqueness**: All Risk Segment Names must be unique. The application will block saving and display an error message if duplicates are found.

## Scalars & Scalar Calculation

Scalars serve as the mathematical bridge between **observed** performance (at a specific Months on Book) and **projected** ultimate performance (Lifetime).

### How Scalars are Used
In risk modeling, current performance is often a "leading indicator." To see the "ultimate" risk, we must scale current observations to their expected lifetime destination. The tool calculates a **Risk Scalar Factor** for each segment, which is then applied during the iteration process.

### Editable Inputs
- **Current Bad Rate**: The observed portfolio bad rate at the project's current MOB (e.g., at 12 months).
- **Lifetime Bad Rate**: The destination portfolio bad rate at maturity (e.g., at 36 months).
- **Maturity Adjustment Factor (MAF)**: A tier-specific adjustment that accounts for different maturation speeds. Higher risk tiers often "mature" faster than prime ones, requiring an adjustment to the global scalar.

### Mathematical Logic
The calculation ensures that projected loss rates remain logically consistent:

1.  **Portfolio Scalar**:
    `Portfolio Scalar = Lifetime Rate / Current Rate`
    *This represents the average growth factor expected across the entire portfolio.*

2.  **Risk Scalar Factor**:
    `Risk Scalar Factor = max(Portfolio Scalar * MAF, 1.0)`
    *Since bad rates are cumulative, they can only stay the same or increase over time. If the combination of Portfolio Scalar and MAF results in a factor below 1.0, it is automatically capped at 1.0.*

### Separate Metrics
The application maintains independent scalars for:
- **Dollar ($) Bad Rate**: Used for financial exposure and profitability projections.
- **Unit (#) Bad Rate**: Used for account-level frequency and volume projections.
