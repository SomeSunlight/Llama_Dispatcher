"""S01 backend boundary: capability declaration, compilation and HTTP endpoint ownership.

The llama.cpp compiler and legacy launcher still live in dispatcher_core during
the compatibility transition. This module deliberately has no process operations,
network probes, engine registry or Strata implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import urlsplit


class UnsupportedBackendCapability(ValueError):
    """An operation is not implemented by the selected engine backend."""


@dataclass(frozen=True)
class BackendCapabilities:
    """True = implemented, False = unsupported, None = not characterized yet."""

    native_compile: bool
    http_proxy: bool
    legacy_managed_start: bool
    http_attach: bool
    streaming: bool | None = None
    tools: bool | None = None
    vision: bool | None = None

    def require(self, feature: str) -> None:
        if not hasattr(self, feature):
            raise UnsupportedBackendCapability(f"Unknown backend capability: {feature}")
        if getattr(self, feature) is not True:
            raise UnsupportedBackendCapability(
                f"Backend capability {feature!r} is unavailable or unverified"
            )


@dataclass(frozen=True)
class BackendEndpoint:
    """HTTP routing descriptor, *not* a process handle or supervision receipt.

    'attached' never grants stop/restart/kill rights. 'legacy_managed' describes
    the current llama.cpp compatibility path; its existing lifecycle remains
    solely in dispatcher_core until a separately approved migration.
    """

    base_url: str
    ownership: Literal["attached", "legacy_managed"]

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError("Engine endpoint requires a credential-free HTTP(S) base URL")
        if self.ownership not in ("attached", "legacy_managed"):
            raise ValueError("Unknown endpoint ownership")

    @classmethod
    def attach(cls, base_url: str) -> BackendEndpoint:
        """Describe an externally owned endpoint; does not probe or start it."""
        return cls(base_url.rstrip("/"), "attached")

    @classmethod
    def legacy_managed(cls, port: int) -> BackendEndpoint:
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("Invalid llama.cpp managed endpoint port")
        return cls(f"http://127.0.0.1:{port}", "legacy_managed")

    @property
    def may_control_process(self) -> bool:
        """Only the retained *legacy* mode can use the old lifecycle operations."""
        return self.ownership == "legacy_managed"

    def v1_url(self, path: str) -> str:
        """Build an OpenAI-compatible forwarding URL without changing the path."""
        return f"{self.base_url.rstrip('/')}/v1/{path}"


class InferenceBackend(Protocol):
    """Small explicit seam, not a dynamically loaded engine plugin framework."""

    name: str
    capabilities: BackendCapabilities

    def compile_ensemble(self, compiler: Any, name: str, overrides: dict) -> tuple[str, dict, list]: ...
    def compile_profile(self, compiler: Any, name: str, overrides: dict) -> tuple[str, dict, list]: ...
    def compile_task(self, compiler: Any, name: str, mode: str, overrides: dict) -> tuple[str, dict, list]: ...


class LlamaCppBackend:
    """Compatibility facade over the existing proven llama.cpp compiler.

    Calling compiler methods dynamically is intentional: the Windows/WSL
    runtime-path adapter in dispatcher.py wraps these methods at launch time.
    """

    name = "llama.cpp"
    capabilities = BackendCapabilities(
        native_compile=True, http_proxy=True,
        legacy_managed_start=True, http_attach=False,
        streaming=True, tools=None, vision=None,
    )

    def compile_ensemble(self, compiler: Any, name: str, overrides: dict) -> tuple[str, dict, list]:
        return compiler.compile_serve_ensemble(name, overrides)

    def compile_profile(self, compiler: Any, name: str, overrides: dict) -> tuple[str, dict, list]:
        return compiler.compile_serve_profile(name, overrides)

    def compile_task(self, compiler: Any, name: str, mode: str, overrides: dict) -> tuple[str, dict, list]:
        return compiler.compile_task_profile(name, mode, overrides)

    def legacy_endpoint(self, port: int) -> BackendEndpoint:
        return BackendEndpoint.legacy_managed(port)

    def attach(self, base_url: str) -> BackendEndpoint:
        # Generic attachment descriptor exists, but *this adapter* does not
        # yet support connecting llama.cpp without the legacy launcher.
        raise UnsupportedBackendCapability(
            "llama.cpp attach mode is not implemented in S01"
        )
