"""Pydantic models for API requests and responses."""

from typing import Any
from pydantic import BaseModel, Field


class MemberAnalysis(BaseModel):
    """Single council member's analysis."""

    key: str | None = None
    role_name: str | None = None
    provider: str | None = None
    model: str | None = None
    success: bool = True
    content: str | None = None
    recommendation: str | None = None
    key_risk: str | None = None
    confidence: float | None = None
    error: str | None = None


class CouncilRound(BaseModel):
    """A round of council deliberation."""

    members: list[MemberAnalysis] = Field(default_factory=list)

    def __iter__(self):
        return iter(self.members)

    def __len__(self):
        return len(self.members)

    def __getitem__(self, index: int | slice):
        return self.members[index]


class CouncilResponse(BaseModel):
    """Full response from the council API."""

    question: str | None = None
    decision_charter: str | None = None
    final_answer: str | None = None
    round1: list[dict[str, Any]] = Field(default_factory=list)
    round2: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def round_one(self) -> CouncilRound:
        return CouncilRound(members=[MemberAnalysis(**m) for m in self.round1 if isinstance(m, dict)])

    @property
    def round_two(self) -> CouncilRound:
        return CouncilRound(members=[MemberAnalysis(**m) for m in self.round2 if isinstance(m, dict)])

    @property
    def round_two_by_key(self) -> dict[str, MemberAnalysis]:
        return {m.key: m for m in self.round_two if m.key}


class AskRequest(BaseModel):
    """Request payload for /ask endpoint."""

    prompt: str
    debate: bool = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str | None = None


class ApiError(Exception):
    """Custom exception for API errors."""

    def __init__(self, message: str, status_code: int | None = None, detail: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail