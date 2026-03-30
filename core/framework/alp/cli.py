"""CLI command: hive export-alp <agent-id>"""

import argparse
import json
import sys
from pathlib import Path


def register_alp_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register ALP export command with the main CLI."""
    p = subparsers.add_parser(
        "export-alp",
        help="Export a Hive agent as an ALP v0.2.2 card (agent.alp.json)",
        description=(
            "Reads a finalized Hive worker agent graph and writes an ALP-compliant "
            "agent.alp.json card to the current directory."
        ),
    )
    p.add_argument(
        "agent_id",
        type=str,
        help="Agent directory name (e.g. meeting_notes_agent)",
    )
    p.add_argument(
        "--server-url",
        type=str,
        default="https://your-hive-alp-server.com",
        help="URL where this agent's ALP server is hosted (default: placeholder)",
    )
    p.add_argument(
        "--output",
        "-o",
        type=str,
        default="agent.alp.json",
        help="Output file path (default: agent.alp.json in current directory)",
    )
    p.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip schema validation after export",
    )
    p.set_defaults(func=_cmd_export_alp)


def _cmd_export_alp(args: argparse.Namespace) -> int:
    from framework.alp.exporter import export_alp_card
    from framework.alp.validator import validate_alp_card

    print(f"Exporting ALP card for agent: {args.agent_id}")

    try:
        card = export_alp_card(args.agent_id, server_url=args.server_url)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if not args.no_validate:
        try:
            validate_alp_card(card)
            print("✓ ALP card validated against schema")
        except (ValueError, RuntimeError) as e:
            print(f"Validation warning: {e}", file=sys.stderr)
            print("Writing card anyway — fix validation errors before deploying.")

    output_path = Path(args.output)
    output_path.write_text(json.dumps(card, indent=2), encoding="utf-8")
    print(f"✓ ALP card written to: {output_path.resolve()}")
    return 0
