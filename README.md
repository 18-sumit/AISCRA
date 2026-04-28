# Supply Chain Risk Monitor

AI-powered supply chain risk analysis for pharma companies.
Currently: **Module 1 (Data Ingestion) + Dashboard**.

---

## Quick Start

### 1. Python setup (Module 1 + Backend)

```bash
# Install all Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Initialize database (creates tables, seeds Cipla data)
python -m module1.main --init-db

# Run one ingestion cycle
python -m module1.main --once

# Check what came in
python -m module1.main --status
```

### 2. Start the API backend

```bash
# From the project root
uvicorn backend.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard available at: http://localhost:5173

### 4. Start continuous ingestion (optional)

```bash
# In a separate terminal — runs every 30 minutes
python -m module1.main --schedule
```

---

## Switching Companies

Edit `company_profile.yaml` — change the `company` block, replace
`suppliers` and `keyword_registry` — then re-run:

```bash
python -m module1.main --init-db
```

Zero code changes required.

---

## Project Structure

```
supply_chain_risk/
├── .env                        ← API keys (pre-filled)
├── company_profile.yaml        ← Cipla config — edit to switch companies
├── requirements.txt            ← Module 1 Python deps
│
├── module1/                    ← Data Ingestion
│   ├── main.py                 ← CLI: --init-db | --once | --status | --schedule
│   ├── scheduler.py            ← APScheduler 30-min loop
│   ├── config/company_profile.py
│   ├── db/models.py            ← All 8 ORM tables
│   ├── db/session.py           ← SQLite / PostgreSQL engine
│   ├── db/seed.py              ← Country risk + source credibility seed data
│   ├── ingestion/
│   │   ├── normalizer.py       ← NewsAPI / GNews / RSS / GDELT → unified format
│   │   ├── pipeline.py         ← Track A + B parallel orchestration
│   │   └── track_a/
│   │       ├── newsapi_fetcher.py
│   │       ├── gnews_fetcher.py
│   │       ├── rss_fetcher.py
│   │       └── gdelt_fetcher.py
│   └── dedup/deduplicator.py   ← URL hash + semantic cosine dedup
│
├── backend/                    ← FastAPI backend
│   ├── main.py                 ← FastAPI app + CORS
│   ├── requirements.txt
│   └── routers/
│       ├── dashboard.py        ← /api/dashboard/stats, country-risk, timeline
│       ├── articles.py         ← /api/articles/ (paginated, filterable)
│       ├── suppliers.py        ← /api/suppliers/
│       └── logs.py             ← /api/logs/
│
├── frontend/                   ← React + Vite dashboard
│   ├── src/
│   │   ├── App.jsx             ← Main layout + navigation
│   │   ├── components/
│   │   │   ├── StatsBar.jsx         ← 6 live stat cards
│   │   │   ├── ArticleFeed.jsx      ← Paginated feed + article detail pane
│   │   │   ├── SupplierPanel.jsx    ← Supplier list by tier + criticality
│   │   │   ├── CountryRiskTable.jsx ← 48 countries with risk scores
│   │   │   ├── FetchLogsPanel.jsx   ← Ingestion run history
│   │   │   ├── IngestionChart.jsx   ← 14-day stacked bar chart
│   │   │   └── SourceBreakdown.jsx  ← Top news sources
│   │   └── hooks/useApi.js     ← Auto-refreshing API hook
│
└── tests/
    └── test_module1.py         ← 43 unit tests (run: pytest tests/ -v)
```

---

## Dashboard Views

| View | What you see |
|------|-------------|
| **Live Feed** | Real-time article stream (Track A + B), click any article for full detail with impact chain, Gemini confidence, affected suppliers |
| **Suppliers** | All 16 Cipla suppliers grouped by tier, with dependency weight bars and criticality indicators |
| **Country Risk** | 48 countries with risk scores (0–100), filterable by category |
| **Analytics** | 14-day ingestion volume chart + top source breakdown + module status |
| **Ingest Logs** | Every fetch run: articles fetched/new/relevant, duration, errors |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/dashboard/stats` | Top-level counts (auto-refreshes every 30s) |
| `GET /api/dashboard/country-risk` | All country risk scores |
| `GET /api/dashboard/ingestion-timeline` | Articles per day (14 days) |
| `GET /api/dashboard/feed-summary` | Top source domains |
| `GET /api/articles/?fetch_type=targeted&page=1` | Paginated articles |
| `GET /api/articles/{id}` | Single article detail |
| `GET /api/suppliers/` | All active suppliers |
| `GET /api/logs/` | Recent fetch run logs |
| `GET /api/health` | Health check |

Full interactive docs: http://localhost:8000/docs

---

## Modules Roadmap

- ✅ **Module 1** — Dual-track data ingestion (Track A + Track B)
- ⬛ **Module 2** — Risk Analysis Engine (7-stage ML pipeline)
- ⬛ **Module 3** — Alternate Supplier Recommender
- 🟡 **Module 4** — Dashboard + AI Agent (frontend done, agent pending)
