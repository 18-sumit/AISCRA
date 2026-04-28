"""
module4/main.py
────────────────
CLI for AISCRA — AI Supply Chain Risk Analysis.

Commands:
  --chat          Interactive chat loop with the AI agent
  --ask "query"   Single question, print answer, exit
  --briefing      Generate and print (+ optionally send) the analysis briefing
  --status        Show notification config status

Usage:
  python -m module4.main --chat
  python -m module4.main --ask "What are our biggest supply chain risks this week?"
  python -m module4.main --briefing --send
"""

import argparse
import logging
import os
import sys

import colorlog
from dotenv import load_dotenv

load_dotenv()


def _setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s:%(reset)s %(message)s",
        datefmt="%H:%M:%S",
        log_colors={"DEBUG": "cyan", "INFO": "green", "WARNING": "yellow",
                    "ERROR": "red", "CRITICAL": "bold_red"},
    ))
    logging.getLogger().setLevel(getattr(logging, level, logging.INFO))
    logging.getLogger().addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def cmd_chat():
    """Interactive chat loop with the AI agent."""
    from module4.agent import query, get_agent

    print("\n" + "═" * 65)
    print("  Supply Chain Risk — AI Agent")
    print("  Type your question. 'exit' or Ctrl+C to quit.")
    print("═" * 65)

    agent = get_agent()
    method_note = "(LangChain ReAct agent)" if agent else "(direct tool fallback — install langchain for full agent)"
    print(f"\n  Mode: {method_note}\n")

    while True:
        try:
            question = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n  Goodbye.")
            break

        if question.lower() in ("exit", "quit", "q", ""):
            print("  Goodbye.")
            break

        print()
        result = query(question)
        print(f"  Agent [{result['method']}]:\n")
        # Word-wrap the answer for terminal readability
        answer = result["answer"]
        for line in answer.split("\n"):
            if len(line) > 90:
                words = line.split()
                current = "  "
                for word in words:
                    if len(current) + len(word) > 90:
                        print(current)
                        current = "  " + word + " "
                    else:
                        current += word + " "
                if current.strip():
                    print(current)
            else:
                print(f"  {line}" if line else "")
        print()


def cmd_ask(question: str):
    """Single question mode."""
    from module4.agent import query
    result = query(question)
    print(f"\n{result['answer']}\n")
    print(f"[method: {result['method']}]")


def cmd_briefing(send: bool = False):
    """Generate the supply chain analysis briefing."""
    from module4.agent import generate_weekly_briefing
    from module4.notifications import send_slack_briefing, send_email_briefing

    print("\nGenerating supply chain analysis briefing…\n")
    briefing = generate_weekly_briefing()
    print("─" * 65)
    print(briefing)
    print("─" * 65)

    if send:
        slack_ok = send_slack_briefing(briefing)
        email_ok = send_email_briefing(briefing)
        print(f"\nSent via Slack: {'✓' if slack_ok else '✗ (not configured)'}")
        print(f"Sent via Email: {'✓' if email_ok else '✗ (not configured)'}")


def cmd_status():
    """Show notification channel configuration status."""
    import os

    slack_ok = bool(os.getenv("SLACK_WEBHOOK_URL"))
    smtp_ok  = bool(os.getenv("SMTP_HOST"))
    email_to = os.getenv("ALERT_EMAIL_TO", "not set")
    from gemini_api_utils import get_all_api_keys
    gemini   = bool(get_all_api_keys())
    threshold = os.getenv("ALERT_SCORE_THRESHOLD", "50")

    try:
        from langchain.agents import AgentExecutor
        langchain_ok = True
    except ImportError:
        langchain_ok = False

    print("\n" + "═" * 65)
    print("  AISCRA — AI Agent & Supply Chain Analysis")
    print("═" * 65)
    print(f"\n  AI Agent")
    print(f"    Gemini API key:   {'✓ set' if gemini else '✗ not set'}")
    print(f"    LangChain:        {'✓ installed' if langchain_ok else '✗ not installed (pip install langchain langchain-google-genai)'}")
    print(f"\n  Notifications")
    print(f"    Slack webhook:    {'✓ configured' if slack_ok else '✗ not set (add SLACK_WEBHOOK_URL to .env)'}")
    print(f"    Email (SMTP):     {'✓ configured' if smtp_ok else '✗ not set (add SMTP_HOST to .env)'}")
    print(f"    Alert recipient:  {email_to}")
    print(f"    Alert threshold:  score >= {threshold}")
    print("\n" + "═" * 65 + "\n")


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        description="AISCRA — AI Agent & Supply Chain Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m module4.main --chat
  python -m module4.main --ask "What are our biggest risks this week?"
  python -m module4.main --ask "If Lonza shuts down, what are our options?"
  python -m module4.main --briefing
  python -m module4.main --briefing --send
  python -m module4.main --status
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--chat",         action="store_true", help="Interactive chat with the AI agent")
    group.add_argument("--ask",          type=str,            help="Single question, print answer, exit")
    group.add_argument("--briefing",     action="store_true", help="Generate supply chain analysis briefing")
    group.add_argument("--status",       action="store_true", help="Show configuration status")
    parser.add_argument("--send",        action="store_true", help="With --briefing: also send via Slack/email")

    args = parser.parse_args()

    try:
        if args.chat:         cmd_chat()
        elif args.ask:        cmd_ask(args.ask)
        elif args.briefing:   cmd_briefing(send=args.send)
        elif args.status:     cmd_status()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logging.getLogger(__name__).error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
