"""ALP (Agent Load Protocol) exporter for Hive agents.

Reads a finalized Hive worker agent graph and maps it to an ALP v0.4.0 card.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from framework.config import get_hive_config

logger = logging.getLogger(__name__)

ALP_VERSION = "0.4.0"
ALP_SCHEMA_URL = (
    "https://raw.githubusercontent.com/RodrigoMvs123/agent-load-protocol"
    "/main/schema/agent.alp.schema.json"
)

# Map Hive LLM provider names to ALP-allowed provider values
_PROVIDER_MAP: dict[str, str] = {
    "anthropic": "anthropic",
    "openai": "openai",
    "google": "google",
    "gemini": "google",
    "mistral": "mistral",
    "ollama": "ollama",
}


def _slugify(text: str) -> str:
    """Convert a string to a lowercase slug safe for ALP id field."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _map_provider(model_str: str) -> tuple[str, str]:
    """Return (alp_provider, model) from a Hive model string like 'gemini/gemini-2.0-flash'."""
    if "/" in model_str:
        prefix, model = model_str.split("/", 1)
        provider = _PROVIDER_MAP.get(prefix.lower(), "any")
        return provider, model
    return "any", model_str


def _map_capabilities(agent_data: dict) -> list[str]:
    """Derive ALP capabilities from the agent graph definition."""
    caps: list[str] = ["tool-use", "streaming", "memory"]

    graph = agent_data.get("graph", {})
    nodes = graph.get("nodes", [])

    # human-in-the-loop: any node is client_facing (pauses for user input)
    if any(n.get("client_facing") for n in nodes):
        caps.append("human-in-the-loop")

    # self-healing: Hive queen always provides self-healing via the coding agent
    caps.append("self-healing")

    # parallel-execution: multiple nodes with no sequential dependency
    if len(nodes) > 2:
        caps.append("parallel-execution")

    # triggered-execution: agent has triggers defined
    if graph.get("entry_points") and len(graph.get("entry_points", {})) > 1:
        caps.append("triggered-execution")

    return list(dict.fromkeys(caps))  # deduplicate, preserve order


# Read-only tools that perform no mutations
_READONLY_TOOLS: frozenset[str] = frozenset({
    "search_files", "read_file", "list_directory", "get_agent_info",
    "list_agents", "get_logs", "get_session_status",
})


def _map_tools(agent_data: dict, server_url: str) -> list[dict]:
    """Map Hive agent nodes with tools to ALP tool definitions."""
    graph = agent_data.get("graph", {})
    nodes = graph.get("nodes", [])
    required_tools: list[str] = agent_data.get("required_tools", [])

    alp_tools = []
    seen: set[str] = set()

    for node in nodes:
        node_tools = node.get("tools", [])
        for tool_name in node_tools:
            if tool_name in seen:
                continue
            seen.add(tool_name)
            alp_tools.append({
                "name": tool_name,
                "description": f"Hive tool: {tool_name.replace('_', ' ')}",
                "endpoint": f"/tools/{tool_name}",
                "readonly": tool_name in _READONLY_TOOLS,
                "deprecated": False,
                "auth": {"type": "none"},
            })

    for tool_name in required_tools:
        if tool_name not in seen:
            seen.add(tool_name)
            alp_tools.append({
                "name": tool_name,
                "description": f"Hive tool: {tool_name.replace('_', ' ')}",
                "endpoint": f"/tools/{tool_name}",
                "readonly": tool_name in _READONLY_TOOLS,
                "deprecated": False,
                "auth": {"type": "none"},
            })

    return alp_tools


def _map_triggers(agent_data: dict) -> list[dict]:
    """Derive ALP triggers from the agent graph definition."""
    graph = agent_data.get("graph", {})
    triggers = []

    # Hive supports schedulers and webhooks as entry points
    entry_points = graph.get("entry_points", {})
    for ep_name in entry_points:
        if "schedule" in ep_name.lower() or "cron" in ep_name.lower():
            triggers.append({"type": "schedule", "config": {}})
        elif "webhook" in ep_name.lower():
            triggers.append({"type": "webhook", "config": {}})

    if not triggers:
        triggers.append({"type": "manual", "config": {}})

    return triggers


def _map_toolsets(agent_data: dict) -> dict:
    """Build ALP toolsets from agent node tool groupings."""
    graph = agent_data.get("graph", {})
    nodes = graph.get("nodes", [])

    groups: dict[str, list[str]] = {"default": []}
    seen: set[str] = set()

    for node in nodes:
        for tool_name in node.get("tools", []):
            if tool_name not in seen:
                seen.add(tool_name)
                groups["default"].append(tool_name)

    return {"groups": groups, "active": "default"}


def _load_agent_data(agent_path: Path) -> dict:
    """Load agent.json from the given path."""
    agent_json = agent_path / "agent.json"
    if not agent_json.exists():
        raise FileNotFoundError(f"agent.json not found at {agent_json}")
    return json.loads(agent_json.read_text(encoding="utf-8"))


def _resolve_agent_path(agent_id: str) -> Path:
    """Resolve agent_id to a filesystem path.

    Searches in order:
    1. exports/<agent_id>
    2. examples/templates/<agent_id>
    3. ~/.hive/agents/<agent_id>
    """
    from framework.cli import _configure_paths
    _configure_paths()

    # Determine project root
    framework_dir = Path(__file__).resolve().parent.parent  # core/framework
    core_dir = framework_dir.parent                          # core
    project_root = core_dir.parent                           # project root

    candidates = [
        project_root / "exports" / agent_id,
        project_root / "examples" / "templates" / agent_id,
        Path.home() / ".hive" / "agents" / agent_id,
    ]

    for path in candidates:
        if (path / "agent.json").exists():
            return path

    raise FileNotFoundError(
        f"Agent '{agent_id}' not found. Searched:\n"
        + "\n".join(f"  {p}" for p in candidates)
    )


def export_alp_card(
    agent_id: str,
    server_url: str = "https://your-hive-alp-server.com",
) -> dict[str, Any]:
    """Read a finalized Hive worker agent and return an ALP v0.2.2 card dict.

    Args:
        agent_id: The agent directory name (e.g. 'meeting_notes_agent').
        server_url: The URL where this agent's ALP server is hosted.

    Returns:
        A dict conforming to the ALP v0.2.2 schema. No secrets included.
    """
    agent_path = _resolve_agent_path(agent_id)
    agent_data = _load_agent_data(agent_path)

    agent_meta = agent_data.get("agent", {})
    graph = agent_data.get("graph", {})
    goal = agent_data.get("goal", {})

    # Identity
    name = agent_meta.get("name", agent_id)
    description = agent_meta.get("description", goal.get("description", ""))
    persona = graph.get("identity_prompt", f"You are {name}.")

    # LLM config — read from hive config, never hardcode
    hive_cfg = get_hive_config()
    model_str = hive_cfg.get("llm", {}).get("model", "")
    alp_provider, alp_model = _map_provider(model_str) if model_str else ("any", "user-defined")

    # Capabilities
    capabilities = _map_capabilities(agent_data)

    # Tools
    tools = _map_tools(agent_data, server_url)

    # Workforce: Hive workers are standalone by default
    # Queen-managed agents are "worker" role
    workforce = {
        "role": "worker",
        "connections": [],
    }

    # Toolsets and triggers
    toolsets = _map_toolsets(agent_data)
    triggers = _map_triggers(agent_data)

    card: dict[str, Any] = {
        "alp_version": ALP_VERSION,
        "id": _slugify(name),
        "name": name,
        "description": description,
        "agent_type": "single",
        "capabilities": capabilities,
        "persona": persona,
        "llm": {
            "provider": alp_provider,
            "model": alp_model,
        },
        "toolsets": toolsets,
        "tools_discovery": {
            "enabled": False,
            "mode": "static",
        },
        "security": {
            "read_only": False,
            "lockdown_mode": False,
            "max_tool_retries": 5,
        },
        "tools": tools,
        "triggers": triggers,
        "bulk_schedule": {
            "enabled": False,
            "concurrency": 1,
        },
        "memory": {
            "enabled": True,
            "backend": "hive-internal",
        },
        "observability": {
            "websocket": True,
            "endpoint": "/stream",
            "logs_endpoint": "/logs",
        },
        "workforce": workforce,
        "alerts": [
            {
                "trigger": "tool_failure",
                "action": "escalate",
                "channel": "webhook",
                "auth_ref": "hive_alert_webhook",
            },
            {
                "trigger": "human_approval_required",
                "action": "pause",
                "channel": "email",
                "auth_ref": "hive_alert_email",
            },
        ],
        "server": {
            "url": server_url,
            "transport": "websocket",
            "channel": "stable",
            "modes": {
                "read_only": False,
                "lockdown": False,
            },
        },
        "marketplace": {
            "category": "automation",
            "tags": ["hive", agent_id.replace("_", "-")],
            "pricing_model": "per-run",
        },
        "variables": {},
        "metadata": {
            "author": "",
            "version": agent_meta.get("version", "1.0.0"),
            "tags": ["hive"],
            "repository": "https://github.com/aden-hive/hive",
        },
        "platform": {
            "name": "hive",
            "agent_id": agent_id,
        },
    }

    logger.info("Exported ALP card for agent '%s' (id=%s)", name, card["id"])
    return card
