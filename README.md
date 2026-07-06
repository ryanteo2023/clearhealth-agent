# clearhealth-agent

A multi-agent health information system built with [Google ADK](https://adk.dev).

## Project Structure

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

## Setup

```bash
# Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# Install dependencies
pip install -e ".[dev]"
```

## Running locally

```bash
python -m app.agent
```
