"""
module1/db/seed.py
──────────────────
Seeds the following tables on --init-db:
  • country_risk       — risk scores for all major sourcing countries
  • source_credibility — domain-level credibility scores for all known sources
  • suppliers          — loaded from company_profile.yaml
  • keyword_registry   — loaded from company_profile.yaml

Re-seeding is idempotent: existing rows are updated, new rows inserted.
"""

import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from module1.db.models import CountryRisk, KeywordRegistry, SourceCredibility, Supplier

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  COUNTRY RISK SCORES
#  0–100: 0=perfectly stable, 100=active conflict/sanctioned
#  Categories: stable(0-24) | moderate(25-49) | high(50-74) | critical(75-100)
# ─────────────────────────────────────────────────────────────────────────────
COUNTRY_RISK_DATA = [
    # Active conflict / sanctioned
    {"code": "RU", "name": "Russia",          "score": 92, "category": "critical", "notes": "Ukraine war, heavy sanctions"},
    {"code": "IR", "name": "Iran",             "score": 90, "category": "critical", "notes": "US/EU sanctions, regional conflict"},
    {"code": "MM", "name": "Myanmar",          "score": 85, "category": "critical", "notes": "Military coup, civil conflict"},
    {"code": "AF", "name": "Afghanistan",      "score": 95, "category": "critical", "notes": "Taliban, sanctions, instability"},
    {"code": "SY", "name": "Syria",            "score": 88, "category": "critical", "notes": "Civil war, sanctions"},
    {"code": "YE", "name": "Yemen",            "score": 90, "category": "critical", "notes": "Civil war, Red Sea conflict"},
    {"code": "LY", "name": "Libya",            "score": 80, "category": "critical", "notes": "Political instability"},
    {"code": "KP", "name": "North Korea",      "score": 99, "category": "critical", "notes": "Full sanctions"},
    {"code": "VE", "name": "Venezuela",        "score": 78, "category": "critical", "notes": "Sanctions, political crisis"},

    # High risk
    {"code": "CN", "name": "China",            "score": 58, "category": "high",     "notes": "Geopolitical tension, trade war risk, regulatory uncertainty"},
    {"code": "PK", "name": "Pakistan",         "score": 65, "category": "high",     "notes": "Economic crisis, political instability"},
    {"code": "BD", "name": "Bangladesh",       "score": 52, "category": "high",     "notes": "Political unrest, flood risk"},
    {"code": "EG", "name": "Egypt",            "score": 55, "category": "high",     "notes": "Economic stress, Suez proximity"},
    {"code": "NG", "name": "Nigeria",          "score": 62, "category": "high",     "notes": "Currency crisis, security issues"},
    {"code": "ET", "name": "Ethiopia",         "score": 68, "category": "high",     "notes": "Conflict in northern regions"},
    {"code": "UA", "name": "Ukraine",          "score": 95, "category": "critical", "notes": "Active war with Russia"},
    {"code": "IQ", "name": "Iraq",             "score": 72, "category": "high",     "notes": "Political instability, militia activity"},
    {"code": "SD", "name": "Sudan",            "score": 85, "category": "critical", "notes": "Civil war 2023"},
    {"code": "TW", "name": "Taiwan",           "score": 55, "category": "high",     "notes": "Cross-strait tensions with China"},
    {"code": "SA", "name": "Saudi Arabia",     "score": 48, "category": "moderate", "notes": "Regional conflict exposure, oil price volatility"},

    # Moderate risk
    {"code": "IN", "name": "India",            "score": 32, "category": "moderate", "notes": "Stable but monsoon, regulatory risk"},
    {"code": "TR", "name": "Turkey",           "score": 45, "category": "moderate", "notes": "Inflation, regional geopolitics"},
    {"code": "MX", "name": "Mexico",           "score": 42, "category": "moderate", "notes": "Cartel activity, US tariff exposure"},
    {"code": "BR", "name": "Brazil",           "score": 38, "category": "moderate", "notes": "Political polarisation, Amazon risk"},
    {"code": "ZA", "name": "South Africa",     "score": 40, "category": "moderate", "notes": "Load shedding, logistics issues"},
    {"code": "ID", "name": "Indonesia",        "score": 30, "category": "moderate", "notes": "Earthquake risk, regulatory complexity"},
    {"code": "MY", "name": "Malaysia",         "score": 28, "category": "moderate", "notes": "Moderate political risk, storm exposure"},
    {"code": "TH", "name": "Thailand",         "score": 30, "category": "moderate", "notes": "Political instability risk, flood prone"},
    {"code": "PL", "name": "Poland",           "score": 35, "category": "moderate", "notes": "NATO eastern flank, Ukraine proximity"},
    {"code": "IL", "name": "Israel",           "score": 60, "category": "high",     "notes": "Active regional conflict 2023–24"},
    {"code": "AE", "name": "UAE",              "score": 35, "category": "moderate", "notes": "Gulf stability, Iran proximity"},

    # Stable / low risk
    {"code": "DE", "name": "Germany",          "score": 15, "category": "stable",   "notes": "Energy transition risk, otherwise stable"},
    {"code": "CH", "name": "Switzerland",      "score": 5,  "category": "stable",   "notes": "Highly stable"},
    {"code": "US", "name": "United States",    "score": 12, "category": "stable",   "notes": "Trade policy risk under tariff regimes"},
    {"code": "GB", "name": "United Kingdom",   "score": 14, "category": "stable",   "notes": "Post-Brexit supply chain complexity"},
    {"code": "FR", "name": "France",           "score": 12, "category": "stable",   "notes": "Political polarisation risk, otherwise stable"},
    {"code": "JP", "name": "Japan",            "score": 10, "category": "stable",   "notes": "Earthquake risk, otherwise very stable"},
    {"code": "KR", "name": "South Korea",      "score": 18, "category": "stable",   "notes": "North Korea proximity risk"},
    {"code": "AU", "name": "Australia",        "score": 8,  "category": "stable",   "notes": "Very stable"},
    {"code": "CA", "name": "Canada",           "score": 8,  "category": "stable",   "notes": "Very stable"},
    {"code": "SG", "name": "Singapore",        "score": 5,  "category": "stable",   "notes": "Very stable, key logistics hub"},
    {"code": "NL", "name": "Netherlands",      "score": 10, "category": "stable",   "notes": "Rotterdam port critical, otherwise stable"},
    {"code": "BE", "name": "Belgium",          "score": 10, "category": "stable",   "notes": "Antwerp port, otherwise stable"},
    {"code": "SE", "name": "Sweden",           "score": 8,  "category": "stable",   "notes": "Stable"},
    {"code": "FI", "name": "Finland",          "score": 12, "category": "stable",   "notes": "Russia border, NATO member"},
    {"code": "DK", "name": "Denmark",          "score": 8,  "category": "stable",   "notes": "Stable"},
    {"code": "NO", "name": "Norway",           "score": 7,  "category": "stable",   "notes": "Very stable, energy exporter"},
    {"code": "ES", "name": "Spain",            "score": 15, "category": "stable",   "notes": "Stable"},
    {"code": "IT", "name": "Italy",            "score": 18, "category": "stable",   "notes": "Political fragility, debt risk"},
    {"code": "IE", "name": "Ireland",          "score": 8,  "category": "stable",   "notes": "Pharma hub, stable"},
]


# ─────────────────────────────────────────────────────────────────────────────
#  SOURCE CREDIBILITY SCORES
#  0–100: higher = more credible / more weight in risk scoring
#  Tier 1 (85–100): wire services, government bodies
#  Tier 2 (60–84): established trade/business publications
#  Tier 3 (20–59): regional outlets, blogs, unknown
# ─────────────────────────────────────────────────────────────────────────────
SOURCE_CREDIBILITY_DATA = [
    # Tier 1 — Wire services & government
    {"domain": "reuters.com",            "score": 95, "category": "tier1", "type": "wire_service"},
    {"domain": "apnews.com",             "score": 93, "category": "tier1", "type": "wire_service"},
    {"domain": "bloomberg.com",          "score": 90, "category": "tier1", "type": "wire_service"},
    {"domain": "fda.gov",                "score": 98, "category": "tier1", "type": "government"},
    {"domain": "who.int",                "score": 92, "category": "tier1", "type": "government"},
    {"domain": "cdc.gov",                "score": 92, "category": "tier1", "type": "government"},
    {"domain": "ema.europa.eu",          "score": 95, "category": "tier1", "type": "government"},
    {"domain": "bbc.com",                "score": 88, "category": "tier1", "type": "wire_service"},
    {"domain": "bbc.co.uk",              "score": 88, "category": "tier1", "type": "wire_service"},
    {"domain": "ft.com",                 "score": 88, "category": "tier1", "type": "wire_service"},
    {"domain": "wsj.com",                "score": 87, "category": "tier1", "type": "wire_service"},

    # Tier 2 — Trade publications & established business media
    {"domain": "fiercepharma.com",       "score": 82, "category": "tier2", "type": "trade_pub"},
    {"domain": "pharmabiz.com",          "score": 75, "category": "tier2", "type": "trade_pub"},
    {"domain": "pharmaceutical-technology.com", "score": 78, "category": "tier2", "type": "trade_pub"},
    {"domain": "drugtopics.com",         "score": 72, "category": "tier2", "type": "trade_pub"},
    {"domain": "supplychaindive.com",    "score": 80, "category": "tier2", "type": "trade_pub"},
    {"domain": "freightwaves.com",       "score": 78, "category": "tier2", "type": "trade_pub"},
    {"domain": "oilprice.com",           "score": 72, "category": "tier2", "type": "trade_pub"},
    {"domain": "chemweek.com",           "score": 75, "category": "tier2", "type": "trade_pub"},
    {"domain": "economictimes.indiatimes.com", "score": 78, "category": "tier2", "type": "regional"},
    {"domain": "businessstandard.com",   "score": 75, "category": "tier2", "type": "regional"},
    {"domain": "business-standard.com",  "score": 75, "category": "tier2", "type": "regional"},
    {"domain": "livemint.com",           "score": 74, "category": "tier2", "type": "regional"},
    {"domain": "aljazeera.com",          "score": 78, "category": "tier2", "type": "wire_service"},
    {"domain": "foreignpolicy.com",      "score": 82, "category": "tier2", "type": "trade_pub"},
    {"domain": "nikkei.com",             "score": 83, "category": "tier2", "type": "regional"},
    {"domain": "asia.nikkei.com",        "score": 82, "category": "tier2", "type": "regional"},
    {"domain": "scmp.com",               "score": 76, "category": "tier2", "type": "regional"},
    {"domain": "thediplomat.com",        "score": 78, "category": "tier2", "type": "trade_pub"},
    {"domain": "politico.com",           "score": 80, "category": "tier2", "type": "wire_service"},
    {"domain": "thehindu.com",           "score": 76, "category": "tier2", "type": "regional"},

    # Tier 3 — Regional / general / unknown
    {"domain": "newsapi.org",            "score": 30, "category": "tier3", "type": "aggregator"},
    {"domain": "gnews.io",               "score": 30, "category": "tier3", "type": "aggregator"},
    {"domain": "gdelt.org",              "score": 55, "category": "tier2", "type": "aggregator"},
    {"domain": "unknown",                "score": 20, "category": "tier3", "type": "unknown"},
]


# ─────────────────────────────────────────────────────────────────────────────
#  Seed functions
# ─────────────────────────────────────────────────────────────────────────────

def seed_country_risk(session: Session) -> int:
    """Upsert country risk data. Returns number of rows upserted."""
    count = 0
    for row in COUNTRY_RISK_DATA:
        existing = session.query(CountryRisk).filter_by(country_code=row["code"]).first()
        if existing:
            existing.risk_score = row["score"]
            existing.risk_category = row["category"]
            existing.notes = row.get("notes")
            existing.updated_at = datetime.utcnow()
        else:
            session.add(CountryRisk(
                country_name=row["name"],
                country_code=row["code"],
                risk_score=row["score"],
                risk_category=row["category"],
                notes=row.get("notes"),
            ))
        count += 1
    logger.info(f"  Seeded {count} country risk records")
    return count


def seed_source_credibility(session: Session) -> int:
    """Upsert source credibility data. Returns number of rows upserted."""
    count = 0
    for row in SOURCE_CREDIBILITY_DATA:
        existing = session.query(SourceCredibility).filter_by(domain=row["domain"]).first()
        if existing:
            existing.credibility_score = row["score"]
            existing.category = row["category"]
            existing.source_type = row["type"]
        else:
            session.add(SourceCredibility(
                domain=row["domain"],
                credibility_score=row["score"],
                category=row["category"],
                source_type=row["type"],
            ))
        count += 1
    logger.info(f"  Seeded {count} source credibility records")
    return count


def seed_suppliers(session: Session, profile: dict) -> int:
    """
    Load suppliers from company_profile.yaml into the suppliers table.
    Existing rows (matched by name) are updated; new rows inserted.
    Suppliers not in the YAML are deactivated.
    """
    yaml_names = set()
    count = 0

    for s in profile.get("suppliers", []):
        yaml_names.add(s["name"])
        existing = session.query(Supplier).filter_by(name=s["name"]).first()
        aliases_json = json.dumps(s.get("aliases", []))

        if existing:
            existing.name_aliases_json = aliases_json
            existing.commodity = s.get("commodity")
            existing.country = s.get("country")
            existing.country_code = s.get("country_code")
            existing.tier = s["tier"]
            existing.criticality = s.get("criticality")
            existing.dependency_weight = s.get("dependency_weight")
            existing.notes = s.get("notes")
            existing.active = True
            existing.updated_at = datetime.utcnow()
        else:
            session.add(Supplier(
                name=s["name"],
                name_aliases_json=aliases_json,
                commodity=s.get("commodity"),
                country=s.get("country"),
                country_code=s.get("country_code"),
                tier=s["tier"],
                criticality=s.get("criticality"),
                dependency_weight=s.get("dependency_weight"),
                notes=s.get("notes"),
                active=True,
            ))
        count += 1

    # Deactivate suppliers no longer in YAML
    session.query(Supplier).filter(
        Supplier.name.notin_(yaml_names)
    ).update({"active": False}, synchronize_session=False)

    logger.info(f"  Seeded {count} suppliers from company_profile.yaml")
    return count


def seed_keyword_registry(session: Session, profile: dict) -> int:
    """
    Load keyword_registry from company_profile.yaml.
    Idempotent — existing entity entries are updated.
    """
    count = 0
    for entry in profile.get("keyword_registry", []):
        existing = session.query(KeywordRegistry).filter_by(
            entity_name=entry["entity_name"],
            category=entry["category"]
        ).first()

        keywords_json = json.dumps(entry.get("keywords", []))

        if existing:
            existing.keywords_json = keywords_json
            existing.active = True
        else:
            session.add(KeywordRegistry(
                category=entry["category"],
                entity_name=entry["entity_name"],
                keywords_json=keywords_json,
                active=True,
            ))
        count += 1

    logger.info(f"  Seeded {count} keyword registry entries")
    return count


def run_all_seeds(session: Session, profile: dict):
    """Run all seed operations in sequence."""
    logger.info("Running database seed operations...")
    seed_country_risk(session)
    seed_source_credibility(session)
    seed_suppliers(session, profile)
    seed_keyword_registry(session, profile)
    logger.info("✅ All seed operations complete")
