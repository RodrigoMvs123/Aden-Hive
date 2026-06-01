"""ALP v0.4.0 server — serves GET /card, GET /persona, GET /agents.

Start via: hive export-alp <agent_id> --serve [--port 8080]
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class _ALPHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for ALP v0.4.0 required endpoints."""

    card: dict[str, Any] = {}
    agents_dir: Path | None = None

    def log_message(self, fmt: str, *args: Any) -> None:  # silence default access log
        logger.debug(fmt, *args)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/card":
            self._send_json(self.card)

        elif self.path == "/persona":
            # Required in ALP v0.4.0
            self._send_json({
                "persona": self.card.get("persona", ""),
                "id": self.card.get("id", ""),
                "name": self.card.get("name", ""),
            })

        elif self.path == "/agents":
            # Optional in v0.4.0 — scan AGENTS_DIR or fall back to single card
            agents_dir = self.agents_dir or (
                Path(os.environ["AGENTS_DIR"]) if "AGENTS_DIR" in os.environ else None
            )
            if agents_dir and agents_dir.is_dir():
                agents = []
                for alp_file in sorted(agents_dir.rglob("agent.alp.json")):
                    try:
                        agents.append(json.loads(alp_file.read_text(encoding="utf-8")))
                    except Exception:
                        pass
                self._send_json({"agents": agents})
            else:
                self._send_json({"agents": [self.card]})

        elif self.path == "/health":
            self._send_json({"status": "ok", "alp_version": self.card.get("alp_version", "")})

        else:
            self._send_json({"error": f"Unknown endpoint: {self.path}"}, status=404)


def serve_alp(
    card: dict[str, Any],
    port: int = 8080,
    agents_dir: Path | None = None,
) -> None:
    """Start a blocking ALP v0.4.0 HTTP server serving the given card.

    Endpoints:
        GET /card     — full ALP card
        GET /persona  — persona text (required by v0.4.0)
        GET /agents   — all cards in agents_dir (optional, v0.4.0)
        GET /health   — liveness check
    """
    _ALPHandler.card = card
    _ALPHandler.agents_dir = agents_dir

    server = HTTPServer(("0.0.0.0", port), _ALPHandler)
    agent_id = card.get("id", "unknown")
    print(f"\u2713 ALP v0.4.0 server running for '{agent_id}' on http://0.0.0.0:{port}")
    print(f"  GET http://localhost:{port}/card")
    print(f"  GET http://localhost:{port}/persona")
    print(f"  GET http://localhost:{port}/agents")
    print("  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nALP server stopped.")
    finally:
        server.server_close()
