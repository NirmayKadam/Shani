# AlphaStreams — Quantitative Sentiment Analytics

A Python-based **Event-Driven Analytics Engine** that combines **Financial News Sentiment** (scored by FinBERT AI) with **Real-Time F&O Options Analytics** (Put-Call Ratio, Implied Volatility, Anomaly Detection) to generate actionable trading signals and webhook alerts.

Built with **FastAPI, Celery, Redis, TimescaleDB, SciPy, and PyTorch**.

---

## 💡 Event-Driven Data Pipelines (What It Does)

Alpha Streams works like an institutional quant fund, gathering evidence from three completely independent data pipelines before firing an alert.

### 🌊 Pipeline A: News Sentiment (`/NewsSentiment`)
**The "Confirming Indicator" (Public Narrative)**
- Reads financial news articles about your watchlist (Reliance, NIFTY, etc.).
- Uses the **FinBERT AI model** to syntactically score if the text is *Bullish*, *Bearish*, or *Neutral*.
- Computes **Exponential Moving Averages (EMA)** to mathematically track how overall market emotion is shifting over 24-48 hours.

### 🌊 Pipeline B: Quantitative Math Engine (`/Derivatives`)
**The "Leading Indicator" (Smart Money / Institutional Footprint)**
- Retail investors buy stocks, but institutions hedge with **Derivatives (F&O)**.
- Fetches real-time Options Chains directly from **NSE India**.
- Computes **Put-Call Ratios (PCR)** (Are billionaires placing bearish or bullish bets?).
- Extracts **Implied Volatility (IV)** by perfectly backward-solving the Nobel Prize-winning **Black-Scholes-Merton** formula using `SciPy`.
- Flags **Volume Anomalies** when sudden, massive institutional sweeps occur.

### 🌊 Pipeline C: Machine Learning Forecaster (`/MLForecasting`)
**The "Statistical Engine" (End-of-Day Predictions)**
- Fetches 20-years of OHLCV daily data using `yfinance` across a cross-asset macro watchlist (Indian Indices + Gold, Silver, Brent Crude).
- Converts bare price action into **10 vectorized, scale-invariant features**: RSI 14, EMA 9/21 Percentage Distances, Bollinger Band Widths & Relative Position, Multi-day Returns, Volume Momentum, and a **Sentiment Proxy** (contrarian mean-reversion signal, overridden with live FinBERT EMA sentiment during inference).
- Groups data into 21-day overlapping sequences (forming 3D Tensors).
- Feeds the 21-day sequences into a highly optimized **PyTorch 1D-Convolutional Neural Network (CNN)** (GPU-accelerated via CUDA passthrough).
- Trains with **100 epochs, StepLR learning rate decay, early stopping (patience=10), and best-model checkpoint saving**.
- Predicts a percentage probability (>50% true probability boundary) of whether the stock will open Bullish or Bearish tomorrow.

### The User Flow

```
You configure watchlist symbols in .env (e.g., NIFTY, RELIANCE, HDFCBANK)
                 ↓
Platform automatically fetches news + option chain data every 60-120 seconds
                 ↓
AI scores news sentiment → Moving Average tracks the trend
Options data → PCR, IV, and anomalies are computed
                 ↓
If a signal fires → Webhook alert sent to your endpoint
                 ↓
You query the REST API anytime to see latest analytics:
  GET /v1/sentiment/NIFTY     → Latest FinBERT score
  GET /v1/signals/NIFTY       → Sentiment EMA + crossovers
  GET /v1/events/NIFTY        → Historical timeline of all events
  GET /v1/derivatives/NIFTY   → PCR, IV surface, and anomalies
  GET /v1/predictions/NIFTY   → CNN AI next-day forecast
```

---

## 📊 How Data Flows Through the System

```
NewsAPI ──→ NewsIngestor ──→ [nlp queue] ──→ FinBERT AI ──→ SignalComposer ──→ AlertDispatcher
                                                                  ↑
NSE India ──→ TickIngestor ──→ [derivatives queue] ──→ MetricsComputer ──→ AnomalyDetector ─┘
                  │                                        │
                  ▼                                        ▼
             TickData (DB)                          Redis (PCR/IV cache)
                                                        │
                                                        ▼
                                              FastAPI REST Endpoints
```

Each arrow is a **Celery message queue** — meaning every stage runs independently and can be scaled horizontally.

---

## 🛠 Prerequisites
1. **Docker Desktop** installed (WSL2 recommended for Windows).
2. A `.env` file copied from the template containing `NEWS_API_KEY`.

---

## 🚀 How to Run the Platform

This project relies on a deeply optimized `docker-compose.yml` that mounts your local `/app` directory into the containers. This means **you do not need to rebuild the containers when editing Python code.**

1. **Start the Infrastructure**
   ```bash
   docker compose up -d
   ```
   *(Note: Redis and Postgres ports are now strictly internal to the Docker network for security. They are no longer exposed to your host machine's port 5432 or 6379, preventing Windows permission conflicts.)*

2. **Initialize the Database Schema** (First Boot Only)
   If you destroy the `pg_data` volume, you must instantiate the tables and indexes:
   ```bash
   docker compose cp scripts/init_schema.sql postgres:/tmp/init_schema.sql
   docker compose exec postgres psql -U postgres -d AlphaStreamsDB -f /tmp/init_schema.sql
   ```

3. **Stop the Infrastructure**
   ```bash
   docker compose down
   ```

---

## 🔁 Changing the Python Code (Hot-Reload)
Because the `app/` folder is mounted globally via Docker `volumes`:
- The **FastAPI App** running `uvicorn` will instantly restart itself in `<1ms` the moment you save a file.
- The **Celery Workers** (`worker-nlp`, `worker-signals`, etc.) will instantly use your new Python logic the next time they receive a task from the queue. You don't need to do anything!
*(If you change `requirements.txt` to add a completely new library, only then must you run `docker compose up --build -d`)*.

---

## 🧪 Testing the Pipeline End-to-End

### Test the News Sentiment Pipeline

1. **Clear the Deduplication Cache** (optional—tricks the platform into thinking old news is new):
   ```bash
   docker compose exec redis redis-cli FLUSHALL
   ```

2. **Manually Force Ingestion:**
   ```bash
   docker compose exec app python -m scripts.TestIngest
   ```
   *Give the Celery Worker ~15 seconds to crunch the FinBERT numbers.*

3. **Check the API Endpoints:**
   ```bash
   curl http://localhost:8000/v1/sentiment/RELIANCE
   curl http://localhost:8000/v1/signals/RELIANCE
   curl http://localhost:8000/v1/events/RELIANCE
   ```

### Test the Derivatives Analytics Pipeline

1. **Run the derivatives test script:**
   ```bash
   docker compose exec app python -m scripts.TestDerivatives
   ```
   This fetches live option chain data from **NSE India**, computes PCR and IV, and prints results.

2. **Check the Derivatives API:**
   ```bash
   curl http://localhost:8000/v1/derivatives/NIFTY
   curl http://localhost:8000/v1/derivatives/HDFCBANK
   ```

> **Note:** The NSE API returns live data only during market hours (9:15 AM – 3:30 PM IST, Mon-Fri). Outside these hours, the system gracefully reports "No ticks available" without generating synthetic data.

### Test the ML Prediction Pipeline

1. **Train the CNN model** (first time only):
   ```bash
   docker compose exec app python -m scripts.TrainCNNPredictor
   ```

2. **Trigger predictions manually:**
   ```bash
   docker compose exec app python -c "from app.MLForecasting.Tasks import RunDailyPredictionsTask; RunDailyPredictionsTask.delay()"
   ```

3. **Check the Predictions API:**
   ```bash
   curl http://localhost:8000/v1/predictions/NIFTY
   ```

### Testing Endpoints with Bruno (VS Code Extension)

Instead of using `curl` in the terminal, you can visually test all API endpoints using the **Bruno** extension for VS Code:

1. **Install Bruno:** Open VS Code → Extensions (`Ctrl+Shift+X`) → Search for **"Bruno"** → Install.
2. **Create a new request** in Bruno and point it to any of the following endpoints:

   | Method | URL | Description |
   |--------|-----|-------------|
   | `GET` | `http://localhost:8000/v1/sentiment/NIFTY` | Latest FinBERT sentiment score |
   | `GET` | `http://localhost:8000/v1/signals/NIFTY` | Sentiment EMA + crossover events |
   | `GET` | `http://localhost:8000/v1/events/NIFTY` | Historical event timeline |
   | `GET` | `http://localhost:8000/v1/derivatives/NIFTY` | PCR, IV surface, anomalies |
   | `GET` | `http://localhost:8000/v1/predictions/NIFTY` | CNN AI next-day forecast |

3. **Hit Send** — Bruno will display the JSON response with syntax highlighting, making it easy to inspect the data structure and verify the pipeline outputs.

> **Tip:** Replace `NIFTY` with any watchlist symbol (e.g., `RELIANCE`, `BANKNIFTY`, `TCS`, `HDFCBANK`, `INFY`, `ICICIBANK`) to test different stocks.

---

## ☁️ Cloud Deployment (Production)

To deploy the AlphaStreams to a remote cloud server (e.g., AWS EC2, DigitalOcean Droplet, Linode):

1. **Clone your repository** onto the cloud instance:
   ```bash
   git clone <your-repo-url>
   cd AlphaStreams
   ```
2. **Configure `.env`**:
   Ensure you create a `.env` file containing your production API keys. **Never commit `.env` to Git.**
3. **Start the Engine**:
   Run the platform in detached mode:
   ```bash
   docker compose up --build -d
   ```
4. **Accessing the APIs**:
   By default, the `docker-compose.yml` binds to `0.0.0.0`, meaning your API will be available publicly at `http://<YOUR_SERVER_IP>:8000`. 

**Security Warning:** If deploying to production, it is highly recommended to:
- Use an **Nginx Reverse Proxy** with Let's Encrypt (Certbot) to secure traffic over HTTPS.
- Restrict access to the Flower monitoring dashboard (`Port 5555`) using a firewall (e.g., `ufw`) or by locking `docker-compose.yml` Flower ports back to `127.0.0.1` and using an SSH Tunnel from your local machine.

---

## ⚙️ Key Configuration (.env)

| Variable | Description | Default |
|:---------|:------------|:--------|
| `WATCHLIST_SYMBOLS` | Comma-separated stock symbols to track | `NIFTY,BANKNIFTY,RELIANCE,...` |
| `NEWS_POLL_INTERVAL_SECONDS` | How often to check for new articles | `120` |
| `TICK_POLL_INTERVAL_SECONDS` | How often to fetch option chain data | `60` |
| `NEWS_API_KEY` | Your NewsAPI.org API key | *(required)* |

---

## 🧹 Maintenance: Shrinking Docker Disk Space (WSL2)
If you run `docker compose build` frequently, Docker Desktop's `ext4.vhdx` virtual disk file will expand dynamically but **will not shrink automatically**, silently eating gigabytes of your SSD.

To permanently reclaim the space:

1. Wipe unused dangling images:
   ```bash
   docker system prune -f

   docker system prune -a -f
   ```
2. Shut down WSL entirely from a PowerShell Administrator window:
   ```powershell
   wsl --shutdown
   ```
3. Run `diskpart` in PowerShell to compact the drive (replace the path with your exact user path):
   ```powershell
   diskpart
   
   # Inside the DISKPART> prompt:
   select vdisk file="Path to docker_data.vhdx file"
   attach vdisk readonly
   compact vdisk
   detach vdisk
   exit
   ```
