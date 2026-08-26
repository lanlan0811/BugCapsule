from pathlib import Path

import pytest

from bugcapsule.patching.safety import PatchSafetyError, PatchSafetyValidator

SOURCE_PATH = "src/bugcapsule/demo/database.py"


def diff_for(path: str = SOURCE_PATH, *, line_ending: str = "\n") -> str:
    lines = [
        f"diff --git a/{path} b/{path}",
        "index 1111111..2222222 100644",
        f"--- a/{path}",
        f"+++ b/{path}",
        "@@ -43,2 +43,3 @@",
        " session = session_factory()",
        "+try:",
        " session.execute(statement)",
    ]
    return line_ending.join(lines)


def validator(tmp_path: Path, *, max_bytes: int = 4096) -> PatchSafetyValidator:
    target = tmp_path / Path(*SOURCE_PATH.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("session = session_factory()\nsession.execute(statement)\n", encoding="utf-8")
    return PatchSafetyValidator(
        source_root=tmp_path,
        allowed_roots=("src",),
        protected_paths=("tests", "pyproject.toml", "uv.lock"),
        max_bytes=max_bytes,
    )


def test_validator_canonicalizes_text_diff_and_reports_deterministic_checks(
    tmp_path: Path,
) -> None:
    result = validator(tmp_path).validate(
        diff_for(line_ending="\r\n"),
        source_evidence_paths={SOURCE_PATH},
    )
    assert result.diff.endswith("\n")
    assert "\r" not in result.diff
    assert result.modified_files == (SOURCE_PATH,)
    assert result.safety_checks == (
        "text_unified_diff",
        "no_delete_or_rename",
        "allowed_paths_only",
        "protected_paths_unchanged",
        "source_evidence_bound",
        "workspace_contained",
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("```diff\n" + diff_for() + "\n```", "Markdown fences"),
        (diff_for() + "\x00", "binary Patch"),
        (diff_for().replace("index 1111111..2222222 100644", "GIT binary patch"), "binary"),
        (diff_for().replace(f"+++ b/{SOURCE_PATH}", "+++ /dev/null"), "new file header"),
        (
            diff_for().replace(
                f"diff --git a/{SOURCE_PATH} b/{SOURCE_PATH}",
                f"diff --git a/{SOURCE_PATH} b/src/bugcapsule/demo/renamed.py",
            ),
            "rename",
        ),
        (diff_for().replace("@@ -43,2 +43,3 @@", "@@ bad @@"), "invalid hunk"),
        ("untrusted preamble\n" + diff_for(), "only git-style"),
        (
            diff_for().replace(
                f"diff --git a/{SOURCE_PATH} b/{SOURCE_PATH}",
                f'diff --git "a/{SOURCE_PATH}" "b/{SOURCE_PATH}"',
            ),
            "unquoted",
        ),
        (diff_for().replace("@@ -43,2 +43,3 @@", ""), "no hunks"),
        (diff_for().replace(f"--- a/{SOURCE_PATH}\n", ""), "one old and one new"),
        (
            diff_for().replace(f"--- a/{SOURCE_PATH}", "--- a/src/bugcapsule/demo/other.py"),
            "old file header",
        ),
        (
            diff_for().replace("index 1111111..2222222 100644", "unsupported metadata"),
            "unsupported file metadata",
        ),
        (diff_for() + "\ninvalid hunk content", "invalid hunk content"),
        (diff_for() + "\n@@ bad @@", "invalid hunk header"),
    ],
)
def test_validator_rejects_ambiguous_or_destructive_diff(
    tmp_path: Path,
    value: str,
    message: str,
) -> None:
    with pytest.raises(PatchSafetyError, match=message):
        validator(tmp_path).validate(value, source_evidence_paths={SOURCE_PATH})


def test_validator_rejects_uncited_protected_traversal_and_oversized_paths(
    tmp_path: Path,
) -> None:
    safe_validator = validator(tmp_path)
    with pytest.raises(PatchSafetyError, match="no matching source evidence"):
        safe_validator.validate(diff_for(), source_evidence_paths=set())
    with pytest.raises((PatchSafetyError, ValueError), match=r"traverse|normalized"):
        safe_validator.validate(
            diff_for("src/../pyproject.toml"),
            source_evidence_paths={"src/../pyproject.toml"},
        )
    with pytest.raises(PatchSafetyError, match="byte limit"):
        validator(tmp_path, max_bytes=32).validate(diff_for(), source_evidence_paths={SOURCE_PATH})
    with pytest.raises(PatchSafetyError, match="outside allowed roots"):
        safe_validator.validate(
            diff_for("other/module.py"),
            source_evidence_paths={"other/module.py"},
        )
    with pytest.raises(PatchSafetyError, match="same file more than once"):
        safe_validator.validate(
            diff_for() + "\n" + diff_for(),
            source_evidence_paths={SOURCE_PATH},
        )

    protected = PatchSafetyValidator(
        source_root=tmp_path,
        allowed_roots=("tests",),
        protected_paths=("tests",),
        max_bytes=4096,
    )
    with pytest.raises(PatchSafetyError, match="protected"):
        protected.validate(
            diff_for("tests/test_hidden.py"),
            source_evidence_paths={"tests/test_hidden.py"},
        )
    with pytest.raises(PatchSafetyError, match="invalid configured Patch path"):
        PatchSafetyValidator(
            source_root=tmp_path,
            allowed_roots=("../outside",),
            protected_paths=("tests",),
            max_bytes=4096,
        )
