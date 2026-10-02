# SPDX-FileCopyrightText: 2026 Mykel Alvis <mykelalvis@infrastructurebuilder.org>
#
# SPDX-License-Identifier: Apache-2.0

"""What the Okta API services app can show about itself, with its own
credentials (stage 70 step 6, decision D5: the app is checked, never made).

The ``okta`` provider authenticates as that app by OAuth 2.0 client
credentials with a private-key JWT, reading ``OKTA_API_CLIENT_ID``,
``OKTA_API_PRIVATE_KEY`` (the PEM, or a path to it), ``OKTA_API_PRIVATE_KEY_ID``
and ``OKTA_API_SCOPES`` from the environment. The check does what the
provider does: it signs a client assertion with that key and asks the org's
token endpoint for exactly those scopes. A token back proves the app exists,
authenticates with that key and holds those scopes; the scopes it holds are
read off the answer. Whether the app ALSO holds a ``*.manage`` scope it was
not asked for is visible only to a caller with ``okta.apps.read``, so the
check tries ``GET /api/v1/apps/{client_id}`` with the token and reports
"unreadable" when it is refused -- a check for the org's Okta admins, never
a guess. Nothing here writes anything, and no secret is returned or logged.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

#: ``(method, url, headers, body) -> (status, parsed JSON or None)``
Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]


def _urllib_http(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:            # noqa: S310 - an https URL we built
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        return status, json.loads(raw.decode() or "null")
    except ValueError:
        return status, None


@dataclass
class AppCheck:
    """What could be established. ``authenticates`` is None when there were
    no credentials to try; ``readable`` False when the app's own record is
    not visible to it (no ``okta.apps.read``)."""
    client_id: str
    authenticates: bool | None = None
    error: str = ""
    requested: list[str] = field(default_factory=list)
    granted: list[str] = field(default_factory=list)
    readable: bool | None = None
    auth_method: str | None = None            # the app's token_endpoint_auth_method, when readable

    @property
    def read_only(self) -> bool | None:
        """No ``*.manage`` among the scopes it was granted (of those asked)."""
        if self.authenticates is not True:
            return None
        return not any(s.endswith(".manage") for s in self.granted)


def scopes_from(text: str | None) -> list[str]:
    return [s for s in str(text or "").replace(",", " ").split() if s]


def private_key_pem(value: str | None) -> bytes | None:
    """The key as the provider accepts it: the PEM itself, or a path to it."""
    if not value:
        return None
    if "-----BEGIN" in value:
        return value.encode()
    path = Path(value).expanduser()
    return path.read_bytes() if path.is_file() else None


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def client_assertion(client_id: str, key_pem: bytes, key_id: str | None, audience: str) -> str:
    """An RS256 private-key JWT, as RFC 7523 and Okta's token endpoint ask."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise ValueError("the Okta API key is not an RSA key")
    header = {"alg": "RS256", "typ": "JWT", **({"kid": key_id} if key_id else {})}
    now = int(time.time())
    claims = {"iss": client_id, "sub": client_id, "aud": audience, "iat": now, "exp": now + 300, "jti": str(uuid.uuid4())}
    signing_input = f"{_b64(json.dumps(header, separators=(',', ':')).encode())}." \
                    f"{_b64(json.dumps(claims, separators=(',', ':')).encode())}"
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64(signature)}"


def org_url(org: str, base_url: str = "okta.com") -> str:
    return f"https://{org}.{base_url.strip().strip('.') or 'okta.com'}"


def check_app(org: str, base_url: str = "okta.com", env: Mapping[str, str] | None = None,
              http: Http | None = None) -> AppCheck:
    """Ask the token endpoint as the app, then try to read the app."""
    env = os.environ if env is None else env
    http = http or _urllib_http
    client_id = str(env.get("OKTA_API_CLIENT_ID") or "")
    result = AppCheck(client_id=client_id, requested=scopes_from(env.get("OKTA_API_SCOPES")))
    key = private_key_pem(env.get("OKTA_API_PRIVATE_KEY"))
    if not client_id or key is None or not result.requested:
        result.error = "no credentials to try (OKTA_API_CLIENT_ID, OKTA_API_PRIVATE_KEY and OKTA_API_SCOPES)"
        return result
    base = org_url(org, base_url)
    token_url = f"{base}/oauth2/v1/token"
    try:
        assertion = client_assertion(client_id, key, env.get("OKTA_API_PRIVATE_KEY_ID"), token_url)
    except Exception as e:  # noqa: BLE001 - an unreadable key is a finding, not a crash
        result.authenticates, result.error = False, f"the private key could not be used: {e.__class__.__name__}"
        return result
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials", "scope": " ".join(result.requested),
        "client_assertion_type": "urn:ietf:params:oauth:client-assertion-type:jwt-bearer",
        "client_assertion": assertion}).encode()
    status, body = http("POST", token_url, {"Accept": "application/json",
                                            "Content-Type": "application/x-www-form-urlencoded"}, form)
    if status != 200 or not isinstance(body, dict) or not body.get("access_token"):
        result.authenticates = False
        detail = body.get("error_description") or body.get("error") if isinstance(body, dict) else None
        result.error = f"the token endpoint answered {status}" + (f": {detail}" if detail else "")
        return result
    result.authenticates = True
    result.granted = scopes_from(body.get("scope"))
    token = str(body["access_token"])
    status, app = http("GET", f"{base}/api/v1/apps/{urllib.parse.quote(client_id)}",
                       {"Accept": "application/json", "Authorization": f"Bearer {token}"}, None)
    if status == 200 and isinstance(app, dict):
        result.readable = True
        result.auth_method = (((app.get("credentials") or {}).get("oauthClient") or {})
                              .get("token_endpoint_auth_method"))
    else:
        result.readable = False
    return result
