# RisC Tool
**Risk Identifier and Segmentation Creator**

![RisC Tool](https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=Streamlit&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)

The **RisC Tool** (Risk Identifier and Segmentation Creator) is a professional-grade platform designed for risk analysts to build, validate, and analyze risk segmentation strategies. It streamlines the workflow from raw data ingestion to generating production-ready code for risk tiering.

---

## 🚀 Key Features

### 📥 Intelligent Data Management
- **Multi-Source Ingestion**: Import multiple CSV and Excel datasets simultaneously.
- **Auto-Alignment**: Automatic concatenation of datasets based on column names with support for inconsistent schemas.
- **Variable Mapping**: Standardize your KPIs (Bad Rates, MOB, Accounts) across different data sources.

### 🔍 Data Exploration & Cleaning
- **Variable Strength**: Analyze Information Value (IV) and distribution for all predictors.
- **Outlier Handling**: Identify and manage extreme values to ensure robust model performance.
- **Interactive Previews**: Real-time inspection of your unified data.

### 🛠️ Flexible Logic Engines
- **Metric Editor**: Define complex, expression-based metrics (e.g., Annualized Bad Rates, Dollar Loss) using a Python-like syntax.
- **Filter Editor**: Build hierarchical population subsets to isolate specific risk cohorts.

### 🔄 Strategy Simulation (Iterations)
- **Rapid Prototyping**: Combine metrics and filters to simulate different risk tiering strategies.
- **Instant Validation**: Get immediate feedback on population volume and risk performance for every iteration.

### 📊 Reporting & Deployment
- **Summary Dashboard**: Compare multiple iterations side-by-side with interactive charts.
- **Code Generation**: Export your finalized risk tiers directly to **SAS** or **Python** code for seamless deployment.

---

## 🛠️ Getting Started

### Prerequisites
- **Python 3.12 or higher**
- [uv](https://github.com/astral-sh/uv) (Recommended for fast dependency management)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Arkonil/risk-tier-tool-v2.git
   cd risk-tier-tool
   ```

2. **Set up the environment:**
   Using `uv`:
   ```bash
   uv venv
   uv sync
   ```
   *Or using standard `pip`:*
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Running the App

Start the Streamlit application by running the `main.py` entry point:

```bash
streamlit run main.py
```

For Windows users, a convenience script is provided:
```powershell
./scripts/run-win.ps1
```

---

## Testing

### Unit / integration tests

Run the non-browser tests with:

```bash
uv run pytest
```

### End-to-end (E2E) UI tests

The E2E tests drive a real browser through **SeleniumBase** and therefore
require a webdriver (Chrome/Edge/Firefox) on the test machine. They are
**opt-in** and **skipped by default** so that running `pytest` never fails
on a machine that lacks a browser or webdriver.

1. **Install the E2E extra** (includes SeleniumBase):
   ```bash
   uv sync --extra e2e
   ```

2. **Run the tests** by opting in with either:
   ```bash
   RUN_E2E=1 uv run pytest tests/e2e
   # or, on Windows (PowerShell):
   $env:RUN_E2E = "1"; uv run pytest tests/e2e
   ```
   ```bash
   uv run pytest tests/e2e --run-e2e
   ```

Without opt-in, the E2E tests are reported as skipped.


---

## 📖 Documentation

The application includes a comprehensive, built-in documentation system. Once the app is running, navigate to the **Documentation** page in the sidebar to access detailed guides on:
- High-level workflows
- Metric and Filter syntax references
- Data cleaning best practices
- Exporting strategies

---

## 🏗️ Project Structure

- `risc_tool/`: Core application logic and Streamlit components.
- `data/`: Local storage for session archives and temporary data.
- `assets/`: UI assets and the raw documentation markdown files.
- `scripts/`: Utility scripts for running and building the project.
- `main.py`: The main entry point for the Streamlit application.

---
