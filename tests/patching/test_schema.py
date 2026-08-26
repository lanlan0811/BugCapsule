import pytest
from pydantic import ValidationError

from bugcapsule.capsule.identifiers import sha256_hex
from bugcapsule.capsule.schema import PatchCandidate
from bugcapsule.patching.schema import ModelPatchResponse


def test_model_patch_rejects_model_ids_duplicate_refs_and_extra_fields() -> None:
    evidence_id = "EV-AAAAAAAAAAAA"
    with pytest.raises(ValidationError, match="duplicates"):
        ModelPatchResponse(
            summary="修复连接归还",
            unified_diff="diff",
            evidence_refs=(evidence_id, evidence_id),
            safety_notes=(),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        ModelPatchResponse.model_validate(
            {
                "summary": "修复连接归还",
                "unified_diff": "diff",
                "evidence_refs": [evidence_id],
                "safety_notes": [],
                "patch_id": "PATCH-AAAAAAAAAAAA",
            }
        )


def test_patch_candidate_id_and_file_inventory_are_content_derived() -> None:
    diff_sha = sha256_hex(b"diff\n")
    candidate = PatchCandidate.create(
        root_cause_id="RC-AAAAAAAAAAAA",
        summary="修复连接归还",
        diff_path="patches/candidate.diff",
        sha256=diff_sha,
        modified_files=("src/app.py",),
        evidence_refs=("EV-AAAAAAAAAAAA",),
        safety_checks=("text_unified_diff",),
    )
    assert candidate.patch_id.startswith("PATCH-")
    tampered = candidate.model_dump(mode="json")
    tampered["patch_id"] = "PATCH-AAAAAAAAAAAA"
    with pytest.raises(ValidationError, match="canonical Patch"):
        PatchCandidate.model_validate(tampered)
    with pytest.raises(ValidationError, match="sorted"):
        PatchCandidate.create(
            root_cause_id="RC-AAAAAAAAAAAA",
            summary="修复连接归还",
            diff_path="patches/candidate.diff",
            sha256=diff_sha,
            modified_files=("src/z.py", "src/a.py"),
            evidence_refs=("EV-AAAAAAAAAAAA",),
            safety_checks=("text_unified_diff",),
        )
