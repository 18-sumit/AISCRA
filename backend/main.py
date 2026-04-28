"""
backend/main.py
───────────────
FastAPI backend for the Supply Chain Risk Dashboard.
Reads directly from the same SQLite/PostgreSQL DB as Module 1.

Run:
    uvicorn backend.main:app --reload --port 8000
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

load_dotenv()

from backend.routers import articles, dashboard, suppliers, logs, risk_events, alternates, agent

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="Supply Chain Risk API",
    description="Real-time supply chain risk monitoring for pharma companies",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router,     prefix="/api/dashboard",     tags=["Dashboard"])
app.include_router(articles.router,      prefix="/api/articles",      tags=["Articles"])
app.include_router(suppliers.router,     prefix="/api/suppliers",     tags=["Suppliers"])
app.include_router(logs.router,          prefix="/api/logs",          tags=["Logs"])
app.include_router(risk_events.router,   prefix="/api/risk-events",   tags=["Risk Events"])
app.include_router(alternates.router,    prefix="/api/alternates",    tags=["Alternates"])
app.include_router(agent.router,         prefix="/api/agent",         tags=["Agent"])

@app.get("/api/health")
def health():
    return {"status": "ok"}
