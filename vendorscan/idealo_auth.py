"""Browser sign-in for the idealo MCP server (OAuth 2.1 with dynamic client registration).

The first connection opens the idealo sign-in page in the browser and waits for
the redirect on http://localhost:6274/callback. Tokens and the registered client
are cached in ``.idealo_oauth.json`` (git-ignored) so later runs reuse them.

Run ``python -m vendorscan.idealo_auth`` once to sign in before starting the app.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from mcp.client.auth import OAuthClientProvider, TokenStorage
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from .settings import TOKEN_TIMEOUT

log = logging.getLogger(__name__)

SERVER_URL = "https://mcp.idealo.com/mcp"
CALLBACK_PORT = 6274
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
SCOPE = "https://mcp.idealo.com/mcp/api.full-access"
CACHE_FILE = Path(__file__).resolve().parent.parent / ".idealo_oauth.json"


class FileTokenStorage(TokenStorage):
    """Keeps OAuth tokens and client registration in one owner-only JSON file."""

    def __init__(self, path: Path = CACHE_FILE):
        self.path = path

    def _read(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _write(self, key: str, value: dict) -> None:
        data = self._read()
        data[key] = value
        self.path.write_text(json.dumps(data, indent=2))
        os.chmod(self.path, 0o600)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._write("tokens", tokens.model_dump(mode="json", exclude_none=True))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._write("client", client_info.model_dump(mode="json", exclude_none=True))


def _wait_for_callback(timeout: float) -> tuple[str, str | None]:
    """Serve one request on the callback port and return (code, state)."""
    result: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server API)
            query = parse_qs(urlparse(self.path).query)
            result["code"] = query.get("code", [None])[0]
            result["state"] = query.get("state", [None])[0]
            result["error"] = query.get("error", [None])[0]
            ok = result["code"] is not None
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            message = "Signed in to idealo. You can close this tab." if ok else "idealo sign-in failed."
            self.wfile.write(message.encode())

        def log_message(self, *args):  # keep the console quiet
            pass

    server = HTTPServer(("localhost", CALLBACK_PORT), Handler)
    server.timeout = timeout
    try:
        server.handle_request()
    finally:
        server.server_close()
    if not result.get("code"):
        raise RuntimeError(f"idealo sign-in did not complete: {result.get('error') or 'no code received'}")
    return result["code"], result["state"]


async def _open_browser(url: str) -> None:
    # Deliberately print(), not logging: during the one-time sign-in the user must see this
    # URL in the terminal if no browser opens, and logging hides INFO by default.
    print(f"Opening idealo sign-in in your browser. If it doesn't open, visit:\n{url}")
    webbrowser.open(url)


TOKEN_ENDPOINT = "https://mcp.idealo.com/oauth2/token"
REFRESH_MARGIN_SECONDS = 300


def _expires_at(access_token: str) -> float | None:
    """Expiry time from the access token (a JWT); None if it can't be read."""
    try:
        payload = access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return float(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def refresh_if_expiring(path: Path = CACHE_FILE) -> bool:
    """Refresh the cached token if it expires within 5 minutes. Returns True if refreshed.

    idealo's gateway answers an expired token with 403 (not 401), and the MCP SDK only
    refreshes on 401, so without this every session silently breaks after an hour.
    """
    try:
        data = json.loads(path.read_text())
        tokens, client = data["tokens"], data["client"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return False
    expires = _expires_at(tokens.get("access_token", ""))
    if expires and expires - time.time() > REFRESH_MARGIN_SECONDS:
        return False
    if not tokens.get("refresh_token"):
        return False
    response = httpx.post(TOKEN_ENDPOINT, timeout=TOKEN_TIMEOUT, data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
        "client_id": client["client_id"]})
    if response.status_code != 200:
        return False  # fall back to the browser sign-in
    fresh = response.json()
    fresh.setdefault("refresh_token", tokens["refresh_token"])
    data["tokens"] = fresh
    path.write_text(json.dumps(data, indent=2))
    os.chmod(path, 0o600)
    return True


def oauth_provider(timeout: float = 300.0) -> OAuthClientProvider:
    """httpx auth that signs in through the browser once, then refreshes from the cache."""

    async def callback() -> tuple[str, str | None]:
        return await asyncio.to_thread(_wait_for_callback, timeout)

    metadata = OAuthClientMetadata(
        client_name="VendorScan (hackathon prototype)",
        redirect_uris=[REDIRECT_URI],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
        scope=SCOPE,
    )
    return OAuthClientProvider(server_url=SERVER_URL, client_metadata=metadata,
                               storage=FileTokenStorage(), redirect_handler=_open_browser,
                               callback_handler=callback, timeout=timeout)


async def _sign_in() -> None:
    from idealo_client import connect

    async with connect() as client:
        tools = await client.session.list_tools()
        log.info("Signed in. idealo tools: %s", ", ".join(t.name for t in tools.tools))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(_sign_in())
