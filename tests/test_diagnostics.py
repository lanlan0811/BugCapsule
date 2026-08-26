import subprocess
from pathlib import Path

from bugcapsule.config import Settings
from bugcapsule.diagnostics import DoctorService


def test_doctor_reports_ready_without_mutating_workspace(tmp_path: Path) -> None:
    dockerfile = tmp_path / "Dockerfile.verify"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    replay = tmp_path / "replay"
    replay.mkdir()
    settings = Settings(
        source_root=tmp_path,
        data_dir=tmp_path / "data",
        replay_dir=replay,
        model_mode="replay",
        verification_dockerfile=dockerfile,
    )

    def finder(name: str) -> str | None:
        return f"/tools/{name}"

    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(("docker", "version"), 0, "27.0.1\n", "")

    report = DoctorService(settings, command_runner=runner, executable_finder=finder).run()
    assert report.ready is True
    assert all(check.status == "passed" for check in report.checks)
    assert not settings.data_dir.exists()


def test_doctor_explains_missing_prerequisites_and_model_modes(tmp_path: Path) -> None:
    settings = Settings(
        source_root=tmp_path / "missing",
        data_dir=tmp_path / "data",
        verification_dockerfile=tmp_path / "missing.Dockerfile",
        model_mode="off",
    )
    report = DoctorService(settings, executable_finder=lambda _: None).run()
    statuses = {check.check_id: check.status for check in report.checks}
    assert report.ready is False
    assert statuses["source_root"] == "failed"
    assert statuses["git_cli"] == "failed"
    assert statuses["docker_engine"] == "failed"
    assert statuses["model_mode"] == "warning"

    live = settings.model_copy(update={"model_mode": "live"})
    live_report = DoctorService(live, executable_finder=lambda _: None).run()
    assert next(check for check in live_report.checks if check.check_id == "model_mode").status == (
        "failed"
    )
