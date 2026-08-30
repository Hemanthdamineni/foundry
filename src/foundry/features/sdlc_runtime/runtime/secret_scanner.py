"""Built-in secret scanner for detecting hardcoded credentials.

Optional, configurable gate — controlled by environment variables:
  SDLC_SECRET_SCANNER_ENABLED  Set to "1" or "true" to enable scanning.
  SDLC_SECRET_SCANNER_PATTERNS JSON list of extra pattern dicts:
    [{"pattern": "...", "name": "...", "severity": "..."}, ...]
  SDLC_SECRET_SCANNER_IGNORE  JSON list of extra regex ignore-path patterns.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Default secret patterns — regex, human name, severity
# ---------------------------------------------------------------------------
DEFAULT_PATTERNS: list[dict[str, str]] = [
    # AWS
    {
        "pattern": r"AKIA[0-9A-Z]{16}",
        "name": "AWS Access Key ID",
        "severity": "high",
    },
    {
        "pattern": r"(?i)aws(.{0,20})?(?-i)['\"][0-9a-zA-Z\/+]{40}['\"]",
        "name": "AWS Secret Access Key",
        "severity": "critical",
    },
    # GitHub
    {
        "pattern": r"gh[pousr]_[A-Za-z0-9_]{36,}",
        "name": "GitHub Token",
        "severity": "high",
    },
    {
        "pattern": r"github_pat_[A-Za-z0-9_]{22,}",
        "name": "GitHub Personal Access Token",
        "severity": "high",
    },
    # GitLab
    {
        "pattern": r"glpat-[A-Za-z0-9\-_]{20,}",
        "name": "GitLab Personal Access Token",
        "severity": "high",
    },
    # Generic API keys and secrets
    {
        "pattern": r"(?i)(api[_-]?key|apikey|api_secret)\s*[:=]\s*['\"][0-9a-zA-Z_\-]{16,}['\"]",
        "name": "Generic API Key",
        "severity": "medium",
    },
    {
        "pattern": r"(?i)(secret|token|password|passwd)\s*[:=]\s*['\"][0-9a-zA-Z_\-!@#$%^&*()+]{20,}['\"]",
        "name": "Generic Secret / Token / Password",
        "severity": "medium",
    },
    # Private keys
    {
        "pattern": r"-----BEGIN (RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----",
        "name": "Private Key",
        "severity": "critical",
    },
    # JWT
    {
        "pattern": r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+",
        "name": "JWT Token",
        "severity": "high",
    },
    # Database connection strings with embedded credentials
    {
        "pattern": r"(?i)(mongodb|postgresql|mysql|redis|amqp|rabbitmq)://[^@]+@",
        "name": "Database Connection String (with credentials)",
        "severity": "high",
    },
    # Slack tokens
    {
        "pattern": r"xox[baprs]-[0-9A-Za-z\-]{10,}",
        "name": "Slack Token",
        "severity": "high",
    },
    # Discord tokens
    {
        "pattern": r"[MN][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}",
        "name": "Discord Token",
        "severity": "high",
    },
    # Heroku API keys
    {
        "pattern": r"heroku[a-z_]*\s*[:=]\s*['\"][A-Za-z0-9\-_]{20,}['\"]",
        "name": "Heroku API Key",
        "severity": "high",
    },
    # Telegram bot tokens
    {
        "pattern": r"(?i)telegram_bot_token\s*[:=]\s*['\"][0-9]{8,10}:[A-Za-z0-9_-]{35,40}['\"]",
        "name": "Telegram Bot Token",
        "severity": "high",
    },
]

# ---------------------------------------------------------------------------
# Ignored file path patterns (binary, vendor directories, etc.)
# ---------------------------------------------------------------------------
IGNORED_PATTERNS: list[str] = [
    r"\.(png|jpg|jpeg|gif|bmp|ico|svg|woff2?|eot|ttf|otf|mp3|mp4|avi|mov|mkv"
    r"|zip|tar|gz|bz2|rar|7z|exe|dll|so|dylib|bin|dat|pyc|pyd|pyo|lock)$",
    r"(node_modules|\.git|__pycache__|\.venv|\.pixi|"
    r"\.mypy_cache|\.ruff_cache|\.pytest_cache|\.eggs)/",
]

# Max file size to scan (bytes)
_MAX_FILE_SIZE = 1024 * 1024  # 1 MiB

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_extra_patterns() -> list[dict[str, str]]:
    """Load extra scanner patterns from *SDLC_SECRET_SCANNER_PATTERNS* env var."""
    raw = os.environ.get("SDLC_SECRET_SCANNER_PATTERNS", "")
    if not raw:
        return []
    try:
        extra = json.loads(raw)
        if isinstance(extra, list):
            return extra
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _load_ignored_extra() -> list[str]:
    """Load extra ignored path patterns from *SDLC_SECRET_SCANNER_IGNORE* env var."""
    raw = os.environ.get("SDLC_SECRET_SCANNER_IGNORE", "")
    if not raw:
        return []
    try:
        extra = json.loads(raw)
        if isinstance(extra, list):
            return extra
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _should_ignore(file_path: str) -> bool:
    """Return *True* if *file_path* matches any ignore pattern."""
    for pat in IGNORED_PATTERNS + _load_ignored_extra():
        if re.search(pat, file_path):
            return True
    return False


def _compiled_patterns() -> list[tuple[re.Pattern, str, str]]:
    """Compile default + extra patterns into ``(compiled_regex, name, severity)`` tuples."""
    entries: list[dict[str, str]] = list(DEFAULT_PATTERNS)
    entries.extend(_load_extra_patterns())
    compiled: list[tuple[re.Pattern, str, str]] = []
    for entry in entries:
        try:
            pat = re.compile(entry["pattern"])
            compiled.append((pat, entry.get("name", "Unknown"), entry.get("severity", "medium")))
        except re.error:
            continue
    return compiled


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_enabled() -> bool:
    """Return *True* when the secret scanner has been opted in via env var."""
    val = os.environ.get("SDLC_SECRET_SCANNER_ENABLED", "").lower().strip()
    return val in ("1", "true", "yes", "enabled")


def scan_text(text: str) -> list[dict[str, Any]]:
    """Scan *text* for secrets.

    Returns a list of finding dicts::

        {"line": int, "type": str, "match": str, "severity": str}
    """
    findings: list[dict[str, Any]] = []
    patterns = _compiled_patterns()

    for line_num, line in enumerate(text.splitlines(), 1):
        for pat, name, severity in patterns:
            m = pat.search(line)
            if m:
                matched = m.group()
                # Truncate leaked value — show first 6 + last 4 chars
                display = f"{matched[:6]}...{matched[-4:]}" if len(matched) > 12 else matched
                findings.append({
                    "line": line_num,
                    "type": name,
                    "match": display,
                    "severity": severity,
                })
    return findings


def scan_file(file_path: str) -> list[dict[str, Any]]:
    """Scan a single file for secrets.

    Each finding includes an extra ``"file"`` key with the absolute path.
    Returns an empty list when the file is ignored, too large, or binary.
    """
    path = Path(file_path)
    if not path.is_file():
        return []
    if _should_ignore(str(path)):
        return []
    try:
        if path.stat().st_size > _MAX_FILE_SIZE:
            return []
    except OSError:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return []

    findings = scan_text(text)
    for f in findings:
        f["file"] = str(path)
    return findings


def scan_files(file_paths: list[str]) -> list[dict[str, Any]]:
    """Scan a list of files for secrets.

    Returns findings sorted by file path then line number.
    """
    all_findings: list[dict[str, Any]] = []
    for fp in file_paths:
        all_findings.extend(scan_file(fp))
    return sorted(all_findings, key=lambda f: (f.get("file", ""), f.get("line", 0)))


def scan_directory(
    directory: str,
    *,
    pattern: str = "**/*",
    max_files: int = 5000,
) -> list[dict[str, Any]]:
    """Scan a directory tree for secrets.

    Args:
        directory: Root path to scan recursively.
        pattern: Glob pattern for file matching (default ``**/*``).
        max_files: Upper bound on files to scan (default 5000).

    Returns findings sorted by file path then line number.
    """
    root = Path(directory)
    if not root.is_dir():
        return []

    file_paths: list[str] = []
    for fpath in root.rglob(pattern):
        if not fpath.is_file():
            continue
        if _should_ignore(str(fpath)):
            continue
        file_paths.append(str(fpath))
        if len(file_paths) >= max_files:
            break

    return scan_files(sorted(file_paths))
