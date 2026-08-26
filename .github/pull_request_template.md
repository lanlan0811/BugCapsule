## Summary

Describe the user-visible outcome and the evidence or safety boundary affected.

## Verification

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy`
- [ ] `uv run pytest`
- [ ] Relevant Docker, browser, or manual verification completed or documented as pending

## Safety and compatibility

- [ ] No credentials, production logs, personal data, or proprietary source were added
- [ ] Capsule Schema, replay, CLI/Web/report fact consistency, and compatibility were considered
- [ ] Documentation and changelog were updated when behavior changed
