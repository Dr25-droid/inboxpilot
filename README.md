# InboxPilot

An email assistant that reads your incoming mail, sorts what needs attention from what doesn't, drafts replies on your behalf, and asks for your approval before sending anything.

**Owner:** Deepthi R

---

## What It Does

InboxPilot monitors your inbox and handles each email in one of three ways:

- **Ignore** — newsletters, social notifications, spam, and irrelevant bulk mail are silently skipped
- **Notify** — important information you should know about (system alerts, team announcements, reminders) is surfaced for your awareness without requiring a reply
- **Respond** — emails that need a reply get a drafted response for your review

When a response is needed, InboxPilot:

1. Reads the email and understands what's being asked
2. Checks your calendar if a meeting needs to be scheduled
3. Drafts an email reply in your preferred writing style
4. Shows you the draft for approval before anything is sent
5. Learns from your edits and feedback so future drafts need fewer corrections

You remain in control. Nothing is sent without your explicit approval.

---

## Use Cases

**Inbox filtering for busy professionals**
You receive 80+ emails a day. InboxPilot filters out newsletters, CC chains you don't need to act on, and automated system notifications — so your attention goes only to what requires it.

**Meeting scheduling from email requests**
A colleague requests a 45-minute call next week. InboxPilot checks your calendar, drafts a reply with proposed times, prepares a calendar invite, and waits for your approval before booking anything.

**Technical inquiry acknowledgment**
A client asks about a missing API endpoint. InboxPilot drafts a professional acknowledgment that commits to investigating and provides a response timeline — in your tone.

**Personal reminder handling**
Your doctor's office sends a checkup reminder. InboxPilot drafts a brief acknowledgment and flags it for your attention rather than letting it get buried.

**Preference learning over time**
Every time you edit a draft, reject an email response, or correct a calendar detail, InboxPilot updates its preferences. After a few sessions, it responds more and more like you would — fewer edits needed.

---

## How It Works

```
Incoming Email
      │
      ▼
  Triage Step ─── classifies email as: IGNORE / NOTIFY / RESPOND
      │
      ├─ IGNORE ──► Done. Nothing sent, nothing shown.
      │
      ├─ NOTIFY ──► Show email to you. You can:
      │               ├─ Dismiss ──► Done
      │               └─ Reply  ──► Draft reply step (below)
      │
      └─ RESPOND ──► Draft reply step
                          │
                          ▼
                    InboxPilot checks calendar (if needed)
                    InboxPilot drafts reply email
                          │
                          ▼
                    Show draft to you for approval
                          │
                          ├─ Accept  ──► Send as-is
                          ├─ Edit    ──► Update preferences + send edited version
                          ├─ Reject  ──► Update preferences + stop
                          └─ Respond ──► Add your feedback + revise draft
```

**Memory** is updated after every interaction. InboxPilot remembers:
- Which types of email you respond to (triage preferences)
- How you prefer to write replies (response style)
- Your meeting and scheduling preferences (calendar preferences)

These preferences persist across sessions and improve with use.

---

## Setup

### Requirements

- Python 3.11 or later
- An OpenAI API key
- A LangSmith API key (optional, for evaluation and tracing)

### Install

Navigate into the `inboxpilot/` directory and install:

```bash
cd inboxpilot

# Recommended: using uv
pip install uv
uv sync

# Or using pip
pip install -e .
```

### Configure

Copy the example environment file and fill in your details:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-...
USER_NAME=Deepthi R
USER_ROLE=a software engineer at Acme Corp
```

The `USER_NAME` and `USER_ROLE` values tell InboxPilot who it is acting on behalf of — this shapes how it writes email responses.

---

## How to Run

### Process a sample email (quick test, no server needed)

```bash
python main.py
```

This runs the built-in API documentation email through the full pipeline and prints the triage decision and drafted reply to your terminal. Useful for testing your API key and setup.

### Process your own email

Create a JSON file with your email:

```json
{
    "author": "Sender Name <sender@example.com>",
    "to": "Your Name <you@example.com>",
    "subject": "Your email subject",
    "email_thread": "Email body content here."
}
```

Then run:

```bash
python main.py --email path/to/your_email.json
```

### Full assistant with approval workflow (Agent Inbox UI)

For the complete experience — where you review and approve every draft before it's sent — start the LangGraph server:

```bash
python main.py --serve
```

Then open the [Agent Inbox](https://agentinbox.io) in your browser. Connect it to `http://localhost:2024` and select the `pilot` graph.

Available graphs:
| Graph name      | Description                                          |
|-----------------|------------------------------------------------------|
| `pilot`         | Full assistant: triage + approval + memory           |
| `pilot_simple`  | Automated response, no approval step                 |
| `pilot_review`  | Approval workflow, no persistent memory              |
| `pilot_gmail`   | Gmail integration (requires Gmail credentials)       |

### Gmail integration

First, complete the one-time Gmail OAuth setup:

```bash
python src/inboxpilot/tools/gmail/setup_gmail.py
```

This opens a browser window for you to authorize Gmail access. Credentials are saved locally.

Then start the server and use the `pilot_gmail` graph in Agent Inbox.

To fetch and process emails on a schedule, run the ingestion script:

```bash
python src/inboxpilot/tools/gmail/run_ingest.py --email you@gmail.com --minutes-since 60
```

---

## Running Tests

```bash
cd inboxpilot
python tests/run_tests.py
```

Tests run the assistant against 16 categorized emails and verify:
- Correct triage classification (ignore / notify / respond)
- Correct tool usage (calendar check when needed, email drafts for responses)
- Response quality against human-written criteria

Test results are logged to LangSmith when `LANGSMITH_API_KEY` is set.

---

## Project Structure

```
inboxpilot/
├── main.py                  Primary entry point
├── pyproject.toml           Package configuration
├── langgraph.json           Graph definitions for LangGraph server
├── .env.example             Environment variable template
│
├── src/inboxpilot/
│   ├── pilot.py             Main assistant (triage + approval + memory)
│   ├── pilot_simple.py      Automated assistant (no approval step)
│   ├── pilot_review.py      Approval workflow without persistent memory
│   ├── pilot_gmail.py       Gmail API integration
│   ├── cron.py              Periodic email ingestion job
│   ├── prompts.py           All LLM prompt templates
│   ├── schemas.py           Data models (State, RouterSchema, etc.)
│   ├── configuration.py     Runtime configuration
│   ├── utils.py             Formatting and parsing utilities
│   │
│   ├── tools/
│   │   ├── actions.py       Email and calendar tools (write, schedule, check)
│   │   ├── registry.py      Tool loader and lookup
│   │   ├── prompt_templates.py  Tool description strings for prompts
│   │   └── gmail/           Real Gmail API tools
│   │       ├── gmail_tools.py
│   │       ├── run_ingest.py
│   │       └── setup_gmail.py
│   │
│   └── eval/
│       ├── email_dataset.py  16-email test dataset with ground truth
│       ├── evaluate_triage.py  LangSmith-based triage evaluation
│       └── prompts.py        Evaluation prompt templates
│
└── tests/
    ├── conftest.py           pytest fixtures
    ├── test_response.py      Response quality and tool call tests
    └── run_tests.py          Test runner with LangSmith integration
```

---

## Owner

**Deepthi R**

For questions or contributions, please open an issue in this repository.
