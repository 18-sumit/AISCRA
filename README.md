# AISCRA - AI Supply Chain Risk Analysis

End-to-end supply chain risk monitoring for pharma operations, from article ingestion to scored risk events, alternate supplier recommendations, and AI-generated briefings.

## What This Project Includes

- Module 1: Data ingestion from NewsAPI, GNews, RSS, and GDELT with normalization and deduplication
- Module 2: Risk analysis pipeline (Gemini screening + scoring stages)
- Module 3: Alternate supplier recommender for high-risk disruptions
- Module 4: AI agent, briefing generation, and notification delivery
- FastAPI backend for dashboard and API access
- React + Vite frontend dashboard

## Prerequisites

- Python 3.10+
- Node.js 18+
- npm

## Quick Start

### 1) Install dependencies

```bash
pip install -r requirements.txt
pip install -r backend/requirements.txt

cd frontend
npm install
cd ..
```

### 2) Configure environment

Create `.env` in the project root (you can start from `.env.example`) and set at least:

- NEWSAPI_KEY
- GNEWS_KEY
- GOOGLE_API_KEY (or GOOGLE_API_KEY2-5 / GEMINI_KEY)
- DB_TYPE and SQLITE_PATH (or POSTGRES_URL)

Optional for notifications:

- SLACK_WEBHOOK_URL
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, ALERT_EMAIL_TO

### 3) Initialize DB and run one ingestion cycle

```bash
python -m module1.main --init-db
python -m module1.main --once
python -m module1.main --status
```

### 4) Start backend API

```bash
uvicorn backend.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 5) Start frontend dashboard

```bash
cd frontend
npm run dev
```

Dashboard: http://localhost:5173

## Running Full Pipeline

Run all modules in sequence:

```bash
python run_all.py
```

Run continuously every 30 minutes:

```bash
python run_all.py --schedule
```

Custom schedule interval:

```bash
python run_all.py --schedule --interval 60
```

Skip selected modules (example):

```bash
python run_all.py --schedule --skip-m1
```

## Module Commands

### Module 1 - Ingestion

```bash
python -m module1.main --init-db
python -m module1.main --once
python -m module1.main --status
python -m module1.main --schedule
```

### Module 2 - Risk Analysis

```bash
python -m module2.main --run-once
python -m module2.main --status
python -m module2.main --run-continuous
```

### Module 3 - Alternate Recommender

```bash
python -m module3.main --run-once
python -m module3.main --status
```

### Module 4 - AI Agent and Briefings

```bash
python -m module4.main --status
python -m module4.main --chat
python -m module4.main --ask "What are our biggest risks this week?"
python -m module4.main --briefing
python -m module4.main --briefing --send
```

## API Endpoints

### Health

- GET /api/health

### Dashboard

- GET /api/dashboard/stats
- GET /api/dashboard/country-risk
- GET /api/dashboard/feed-summary
- GET /api/dashboard/ingestion-timeline
- GET /api/dashboard/module-status
- GET /api/dashboard/thresholds
- POST /api/dashboard/thresholds

### Articles

- GET /api/articles/
- GET /api/articles/{article_id}

### Suppliers

- GET /api/suppliers/

### Risk Events

- GET /api/risk-events/
- GET /api/risk-events/summary

### Alternates

- GET /api/alternates/
- GET /api/alternates/by-risk-event/{risk_event_id}
- GET /api/alternates/summary

### Agent

- GET /api/agent/status
- POST /api/agent/query
- WS /api/agent/ws

## Project Structure

```text
mjpj/
├── .env.example
├── company_profile.yaml
├── requirements.txt
├── run_all.py
├── backend/
├── frontend/
├── module1/
├── module2/
├── module3/
└── module4/
```

## Switching Company Profile

Update `company_profile.yaml` with your company, supplier list, and keywords, then re-run:

```bash
python -m module1.main --init-db
```

## Notes

- This repository ignores local secrets and runtime artifacts via `.gitignore`.
- Keep `.env` private and commit only `.env.example`.
