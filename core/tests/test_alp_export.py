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
    "alp_version": "0.9.0",
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
    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
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
            with patch("framework.alp.exporter.get_hive_config",
                       return_value={"llm": {"model": "gemini/gemini-2.0-flash"}}):
                card = export_alp_card("test_agent")

        assert isinstance(card, dict)
        for field in ("alp_version", "id", "name", "persona", "llm", "server"):
            assert field in card, f"Missing required ALP field: {field}"

    def test_alp_version_is_correct(self, tmp_path):
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.alp.exporter.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        assert card["alp_version"] == "0.9.0"

    def test_no_secrets_in_card(self, tmp_path):
        """Card must not contain any raw API keys — only auth_ref strings."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.alp.exporter.get_hive_config",
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
            with patch("framework.alp.exporter.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        tool_names = [t["name"] for t in card.get("tools", [])]
        assert "save_data" in tool_names
        assert "serve_file_to_user" in tool_names

    def test_provider_mapped_correctly(self, tmp_path):
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.alp.exporter.get_hive_config",
                       return_value={"llm": {"model": "gemini/gemini-2.0-flash"}}):
                card = export_alp_card("test_agent")

        assert card["llm"]["provider"] == "google"
        assert card["llm"]["model"] == "gemini-2.0-flash"

    def test_v090_fields_present(self, tmp_path):
        """Card includes new v0.9.0 fields: runtime, toolsets, security, server.channel."""
        from framework.alp.exporter import export_alp_card

        agent_dir = _make_mock_agent(tmp_path)
        with patch("framework.alp.exporter._resolve_agent_path", return_value=agent_dir):
            with patch("framework.alp.exporter.get_hive_config", return_value={}):
                card = export_alp_card("test_agent")

        # runtime.deploy block (v0.9.0)
        assert "runtime" in card
        assert "deploy" in card["runtime"]
        assert card["runtime"]["deploy"]["trigger"] == "manual"

        # toolsets (v0.3.0)
        assert "toolsets" in card
        assert "groups" in card["toolsets"]

        # security (v0.3.0)
        assert "security" in card
        assert "read_only" in card["security"]
        assert "max_tool_retries" in card["security"]

        # server.channel (v0.9.0)
        assert card["server"]["channel"] == "stable"


# ---------------------------------------------------------------------------
# validate_alp_card tests
# ---------------------------------------------------------------------------

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
