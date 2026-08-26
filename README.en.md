# BugCapsule

BugCapsule is an evidence-first, open-source AI debugging tool. It packages traces, logs, stack traces, bounded source snippets, Git context, model analysis, a proposed Patch, and isolated before/after verification into a portable and integrity-checked `.bugcapsule` archive.

The model cannot edit the main workspace. Every root-cause citation must resolve to evidence included in the model request; every Patch is parsed and checked locally; verification requires an exact Patch ID, SHA-256, and explicit approval before it runs in restricted temporary Docker copies.

The primary repository and contribution entry point are on [Gitee](https://gitee.com/lan0811/bug-capsule). The GitHub repository is a mirror.

## Requirements

- Python 3.10, 3.11, or 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop or Docker Engine with Compose v2 for the main demo and isolated verification
- Git

Windows 10/11 and Linux are the intended development environments. All Web assets are packaged locally; replay mode can be demonstrated without model network access.

## Quick start

```powershell
git clone https://gitee.com/lanlan0811/bug-capsule.git
cd bug-capsule
Copy-Item .env.example .env
uv sync --frozen --group dev
uv run bugcapsule doctor
uv run bugcapsule serve
```

Open `http://127.0.0.1:8765`. The service intentionally refuses public bind addresses.

Start and reproduce the controlled PostgreSQL connection-pool failure:

```powershell
uv run bugcapsule demo up
uv run bugcapsule demo run
uv run bugcapsule demo reset
```

Use the Trace ID produced by the demo to capture and inspect a capsule:

```powershell
uv run bugcapsule capture --trace-id <32-lowercase-hex-trace-id>
uv run bugcapsule capsules list
uv run bugcapsule capsules show <capsule-id>
```

## Analysis, Patch, verification, and report

Configure an OpenAI-compatible provider in `.env` for `live`, or use a matching structured replay record for `replay`. `off` never calls a model.

```powershell
uv run bugcapsule analyze <capsule-id> --mode replay
uv run bugcapsule patch generate <capsule-id> --mode replay
uv run bugcapsule verify <capsule-id> `
  --patch-id <full-patch-id> `
  --approved-sha256 <full-64-character-sha256> `
  --approve
uv run bugcapsule report <capsule-id> --output .\verification-report.html
```

The self-contained HTML report has no scripts or external resources and can be viewed or printed offline.

## Reproducible benchmark

The packaged simulated dataset contains 12 annotated capsules: four connection leaks, four unreachable databases, and four slow-query cases.

```powershell
uv run bugcapsule benchmark build --output .\benchmark-data
uv run bugcapsule benchmark run --mode replay --output .\benchmark-replay
```

Replay measurements validate the offline pipeline and scoring method; they are never presented as live-model capability. See [the benchmark protocol](docs/benchmark.md).

A [checksum-pinned simulated connection-leak capsule](examples/README.md) is committed for direct format review and Web import. Tests continuously verify its archive integrity and provenance from the versioned dataset.

## Quality gates

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

The current test gate requires at least 90% branch-aware coverage. CI runs the locked dependency graph on Python 3.10-3.12 and executes the restricted before/after regression 20 times per state.

The supply-chain gate builds the wheel and source archive, generates a CycloneDX 1.6 SBOM from the production-only environment, audits hash-locked dependencies, and writes SHA-256 checksums for every deliverable. See the [release supply-chain guide](docs/supply-chain.md) for reproduction steps and limitations.

## Security and contribution

Do not submit production logs, credentials, personal data, or proprietary source. Review the redaction report before sharing a capsule or HTML report. See the [security policy](SECURITY.md), [contribution guide](CONTRIBUTING.md), [threat model](docs/threat-model.md), [supply-chain guide](docs/supply-chain.md), and [roadmap](docs/roadmap.md).

BugCapsule is licensed under the [Apache License 2.0](LICENSE).
