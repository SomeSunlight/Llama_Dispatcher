"""S02: Optional, independent bearer identities and explicit request policy.

No raw token is loaded from configuration, logged or persisted. Authenticated
mode is opt-in with a private JSON digest file; legacy mode remains unchanged.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

PolicyMode = Literal["default", "enforce", "passthrough"]
MODES = frozenset(("default", "enforce", "passthrough"))
_CLIENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
_DIGEST_RE = re.compile(r"[a-f0-9]{64}\Z")


class ClientConfigurationError(ValueError):
    """Invalid auth configuration: refuse startup rather than fail open."""


@dataclass(frozen=True)
class ClientIdentity:
    client_id: str
    token_sha256: str
    policy: PolicyMode


@dataclass(frozen=True)
class ClientSecurity:
    clients: tuple[ClientIdentity, ...] = ()

    @property
    def enabled(self) -> bool:
        return bool(self.clients)

    def authenticate(self, authorization: str | None) -> ClientIdentity | None:
        if not authorization:
            return None
        scheme, sep, secret = authorization.partition(" ")
        if not sep or scheme.lower() != "bearer" or not secret or secret.strip() != secret:
            return None
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        result = None
        # Compare against ALL stored digests without early exit.
        for identity in self.clients:
            if hmac.compare_digest(identity.token_sha256, digest):
                result = identity
        return result


def load_client_security(path: str | None = None) -> ClientSecurity:
    """Read a private operator-managed file; no file means legacy mode.

    A supplied invalid/unreadable file is a fatal configuration error.
    """
    if path is None:
        path = os.environ.get("DISPATCHER_CLIENT_CONFIG")
    if not path:
        return ClientSecurity()
    try:
        doc = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ClientConfigurationError(
            "Client authentication configuration cannot be read or parsed."
        ) from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ClientConfigurationError("Expected client configuration schema_version 1.")
    entries = doc.get("clients")
    if not isinstance(entries, list) or not entries:
        raise ClientConfigurationError("Authenticated mode requires at least one client.")
    clients = []
    seen_ids, seen_digests = set(), set()
    for item in entries:
        if not isinstance(item, dict):
            raise ClientConfigurationError("Client entry must be an object.")
        client_id = item.get("id")
        digest = item.get("token_sha256")
        mode = item.get("policy", "enforce")
        if not isinstance(client_id, str) or not _CLIENT_ID_RE.fullmatch(client_id):
            raise ClientConfigurationError("Invalid client id.")
        if not isinstance(digest, str) or not _DIGEST_RE.fullmatch(digest):
            raise ClientConfigurationError("Expected lowercase SHA-256 token digest.")
        if mode not in MODES:
            raise ClientConfigurationError("Invalid client policy mode.")
        if client_id in seen_ids or digest in seen_digests:
            raise ClientConfigurationError("Duplicate client id or credential digest.")
        seen_ids.add(client_id)
        seen_digests.add(digest)
        clients.append(ClientIdentity(client_id, digest, mode))
    return ClientSecurity(tuple(clients))


def apply_request_policy(
    client_request: dict[str, Any],
    profile_params: dict[str, Any],
    mode: PolicyMode,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve profile defaults without modifying the original request.

    enforce = profile wins (legacy); default = client wins; passthrough = no
    profile injection. Model alias remapping is separate and always occurs.
    """
    if mode not in MODES:
        raise ValueError("Invalid request policy mode.")
    result = client_request.copy()
    injected = {}
    if mode != "passthrough":
        for key, value in profile_params.items():
            if mode == "enforce" or key not in result:
                if result.get(key) != value:
                    injected[key] = value
                result[key] = value
    return result, injected
