"""
module4/agent.py
─────────────────
LangChain ReAct agent powered by Gemini.

The agent has 4 tools:
  1. get_active_risks    — current HIGH/CRITICAL events with impact chains
  2. get_supplier_graph  — full supplier dependency network
  3. get_alternates      — ranked alternate suppliers for disrupted supplier
  4. get_risk_summary    — high-level risk landscape stats

Example queries the agent handles:
  - "What is our biggest supply chain risk this week?"
  - "Which of our suppliers are exposed to the current situation in the Middle East?"
  - "Generate a Monday morning procurement briefing for leadership"
  - "If Zhejiang Huahai shuts down, what are our options for cardiovascular APIs?"
  - "What indirect risks has the system detected in the last 48 hours?"
"""

import logging
import os
from typing import Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env at module import time
load_dotenv()


def _build_agent(api_key=None):
    """
    Build a simple agent using Gemini that can call tools directly.
    Uses the new API key to enable intelligent reasoning.
    
    Args:
        api_key: Optional specific API key to use. If None, gets first available key.
    """
    try:
        if api_key is None:
            from gemini_api_utils import get_gemini_api_key
            api_key = get_gemini_api_key()
    except ValueError as e:
        logger.error(f"No API key available: {e}")
        return None, None

    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        logger.info("✓ Gemini 2.5 Flash model initialized for intelligent agent")
        return model, api_key
    except Exception as e:
        logger.error(f"Failed to initialize Gemini: {e}")
        return None, None


# Singleton agent instance
_agent_instance = None
_agent_available = None
_current_agent_key = None  # Tracks the currently working API key
_working_key_index = 0     # Index of the working key in the key list


def get_agent():
    global _agent_instance, _agent_available, _current_agent_key
    if _agent_available is False:
        return None
    if _agent_instance is not None:
        return _agent_instance

    _agent_instance, _current_agent_key = _build_agent()
    _agent_available = _agent_instance is not None

    if _agent_available:
        logger.info("LangChain ReAct agent initialised ✓")
    else:
        logger.warning("Agent not available — falling back to direct tool responses")

    return _agent_instance


def query(question: str) -> dict:
    """
    Process a natural language query through the Gemini agent.
    Uses intelligent reasoning to select and use tools appropriately.
    Automatically rotates API keys on quota exhaustion.
    
    Smart key management:
    - Uses the last working API key by default
    - Only rotates to the next key when current key hits quota
    - Remembers which key is working and keeps using it

    Returns:
        {
            "answer": str,
            "method": "agent" | "fallback" | "error",
            "question": str,
        }
    """
    global _agent_instance, _current_agent_key, _working_key_index
    
    from gemini_api_utils import is_quota_error, get_all_api_keys
    from module4.tools import (
        get_active_risks, get_supplier_graph,
        get_alternates, get_risk_summary,
    )
    from module1.db.session import get_session
    from module1.db.models import Supplier
    
    all_keys = get_all_api_keys()
    max_retries = len(all_keys)
    retry_count = 0
    
    # Initialize with the working key if we haven't yet
    if _current_agent_key is None and all_keys:
        _agent_instance, _current_agent_key = _build_agent(all_keys[_working_key_index])
    
    while retry_count < max_retries:
        agent = get_agent()

        if agent is not None:
            try:
                # Fetch all critical supplier names to get their alternates
                with get_session() as session:
                    high_risk_suppliers = (
                        session.query(Supplier)
                        .filter(Supplier.criticality.in_(["critical", "high"]))
                        .limit(10)
                        .all()
                    )
                    critical_supplier_names = [s.name for s in high_risk_suppliers]

                system_prompt = """You are an expert supply chain risk analyst for a pharmaceutical company.

CRITICAL INSTRUCTIONS:
1. **Be conversational and professional** — never show tool names or function calls
2. **Provide direct answers** based on the data provided
3. **Be concise** — get to the point quickly with actionable insights
4. **Use data-driven language** — quote specific numbers, supplier names, and scores from the data
5. **Avoid technical details** — focus on business impact and recommendations
6. **Structure responses clearly** — use formatting to highlight key findings
7. **Always reference alternates** — when asked about alternatives or disruptions, provide specific alternate supplier names and scores from the ALTERNATE SUPPLIER RECOMMENDATIONS section

When answering questions:
- Lead with the most important finding
- Support with specific data points, supplier names, and numeric scores
- When mentioning alternates, include their scores (e.g., "Hetero Drugs API with a score of 78/100")
- Provide 1-2 actionable recommendations
- Keep responses under 200 words unless asking for detailed briefing"""

                # Prepare tool context for the model
                tool_context = f"""
RISK SUMMARY:
{get_risk_summary()}

ACTIVE RISKS:
{get_active_risks(40.0)[:2000]}

SUPPLIER NETWORK:
{get_supplier_graph()[:1500]}

ALTERNATE SUPPLIER RECOMMENDATIONS FOR CRITICAL SUPPLIERS:
"""
                
                # Add alternates for all high-risk suppliers
                for supplier_name in critical_supplier_names:
                    alt_data = get_alternates(supplier_name=supplier_name)
                    tool_context += f"\n{alt_data}\n"

                # Let Gemini synthesize answer from available data
                prompt = f"""{system_prompt}

User Question: {question}

AVAILABLE DATA:
{tool_context}

Provide a clear, professional response focused on business impact and decisions. Never mention function calls, tool names, or how you accessed the data."""

                response = agent.generate_content(prompt)
                answer = response.text if hasattr(response, 'text') else str(response)
                
                # Success! Log which key worked
                logger.info(f"Query successful with API key index {_working_key_index}")
                
                return {
                    "answer": answer,
                    "method": "agent",
                    "question": question,
                }
            except Exception as e:
                if is_quota_error(e) and retry_count < max_retries - 1:
                    # Current key is exhausted, rotate to next one
                    logger.warning(f"API key index {_working_key_index} quota exhausted, rotating to next key")
                    try:
                        _working_key_index = (_working_key_index + 1) % len(all_keys)
                        next_key = all_keys[_working_key_index]
                        logger.info(f"Switched to API key index {_working_key_index}")
                        _agent_instance, _current_agent_key = _build_agent(next_key)
                        retry_count += 1
                        continue
                    except Exception as rotate_error:
                        logger.error(f"Failed to rotate API key: {rotate_error}")
                        break
                else:
                    logger.error(f"Agent error: {e}")
                    break

        # If we've exhausted retries or agent is not available, use fallback
        break

    # Fallback: simple keyword-based routing
    return _direct_fallback(question)


def _direct_fallback(question: str) -> dict:
    """
    Simple keyword-based fallback when LangChain agent is unavailable.
    Calls tools directly and returns their output.
    """
    from module4.tools import (
        get_active_risks, get_supplier_graph,
        get_alternates, get_risk_summary,
    )

    q = question.lower()

    if any(w in q for w in ["briefing", "report", "summary", "overview", "week"]):
        answer = get_risk_summary() + "\n\n" + get_active_risks(40.0)

    elif any(w in q for w in ["alternate", "alternative", "option", "backup", "replace"]):
        # Try to extract supplier name from question
        from module1.db.session import get_session
        from module1.db.models import Supplier
        supplier_name = ""
        with get_session() as session:
            suppliers = session.query(Supplier).filter_by(active=True).all()
            for s in suppliers:
                if s.name.lower() in q:
                    supplier_name = s.name
                    break
        answer = get_alternates(supplier_name=supplier_name)

    elif any(w in q for w in ["supplier", "network", "graph", "tier", "dependency"]):
        answer = get_supplier_graph()

    elif any(w in q for w in ["risk", "threat", "disruption", "critical", "high", "danger"]):
        min_score = 60.0 if "high" in q or "critical" in q else 40.0
        answer = get_active_risks(min_score)

    else:
        answer = get_risk_summary()

    return {
        "answer": answer,
        "method": "fallback",
        "question": question,
    }


def generate_weekly_briefing() -> str:
    """
    Generate the weekly Monday morning procurement briefing.
    Called by the scheduler.
    """
    briefing_query = (
        "Generate a comprehensive Monday morning procurement briefing for leadership. "
        "Include: the top 5 supply chain risks by score, any critical or high-severity events, "
        "indirect risks detected, and recommended actions for the procurement team this week."
    )
    result = query(briefing_query)
    return result["answer"]
