from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from bugcapsule.index import CapsuleDetail, CapsuleIndex
from bugcapsule.reporting.service import (
    HtmlReportNotFoundError,
    HtmlReportNotReadyError,
    HtmlReportService,
)
from bugcapsule.verification.service import VerificationService
from tests.capsule.factories import make_stage_three_capsule
from tests.patching.test_service import setup_analyzed_capsule
from tests.verification.test_service import FakeExecutor, setup_patch


def verified_detail(tmp_path: Path) -> tuple[HtmlReportService, CapsuleDetail]:
    settings, index, _, patch_id, patch_sha = setup_patch(tmp_path)
    VerificationService(settings, index=index, executor=FakeExecutor()).verify(
        "cap_stage3_0001",
        patch_id=patch_id,
        approved_sha256=patch_sha,
        explicitly_approved=True,
    )
    detail = index.get_detail("cap_stage3_0001")
    assert detail is not None
    return HtmlReportService(settings, index=index), detail


def test_report_is_deterministic_self_contained_and_escapes_untrusted_text(
    tmp_path: Path,
) -> None:
    service, detail = verified_detail(tmp_path)
    assert detail.analysis is not None
    candidate = detail.analysis.root_causes[0].model_copy(
        update={"hypothesis": "<script>alert('unsafe')</script>"}
    )
    analysis = detail.analysis.model_copy(update={"root_causes": (candidate,)})
    unsafe_detail = replace(detail, analysis=analysis)

    class FakeIndex:
        def get_detail(self, capsule_id: str) -> CapsuleDetail | None:
            assert capsule_id == "cap_stage3_0001"
            return unsafe_detail

    service.index = cast(CapsuleIndex, FakeIndex())
    first = service.render("cap_stage3_0001")
    second = service.render("cap_stage3_0001")
    text = first.content.decode("utf-8")

    assert first == second
    assert first.filename == "cap_stage3_0001-verification-report.html"
    assert first.sha256 == second.sha256
    assert "修复前后对比" in text
    assert detail.summary.archive_sha256 in text
    assert detail.verification is not None
    assert detail.verification.run.approved_sha256 in text
    assert detail.patch is not None
    assert detail.patch_diff is not None
    assert detail.patch_diff in text
    assert "[REDACTED:EMAIL]" in text
    assert "user@example.com" not in text
    assert "<script>alert" not in text
    assert "&lt;script&gt;alert" in text
    assert "<link" not in text
    assert 'src="http' not in text


def test_report_requires_each_completed_loop_artifact_and_existing_capsule(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "capture" / "data"
    index = CapsuleIndex(data_dir / "index.sqlite3", data_dir / "capsules")
    make_stage_three_capsule(index.capsules_dir)
    index.rebuild()
    service = HtmlReportService(
        setup_analyzed_capsule(tmp_path / "settings")[0],
        index=index,
    )
    with pytest.raises(HtmlReportNotReadyError, match="模型分析"):
        service.render("cap_stage3_0001")
    with pytest.raises(HtmlReportNotFoundError, match="胶囊不存在"):
        service.render("cap_missing")

    analyzed_settings, analyzed_index, _, _ = setup_analyzed_capsule(tmp_path / "analyzed")
    with pytest.raises(HtmlReportNotReadyError, match="Patch"):
        HtmlReportService(analyzed_settings, index=analyzed_index).render("cap_stage3_0001")

    patch_settings, patch_index, _, _, _ = setup_patch(tmp_path / "patched")
    with pytest.raises(HtmlReportNotReadyError, match="验证结果"):
        HtmlReportService(patch_settings, index=patch_index).render("cap_stage3_0001")
