"""
app/simplifier_agent.py
-----------------------
Defines the ``simplifier_agent`` — an ADK sub-agent whose sole responsibility
is plain-language rewriting.

Role in the pipeline
--------------------
::

    research_agent  ──text──►  simplifier_agent  ──plain text──►  User
    (tool-grounded              (pure LLM, no tools)
     clinic facts)

The simplifier receives a block of text — typically the structured, technical
output produced by ``research_agent`` — and rewrites it at a 5th-grade reading
level so it is accessible to patients regardless of health literacy.

No tools
--------
This agent intentionally has **no tools attached**.  It is a pure text-in /
text-out transformer; all its work happens inside the LLM's forward pass.

Reasons for keeping it tool-free:

* **Separation of concerns** — fact retrieval is ``research_agent``'s job.
  Mixing retrieval and rewriting in one agent would make the pipeline harder
  to test, debug, and evaluate independently.
* **Determinism in testing** — a tool-free agent can be exercised with a
  plain string input and a mocked LLM, with no subprocess or network
  dependencies.
* **Grading transparency** — evaluators can verify rewriting quality by
  inspecting the prompt and output alone, without tracing tool calls.

Design note: target_language
-----------------------------
The instruction accepts an optional ``target_language`` context variable.
The orchestrator can inject it via ``InvocationContext`` metadata or by
prepending a line like "target_language: Spanish" to the input text before
routing to this agent.  When absent the agent defaults to English.

Usage
-----
Imported by ``app/agent.py`` and passed as a sub-agent to the orchestrator::

    from app.simplifier_agent import simplifier_agent
"""

from __future__ import annotations

from google.adk.agents import Agent

# ---------------------------------------------------------------------------
# simplifier_agent definition
# ---------------------------------------------------------------------------
simplifier_agent = Agent(
    name="simplifier_agent",
    # Gemini 2.5 Flash is well-suited for stylistic rewriting: fast, cost-efficient,
    # and capable of following precise tone/register instructions reliably.
    model="gemini-2.5-flash",
    description=(
        "Rewrites clinic and health information in plain, accessible language "
        "at a 5th-grade reading level.  Does not call any tools — accepts text "
        "input and returns transformed text only."
    ),
    instruction=(
        "Rewrite the input text at a 5th-grade reading level. "
        "Remove jargon. "
        "Keep all factual details (hours, eligibility, contact info) intact. "
        "If a target_language is provided, respond in that language."
    ),
    # No tools — this agent performs pure text transformation.
    # Passing an explicit empty list documents the intent clearly and prevents
    # any parent-level tool inheritance that a future refactor might introduce.
    tools=[],
)
