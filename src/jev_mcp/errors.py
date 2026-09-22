"""Structured errors for Jev MCP tool responses."""

from __future__ import annotations

from typing import Any


class JevMcpError(Exception):
    """Application error safe to return to MCP clients."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        next_steps: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable
        self.next_steps = next_steps or []

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
            "next_steps": self.next_steps,
        }


def error(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
    next_steps: list[str] | None = None,
    **extra: Any,
) -> JevMcpError:
    merged = dict(details or {})
    merged.update(extra)
    return JevMcpError(
        code,
        message,
        details=merged,
        retryable=retryable,
        next_steps=next_steps,
    )
