"""
app/research_agent.py
---------------------
Defines the ``research_agent`` — an ADK sub-agent responsible for answering
public-health questions by calling the ``lookup_clinic`` tool exposed by the
local MCP server (``app/tools/clinic_mcp_server.py``).

Architecture overview
---------------------
::

    User / Orchestrator
           │
           ▼
    research_agent  (ADK Agent, Gemini model)
           │  tool call: lookup_clinic(zipcode, need)
           ▼
    MCPToolset  ──stdio──►  clinic_mcp_server.py  (FastMCP subprocess)
                                     │
                                     ▼
                              hardcoded clinic dataset

Transport: stdio vs remote
--------------------------
We use **stdio transport** here because:

* **Zero configuration** — no ports to open, no TLS certificates, no auth
  tokens.  The MCP server is a subprocess whose stdin/stdout is the pipe.
* **Identical process lifetime** — the server lives and dies with the agent
  process, which is ideal during local development and Kaggle evaluation.
* **No network exposure** — the clinic data never leaves the machine, which
  is important when prototyping with patient-adjacent information.

What would change for a **remote / production deployment**:

1. Replace ``StdioConnectionParams`` with ``SseConnectionParams`` (or the
   future ``StreamableHttpConnectionParams`` in ADK ≥ 2.x) pointing at a
   deployed URL, e.g.::

       from google.adk.tools.mcp_tool.mcp_toolset import (
           MCPToolset, SseConnectionParams,
       )
       toolset = MCPToolset(
           connection_params=SseConnectionParams(
               url="https://clinic-mcp.example.com/sse",
               headers={"Authorization": f"Bearer {api_key}"},
           )
       )

2. The MCP server would be containerised (e.g. Cloud Run) and run
   ``mcp.run(transport="sse")`` or ``transport="streamable-http"``.

3. Authentication (OAuth2 / API key) would be handled at the transport layer,
   so the agent code above would not change further.

Usage
-----
This module is imported by ``app/agent.py`` (the root orchestrator).  The
``research_agent`` object is passed as a sub-agent so the orchestrator can
delegate clinic-lookup tasks to it.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file before importing ADK modules
load_dotenv()

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
from mcp.client.stdio import StdioServerParameters

# ---------------------------------------------------------------------------
# Locate the MCP server script
# ---------------------------------------------------------------------------
# We resolve the path at import time so the subprocess command works
# regardless of the current working directory when the agent is launched.
#
# Layout assumption (matches the scaffolded project):
#   clearhealth-agent/
#       app/
#           research_agent.py      ← this file
#           tools/
#               clinic_mcp_server.py  ← MCP server
#
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_MCP_SERVER_MODULE = "app.tools.clinic_mcp_server"

# ---------------------------------------------------------------------------
# MCP toolset — connects to the clinic_mcp_server subprocess via stdio
# ---------------------------------------------------------------------------
# StdioServerParameters tells the MCP client how to spawn the server process:
#   command : the Python interpreter inside our virtual environment
#   args    : run clinic_mcp_server as a module so Python resolves the
#             package imports correctly (equivalent to
#             `python -m app.tools.clinic_mcp_server`)
#   cwd     : project root ensures the `app` package is on sys.path

_clinic_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            # Use the same interpreter that is running the agent, so we are
            # guaranteed to use the venv where google-adk and mcp are installed.
            command=sys.executable,
            args=["-m", _MCP_SERVER_MODULE],
            cwd=str(_PROJECT_ROOT),
        ),
        # timeout (seconds) to wait for the MCP server to start up before
        # the first tool call.  5 s is generous for a local subprocess.
        timeout=5,
    )
)

# ---------------------------------------------------------------------------
# research_agent definition
# ---------------------------------------------------------------------------
research_agent = Agent(
    name="research_agent",
    # Gemini 2.5 Flash is chosen for speed, cost-efficiency, and higher quota availability
    model="gemini-2.5-flash",
    description=(
        "Answers public-health questions by querying a local clinic directory "
        "via the lookup_clinic MCP tool.  Returns factual, tool-grounded "
        "responses only — never invents clinic details."
    ),
    instruction=(
        "You answer public health questions factually using the lookup_clinic tool. "
        "Never invent clinic details — only use what the tool returns. "
        "If the tool finds no match, say so clearly."
    ),
    # Attach the MCP toolset so the agent discovers lookup_clinic automatically
    # via MCP's tool-listing protocol at session start.
    tools=[_clinic_toolset],
)
