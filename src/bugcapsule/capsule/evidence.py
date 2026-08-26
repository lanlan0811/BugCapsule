"""Load, validate, rank, and correlate evidence from an imported capsule."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

from bugcapsule.capsule.archive import ImportedCapsule
from bugcapsule.capsule.schema import EvidenceItem, EvidenceKind

TRACE_PAYLOAD = "evidence/traces.jsonl"
LOG_PAYLOAD = "evidence/logs.jsonl"
SUPPORTING_PAYLOAD = "evidence/source-snippets.json"

KIND_ORDER = {
    EvidenceKind.TRACE: 0,
    EvidenceKind.SPAN: 1,
    EvidenceKind.LOG: 2,
    EvidenceKind.STACKTRACE: 3,
    EvidenceKind.SOURCE: 4,
    EvidenceKind.GIT: 5,
    EvidenceKind.ENVIRONMENT: 6,
    EvidenceKind.TEST: 7,
}
EVIDENCE_LIST_ADAPTER: TypeAdapter[list[EvidenceItem]] = TypeAdapter(list[EvidenceItem])


class EvidenceLoadError(ValueError):
    """Raised when evidence payloads are malformed or internally inconsistent."""


@dataclass(frozen=True)
class EvidenceTimelineEntry:
    """One deterministic causal step derived without a model."""

    sequence: int
    evidence: EvidenceItem
    relation: str
    related_evidence_id: str | None


@dataclass(frozen=True)
class EvidenceChain:
    """Validated evidence exposed through priority and causal timeline views."""

    items: tuple[EvidenceItem, ...]
    ranked: tuple[EvidenceItem, ...]
    timeline: tuple[EvidenceTimelineEntry, ...]
    candidate_sources: tuple[EvidenceItem, ...]

    @property
    def evidence_ids(self) -> frozenset[str]:
        return frozenset(item.evidence_id for item in self.items)


class EvidenceCorrelator:
    """Build deterministic relationships from trace and span identifiers."""

    def build(self, capsule: ImportedCapsule) -> EvidenceChain:
        items = self._load_items(capsule)
        self._validate_items(capsule, items)
        ranked = tuple(
            sorted(
                items,
                key=lambda item: (
                    item.priority,
                    KIND_ORDER[item.kind],
                    item.captured_at,
                    item.evidence_id,
                ),
            )
        )
        timeline_items = sorted(items, key=self._timeline_sort_key)
        relations = self._relationships(capsule, timeline_items)
        timeline = tuple(
            EvidenceTimelineEntry(
                sequence=index,
                evidence=item,
                relation=relations[item.evidence_id][0],
                related_evidence_id=relations[item.evidence_id][1],
            )
            for index, item in enumerate(timeline_items, start=1)
        )
        candidate_sources = tuple(item for item in ranked if item.kind is EvidenceKind.SOURCE)
        return EvidenceChain(
            items=tuple(sorted(items, key=lambda item: item.evidence_id)),
            ranked=ranked,
            timeline=timeline,
            candidate_sources=candidate_sources,
        )

    def _load_items(self, capsule: ImportedCapsule) -> list[EvidenceItem]:
        items: list[EvidenceItem] = []
        for path in (TRACE_PAYLOAD, LOG_PAYLOAD):
            payload = capsule.payloads.get(path)
            if payload is None:
                continue
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise EvidenceLoadError(f"evidence payload is not UTF-8: {path}") from exc
            for line_number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    items.append(EvidenceItem.model_validate_json(line))
                except ValidationError as exc:
                    raise EvidenceLoadError(
                        f"invalid evidence record: {path}:{line_number}"
                    ) from exc

        supporting = capsule.payloads.get(SUPPORTING_PAYLOAD)
        if supporting is not None:
            try:
                items.extend(EVIDENCE_LIST_ADAPTER.validate_json(supporting))
            except ValidationError as exc:
                raise EvidenceLoadError(f"invalid evidence payload: {SUPPORTING_PAYLOAD}") from exc
        return items

    @staticmethod
    def _validate_items(capsule: ImportedCapsule, items: list[EvidenceItem]) -> None:
        if not items:
            raise EvidenceLoadError("capsule contains no evidence records")
        identifiers = [item.evidence_id for item in items]
        duplicates = sorted(item_id for item_id, count in Counter(identifiers).items() if count > 1)
        if duplicates:
            raise EvidenceLoadError(f"duplicate evidence IDs: {', '.join(duplicates)}")
        expected_trace = capsule.manifest.trace.trace_id
        mismatched = sorted(
            item.evidence_id
            for item in items
            if item.trace_id is not None and item.trace_id != expected_trace
        )
        if mismatched:
            raise EvidenceLoadError(
                f"evidence references a different trace: {', '.join(mismatched)}"
            )
        root_span = capsule.manifest.trace.root_span_id
        trace_items = [item for item in items if item.kind is EvidenceKind.TRACE]
        if len(trace_items) != 1 or trace_items[0].span_id != root_span:
            raise EvidenceLoadError("capsule evidence does not contain the manifest root span")
        span_items = [
            item for item in items if item.kind in {EvidenceKind.TRACE, EvidenceKind.SPAN}
        ]
        span_ids = [item.span_id for item in span_items]
        duplicate_spans = sorted(
            span_id
            for span_id, count in Counter(span_ids).items()
            if span_id is not None and count > 1
        )
        if duplicate_spans:
            raise EvidenceLoadError(f"duplicate span evidence: {', '.join(duplicate_spans)}")
        known_spans = {span_id for span_id in span_ids if span_id is not None}
        unknown_spans = sorted(
            item.evidence_id
            for item in items
            if item.span_id is not None and item.span_id not in known_spans
        )
        if unknown_spans:
            raise EvidenceLoadError(
                f"evidence references an unknown span: {', '.join(unknown_spans)}"
            )
        unknown_parents = sorted(
            item.evidence_id
            for item in span_items
            if isinstance(item.content.get("parent_span_id"), str)
            and item.content["parent_span_id"] not in known_spans
        )
        if unknown_parents:
            raise EvidenceLoadError(
                f"span references an unknown parent: {', '.join(unknown_parents)}"
            )

    @staticmethod
    def _timestamp_nanoseconds(item: EvidenceItem) -> int:
        for key in ("start_time_unix_nano", "timestamp_unix_nano", "end_time_unix_nano"):
            value = item.content.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return int(item.captured_at.timestamp() * 1_000_000_000)

    @classmethod
    def _timeline_sort_key(cls, item: EvidenceItem) -> tuple[int, int, int, str]:
        return (
            cls._timestamp_nanoseconds(item),
            KIND_ORDER[item.kind],
            item.priority,
            item.evidence_id,
        )

    @staticmethod
    def _relationships(
        capsule: ImportedCapsule,
        timeline: list[EvidenceItem],
    ) -> dict[str, tuple[str, str | None]]:
        span_evidence = {
            item.span_id: item.evidence_id
            for item in timeline
            if item.kind in {EvidenceKind.TRACE, EvidenceKind.SPAN} and item.span_id is not None
        }
        root_id = span_evidence[capsule.manifest.trace.root_span_id]
        logs_by_span: dict[str, str] = {}
        stacks_by_span: dict[str, str] = {}
        for item in timeline:
            if item.kind is EvidenceKind.LOG and item.span_id:
                logs_by_span.setdefault(item.span_id, item.evidence_id)
            elif item.kind is EvidenceKind.STACKTRACE and item.span_id:
                stacks_by_span.setdefault(item.span_id, item.evidence_id)

        relationships: dict[str, tuple[str, str | None]] = {}
        for item in timeline:
            related: str | None = root_id
            relation = "context_for"
            if item.evidence_id == root_id:
                relation, related = "request_root", None
            elif item.kind is EvidenceKind.SPAN:
                parent = item.content.get("parent_span_id")
                relation = "child_of"
                related = span_evidence.get(parent) if isinstance(parent, str) else root_id
            elif item.kind is EvidenceKind.LOG:
                relation = "observed_on"
                related = span_evidence.get(item.span_id or "", root_id)
            elif item.kind is EvidenceKind.STACKTRACE:
                relation = "exception_from"
                related = logs_by_span.get(item.span_id or "") or span_evidence.get(
                    item.span_id or "", root_id
                )
            elif item.kind is EvidenceKind.SOURCE:
                relation = "points_to"
                related = stacks_by_span.get(item.span_id or "") or root_id
            elif item.kind is EvidenceKind.GIT:
                relation = "version_context"
            elif item.kind is EvidenceKind.ENVIRONMENT:
                relation = "runtime_context"
            elif item.kind is EvidenceKind.TEST:
                relation = "verifies"
            relationships[item.evidence_id] = (relation, related)
        return relationships
