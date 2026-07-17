from typing import Optional

from pydantic import BaseModel


class MemberResponse(BaseModel):
    key: str
    role_name: str
    model: str
    provider: str
    content: Optional[str] = None
    success: bool
    error: Optional[str] = None
    round: int = 1


class CouncilResult(BaseModel):
    question: str
    decision_charter: str
    round1: list[MemberResponse]
    round2: list[MemberResponse]
    final_answer: str


class AskRequest(BaseModel):
    prompt: str
