"""Tests for ALP export and validation."""

import json
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EXAMPLE_CARD_URL = (
    "https://raw.githubusercontent.com/RodrigoMvs123/agent-load-protocol"
    "/main/examples/hive-agent/agent.alp.json"
)

MINIMAL_VALID_CARD = {
    "alp_version": "0.4.0",
    "id": "test-agent",
    "name": "Test Agent",
    "persona": "You are a test agent.",
    "llm": {"provider": "any"},
    "server": {"url": "https://example.com", "transport": "http"},
}

MINIMAL_INVALID_CARD = {
    # Missing required: alp_version, persona, llm, server
    "id": "bad-agent",
    "name": "Bad Agent",
}


def _make_mock_agent(tmp_path: Path, name: str = "Test Agent") -> Path:
    """Create a minimal agent.json in a temp directory."""
    agent_dir = tmp_path / f"test_agent_{name.replace(' ', '_').lower()}"
    agent_dir.mkdir(exist_ok=True)
    agent_data = {
        "agent": {"id": "test_agent", "name": name, "version": "1.0.0",
                  "description": "A test agent."},
        "graph": {
            "id": "test-graph",
            "goal_id": "test-goal",
            "entry_node": "start",
            "identity_prompt": "You are a test agent.",
            "nodes": [
                {"id": "start", "name": "Start", "client_facing": True, "tools": ["save_data"]},
                {"id": "end", "name": "End", "client_facing": False, "tools": []},
            ],
            "edges": [],
            "entry_points": {"start": "start"},
        },
        "goal": {"id": "test-goal", "name": "Test Goal", "description": "Do a test."},
        "required_tools": ["save_data", "serve_file_to_user"],
    }
    (agent_dir / "agent.json").write_text(json.dumps(agent_data), encoding="utf-8")
    return agent_dir


# ---------------------------------------------------------------------------
# export_alp_card tests
# ---------------------------------------------------------------------------

class TestExportAlpCard:
    def test_returns_dict_with_required_fields(self, tmp_path):
        """export_alp_card returns a dict containing all ALP required fields."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)

        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config",
                       return_value={"llm": {"model": "gemini/gemini-2.0-flash"}}):
                card = export_alp_card("test_agent")

        assert isinstance(card, dict)
        for field in ("alp_version", "id", "name", "persona", "llm", "server"):
            assert field in card, f"Missing required ALP field: {field}"

    def test_alp_version_is_correct(self, tmp_path):
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        assert card["alp_version"] == "0.4.0"

    def test_no_secrets_in_card(self, tmp_path):
        """Card must not contain any raw API keys — only auth_ref strings."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config",
                       return_value={"llm": {"model": "anthropic/claude-3-haiku",
                                             "api_key_env_var": "ANTHROPIC_API_KEY"}}):
                card = export_alp_card("test_agent")

        card_str = json.dumps(card)
        # No raw key patterns should appear
        assert "sk-ant-" not in card_str
        assert "api_key" not in card_str.lower() or "auth_ref" in card_str

    def test_tools_mapped_from_agent(self, tmp_path):
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        tool_names = [t["name"] for t in card.get("tools", [])]
        assert "save_data" in tool_names
        assert "serve_file_to_user" in tool_names

    def test_tools_have_readonly_and_auth_fields(self, tmp_path):
        """Every tool in the exported card must have readonly and auth fields."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        for tool in card.get("tools", []):
            assert "readonly" in tool, f"Tool {tool['name']} missing 'readonly'"
            assert "auth" in tool, f"Tool {tool['name']} missing 'auth'"
            assert "deprecated" in tool, f"Tool {tool['name']} missing 'deprecated'"

    def test_v030_fields_present(self, tmp_path):
        """Card must include toolsets, tools_discovery, security, triggers, bulk_schedule."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        assert "toolsets" in card
        assert "groups" in card["toolsets"]
        assert "tools_discovery" in card
        assert card["tools_discovery"]["mode"] == "static"
        assert "security" in card
        assert "max_tool_retries" in card["security"]
        assert "triggers" in card
        assert len(card["triggers"]) > 0
        assert "bulk_schedule" in card
        assert card["bulk_schedule"]["enabled"] is False

    def test_server_block_has_v040_fields(self, tmp_path):
        """server block must include channel and modes (v0.4.0)."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        assert card["server"]["channel"] == "stable"
        assert "modes" in card["server"]

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.config.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        tool_names = [t["name"] for t in card.get("tools", [])]
        assert "save_data" in tool_names
        assert "serve_file_to_user" in tool_names

    def test_provider_mapped_correctly(self, tmp_path):
        from framework.alp.exporter import export_alp_card
        import framework.alp.exporter as exporter_module

        agent_dir = _make_mock_agent(tmp_path, name="Provider Test")
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch.object(exporter_module, "get_hive_config",
                              return_value={"llm": {"model": "gemini/gemini-2.0-flash"}}):
                card = export_alp_card("test_agent")

        assert card["llm"]["provider"] == "google"
        assert card["llm"]["model"] == "gemini-2.0-flash"



# ---------------------------------------------------------------------------
# ALP v0.4.0 server tests
# ---------------------------------------------------------------------------

class TestALPServer:
    def test_persona_endpoint(self):
        """GET /persona returns persona, id, and name."""
        import threading
        import urllib.request
        from framework.alp.server import serve_alp

        card = {
            **MINIMAL_VALID_CARD,
            "alp_version": "0.4.0",
            "id": "test-agent",
            "name": "Test Agent",
            "persona": "You are a test agent.",
        }
        t = threading.Thread(target=serve_alp, kwargs={"card": card, "port": 19876}, daemon=True)
        t.start()
        import time; time.sleep(0.3)

        req = urllib.request.Request("http://localhost:19876/persona")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        assert data["persona"] == "You are a test agent."
        assert data["id"] == "test-agent"
        assert data["name"] == "Test Agent"

    def test_agents_endpoint_fallback(self):
        """GET /agents falls back to single card when no AGENTS_DIR set."""
        import threading
        import urllib.request
        from framework.alp.server import serve_alp

        card = {
            **MINIMAL_VALID_CARD,
            "alp_version": "0.4.0",
            "id": "solo-agent",
            "name": "Solo",
            "persona": "You are solo.",
        }
        t = threading.Thread(target=serve_alp, kwargs={"card": card, "port": 19877}, daemon=True)
        t.start()
        import time; time.sleep(0.3)

        req = urllib.request.Request("http://localhost:19877/agents")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        assert len(data["agents"]) == 1
        assert data["agents"][0]["id"] == "solo-agent"

    def test_agents_endpoint_scans_dir(self, tmp_path):
        """GET /agents scans agents_dir for agent.alp.json files."""
        import threading
        import urllib.request
        from framework.alp.server import serve_alp

        for agent_id in ("agent-a", "agent-b"):
            d = tmp_path / agent_id
            d.mkdir()
            (d / "agent.alp.json").write_text(
                json.dumps({**MINIMAL_VALID_CARD, "id": agent_id, "name": agent_id}),
                encoding="utf-8",
            )

        card = {**MINIMAL_VALID_CARD, "id": "host", "name": "Host", "persona": "Host."}
        t = threading.Thread(
            target=serve_alp,
            kwargs={"card": card, "port": 19878, "agents_dir": tmp_path},
            daemon=True,
        )
        t.start()
        import time; time.sleep(0.3)

        req = urllib.request.Request("http://localhost:19878/agents")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        ids = {a["id"] for a in data["agents"]}
        assert "agent-a" in ids
        assert "agent-b" in ids

class TestValidateAlpCard:
    def test_valid_card_passes(self):
        """validate_alp_card returns True for a valid minimal card."""
        pytest.importorskip("jsonschema")
        from framework.alp.validator import validate_alp_card, _fetch_schema
        import framework.alp.validator as v_module

        # Use cached schema if available, else fetch
        try:
            result = validate_alp_card(MINIMAL_VALID_CARD)
            assert result is True
        except RuntimeError as e:
            pytest.skip(f"Schema unreachable (no internet?): {e}")

    def test_example_card_from_repo_passes(self):
        """The official Hive example card from the ALP repo validates successfully."""
        pytest.importorskip("jsonschema")
        from framework.alp.validator import validate_alp_card
        import framework.alp.validator as v_module

        try:
            req = urllib.request.Request(EXAMPLE_CARD_URL, headers={"User-Agent": "Hive/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                example_card = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            pytest.skip(f"Could not fetch example card (no internet?): {e}")

        try:
            result = validate_alp_card(example_card)
            assert result is True
        except RuntimeError as e:
            pytest.skip(f"Schema unreachable: {e}")

    def test_invalid_card_raises_value_error(self):
        """validate_alp_card raises ValueError for a card missing required fields."""
        pytest.importorskip("jsonschema")
        from framework.alp.validator import validate_alp_card

        try:
            with pytest.raises(ValueError, match="ALP card validation failed"):
                validate_alp_card(MINIMAL_INVALID_CARD)
        except RuntimeError as e:
            pytest.skip(f"Schema unreachable (no internet?): {e}")

    def test_missing_required_field_reported(self):
        """Validation error message names the missing field."""
        pytest.importorskip("jsonschema")
        from framework.alp.validator import validate_alp_card

        card = {**MINIMAL_VALID_CARD}
        del card["persona"]

        try:
            with pytest.raises(ValueError) as exc_info:
                validate_alp_card(card)
            assert "persona" in str(exc_info.value)
        except RuntimeError as e:
            pytest.skip(f"Schema unreachable: {e}")
