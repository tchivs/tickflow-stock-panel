"""Internal Phase 1 receiver for sanitized fixture delivery outcomes."""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from typing import ClassVar


class Receiver(BaseHTTPRequestHandler):
    outcomes: ClassVar[list[dict[str, str]]] = []
    lock: ClassVar[Lock] = Lock()

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: HTTPStatus, body: dict[str, object]) -> None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:  # noqa: N802
        channel = {"/feishu": "feishu", "/telegram": "telegram"}.get(self.path)
        if channel is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "unknown fixture endpoint"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > 32_768:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid request"})
            return
        self.rfile.read(length)
        with self.lock:
            self.outcomes.append({"channel": channel, "status": "received"})
        self._json(HTTPStatus.OK, {"code": 0} if channel == "feishu" else {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/outcomes":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        with self.lock:
            outcomes = list(self.outcomes)
        self._json(HTTPStatus.OK, {"outcomes": outcomes})


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", 8080), Receiver).serve_forever()


if __name__ == "__main__":
    main()
