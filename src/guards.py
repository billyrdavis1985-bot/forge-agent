"""
guards.py — the safety plane (Phase 1, hardened).

A single permission gate the model cannot talk its way past. Runs on every tool
call BEFORE execution. Three layers:

  1. Write containment  — writes only inside configured roots (memory/, scratch/)
  2. Append-only log    — research_log.md cannot be rewritten, only appended
  3. Bash gating        — destructive commands and truncating redirects denied

Budget and turn caps are enforced separately: per-session by the SDK
(max_budget_usd / max_turns), per-day by ledger.budget_check().
"""

from __future__ import annotations

import re
from pathlib import Path

from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_PATH_FIELDS = ("file_path", "path", "notebook_path")

# Files that may only ever be appended to, never rewritten in place.
_APPEND_ONLY = {"research_log.md"}

# Destructive shell patterns, denied outright.
_BASH_DENY = [
    r"\brm\s+-[rf]",
    r"\bdd\s+if=",
    r"\bmkfs\b",
    r"\bshred\b",
    r":\(\)\s*\{.*\};:",                            # fork bomb
    r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f)",   # would destroy memory history
    r"\bchmod\s+-R\s+777",
    r"\bcurl\b[^|]*\|\s*(ba)?sh",                   # curl-pipe-shell
]

# Single '>' redirect (truncating) onto an append-only file. '>>' is fine.
_TRUNCATE_APPEND_ONLY = re.compile(
    r"(?<!>)>(?!>)\s*[^\s|;&]*(" + "|".join(re.escape(f) for f in _APPEND_ONLY) + ")"
)


def _resolve(path_str: str, project_root: Path) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = project_root / p
    return p.resolve()


def _is_within(child: Path, parents: list[Path]) -> bool:
    return any(child == p or p in child.parents for p in parents)


def make_gate(project_root: Path, write_roots: list[str]):
    """Build the can_use_tool callback bound to this project's write policy."""
    allowed = [(project_root / r).resolve() for r in write_roots]

    async def gate(tool_name: str, input_data: dict, context) -> object:
        # --- Bash gating ------------------------------------------------
        if tool_name == "Bash":
            command = input_data.get("command", "") or ""
            for pattern in _BASH_DENY:
                if re.search(pattern, command):
                    return PermissionResultDeny(
                        message=f"Destructive command blocked (matched: {pattern}).",
                        interrupt=False,
                    )
            if _TRUNCATE_APPEND_ONLY.search(command):
                return PermissionResultDeny(
                    message=(
                        "That would truncate an append-only file. "
                        "Use '>>' to append, never '>'."
                    ),
                    interrupt=False,
                )
            return PermissionResultAllow(updated_input=input_data)

        # --- Non-write tools pass through -------------------------------
        if tool_name not in _WRITE_TOOLS:
            return PermissionResultAllow(updated_input=input_data)

        # --- Write containment ------------------------------------------
        target = next((input_data[f] for f in _PATH_FIELDS if input_data.get(f)), None)
        if target is None:
            return PermissionResultDeny(
                message="Write tool called without a resolvable file path.",
                interrupt=False,
            )

        resolved = _resolve(target, project_root)
        if not _is_within(resolved, allowed):
            return PermissionResultDeny(
                message=(
                    f"Write to {resolved} denied. Writes are restricted to: "
                    f"{', '.join(str(a) for a in allowed)}."
                ),
                interrupt=False,
            )

        # --- Append-only enforcement ------------------------------------
        if resolved.name in _APPEND_ONLY:
            return PermissionResultDeny(
                message=(
                    f"{resolved.name} is append-only and cannot be edited in place. "
                    f"Append to it with bash instead, e.g.: "
                    f"printf '%s\\n' \"<your entry>\" >> {resolved}"
                ),
                interrupt=False,
            )

        return PermissionResultAllow(updated_input=input_data)

    return gate
