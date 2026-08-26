"""Tests for backend schemas."""

from app.schemas import CouncilResult, HealthResponse, MemberResponse


def test_member_response_defaults():
    member = MemberResponse(key="test", role_name="Test", model="test", provider="test", success=True)
    assert member.key == "test"
    assert member.success is True
    assert member.content is None
    assert member.confidence is None


def test_member_response_with_data():
    member = MemberResponse(
        key="test",
        role_name="Test",
        model="test",
        provider="test",
        success=True,
        content="Analysis content",
        recommendation="Do it",
        confidence=0.85,
        key_risk="Risk factor",
    )
    assert member.content == "Analysis content"
    assert member.recommendation == "Do it"
    assert member.confidence == 0.85
    assert member.key_risk == "Risk factor"


def test_council_result():
    member1 = MemberResponse(key="m1", role_name="M1", model="m1", provider="p1", success=True)
    member2 = MemberResponse(key="m2", role_name="M2", model="m2", provider="p2", success=True)
    
    result = CouncilResult(
        question="Test question",
        decision_charter="Test charter",
        round1=[member1],
        round2=[member2],
        final_answer="Test answer",
    )
    
    assert result.question == "Test question"
    assert len(result.round1) == 1
    assert len(result.round2) == 1
    assert result.cached is False


def test_health_response():
    health = HealthResponse(status="ok", version="1.0.0", providers_missing=[])
    assert health.status == "ok"
    assert health.version == "1.0.0"
    assert health.providers_missing == []
    
    health_degraded = HealthResponse(status="degraded", providers_missing=["groq (GROQ_API_KEY)"])
    assert health_degraded.status == "degraded"
    assert "groq" in health_degraded.providers_missing[0]