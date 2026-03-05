# Agent Proposal: Meeting Notes Agent (v0.6.2)

**Relates to** [#4150](https://github.com/aden-hive/hive/issues/4150) — Build a Sample Agent with Hive

## Problem Statement

Every team runs meetings, but turning raw transcripts into structured, actionable records is tedious and time-consuming. Currently there is no Hive sample agent that demonstrates:

- Multi-node event loop pipeline with client-facing interaction points
- Structured data extraction with LLM-based parsing
- Slack MCP tool integration for optional delivery
- User review and approval workflow before final delivery
- v0.6.2 NodeSpec-based architecture

This agent fills that gap and serves as an accessible, immediately useful sample for teams new to Hive.

## Proposed Agent

**Goal statement:**

> "Given a meeting transcript, extract a structured executive summary, list of key decisions, action items with assigned owners and due dates (priority: high/medium/low), blockers, and follow-ups. Present results for user review, then save to file and optionally post to a Slack channel."

### Agent Graph

```
intake (client-facing)
  │
  └─ on_success → extract
                    │
                    └─ on_success → review (client-facing)
                                      │
                                      └─ conditional (approved == True) → deliver (client-facing)
```

**4 nodes, 3 edges**

### Success Criteria

| ID | Criterion |
|----|-----------|
| `sc_summary` | 2–3 sentence executive summary produced from transcript |
| `sc_action_items` | All action items extracted with owner, due date, and priority |
| `sc_decisions` | All explicit decisions captured |
| `sc_no_hallucination` | Only information explicitly stated in transcript is extracted |
| `sc_user_review` | User reviews and approves extraction before delivery |
| `sc_slack_delivery` | When slack_channel is provided, message delivered via Slack MCP tool |

### Constraints

| ID | Type | Rule |
|----|------|------|
| `c_no_hallucination` | hard | Only extract what is explicitly stated in the transcript |
| `c_owner_assignment` | hard | Action items only assigned to people named in the transcript |
| `c_user_review` | hard | User must review and approve before delivery |

### Input / Output

**Input:**
```json
{
  "transcript": "...",
  "meeting_name": "Q1 Planning",
  "meeting_date": "2026-02-20",
  "slack_channel": "#team-standup"
}
```

**Output:**
```json
{
  "summary": "...",
  "attendees": ["Sarah Chen (PM)", "..."],
  "decisions": ["Mobile app launch target is March 31st"],
  "action_items": [
    { "task": "Fix Apple cert", "owner": "Marcus", "due": "EOD Tuesday", "priority": "high" }
  ],
  "blockers": ["Apple Developer certificate renewal pending"],
  "follow_ups": ["Aisha to share Figma link by EOD"],
  "delivery_status": "completed"
}
```

## Tools / Integrations Required

| Tool | Already in hive-tools? | Notes |
|------|------------------------|-------|
| `save_data` | ✅ | Save meeting notes to markdown file |
| `serve_file_to_user` | ✅ | Provide download link to user |
| `slack_post_message` | ✅ | Slack Web API chat.postMessage (optional) |

The Slack tool follows the `credentialSpec` + `credentialStore` pattern.

**Slack scopes required:** `chat:write`, `chat:write.public`

### ⚠️ IMPORTANT: Slack OAuth Integration Missing

Currently, **Slack is NOT available** as an OAuth integration on the Aden platform (https://hive.adenhq.com/). 

The following integrations are available:
- Composio Gmail
- Google (Gmail, Calendar, Sheets)
- HubSpot
- GitHub
- Notion
- Twitter / X

**For this agent to work seamlessly in production, Slack needs to be added to the Aden OAuth platform alongside the other integrations listed above.**

**Workaround:** Users can manually set `SLACK_BOT_TOKEN` in their `.env` file or use `hive setup-credentials`, but this is not ideal for the production user experience.

## Files Included

```
examples/templates/meeting_notes_agent/
├── __init__.py
├── __main__.py          # hive run / python -m entry point
├── agent.json           # Legacy metadata (kept for compatibility)
├── agent.py             # Graph orchestration + MeetingNotesAgent class
├── config.py            # RuntimeConfig + AgentMetadata
├── mcp_servers.json     # MCP server config pointing to hive-tools
├── README.md            # Complete documentation with examples
└── nodes/
    └── __init__.py      # NodeSpec definitions for all 4 nodes
```

## Why This Is a Good Sample Agent

- **Beginner-friendly** — Clear 4-node pipeline with intuitive flow
- **Showcases v0.6.2 architecture** — NodeSpec-based, matches Deep Research Agent pattern
- **Client-facing interaction** — Demonstrates user review workflow (3 of 4 nodes are client-facing)
- **Real-world utility** — Immediately useful for any team running meetings
- **Optional Slack integration** — Shows how to conditionally use MCP tools
- **Directly maps to the roadmap** — Aligns with the Sample Agents item in the Foundation section

## How to Run (once merged)

```bash
# Via Hive UI (recommended)
hive serve
# Navigate to http://127.0.0.1:8787 and select "Meeting Notes Agent"

# Via CLI
hive run examples.templates.meeting_notes_agent

# Via Python
python -m examples.templates.meeting_notes_agent
```

## Implementation Status

- ✅ `agent.py` — Graph orchestration with MeetingNotesAgent class
- ✅ `nodes/__init__.py` — All 4 NodeSpec definitions (intake, extract, review, deliver)
- ✅ `config.py` — RuntimeConfig + AgentMetadata with Queen Bee intro message
- ✅ `mcp_servers.json` — MCP server wiring to hive-tools
- ✅ `__init__.py` — Proper exports matching v0.6.2 pattern
- ✅ `__main__.py` — CLI entry point
- ✅ `README.md` — Full setup + usage docs with examples
- ✅ **Tested in UI** — Agent loads successfully, displays pipeline graph, processes through nodes

## Migration Notes

This agent was migrated from an older format to v0.6.2 architecture:

- Restructured to use `NodeSpec` objects instead of `agent.json`-driven nodes
- Removed old `nodes.py` file, created `nodes/__init__.py` with proper NodeSpec definitions
- Updated graph building to use framework imports (`GraphSpec`, `EdgeSpec`, etc.)
- Matched structure of working agents (Deep Research Agent, Email Inbox Management)
- Added Slack integration as optional delivery method
- All nodes use `event_loop` type with proper `client_facing` flags

## Additional Fix: Agent Discovery in Codespaces

Fixed an issue where sample agents were not appearing in the UI when running `hive serve` in Codespaces:

- Modified `core/framework/tui/screens/agent_picker.py` to use absolute paths instead of relative paths
- Changed `Path("examples/templates")` to resolve from project root using `__file__`
- This ensures agents are discovered regardless of the server's working directory
- **File modified:** `core/framework/tui/screens/agent_picker.py`

## Maintainer Review & Assignment

**Branch:** `feat/meeting-notes-agent`  
**Repository:** https://github.com/RodrigoMvs123/Aden-Hive  
**Ready to open a PR to upstream** after review and assignment per [CONTRIBUTING.md](https://github.com/aden-hive/hive/blob/main/CONTRIBUTING.md).

## Action Items for Aden Team

1. **Add Slack OAuth integration** to https://hive.adenhq.com/ platform (same as Gmail, GitHub, HubSpot, etc.)
2. Review and merge this sample agent
3. Consider this agent as a template for future sample agents using v0.6.2 architecture
