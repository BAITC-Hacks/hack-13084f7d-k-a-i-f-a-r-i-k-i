"""Типы из contracts.md. Меняются только вместе с contracts.md."""
from typing import TypedDict, Literal, Optional

Side = Literal["before", "after"]


class Chunk(TypedDict):
    chunk_id: str
    doc_name: str
    side: Side
    page: Optional[int]
    clause: str
    section: str
    text: str


class Source(TypedDict):
    chunk_id: str
    quote: str


class Unit(TypedDict):
    unit_id: str
    side: Side
    code: str
    name: str
    parent: str
    source: Source


class Function(TypedDict):
    func_id: str
    unit_id: str
    text: str
    action_type: str
    source: Source


class Evidence(TypedDict):
    doc_name: str
    side: Side
    clause: str
    page: Optional[int]
    quote: str


class UnitMap(TypedDict):
    before_ids: list
    after_ids: list
    status: str
    rationale: str
    evidence: list


class FunctionMap(TypedDict):
    func_id: str
    status: str            # covered | partial | lost
    matched_func_ids: list
    score: float
    rationale: str


class Finding(TypedDict, total=False):
    finding_id: str
    type: str              # loss | duplicate | conflict
    severity: str          # high | medium | low
    title: str
    description: str
    evidence: list
    recommendation: str
    verified: bool
    verify_note: str


def evidence_from_chunk(ch: Chunk, quote: str | None = None) -> Evidence:
    return {"doc_name": ch["doc_name"], "side": ch["side"], "clause": ch["clause"],
            "page": ch["page"], "quote": quote if quote is not None else ch["text"]}
