"""Pydantic schemas for the AI Council backend API."""

from typing import Any

from pydantic import BaseModel, Field


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
    # Populated when auto-fallback switched to a different model due to rate-limiting
    switched_from_model: str | None = None


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
    sources: list[str] = Field(default_factory=list)


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
