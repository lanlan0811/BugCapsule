"""Static safety contracts for the Docker integration workflow."""

from pathlib import Path

WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"


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
