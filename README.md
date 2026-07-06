# clearhealth-agent

A multi-agent health information system built with [Google ADK](https://adk.dev).

## Problem

Public health information — vaccine eligibility, clinic hours, benefit
forms — is often technically available but written in dense, bureaucratic
language. Low-literacy adults, non-native speakers, and elderly users
frequently give up trying to find an answer, not because the information
doesn't exist, but because they can't parse it. ClearHealth closes that
gap by answering health questions and rewriting the answer in simple,
plain language.

## First Implementation plan Project Structure

```
clearhealth-agent/
├── app/
│   ├── __init__.py
│   ├── agent.py            # Entry point — root orchestrator agent
│   ├── research_agent.py   # Sub-agent: fetches & summarises health info
│   ├── simplifier_agent.py # Sub-agent: rewrites content in plain language
│   └── tools/
│       ├── __init__.py
│       └── placeholder.py  # Placeholder — add custom tools here
├── pyproject.toml
└── README.md
```

## Actual Project Structure

```
clearhealth-agent/
├── app/
│   ├── __init__.py
|   ├── .adk
│   ├── agent.py            # Entry point — root orchestrator agent
│   ├── research_agent.py   # Sub-agent: fetches & summarises health info
│   ├── simplifier_agent.py # Sub-agent: rewrites content in plain language
│   └── tools/
│       ├── __init__.py
│       ├── clinic_mcp_server.py  # MCP
│       └── placeholder.py  # Placeholder — add custom tools here
├── pyproject.toml
├── validate_agent
├── uv.lock
├──.gitignore # Keep secrets like API keys from being pushed into Github repository
├──.env # contains GEMINI_API_KEY
├──.venv
├──.pytest_cache
├──tests
│       └── test_clearhealth.py  # tests
└── README.md
```

## Architecture

ClearHealth uses two cooperating agents built with Google's Agent
Development Kit (ADK), connected through a custom MCP server.

1. **Research agent** — Receives the user's question, sanitizes the
   input, and calls a custom MCP tool (`lookup_clinic`) to retrieve
   factual clinic information (hours, eligibility, contact details). It
   never invents details — only reports what the tool returns.
2. **MCP server** (`app/tools/clinic_mcp_server.py`) — A local MCP server
   exposed over stdio, backed by a small sample dataset of clinics. This
   keeps the data/tool layer decoupled from agent logic, so a real data
   source (e.g. a 211 API or open health department dataset) could be
   swapped in without touching the agents.
3. **Simplifier agent** — Takes the research agent's factual answer and
   rewrites it at a 5th-grade reading level, removing jargon, and
   translating into the user's requested language while preserving all
   factual details (hours, eligibility, contact info).

```
User question
     │
     ▼
Research agent ──tool call──▶ MCP server (clinic lookup)
     │            ◀──result──
     ▼
Simplifier agent
     │
     ▼
Plain-language answer
```

See `docs/architecture.png` for the full diagram.

## Setup

**Requirements:** Python 3.10+, pip

1. Clone the repository:
   ```bash
   git clone https://github.com/<your-username>/clearhealth-agent.git
   cd clearhealth-agent
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. Install dependencies & Gemini API Key:
   ```bash
   pip install -e .
   ```
   (This installs `google-adk`, `mcp`, and other project dependencies —
   see `requirements.txt` for the full list.)

   Insert Gemini API Key into your own created .env file, GEMINI_API_KEY=<your_api_key>

4. Run the agent locally with the ADK dev UI:
   ```bash
   adk web
   ```
   This starts a local web server (default `http://localhost:8000`) where
   you can chat with the agent and inspect tool calls and agent traces.

5. Try it with a sample question, e.g.:
   > "Where can I get a flu shot near 10001, explain simply?"

## Security & privacy

- No personal data is stored, cached, or logged at any point. Questions
  are processed in memory only, for the duration of a single request.
- User input is sanitized before being passed to any agent or tool, to
  reduce the risk of prompt injection reaching the MCP tool layer.
- The MCP server's sample dataset contains no real individuals' data —
  all clinic records are illustrative placeholders for demo purposes.

## What's next

With more time: connect to real public data sources (211, local health
department open data), add voice input for lower-literacy users, and add
a safety-check agent that routes urgent/emergency questions to a human
rather than answering automatically.

## Built with

Built end-to-end in **Google Antigravity**, using Google's ADK to define
and orchestrate the two agents, and a lightweight custom MCP server for
the clinic lookup tool.
