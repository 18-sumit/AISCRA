"""
module1/config/company_profile.py
───────────────────────────────────
Loads company_profile.yaml into typed Python dataclasses.

Usage:
    from module1.config.company_profile import load_profile, CompanyProfile
    profile = load_profile()  # reads company_profile.yaml from project root
    print(profile.company.name)            # "Cipla Limited"
    print(profile.get_all_keywords())      # flat list of all Track A search phrases
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


# ─────────────────────────────────────────────────────────────────────────────
#  Dataclasses — one per YAML section
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CompanyInfo:
    name: str
    short_name: str
    industry: str
    sector: str
    headquarters_country: str
    headquarters_city: str
    headquarters_country_code: str
    description: str = ""


@dataclass
class SupplierEntry:
    name: str
    aliases: list
    commodity: str
    country: str
    country_code: str
    tier: int
    criticality: str
    dependency_weight: float
    notes: str = ""

    def all_names(self) -> list:
        return [self.name] + self.aliases


@dataclass
class AlternateEntry:
    name: str
    country: str
    country_code: str
    capacity_fit: str
    lead_time_weeks: int
    notes: str = ""


@dataclass
class AlternateGroup:
    for_commodity: str
    suppliers: list  # list of AlternateEntry


@dataclass
class KeywordEntry:
    category: str
    entity_name: str
    keywords: list


@dataclass
class RssFeed:
    name: str
    url: str
    category: str


@dataclass
class RssConfig:
    track_a: list  # list of RssFeed
    track_b: list


@dataclass
class CompanyProfile:
    """Top-level profile object. Switch companies by changing company_profile.yaml."""
    company: CompanyInfo
    suppliers: list         # list[SupplierEntry]
    alternates: list        # list[AlternateGroup]
    keyword_registry: list  # list[KeywordEntry]
    rss_feeds: RssConfig
    _raw: dict = field(default_factory=dict, repr=False)

    # ── Convenience helpers ───────────────────────────────────────────────

    def get_all_keywords(self) -> list:
        """Flat list of all Track A search keywords (deduplicated)."""
        seen = set()
        result = []
        for entry in self.keyword_registry:
            for kw in entry.keywords:
                if kw not in seen:
                    seen.add(kw)
                    result.append(kw)
        return result

    def get_keywords_by_category(self, category: str) -> list:
        """All keywords for a given category (e.g. 'supplier', 'commodity')."""
        result = []
        for entry in self.keyword_registry:
            if entry.category == category:
                result.extend(entry.keywords)
        return result

    def get_supplier_keywords(self) -> list:
        """Keyword batches for supplier names — used in Track A searches."""
        return self.get_keywords_by_category("supplier")

    def get_tier1_suppliers(self) -> list:
        return [s for s in self.suppliers if s.tier == 1]

    def get_critical_suppliers(self) -> list:
        return [s for s in self.suppliers if s.criticality == "critical"]

    def get_supplier_countries(self) -> list:
        """Unique country codes across all suppliers."""
        return list({s.country_code for s in self.suppliers})

    def get_supplier_by_name(self, name: str) -> Optional[SupplierEntry]:
        for s in self.suppliers:
            if s.name.lower() == name.lower() or name.lower() in [a.lower() for a in s.aliases]:
                return s
        return None

    def build_stage0_system_prompt(self) -> str:
        """
        Generates the Gemini Stage 0 system prompt from the profile.
        Injected as context for every hot_news article screening call.
        """
        lines = [
            f"You are a supply chain risk analyst for {self.company.name}, "
            f"a {self.company.industry} company headquartered in {self.company.headquarters_city}, "
            f"{self.company.headquarters_country}.",
            "",
            "Key supply chain dependencies:",
        ]

        for s in self.get_tier1_suppliers():
            lines.append(
                f"  • {s.name} supplies {s.commodity} from {s.country} "
                f"(criticality: {s.criticality}, dependency: {int(s.dependency_weight * 100)}%)"
            )

        lines += [
            "",
            "Key sourcing countries: " + ", ".join(
                f"{s.country} ({s.country_code})" for s in self.suppliers
            ),
            "",
            "Key commodities: " + ", ".join(
                set(s.commodity.split("(")[0].strip() for s in self.get_tier1_suppliers())
            ),
            "",
            "Your job: read a news article and determine whether it creates a plausible "
            "supply chain risk for this company, even if the company or its suppliers are "
            "not mentioned by name.",
            "",
            "Always respond in valid JSON only. No preamble. No markdown.",
        ]

        return "\n".join(lines)

    def to_dict(self) -> dict:
        return self._raw


# ─────────────────────────────────────────────────────────────────────────────
#  Loader
# ─────────────────────────────────────────────────────────────────────────────

def _find_profile_path() -> Path:
    """Searches for company_profile.yaml in: CWD → project root → env override."""
    env_override = os.getenv("COMPANY_PROFILE_PATH")
    if env_override:
        p = Path(env_override)
        if p.exists():
            return p
        raise FileNotFoundError(f"COMPANY_PROFILE_PATH set but not found: {env_override}")

    candidates = [
        Path.cwd() / "company_profile.yaml",
        Path(__file__).parent.parent.parent / "company_profile.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "company_profile.yaml not found. "
        "Run: cp company_profile.example.yaml company_profile.yaml and fill in your company data."
    )


def load_profile(path: Optional[Path] = None) -> CompanyProfile:
    """
    Load and parse company_profile.yaml.
    Args:
        path: explicit path override (useful for tests)
    Returns:
        CompanyProfile dataclass
    """
    yaml_path = path or _find_profile_path()

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # ── Company ────────────────────────────────────────────────────────────
    c = raw["company"]
    company = CompanyInfo(
        name=c["name"],
        short_name=c["short_name"],
        industry=c["industry"],
        sector=c["sector"],
        headquarters_country=c["headquarters_country"],
        headquarters_city=c["headquarters_city"],
        headquarters_country_code=c["headquarters_country_code"],
        description=c.get("description", ""),
    )

    # ── Suppliers ──────────────────────────────────────────────────────────
    suppliers = []
    for s in raw.get("suppliers", []):
        suppliers.append(SupplierEntry(
            name=s["name"],
            aliases=s.get("aliases", []),
            commodity=s.get("commodity", ""),
            country=s.get("country", ""),
            country_code=s.get("country_code", ""),
            tier=int(s["tier"]),
            criticality=s.get("criticality", "medium"),
            dependency_weight=float(s.get("dependency_weight", 0.0)),
            notes=s.get("notes", ""),
        ))

    # ── Alternates ─────────────────────────────────────────────────────────
    alternates = []
    for group in raw.get("alternates", []):
        alt_entries = [
            AlternateEntry(
                name=a["name"],
                country=a.get("country", ""),
                country_code=a.get("country_code", ""),
                capacity_fit=a.get("capacity_fit", "medium"),
                lead_time_weeks=int(a.get("lead_time_weeks", 8)),
                notes=a.get("notes", ""),
            )
            for a in group.get("suppliers", [])
        ]
        alternates.append(AlternateGroup(
            for_commodity=group["for_commodity"],
            suppliers=alt_entries,
        ))

    # ── Keyword registry ───────────────────────────────────────────────────
    keyword_registry = []
    for entry in raw.get("keyword_registry", []):
        keyword_registry.append(KeywordEntry(
            category=entry["category"],
            entity_name=entry["entity_name"],
            keywords=entry.get("keywords", []),
        ))

    # ── RSS feeds ──────────────────────────────────────────────────────────
    rss_raw = raw.get("rss_feeds", {})
    rss = RssConfig(
        track_a=[RssFeed(**f) for f in rss_raw.get("track_a", [])],
        track_b=[RssFeed(**f) for f in rss_raw.get("track_b", [])],
    )

    return CompanyProfile(
        company=company,
        suppliers=suppliers,
        alternates=alternates,
        keyword_registry=keyword_registry,
        rss_feeds=rss,
        _raw=raw,
    )
