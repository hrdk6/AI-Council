"""Tests for Pydantic API models."""

from frontend.api.models import (
    AskRequest,
    CouncilResponse,
    CouncilRound,
    MemberAnalysis,
)


class TestMemberAnalysis:
    def test_defaults(self):
        member = MemberAnalysis()
        assert member.success is True
        assert member.key is None
        assert member.content is None

    def test_extra_fields_ignored(self):
        member = MemberAnalysis(key="a", success=False, unknown_field="ignored")
        assert member.key == "a"
        assert member.success is False


class TestCouncilRound:
    def test_empty(self):
        round_ = CouncilRound()
        assert len(round_) == 0

    def test_from_dicts(self):
        round_ = CouncilRound(members=[MemberAnalysis(key="a"), MemberAnalysis(key="b")])
        assert [m.key for m in round_] == ["a", "b"]


class TestCouncilResponse:
    def test_round_properties(self):
        response = CouncilResponse(
            question="q",
            final_answer="a",
            round1=[{"key": "m1", "success": True}],
            round2=[{"key": "m1", "success": True, "content": "revised"}],
        )
        assert len(response.round_one) == 1
        assert len(response.round_two) == 1
        assert response.round_two_by_key["m1"].content == "revised"

    def test_empty_rounds(self):
        response = CouncilResponse()
        assert len(response.round_one) == 0
        assert response.round_two_by_key == {}

    def test_serialization_roundtrip(self):
        response = CouncilResponse(
            question="q",
            final_answer="a",
            round1=[{"key": "m1", "success": True, "confidence": 0.8}],
        )
        data = {"question": "q", "final_answer": "a",
                "round1": [m.model_dump() for m in response.round_one],
                "round2": [m.model_dump() for m in response.round_two]}
        restored = CouncilResponse(**data)
        assert restored.round_one[0].confidence == 0.8


class TestAskRequest:
    def test_serialization(self):
        request = AskRequest(prompt="Should we?", debate=True)
        assert request.model_dump() == {"prompt": "Should we?", "debate": True, "sources": []}
