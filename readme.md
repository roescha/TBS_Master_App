# TBS Master App (v8.3)

[cite_start]The TBS Master App is the automated implementation of the **8-Step Daily Battle Card Pipeline**[cite: 1610, 1891]. [cite_start]It functions as the Layer 3 Master Orchestrator, linking the Systemic Sentinel, Asset Gates, Clean Trade Audit, and the Technical Purity Engine[cite: 1567, 1568, 1569].

[cite_start]This application strictly enforces the Analyst-Operator split: the Python backend handles deterministic math, structural proximity limits, and macro classification (The Algorithmic Track), while the React frontend acts as the Human-in-the-Loop dashboard for visual verification and final execution sign-off[cite: 1480, 1481, 1486].

## Prerequisites

Before running the application, ensure you have the following installed and running:
* **Python 3.9+** (For the FastAPI backend)
* **Node.js 18+** (For the Next.js frontend)
* **Interactive Brokers TWS or IB Gateway** running and authenticated on your machine.
    * **API Settings:** Ensure "Enable ActiveX and Socket Clients" is checked.
    * [cite_start]**Ports:** The system routes `INFO` mode to the paper trading port (`4002`) and `LIVE` mode to the live execution port (`4001`). Ensure your IBKR software matches these port configurations.

---

## 1. Backend Setup (Python / FastAPI)

[cite_start]The backend drives the data retrieval and algorithm execution across IBKR and Yahoo Finance[cite: 1590, 1591].

1.  **Navigate to the project root directory:**
    ```bash
    cd TBS_Master_App
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    # Windows
    python -m venv .venv
    .venv\Scripts\activate

    # macOS/Linux
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: Ensure `kaleido>=1.0.0` is installed for the Technical Engine chart exports.*

4.  **Configure Environment Variables:**
    Create a `.env` file in the root directory. Add any necessary API keys (e.g., if you are using an LLM provider for the AI Analyst Retrieval features).

5.  **Start the Backend Server:**
    ```bash
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
    ```
    The FastAPI backend will now be running at `http://localhost:8000`. You can view the API documentation at `http://localhost:8000/docs`.

---

## 2. Frontend Setup (Next.js / React)

[cite_start]The frontend provides the Operator dashboard to input parameters, view pipeline telemetry, and authorize final execution[cite: 1486, 1487].

1.  **Navigate to the frontend directory:**
    Open a *new* terminal window/tab and navigate to the frontend folder:
    ```bash
    cd TBS_Master_App/tbs-frontend
    ```

2.  **Install Node dependencies:**
    ```bash
    npm install
    ```

3.  **Start the Development Server:**
    ```bash
    npm run dev
    ```
    The Next.js frontend will start. Open your browser and navigate to `http://localhost:3000`.

---

## Usage Guide & Modes

The `PreFlight` dashboard allows you to select the operational mode before engaging the pipeline:

* [cite_start]**INFO Mode:** Used for daily scanning and frictionless research[cite: 1579]. [cite_start]Bypasses the Governor's capacity checks and routes to the IBKR Paper port (`4002`)[cite: 1580, 1617].
* [cite_start]**LIVE Mode:** Used exclusively for capital deployment[cite: 1581]. [cite_start]Enforces the strict 8-step pipeline, routes to the IBKR Live port (`4001`), and requires human sign-off on risk and sizing parameters[cite: 1581, 1582, 1616].
* [cite_start]**Position Monitor:** To evaluate an existing position, provide BOTH the **Average Entry Price** and **Shares Held**[cite: 1619]. [cite_start]The pipeline will bypass the "fail-fast" entry gates, collect all structural threats, and provide a Three-State Recommendation: `EXIT`, `NO ACTION`, or `FIT FOR ADD`[cite: 1620, 1677, 1690, 1691, 1692].

### The Fallback Track (Analyst Overrides)
[cite_start]If the Yahoo Finance API fails or returns masked fundamental data, the pipeline will issue a `HALT`[cite: 1586, 1593, 1596]. [cite_start]You can open the **Manual Track Overrides** section in the UI to inject verified values (e.g., ROIC, WACC, Moat) directly into the engine, fulfilling the Dual-Track Mandate[cite: 1483, 1484, 1599].