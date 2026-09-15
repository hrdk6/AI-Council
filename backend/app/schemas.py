"""Pydantic schemas for the AI Council backend API."""

from typing import Any

from pydantic import BaseModel, Field


class Challenge(BaseModel):
    """A point one council member raises against a peer during the cross-examination round."""

    member: str
    point: str


class AttachmentSummary(BaseModel):
    """What the council received from one uploaded file (the extracted text itself is not stored)."""

    filename: str
    kind: str  # "pdf" | "image"
    pages: int | None = None
    chars: int = 0
    method: str  # "text" | "vision" | "unreadable"
    truncated: bool = False
    note: str | None = None


class WebSource(BaseModel):
    """A web page found during live research. ``read`` is False when only the search snippet was used."""

    title: str
    url: str
    domain: str
    snippet: str = ""
    published: str | None = None
    read: bool = False


class ResearchSummary(BaseModel):
    """The live web research the council received before deliberating."""

    status: str  # "ok" | "unavailable"
    searched_on: str  # ISO date
    queries: list[str] = Field(default_factory=list)
    engine: str | None = None
    sources: list[WebSource] = Field(default_factory=list)
    brief: str | None = None
    note: str | None = None


class MemberResponse(BaseModel):
    key: str
    role_name: str
    model: str
    provider: str
    content: str | None = None
    recommendation: str | None = None
    confidence: float | None = None
    key_risk: str | None = None
    success: bool
    error: str | None = None
    round: int = 1
    latency_s: float | None = None
    tokens_used: int | None = None
    # Populated when a backup model answered: the model that was tried first, and why it was skipped
    switched_from_model: str | None = None
    switch_reason: str | None = None
    # Round 2 only: which peers this member challenged, and on what
    challenges: list[Challenge] = Field(default_factory=list)


class CouncilResult(BaseModel):
    question: str
    decision_charter: str
    council_composition: list[str] = []
    round1: list[MemberResponse]
    round2: list[MemberResponse]
    agreement_score: float | None = None
    confidence_score: float | None = None
    debate_skipped: bool = False
    final_answer: str
    request_id: str | None = None
    total_latency_s: float | None = None
    cached: bool = False
    # True when a member or the chairman failed and the directive is based on partial deliberation
    degraded: bool = False
    sources: list[str] = Field(default_factory=list)
    attachments: list[AttachmentSummary] = Field(default_factory=list)
    research: ResearchSummary | None = None


class DecisionRecord(BaseModel):
    id: str
    created_at: str
    question: str
    result: dict[str, Any]
    rating: int | None = None
    outcome_note: str | None = None


class FeedbackInput(BaseModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    outcome_note: str | None = Field(default=None, max_length=2000)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str | None = None
    providers_missing: list[str] | None = None


class AskRequest(BaseModel):
    prompt: str
    debate: bool = True
    sources: list[str] = Field(default_factory=list)
