#!/usr/bin/env python3
"""Local HTTP API and static server for the Bufftag live terminal.

The server binds only to loopback, validates Host and Origin, requires a
same-origin token for mutations, contains all filesystem operations under one
workspace, never executes shell commands, and keeps writes disabled unless the
operator starts it with --allow-write.
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
import secrets
import sys
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

try:
    from Bufftag import bufftag
except ModuleNotFoundError:  # Allows `python Bufftag/server.py` from repository root.
    import bufftag


WEB_ROOT = Path(__file__).resolve().parent / "web"
DEFAULT_WORKSPACE = Path(__file__).resolve().parents[1]
MAX_BODY_BYTES = 64 * 1024
ALLOWED_HOSTS = {"localhost", "127.0.0.1"}
CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}


class RequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ServerConfig:
    workspace: Path
    allow_write: bool
    signing_secret: bytes | None
    signing_env: str
    api_token: str


class BufftagServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], config: ServerConfig):
        self.config = config
        super().__init__(address, BufftagRequestHandler)


class BufftagRequestHandler(BaseHTTPRequestHandler):
    server_version = "BufftagLocal/1"
    sys_version = ""

    @property
    def config(self) -> ServerConfig:
        return self.server.config  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.client_address[0]} "
            f"{format % args}\n"
        )

    def _host_is_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        if host.startswith("["):
            return host in {"[::1]", "[::1]:8765"}
        hostname, separator, port = host.rpartition(":")
        if not separator:
            hostname, port = host, ""
        if hostname not in ALLOWED_HOSTS:
            return False
        expected = str(self.server.server_address[1])
        return not port or port == expected

    def _origin_is_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        parsed = urlsplit(origin)
        request_host = self.headers.get("Host", "")
        return parsed.scheme == "http" and parsed.netloc == request_host

    def _security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'self'",
        )

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self._security_headers(content_type)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", extra_headers)

    def _send_error_json(self, error: RequestError) -> None:
        self._send_json(
            error.status,
            {"ok": False, "error": {"code": error.code, "message": error.message}},
        )

    def _guard_request(self, mutation: bool = False) -> None:
        if not self._host_is_allowed():
            raise RequestError(HTTPStatus.FORBIDDEN, "host_denied", "Host is not loopback")
        if not self._origin_is_allowed():
            raise RequestError(HTTPStatus.FORBIDDEN, "origin_denied", "Origin does not match Host")
        if mutation:
            supplied = self.headers.get("X-Bufftag-Token", "")
            if not hmac.compare_digest(supplied, self.config.api_token):
                raise RequestError(
                    HTTPStatus.UNAUTHORIZED,
                    "token_denied",
                    "same-origin API token is required",
                )

    def _read_json(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            raise RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "content_type",
                "Content-Type must be application/json",
            )
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, "content_length", "invalid Content-Length") from exc
        if length <= 0:
            raise RequestError(HTTPStatus.BAD_REQUEST, "empty_body", "request body is required")
        if length > MAX_BODY_BYTES:
            raise RequestError(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "body_too_large",
                f"request body exceeds {MAX_BODY_BYTES} bytes",
            )
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RequestError(HTTPStatus.BAD_REQUEST, "json_invalid", str(exc)) from exc
        if not isinstance(payload, dict):
            raise RequestError(HTTPStatus.BAD_REQUEST, "json_shape", "body must be an object")
        return payload

    def _scope(self, raw: Any) -> Path:
        if raw is None or raw == ".":
            scope = self.config.workspace
        elif isinstance(raw, str) and raw:
            requested = Path(raw)
            if requested.is_absolute() or ".." in requested.parts:
                raise RequestError(HTTPStatus.BAD_REQUEST, "scope_denied", "scope must be relative")
            scope = (self.config.workspace / requested).resolve()
        else:
            raise RequestError(HTTPStatus.BAD_REQUEST, "scope", "scope must be a string")
        try:
            scope.relative_to(self.config.workspace)
        except ValueError as exc:
            raise RequestError(HTTPStatus.FORBIDDEN, "scope_denied", "scope escapes workspace") from exc
        if not scope.is_dir():
            raise RequestError(HTTPStatus.NOT_FOUND, "scope_missing", "scope does not exist")
        return scope

    def _receipts(self, scope: Path) -> Path:
        return scope / ".bufftag" / "receipts.jsonl"

    def _static(self) -> None:
        self._guard_request()
        raw_path = unquote(urlsplit(self.path).path)
        if "\x00" in raw_path:
            raise RequestError(HTTPStatus.BAD_REQUEST, "path_invalid", "null byte in path")
        relative = "index.html" if raw_path == "/" else raw_path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()
        try:
            target.relative_to(WEB_ROOT.resolve())
        except ValueError as exc:
            raise RequestError(HTTPStatus.FORBIDDEN, "path_denied", "path escapes web root") from exc
        if not target.is_file():
            raise RequestError(HTTPStatus.NOT_FOUND, "not_found", "resource not found")
        content_type = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
        self._send_bytes(HTTPStatus.OK, target.read_bytes(), content_type)

    def do_GET(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._guard_request()
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "bufftag-local",
                        "version": bufftag.VERSION,
                        "workspace": str(self.config.workspace),
                        "allow_write": self.config.allow_write,
                        "signing": {
                            "mode": "hmac-sha256" if self.config.signing_secret else "unsigned",
                            "environment": self.config.signing_env,
                        },
                        "api_token": self.config.api_token,
                    },
                )
                return
            if path.startswith("/api/"):
                raise RequestError(HTTPStatus.NOT_FOUND, "not_found", "unknown API route")
            self._static()
        except RequestError as exc:
            self._send_error_json(exc)
        except Exception as exc:  # Do not leak filesystem details from an unexpected handler fault.
            self.log_error("unhandled GET error: %s", exc)
            self._send_error_json(
                RequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "internal", "internal server error")
            )

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        try:
            self._guard_request(mutation=True)
            path = urlsplit(self.path).path
            if path not in {"/api/verify", "/api/propose", "/api/stamp"}:
                raise RequestError(HTTPStatus.NOT_FOUND, "not_found", "unknown API route")
            payload = self._read_json()
            if path == "/api/verify":
                self._verify_api(payload)
            elif path == "/api/propose":
                self._propose_api(payload)
            else:
                self._stamp_api(payload)
        except RequestError as exc:
            self._send_error_json(exc)
        except bufftag.BufftagError as exc:
            self._send_error_json(
                RequestError(HTTPStatus.BAD_REQUEST, "bufftag_rejected", str(exc))
            )
        except Exception as exc:
            self.log_error("unhandled POST error: %s", exc)
            self._send_error_json(
                RequestError(HTTPStatus.INTERNAL_SERVER_ERROR, "internal", "internal server error")
            )

    def _verify_api(self, payload: dict[str, Any]) -> None:
        scope = self._scope(payload.get("root"))
        report = bufftag.verify(
            root=scope,
            receipts_path=self._receipts(scope),
            secret=self.config.signing_secret,
            require_complete=bool(payload.get("require_complete", False)),
        )
        self._send_json(
            HTTPStatus.OK,
            {"ok": report.ok, "report": report.as_dict()},
        )

    def _propose_api(self, payload: dict[str, Any]) -> None:
        scope = self._scope(payload.get("root"))
        file_path = payload.get("file")
        if not isinstance(file_path, str) or not file_path:
            raise RequestError(HTTPStatus.BAD_REQUEST, "file", "file is required")
        result = bufftag.propose(scope, file_path)
        self._send_json(HTTPStatus.OK, {"ok": True, "proposal": result})

    def _stamp_api(self, payload: dict[str, Any]) -> None:
        if not self.config.allow_write:
            raise RequestError(
                HTTPStatus.FORBIDDEN,
                "writes_disabled",
                "start the server with --allow-write to enable stamping",
            )
        scope = self._scope(payload.get("root"))
        file_path = payload.get("file")
        if not isinstance(file_path, str) or not file_path:
            raise RequestError(HTTPStatus.BAD_REQUEST, "file", "file is required")
        expected_confirmation = f"STAMP {file_path}"
        if payload.get("confirmation") != expected_confirmation:
            raise RequestError(
                HTTPStatus.BAD_REQUEST,
                "confirmation",
                f"confirmation must equal {expected_confirmation!r}",
            )
        require_signed = bool(payload.get("require_signed", False))
        if require_signed and self.config.signing_secret is None:
            raise RequestError(
                HTTPStatus.CONFLICT,
                "signing_key_missing",
                f"{self.config.signing_env} is not configured on the server",
            )
        metadata_fields = {"origin", "pillar", "role", "author", "deps", "recorded_at"}
        missing = sorted(metadata_fields - set(payload))
        if missing:
            raise RequestError(HTTPStatus.BAD_REQUEST, "metadata", f"missing fields: {missing}")
        unknown = sorted(set(payload) - metadata_fields - {
            "root", "file", "confirmation", "require_signed"
        })
        if unknown:
            raise RequestError(HTTPStatus.BAD_REQUEST, "unknown_fields", f"unknown fields: {unknown}")
        metadata = {key: payload[key] for key in metadata_fields}
        result = bufftag.stamp(
            root=scope,
            file_path=file_path,
            metadata=metadata,
            receipts_path=self._receipts(scope),
            secret=self.config.signing_secret,
        )
        report = bufftag.verify(
            root=scope,
            receipts_path=self._receipts(scope),
            secret=self.config.signing_secret,
        )
        self._send_json(
            HTTPStatus.CREATED,
            {"ok": report.ok, "result": result, "report": report.as_dict()},
        )


def create_server(
    *,
    workspace: str | Path = DEFAULT_WORKSPACE,
    host: str = "127.0.0.1",
    port: int = 8765,
    allow_write: bool = False,
    signing_key_env: str = "BUFFTAG_KEY",
) -> BufftagServer:
    if host != "127.0.0.1":
        raise ValueError("Bufftag local server only binds to 127.0.0.1")
    resolved_workspace = Path(workspace).expanduser().resolve()
    if not resolved_workspace.is_dir():
        raise ValueError(f"workspace is not a directory: {resolved_workspace}")
    secret_value = os.environ.get(signing_key_env)
    secret = secret_value.encode("utf-8") if secret_value else None
    config = ServerConfig(
        workspace=resolved_workspace,
        allow_write=allow_write,
        signing_secret=secret,
        signing_env=signing_key_env,
        api_token=secrets.token_urlsafe(32),
    )
    return BufftagServer((host, port), config)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-write", action="store_true")
    parser.add_argument("--signing-key-env", default="BUFFTAG_KEY")
    parser.add_argument("--open", action="store_true", help="open the local terminal in a browser")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        server = create_server(
            workspace=args.workspace,
            port=args.port,
            allow_write=args.allow_write,
            signing_key_env=args.signing_key_env,
        )
    except (OSError, ValueError) as exc:
        print(f"bufftag server: {exc}", file=sys.stderr)
        return 2
    host, port = server.server_address
    print(f"Bufftag local terminal: http://{host}:{port}/")
    print(f"Workspace: {server.config.workspace}")
    print(f"Writes: {'ENABLED' if server.config.allow_write else 'read-only'}")
    print(f"Receipts: {server.config.signing_env and ('HMAC configured' if server.config.signing_secret else 'unsigned')}")
    print("Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(f"http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nBufftag server stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
