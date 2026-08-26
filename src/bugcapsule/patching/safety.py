"""Strict unified-diff parser and workspace path policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from bugcapsule.capsule.schema import validate_archive_path

DIFF_HEADER = re.compile(r"^diff --git a/([^\s]+) b/([^\s]+)$")
HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@(?: .*)?$")
FORBIDDEN_MARKERS = (
    "GIT binary patch",
    "Binary files ",
    "deleted file mode ",
    "rename from ",
    "rename to ",
    "copy from ",
    "copy to ",
    "old mode ",
    "new mode ",
    "similarity index ",
    "dissimilarity index ",
)
DEFAULT_ALLOWED_ROOTS = ("src",)
DEFAULT_PROTECTED_PATHS = (
    ".env",
    ".env.example",
    ".github",
    ".gitee",
    "Dockerfile",
    "compose.yml",
    "pyproject.toml",
    "requirements.txt",
    "tests",
    "uv.lock",
    "verification_tests",
)
SAFETY_CHECKS = (
    "text_unified_diff",
    "no_delete_or_rename",
    "allowed_paths_only",
    "protected_paths_unchanged",
    "source_evidence_bound",
    "workspace_contained",
)


class PatchSafetyError(ValueError):
    """Raised when a proposed diff violates a deterministic safety invariant."""


@dataclass(frozen=True)
class SafePatch:
    """Canonical diff and the files proven safe to modify."""

    diff: str
    modified_files: tuple[str, ...]
    safety_checks: tuple[str, ...] = SAFETY_CHECKS


class PatchSafetyValidator:
    """Reject ambiguous diff syntax and paths outside cited source evidence."""

    def __init__(
        self,
        *,
        source_root: Path,
        allowed_roots: tuple[str, ...],
        protected_paths: tuple[str, ...],
        max_bytes: int,
    ) -> None:
        self.source_root = source_root.resolve()
        self.allowed_roots = tuple(self._policy_path(value) for value in allowed_roots)
        self.protected_paths = tuple(self._policy_path(value) for value in protected_paths)
        self.max_bytes = max_bytes

    @classmethod
    def defaults(cls) -> PatchSafetyValidator:
        """Create the conservative policy used by directly constructed indexes."""
        return cls(
            source_root=Path(),
            allowed_roots=DEFAULT_ALLOWED_ROOTS,
            protected_paths=DEFAULT_PROTECTED_PATHS,
            max_bytes=256 * 1024,
        )

    def validate(self, unified_diff: str, *, source_evidence_paths: set[str]) -> SafePatch:
        normalized = unified_diff.replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.endswith("\n"):
            normalized += "\n"
        encoded = normalized.encode("utf-8")
        if len(encoded) > self.max_bytes:
            raise PatchSafetyError("Patch exceeds the configured byte limit")
        if "\x00" in normalized:
            raise PatchSafetyError("binary Patch content is not permitted")
        if normalized.startswith("```") or normalized.rstrip().endswith("```"):
            raise PatchSafetyError("Patch must not contain Markdown fences")
        for marker in FORBIDDEN_MARKERS:
            if any(line.startswith(marker) for line in normalized.splitlines()):
                raise PatchSafetyError(
                    "Patch deletion, rename, mode, or binary metadata is forbidden"
                )

        sections = self._sections(normalized.splitlines())
        modified_files = tuple(sorted(self._validate_section(section) for section in sections))
        if len(modified_files) != len(set(modified_files)):
            raise PatchSafetyError("Patch must not modify the same file more than once")
        for path in modified_files:
            self._validate_policy(path, source_evidence_paths)
        return SafePatch(diff=normalized, modified_files=modified_files)

    @staticmethod
    def _sections(lines: list[str]) -> list[list[str]]:
        starts = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
        if not starts or starts[0] != 0:
            raise PatchSafetyError("Patch must contain only git-style unified diff sections")
        starts.append(len(lines))
        sections = [lines[start:end] for start, end in pairwise(starts)]
        if any(not section for section in sections):
            raise PatchSafetyError("Patch contains an empty diff section")
        return sections

    @staticmethod
    def _validate_section(lines: list[str]) -> str:
        header = DIFF_HEADER.fullmatch(lines[0])
        if header is None:
            raise PatchSafetyError("Patch file headers must use unquoted a/path and b/path")
        old_path, new_path = header.groups()
        if old_path != new_path:
            raise PatchSafetyError("Patch file rename is forbidden")
        path = validate_archive_path(new_path)
        try:
            hunk_index = next(index for index, line in enumerate(lines) if line.startswith("@@ "))
        except StopIteration as exc:
            raise PatchSafetyError("Patch file section contains no hunks") from exc
        metadata = lines[1:hunk_index]
        old_headers = [line for line in metadata if line.startswith("--- ")]
        new_headers = [line for line in metadata if line.startswith("+++ ")]
        if len(old_headers) != 1 or len(new_headers) != 1:
            raise PatchSafetyError("Patch file section requires one old and one new file header")
        if old_headers[0] not in {f"--- a/{path}", "--- /dev/null"}:
            raise PatchSafetyError("Patch old file header does not match its diff path")
        if new_headers[0] != f"+++ b/{path}":
            raise PatchSafetyError("Patch new file header does not match its diff path")
        allowed_metadata = {old_headers[0], new_headers[0], "new file mode 100644"}
        if any(not line.startswith("index ") and line not in allowed_metadata for line in metadata):
            raise PatchSafetyError("Patch contains unsupported file metadata")
        hunks = lines[hunk_index:]
        if not HUNK_HEADER.fullmatch(hunks[0]):
            raise PatchSafetyError("Patch contains an invalid hunk header")
        for line in hunks:
            if line.startswith("@@ "):
                if HUNK_HEADER.fullmatch(line) is None:
                    raise PatchSafetyError("Patch contains an invalid hunk header")
            elif not line.startswith((" ", "+", "-", "\\")):
                raise PatchSafetyError("Patch contains invalid hunk content")
        return path

    def _validate_policy(self, path: str, source_evidence_paths: set[str]) -> None:
        if not any(self._within(path, root) for root in self.allowed_roots):
            raise PatchSafetyError(f"Patch path is outside allowed roots: {path}")
        if any(self._within(path, protected) for protected in self.protected_paths):
            raise PatchSafetyError(f"Patch path is protected: {path}")
        if path not in source_evidence_paths:
            raise PatchSafetyError(f"Patch path has no matching source evidence: {path}")
        unresolved_target = self.source_root / Path(*path.split("/"))
        if unresolved_target.is_symlink():
            raise PatchSafetyError(f"Patch target must not be a symbolic link: {path}")
        target = unresolved_target.resolve()
        if not target.is_relative_to(self.source_root):
            raise PatchSafetyError(f"Patch path escapes the source workspace: {path}")

    @staticmethod
    def _within(path: str, policy_path: str) -> bool:
        return path == policy_path or path.startswith(f"{policy_path}/")

    @staticmethod
    def _policy_path(value: str) -> str:
        try:
            return validate_archive_path(value)
        except ValueError as exc:
            raise PatchSafetyError(f"invalid configured Patch path: {value}") from exc
