"""
module4/tools.py
─────────────────
The 4 tools available to the LangChain ReAct agent.

Tool 1: get_active_risks()
  Returns all current HIGH and CRITICAL risk events with impact chains.

Tool 2: get_supplier_graph()
  Returns the dependency graph as a JSON adjacency list.

Tool 3: get_alternates(supplier_name, commodity)
  Returns the ranked alternate supplier list for a disrupted supplier.

Tool 4: generate_briefing(focus)
  Generates a structured procurement briefing report.
"""

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_active_risks(min_score: float = 40.0) -> str:
    """
    Fetch all active risk events above a minimum score threshold.
    Returns a structured text summary for the agent to reason about.
    """
    try:
        from module1.db.session import get_session
        from module1.db.models import RiskEvent, Article, Supplier

        with get_session() as session:
            events = (
                session.query(RiskEvent)
                .filter(RiskEvent.risk_score >= min_score)
                .order_by(RiskEvent.risk_score.desc())
                .limit(20)
                .all()
            )

            if not events:
                return f"No risk events found with score >= {min_score}."

            lines = [f"Active Risk Events (score >= {min_score}):\n"]
            for e in events:
                supplier = session.query(Supplier).filter_by(id=e.supplier_id).first()
                article  = session.query(Article).filter_by(id=e.article_id).first()

                lines.append(
                    f"[{e.severity_band}] Score: {e.risk_score:.1f} | "
                    f"Supplier: {supplier.name if supplier else 'Unknown'} | "
                    f"Commodity: {e.commodity or 'N/A'} | "
                    f"Event: {e.event_type or 'N/A'} | "
                    f"Indirect: {'Yes' if e.is_indirect else 'No'}"
                )
                if e.impact_chain:
                    lines.append(f"  Pathway: {e.impact_chain[:300]}")
                if article:
                    lines.append(f"  Source: {article.headline[:120]}")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.error(f"get_active_risks error: {e}")
        return f"Error fetching risks: {e}"


def get_supplier_graph() -> str:
    """
    Returns the supplier dependency graph as a structured text description.
    Lists all suppliers by tier with their commodity, country, and dependency weight.
    """
    try:
        from module1.db.session import get_session
        from module1.db.models import Supplier

        with get_session() as session:
            suppliers = (
                session.query(Supplier)
                .filter_by(active=True)
                .order_by(Supplier.tier, Supplier.criticality)
                .all()
            )

            if not suppliers:
                return "No suppliers found in the database."

            lines = ["Supplier Dependency Graph:\n"]
            current_tier = None

            for s in suppliers:
                if s.tier != current_tier:
                    current_tier = s.tier
                    tier_label = {1: "TIER 1 — Direct Suppliers",
                                  2: "TIER 2 — Sub-tier Suppliers",
                                  3: "TIER 3 — Raw Material Sources"}
                    lines.append(f"\n{tier_label.get(s.tier, f'Tier {s.tier}')}:")

                lines.append(
                    f"  • {s.name} | {s.commodity or 'N/A'} | "
                    f"Country: {s.country} ({s.country_code}) | "
                    f"Criticality: {s.criticality} | "
                    f"Dependency: {int((s.dependency_weight or 0) * 100)}%"
                )
                if s.notes:
                    lines.append(f"    Note: {s.notes[:100]}")

            return "\n".join(lines)

    except Exception as e:
        logger.error(f"get_supplier_graph error: {e}")
        return f"Error fetching supplier graph: {e}"


def get_alternates(supplier_name: str = "", commodity: str = "") -> str:
    """
    Returns ranked alternate supplier recommendations for a disrupted supplier.
    Searches by supplier name and/or commodity.
    """
    try:
        from module1.db.session import get_session
        from module1.db.models import AlternateSupplier, RiskEvent, Supplier

        with get_session() as session:
            q = session.query(AlternateSupplier)

            # Filter by disrupted supplier name if provided
            if supplier_name:
                matching_supplier = (
                    session.query(Supplier)
                    .filter(Supplier.name.ilike(f"%{supplier_name}%"))
                    .first()
                )
                if matching_supplier:
                    q = q.filter_by(disrupted_supplier_id=matching_supplier.id)

            alts = q.order_by(AlternateSupplier.alt_score.desc()).limit(10).all()

            if not alts:
                search_term = supplier_name or commodity or "any supplier"
                return (
                    f"No alternate recommendations found for '{search_term}'. "
                    f"This means either no HIGH+ risk events exist for this supplier, "
                    f"or Module 3 has not yet run. Try: python -m module3.main --run-once"
                )

            lines = [f"Alternate Supplier Recommendations:\n"]
            for a in alts:
                re = session.query(RiskEvent).filter_by(id=a.risk_event_id).first()
                dis = session.query(Supplier).filter_by(id=a.disrupted_supplier_id).first()

                lines.append(
                    f"#{a.rank} {a.alternate_name} ({a.country_code}) | "
                    f"Score: {a.alt_score:.0f}/100 | "
                    f"Capacity: {a.capacity_fit} | "
                    f"Lead time: {a.lead_time_weeks}w | "
                    f"Geo safety: {a.geographic_safety_score:.0f}"
                )
                if dis and re:
                    lines.append(f"  For: {dis.name} — {re.commodity or 'N/A'} [{re.severity_band}]")
                if a.rationale:
                    lines.append(f"  Rationale: {a.rationale[:200]}")
                lines.append("")

            return "\n".join(lines)

    except Exception as e:
        logger.error(f"get_alternates error: {e}")
        return f"Error fetching alternates: {e}"


def get_risk_summary() -> str:
    """
    Returns a high-level summary of current risk landscape for briefing generation.
    """
    try:
        from module1.db.session import get_session
        from module1.db.models import RiskEvent, Article, AlternateSupplier

        with get_session() as session:
            total     = session.query(RiskEvent).count()
            critical  = session.query(RiskEvent).filter_by(severity_band="CRITICAL").count()
            high      = session.query(RiskEvent).filter_by(severity_band="HIGH").count()
            medium    = session.query(RiskEvent).filter_by(severity_band="MEDIUM").count()
            low       = session.query(RiskEvent).filter_by(severity_band="LOW").count()
            indirect  = session.query(RiskEvent).filter_by(is_indirect=True).count()
            alternates = session.query(AlternateSupplier).count()

            total_articles = session.query(Article).count()
            confirmed_risks = session.query(Article).filter_by(is_supply_chain_risk=True).count()

            top_events = (
                session.query(RiskEvent)
                .order_by(RiskEvent.risk_score.desc())
                .limit(5)
                .all()
            )

            from module1.db.models import Supplier
            top_lines = []
            for e in top_events:
                s = session.query(Supplier).filter_by(id=e.supplier_id).first()
                top_lines.append(
                    f"  - [{e.severity_band}] {s.name if s else '?'}: "
                    f"score={e.risk_score:.0f}, type={e.event_type}"
                )

        return (
            f"Risk Landscape Summary:\n"
            f"Total risk events: {total} "
            f"(CRITICAL: {critical}, HIGH: {high}, MEDIUM: {medium}, LOW: {low})\n"
            f"Indirect exposure events: {indirect}\n"
            f"Alternate recommendations generated: {alternates}\n"
            f"Articles analysed: {total_articles} ({confirmed_risks} confirmed risks)\n\n"
            f"Top 5 Highest-Scoring Events:\n" +
            "\n".join(top_lines)
        )

    except Exception as e:
        return f"Error fetching summary: {e}"
