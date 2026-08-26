"""Static safety contracts for the Docker integration workflow."""

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
RELEASE_WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "release.yml"
DOCKERFILE = Path(__file__).parents[1] / "Dockerfile"
COMPOSE = Path(__file__).parents[1] / "compose.yml"


def test_patched_regression_directory_is_readable_to_the_non_root_container() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    archive = 'git archive HEAD | tar -x -C "$after_dir"'
    patch = 'git -C "$after_dir" apply verification_tests/fixtures/connection-release.diff'
    permission = 'chmod 0755 "$after_dir"'
    before_run = 'run_regression "$GITHUB_WORKSPACE" fail'
    after_run = 'run_regression "$after_dir" pass'

    assert workflow.index(archive) < workflow.index(patch) < workflow.index(permission)
    assert workflow.index(permission) < workflow.index(before_run) < workflow.index(after_run)
    assert "--user 10001:10001" in workflow
    assert '--mount "type=bind,source=${source_dir},target=/workspace,readonly"' in workflow
    assert "-p no:cacheprovider -o addopts=" in workflow


def test_release_workflow_requires_complete_submission_manifest() -> None:
    workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")

    assert "submission-readiness:" in workflow
    assert "python scripts/validate_submission_manifest.py --require-ready" in workflow
    assert "needs: [quality-gates, submission-readiness]" in workflow


def test_order_image_is_read_only_ready_and_owns_configured_telemetry_mount() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    compose = COMPOSE.read_text(encoding="utf-8")

    argument = "BUGCAPSULE_DEMO_CONTAINER_TELEMETRY_DIR"
    assert f"ARG {argument}=/var/lib/bugcapsule" in dockerfile
    assert f'mkdir --parents "${argument}"' in dockerfile
    assert f'chown -R bugcapsule:bugcapsule /app "${argument}"' in dockerfile
    assert 'CMD ["/app/.venv/bin/python", "-m", "bugcapsule.demo"]' in dockerfile
    assert f"{argument}: ${{{argument}:-/var/lib/bugcapsule}}" in compose
    assert "docker compose logs --no-color order-service" in WORKFLOW.read_text(encoding="utf-8")


def test_demo_failure_cleanup_preserves_exit_code_and_prints_container_evidence() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    cleanup_start = workflow.index("cleanup_demo()")
    cleanup_end = workflow.index("trap cleanup_demo EXIT")
    cleanup = workflow[cleanup_start:cleanup_end]

    assert 'exit_code="$?"' in cleanup
    assert 'test "$exit_code" -ne 0' in cleanup
    assert "docker compose ps --all || true" in cleanup
    assert "docker compose logs --no-color order-service || true" in cleanup
    assert 'exit "$exit_code"' in cleanup
