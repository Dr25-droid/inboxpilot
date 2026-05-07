#!/usr/bin/env python
"""
InboxPilot — intelligent email triage and response assistant
Owner: Deepthi R

Usage:
    python main.py                         Process built-in sample email (demo)
    python main.py --email path/to/email.json  Process email from JSON file
    python main.py --serve                 Start LangGraph server for Agent Inbox UI

Email JSON format:
    {
        "author": "Sender Name <sender@example.com>",
        "to": "Your Name <you@example.com>",
        "subject": "Email subject line",
        "email_thread": "Email body content"
    }
"""

import argparse
import json
import uuid
import os
import sys

# Ensure src/ is on the path when running from the inboxpilot/ directory
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
load_dotenv(os.path.join(_HERE, ".env"))


def run_demo(email_input: dict):
    """Process a single email through the full pilot (triage + approval + memory)."""
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.store.memory import InMemoryStore
    from inboxpilot.pilot import overall_workflow

    checkpointer = MemorySaver()
    store = InMemoryStore()
    agent = overall_workflow.compile(checkpointer=checkpointer, store=store)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    author = email_input.get("author", "")
    subject = email_input.get("subject", "")

    print("\n── InboxPilot ─────────────────────────────────────────────────")
    print(f"  From   : {author}")
    print(f"  Subject: {subject}")
    print("────────────────────────────────────────────────────────────────\n")

    result = agent.invoke({"email_input": email_input}, config=config)
    decision = result.get("classification_decision", "unknown").upper()

    print(f"\n── Decision: {decision} {'─' * (50 - len(decision))}")
    msgs = result.get("messages", [])
    if msgs:
        content = getattr(msgs[-1], "content", "") or ""
        if content:
            print(content[:600])
    print("────────────────────────────────────────────────────────────────\n")


def run_server():
    """Start the LangGraph dev server for full Agent Inbox UI."""
    import subprocess
    print("Starting InboxPilot server...")
    print("Open the Agent Inbox in your browser to review and approve emails.\n")
    subprocess.run(["langgraph", "dev"], cwd=_HERE)


def main():
    parser = argparse.ArgumentParser(
        description="InboxPilot — intelligent email triage and response assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--email",
        metavar="PATH",
        help="Path to a JSON file with email fields (author, to, subject, email_thread)",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the LangGraph server for the Agent Inbox UI",
    )
    args = parser.parse_args()

    if args.serve:
        run_server()
        return

    if args.email:
        with open(args.email) as f:
            email_input = json.load(f)
    else:
        from inboxpilot.eval.email_dataset import STANDARD_EMAIL
        email_input = STANDARD_EMAIL
        print("No --email provided. Using built-in sample email.\n")

    run_demo(email_input)


if __name__ == "__main__":
    main()
