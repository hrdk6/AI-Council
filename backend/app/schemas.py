from typing import Optional

from pydantic import BaseModel


class MemberResponse(BaseModel):
    key: str
    role_name: str
    model: str
    provider: str
    content: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Optional[float] = None  # self-reported, 0-1
    key_risk: Optional[str] = None
    success: bool
    error: Optional[str] = None
    round: int = 1
    latency_s: Optional[float] = None
    tokens_used: Optional[int] = None


class CouncilResult(BaseModel):
    question: str
    decision_charter: str
    council_composition: list[str] = []
    round1: list[MemberResponse]
    round2: list[MemberResponse]
    agreement_score: Optional[float] = None
    confidence_score: Optional[float] = None
    debate_skipped: bool = False
    final_answer: str
    request_id: Optional[str] = None
    total_latency_s: Optional[float] = None
    cached: bool = False


class AskRequest(BaseModel):
    prompt: str