"""Tests for council logic with mocked LLM calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.council import (
    _cache_key,
    _clip,
    _parse_structured_member_output,
    _score_consensus,
    _select_council,
    run_council,
)
from app.schemas import MemberResponse


class TestParseStructuredOutput:
    def test_valid_json(self):
        raw = '{"recommendation": "Do it", "confidence": 0.8, "key_risk": "Risk", "rationale": "Reasoning"}'
        result = _parse_structured_member_output(raw)
        assert result["recommendation"] == "Do it"
        assert result["confidence"] == 0.8
        assert result["key_risk"] == "Risk"
        assert result["rationale"] == "Reasoning"

    def test_json_with_fences(self):
        raw = '```json\n{"recommendation": "Do it", "confidence": 0.8}\n```'
        result = _parse_structured_member_output(raw)
        assert result["recommendation"] == "Do it"
        assert result["confidence"] == 0.8

    def test_invalid_json_fallback(self):
        raw = "Just some text reasoning"
        result = _parse_structured_member_output(raw)
        assert result["rationale"] == "Just some text reasoning"
        assert result["recommendation"] is None

    def test_confidence_clamping(self):
        raw = '{"confidence": 1.5}'
        result = _parse_structured_member_output(raw)
        assert result["confidence"] == 1.0
        
        raw = '{"confidence": -0.5}'
        result = _parse_structured_member_output(raw)
        assert result["confidence"] == 0.0


class TestSelectCouncil:
    def test_default_council_when_no_match(self):
        charter = "Some charter without council line"
        result = _select_council(charter)
        assert result == ["operator", "analyst", "risk", "researcher"]

    def test_parses_council_line(self):
        charter = "Some text\nCouncil: operator, risk\nMore text"
        result = _select_council(charter)
        assert "operator" in result
        assert "risk" in result

    def test_includes_anchor_experts(self):
        charter = "Council: operator, analyst"
        result = _select_council(charter)
        assert "risk" in result  # anchor expert

    def test_respects_max_size(self):
        charter = "Council: operator, analyst, risk, researcher, operator"
        result = _select_council(charter)
        assert len(result) <= 4


class TestScoreConsensus:
    def test_insufficient_responses(self):
        responses = [
            MemberResponse(key="m1", role_name="M1", model="m1", provider="p1", success=True, confidence=0.8)
        ]
        conf, agree = _score_consensus(responses)
        assert conf is None
        assert agree is None

    def test_calculates_scores(self):
        responses = [
            MemberResponse(key="m1", role_name="M1", model="m1", provider="p1", success=True, confidence=0.8),
            MemberResponse(key="m2", role_name="M2", model="m2", provider="p2", success=True, confidence=0.9),
            MemberResponse(key="m3", role_name="M3", model="m3", provider="p3", success=True, confidence=0.7),
        ]
        conf, agree = _score_consensus(responses)
        assert conf is not None
        assert agree is not None
        assert 0 <= conf <= 1
        assert 0 <= agree <= 1


class TestCacheKey:
    def test_deterministic(self):
        key1 = _cache_key("prompt", "context")
        key2 = _cache_key("prompt", "context")
        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex

    def test_different_for_different_inputs(self):
        key1 = _cache_key("prompt1", "context")
        key2 = _cache_key("prompt2", "context")
        assert key1 != key2

    def test_none_context_handled(self):
        key1 = _cache_key("prompt", None)
        key2 = _cache_key("prompt", "")
        assert key1 == key2


class TestClip:
    def test_no_clip_needed(self):
        text = "Short text"
        result = _clip(text, 100, "Label")
        assert result == "Short text"

    def test_clips_long_text(self):
        text = "x" * 200
        result = _clip(text, 100, "Label")
        assert len(result) > 100
        assert "truncated" in result
        assert "Label" in result


@pytest.mark.asyncio
async def test_run_council_basic(mocker):
    """Integration test with mocked LLM calls."""
    
    # Mock the LLM client
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content='{"recommendation": "Test", "confidence": 0.8, "key_risk": "Risk", "rationale": "Reasoning"}'))]
    mock_response.usage = MagicMock(total_tokens=100)
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    
    with patch('app.council.get_client', return_value=mock_client):
        result = await run_council(
            prompt="Should we test?",
            context=None,
            debate=False,
            use_cache=False,
        )
    
    assert result.question == "Should we test?"
    assert result.final_answer is not None
    assert len(result.round1) > 0
    assert result.cached is False