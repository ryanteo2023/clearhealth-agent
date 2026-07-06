"""
app/agent.py — Root orchestrator (entry point)
------------------------------------------------
Defines the ``root_agent``: a ``SequentialAgent`` that runs the ClearHealth
pipeline in two steps:

    1. ``research_agent``   — calls the ``lookup_clinic`` MCP tool and returns
                              a factual, structured clinic description.
    2. ``simplifier_agent`` — rewrites that description at a 5th-grade reading
                              level for patient accessibility.

Input sanitisation
------------------
A ``before_agent_callback`` is attached to the root agent.  It runs *before*
the pipeline starts and performs two checks on the raw user message:

    1. **Reject empty input** — prevents agents from entering a confused state
       when there is nothing to act on.
    2. **Strip dangerous characters** — removes all characters that are neither
       alphanumeric, whitespace, nor common-English punctuation
       (``.,?!-'():``).

       Security rationale — prompt injection into the MCP tool layer:
       ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
       The ``lookup_clinic`` MCP tool passes ``zipcode`` and ``need``
       directly into subprocess stdin as JSON.  An adversarial string such as::

           "90011\", \"need\": \"x\"}]; import os; os.system('...')  # "

       could attempt to escape the JSON payload and inject code if the MCP
       server were ever rendered with ``exec()`` or an unsafe template.
       Even though the current FastMCP server is safe, sanitising at the
       orchestrator boundary follows the principle of defence-in-depth:
       untrusted input should never reach a tool layer unmodified.

       The allowlist approach (only keep known-safe characters) is stricter
       and safer than a blocklist (removing known-bad characters), because
       it handles novel attack vectors that the blocklist has not anticipated.

Local runner
------------
``InMemoryRunner`` + ``InMemorySessionService`` are used for local development
and automated testing — no external database or network calls are needed.

Usage::

    python -m app.agent                   # smoke-test
    python -m app.agent "90011 primary care"  # pass a query via argv
"""

from __future__ import annotations

import asyncio
import re
import sys
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file before importing ADK modules
load_dotenv()

from google.adk.agents import SequentialAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.runners import InMemoryRunner
from google.genai import types

# ---------------------------------------------------------------------------
# Sub-agent imports
# ---------------------------------------------------------------------------
from app.research_agent import research_agent
from app.simplifier_agent import simplifier_agent

# ---------------------------------------------------------------------------
# Input sanitisation
# ---------------------------------------------------------------------------

# Allowlist: alphanumerics, whitespace, and a curated set of punctuation
# characters that appear in natural health queries ("What's open at 9:30?")
# but are not needed for injection attacks.
#
# SECURITY NOTE — prompt injection defence:
# Keeping this pattern narrow is intentional.  Characters like ``"`, `{``,
# `` ` ``, ``\``, ``|``, and ``;`` have no legitimate role in a clinic lookup
# query but are commonly used in JSON-escape, shell-injection, and template-
# injection attacks.  Stripping them at the orchestrator level means the MCP
# tool subprocess never sees them, regardless of how the MCP server evolves.
_SAFE_CHARS: re.Pattern = re.compile(r"[^\w\s.,?!\-'():]", flags=re.UNICODE)

# Maximum raw query length — long inputs are unusual for a clinic lookup and
# could be used to inflate token cost or overwhelm the tool layer.
_MAX_INPUT_LENGTH: int = 500


def _sanitise_input(raw: str) -> str:
    """
    Return a cleaned version of ``raw`` suitable for passing to research_agent.

    Steps
    -----
    1. Strip leading/trailing whitespace.
    2. Truncate to ``_MAX_INPUT_LENGTH`` characters.
    3. Remove any character not in the alphanumeric + safe-punctuation allowlist.
    4. Collapse runs of whitespace to a single space.
    """
    text = raw.strip()[:_MAX_INPUT_LENGTH]
    text = _SAFE_CHARS.sub("", text)       # remove unsafe characters
    text = re.sub(r"\s+", " ", text).strip()  # normalise whitespace
    return text


def _before_agent_callback(callback_context: CallbackContext) -> Optional[types.Content]:
    """
    Validate and sanitise the user's raw input before the pipeline runs.

    Called automatically by ADK before the root ``SequentialAgent`` executes.
    Returning a ``types.Content`` object short-circuits the entire pipeline and
    delivers that content directly to the caller — the sub-agents never run.

    Returns
    -------
    ``types.Content``
        An error message if validation fails (pipeline is aborted).
    ``None``
        Validation passed — the pipeline runs normally.
    """
    # Pull the raw user message from the invocation context.
    # user_content is a types.Content; we concatenate all text Parts.
    user_content = callback_context.user_content
    raw_text: str = ""
    if user_content and user_content.parts:
        raw_text = " ".join(
            part.text for part in user_content.parts if part.text
        )

    # --- Guard 1: Reject empty input ---
    if not raw_text.strip():
        return types.Content(
            role="model",
            parts=[types.Part(text=(
                "I didn't receive a question. "
                "Please describe what you need — for example: "
                "'Find a free clinic near ZIP 90011 for primary care.'"
            ))],
        )

    # --- Guard 2: Sanitise and check residual length ---
    # SECURITY: strip non-allowlisted characters before the query reaches
    # research_agent and, transitively, the MCP tool subprocess.  See module
    # docstring for the full threat model.
    cleaned = _sanitise_input(raw_text)

    if not cleaned:
        # Every character was stripped — the input was pure punctuation /
        # special characters and contains no meaningful query.
        return types.Content(
            role="model",
            parts=[types.Part(text=(
                "Your message contained only special characters that cannot "
                "be processed safely. Please rephrase using plain text."
            ))],
        )

    # Overwrite the first text Part in place so the downstream agents receive
    # the cleaned string instead of the raw user input.
    if user_content and user_content.parts:
        for part in user_content.parts:
            if part.text is not None:
                # Pydantic models from google-genai are mutable via assignment.
                part.text = cleaned
                break

    # Returning None signals ADK to proceed with the pipeline unchanged.
    return None


# ---------------------------------------------------------------------------
# Root orchestrator — SequentialAgent
# ---------------------------------------------------------------------------
root_agent = SequentialAgent(
    name="clearhealth_orchestrator",
    description=(
        "Two-stage ClearHealth pipeline: (1) research_agent retrieves factual "
        "clinic information via the lookup_clinic MCP tool; (2) simplifier_agent "
        "rewrites the result in plain, accessible language."
    ),
    sub_agents=[
        research_agent,    # Stage 1: tool-grounded fact retrieval
        simplifier_agent,  # Stage 2: plain-language rewriting
    ],
    # Runs _before_ any sub-agent — rejects empty/malicious input early.
    before_agent_callback=_before_agent_callback,
)

# ---------------------------------------------------------------------------
# Local runner
# ---------------------------------------------------------------------------
# InMemoryRunner manages session state in-process (backed by InMemorySessionService
# internally) — no Redis, no database, no network required.  In ADK 2.3.0 the
# session_service is constructed internally; we pass only the root agent.
_runner = InMemoryRunner(agent=root_agent)


# ---------------------------------------------------------------------------
# Smoke-test entry point
# ---------------------------------------------------------------------------

def _extract_text(events: list) -> str:
    """
    Extract the last model-authored text from a list of ADK Events.

    ``run_debug`` returns a ``list[Event]``; we walk it in reverse to find
    the most recent content authored by the model (not the user).
    """
    for event in reversed(events):
        content = getattr(event, "content", None)
        if content and getattr(content, "role", None) == "model":
            parts = getattr(content, "parts", []) or []
            texts = [p.text for p in parts if getattr(p, "text", None)]
            if texts:
                return " ".join(texts)
    return "(no model response)"


async def run_query(query: str, user_id: str = "dev_user", session_id: str = "dev_session") -> str:
    """
    Send a single query through the full pipeline and return the final text.

    Parameters
    ----------
    query      : The user's natural-language health question.
    user_id    : Identifier for the user (arbitrary string for local testing).
    session_id : Identifier for the conversation session.

    Returns
    -------
    str
        The simplified plain-language answer produced by the pipeline, or
        the sanitisation error message if the input was rejected.
    """
    # run_debug returns list[Event]; quiet=True suppresses internal logging.
    events = await _runner.run_debug(query, user_id=user_id, session_id=session_id, quiet=True)
    return _extract_text(events)


async def _smoke_test() -> None:
    """Exercise the pipeline end-to-end with a known-good and a bad input."""
    test_cases = [
        ("Find a free clinic near ZIP 90011 for primary care.", "known-good query"),
        ("",                                                    "empty input"),
        (r'{"zipcode": "90011"; DROP TABLE clinics; --}',       "injection attempt"),
        ("90033 mental health",                                 "short-form query"),
    ]

    for query, label in test_cases:
        print(f"\n{'='*60}")
        print(f"[{label}] Input: {query!r}")
        print("-" * 60)
        result = await run_query(query, session_id=label.replace(" ", "_"))
        print("Output:", result)

    print(f"\n{'='*60}")
    print("Smoke test complete.")


if __name__ == "__main__":
    # Allow passing a single query from the command line:
    #   python -m app.agent "find clinic near 90033"
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
        asyncio.run(run_query(user_query))
    else:
        asyncio.run(_smoke_test())
