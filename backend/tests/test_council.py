"""Tests for council logic with mocked LLM calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

import app.council as council
from app.config import ModelConfig
from app.council import (
    CHAIRMAN_FALLBACK_ANSWER,
    CouncilUnavailableError,
    _cache_key,
    _call_text,
    _clip,
    _is_retriable,
    _parse_structured_member_output,
    _public_provider_error,
    _retry_wait_seconds,
    _score_consensus,
    _select_council,
    run_council,
)
from app.schemas import MemberResponse

MEMBER_JSON = '{"recommendation": "Test", "confidence": 0.8, "key_risk": "Risk", "rationale": "Reasoning"}'


def _status_error(cls, status_code: int, headers: dict | None = None):
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status_code, request=request, headers=headers or {})
    return cls(f"Error code: {status_code}", response=response, body=None)


def _completion(content: str = MEMBER_JSON, tokens: int = 100):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = MagicMock(total_tokens=tokens)
    return response


def _mock_client(create: AsyncMock):
    client = MagicMock()
    client.chat.completions.create = create
    return client


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(council, "_retry_wait_seconds", lambda error, attempt: 0)


class TestParseStructuredOutput:
    def test_valid_json(self):
        result = _parse_structured_member_output(MEMBER_JSON.replace("Test", "Do it").replace("Reasoning", "R"))
        assert result["recommendation"] == "Do it"
        assert result["confidence"] == 0.8
        assert result["key_risk"] == "Risk"
        assert result["rationale"] == "R"

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

    def test_truncated_json_recovers_fields(self):
        raw = '{"recommendation": "Ship it", "confidence": 0.7, "rationale": "Because the data'
        result = _parse_structured_member_output(raw)
        assert result["recommendation"] == "Ship it"
        assert result["confidence"] == 0.7
        assert result["rationale"].startswith("Because the data")

    def test_json_cut_off_inside_first_field_never_leaks_raw_json(self):
        result = _parse_structured_member_output('{"recommendation":"Select Contoso and schedule a short (2-')
        assert result["recommendation"] == "Select Contoso and schedule a short (2-…"
        assert result["rationale"] == ""

    def test_escaped_characters_are_decoded(self):
        raw = '{"recommendation": "Say \\"no\\" for now", "rationale": "Line one\\nLine two'
        result = _parse_structured_member_output(raw)
        assert result["recommendation"] == 'Say "no" for now'
        assert result["rationale"] == "Line one\nLine two…"

    def test_confidence_clamping(self):
        assert _parse_structured_member_output('{"confidence": 1.5}')["confidence"] == 1.0
        assert _parse_structured_member_output('{"confidence": -0.5}')["confidence"] == 0.0


class TestSelectCouncil:
    def test_default_council_when_no_match(self):
        result = _select_council("Some charter without council line")
        assert result == ["operator", "analyst", "risk", "researcher"]

    def test_parses_council_line(self):
        result = _select_council("Some text\nCouncil: operator, risk\nMore text")
        assert "operator" in result
        assert "risk" in result

    def test_includes_anchor_experts(self):
        assert "risk" in _select_council("Council: operator, analyst")

    def test_ignores_unknown_and_duplicate_keys(self):
        result = _select_council("Council: operator, hacker, operator")
        assert result.count("operator") == 1
        assert "hacker" not in result

    def test_respects_max_size(self):
        result = _select_council("Council: operator, analyst, risk, researcher, operator")
        assert len(result) <= council.MAX_COUNCIL_SIZE


class TestScoreConsensus:
    def test_insufficient_responses(self):
        responses = [
            MemberResponse(key="m1", role_name="M1", model="m1", provider="p1", success=True, confidence=0.8)
        ]
        assert _score_consensus(responses) == (None, None)

    def test_calculates_scores(self):
        responses = [
            MemberResponse(key="m1", role_name="M1", model="m1", provider="p1", success=True, confidence=0.8),
            MemberResponse(key="m2", role_name="M2", model="m2", provider="p2", success=True, confidence=0.9),
            MemberResponse(key="m3", role_name="M3", model="m3", provider="p3", success=True, confidence=0.7),
        ]
        conf, agree = _score_consensus(responses)
        assert conf is not None and 0 <= conf <= 1
        assert agree is not None and 0 <= agree <= 1


class TestCacheKey:
    def test_deterministic(self):
        key1 = _cache_key("prompt", "context")
        assert key1 == _cache_key("prompt", "context")
        assert len(key1) == 64  # SHA256 hex

    def test_different_for_different_inputs(self):
        assert _cache_key("prompt1", "context") != _cache_key("prompt2", "context")

    def test_none_context_handled(self):
        assert _cache_key("prompt", None) == _cache_key("prompt", "")

    def test_debate_flag_changes_key(self):
        assert _cache_key("prompt", None, debate=True) != _cache_key("prompt", None, debate=False)


class TestClip:
    def test_no_clip_needed(self):
        assert _clip("Short text", 100, "Label") == "Short text"

    def test_clips_long_text(self):
        result = _clip("x" * 200, 100, "Label")
        assert "truncated" in result
        assert "Label" in result


class TestErrorClassification:
    @pytest.mark.parametrize("status_code", [404, 429, 500, 502, 503, 504])
    def test_transient_status_codes_are_retriable(self, status_code):
        assert _is_retriable(_status_error(openai.APIStatusError, status_code))

    @pytest.mark.parametrize(
        ("cls", "status_code"),
        [(openai.AuthenticationError, 401), (openai.PermissionDeniedError, 403), (openai.BadRequestError, 400)],
    )
    def test_client_errors_are_not_retriable(self, cls, status_code):
        assert not _is_retriable(_status_error(cls, status_code))

    def test_connection_errors_are_retriable(self):
        request = httpx.Request("POST", "https://api.example.com")
        assert _is_retriable(openai.APITimeoutError(request=request))
        assert _is_retriable(openai.APIConnectionError(request=request))

    def test_retry_after_header_is_respected_and_capped(self):
        # Imported before the autouse fixture replaces the module attribute, so this is the real function.
        assert _retry_wait_seconds(_status_error(openai.RateLimitError, 429, {"retry-after": "2"}), 0) == 2.5
        assert _retry_wait_seconds(_status_error(openai.RateLimitError, 429, {"retry-after": "600"}), 0) == 15.0

    def test_public_error_uses_status_code_from_cause(self):
        wrapped = RuntimeError("failed")
        wrapped.__cause__ = _status_error(openai.AuthenticationError, 401)
        assert "credentials" in _public_provider_error(wrapped)


class TestCallText:
    groq_cfg = ModelConfig(provider="groq", model="openai/gpt-oss-20b", role_name="R", system_prompt="S")

    async def test_rate_limit_switches_to_next_model(self):
        create = AsyncMock(side_effect=[_status_error(openai.RateLimitError, 429), _completion("ok")])
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, model = await _call_text("t", self.groq_cfg, "prompt", max_tokens=10)
        assert text == "ok"
        assert model == "openai/gpt-oss-120b"
        assert [c.kwargs["model"] for c in create.await_args_list] == ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]

    async def test_authentication_error_fails_fast(self):
        create = AsyncMock(side_effect=_status_error(openai.AuthenticationError, 401))
        with patch.object(council, "get_client", return_value=_mock_client(create)), \
                pytest.raises(RuntimeError, match="1 attempt"):
            await _call_text("t", self.groq_cfg, "prompt", max_tokens=10)
        assert create.await_count == 1

    async def test_gpt_oss_requests_low_reasoning_effort(self):
        create = AsyncMock(return_value=_completion("ok"))
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            await _call_text("t", self.groq_cfg, "prompt", max_tokens=10)
        assert create.await_args.kwargs["reasoning_effort"] == "low"

    async def test_other_models_get_no_reasoning_option(self):
        other = ModelConfig(provider="gemini", model="gemini-2.5-flash", role_name="R", system_prompt="S")
        create = AsyncMock(return_value=_completion("ok"))
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            await _call_text("t", other, "prompt", max_tokens=10)
        assert "reasoning_effort" not in create.await_args.kwargs

    async def test_budget_doubles_when_reasoning_exhausts_tokens(self):
        cut_off = _completion("")
        cut_off.choices[0].finish_reason = "length"
        nonstreaming = ModelConfig(provider="gemini", model="m", role_name="R", system_prompt="S")
        create = AsyncMock(side_effect=[cut_off, _completion("answer")])
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, _ = await _call_text("t", nonstreaming, "prompt", max_tokens=500)
        assert text == "answer"
        assert [call.kwargs["max_tokens"] for call in create.await_args_list] == [500, 1000]

    async def test_truncated_answer_retried_with_larger_budget(self):
        cut = _completion("Recommendation\nHire the rep. Confidence: 78% that")
        cut.choices[0].finish_reason = "length"
        whole = _completion("Recommendation\nHire the rep.\n\nConfidence and key uncertainty\nModerate.")
        whole.choices[0].finish_reason = "stop"
        create = AsyncMock(side_effect=[cut, whole])
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, _ = await _call_text("chairman", self.groq_cfg, "p", max_tokens=700, retry_truncated=True)
        assert text.endswith("Moderate.")
        assert [call.kwargs["max_tokens"] for call in create.await_args_list] == [700, 1400]

    async def test_truncated_answer_kept_when_longer_retry_fails(self):
        cut = _completion("Recommendation\nHire the rep. Confidence: 78% that")
        cut.choices[0].finish_reason = "length"
        auth = _status_error(openai.AuthenticationError, 401)
        create = AsyncMock(side_effect=[cut, auth])
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, _ = await _call_text("chairman", self.groq_cfg, "p", max_tokens=700, retry_truncated=True)
        assert text.startswith("Recommendation\nHire the rep.")

    async def test_truncation_is_accepted_without_retry_flag(self):
        cut = _completion("Partial answer")
        cut.choices[0].finish_reason = "length"
        create = AsyncMock(return_value=cut)
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, _ = await _call_text("member", self.groq_cfg, "p", max_tokens=500)
        assert text == "Partial answer"
        assert create.await_count == 1

    async def test_member_with_no_usable_position_is_marked_failed(self):
        create = AsyncMock(return_value=_completion('{"confidence": 0.5, "rationale": ""}'))
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            member = await council.call_member("risk", self.groq_cfg, "prompt", round_num=1)
        assert member.success is False

    async def test_empty_response_is_retried(self):
        create = AsyncMock(side_effect=[_completion("<think>hidden</think>"), _completion("answer")])
        with patch.object(council, "get_client", return_value=_mock_client(create)):
            text, _, _ = await _call_text("t", self.groq_cfg, "prompt", max_tokens=10)
        assert text == "answer"


async def test_run_council_basic():
    """Integration test with mocked LLM calls."""
    create = AsyncMock(return_value=_completion())
    with patch.object(council, "get_client", return_value=_mock_client(create)):
        result = await run_council(prompt="Should we test?", context=None, debate=False, use_cache=False)

    assert result.question == "Should we test?"
    assert result.final_answer
    assert len(result.round1) > 0
    assert result.cached is False
    assert result.degraded is False


class TestChallenges:
    def test_parses_challenges_addressed_to_peers(self):
        raw = (
            '{"challenges": [{"member": "operator", "point": "Timeline ignores migration."}, '
            '{"member": "wizard", "point": "Invented peer."}, {"member": "[analyst]", "point": "Weights are arbitrary."}], '
            '"recommendation": "Pilot first", "confidence": 0.6, "rationale": "Because."}'
        )
        result = _parse_structured_member_output(raw, {"operator", "analyst"})
        assert [(c.member, c.point) for c in result["challenges"]] == [
            ("operator", "Timeline ignores migration."), ("analyst", "Weights are arbitrary."),
        ]

    def test_round_one_output_has_no_challenges(self):
        assert _parse_structured_member_output(MEMBER_JSON)["challenges"] == []

    def test_truncated_json_still_recovers_challenges(self):
        raw = '{"challenges": [{"member": "risk", "point": "No exit clause."}], "recommendation": "Wait", "rationale": "Cut'
        result = _parse_structured_member_output(raw, {"risk"})
        assert result["challenges"][0].member == "risk"
        assert result["recommendation"] == "Wait"


async def test_debate_round_streams_member_events_and_challenges():
    events: list[tuple[str, dict]] = []

    async def on_event(event, data):
        events.append((event, data))

    async def create(**kwargs):
        prompt = kwargs["messages"][1]["content"]
        if "PEER POSITIONS" in prompt:
            peer = "analyst" if "[analyst]" in prompt else "operator"
            return _completion(
                f'{{"challenges": [{{"member": "{peer}", "point": "Needs evidence."}}], '
                '"recommendation": "Revised", "confidence": 0.4, "rationale": "Revised view."}'
            )
        if "decision architect" in kwargs["messages"][0]["content"]:
            return _completion("Decision: x\nCouncil: operator, analyst")
        # Divergent first-round answers so the challenge round is not skipped.
        word = "expand" if "Operator" in kwargs["messages"][0]["content"] else "wait"
        return _completion(f'{{"recommendation": "{word} now", "confidence": 0.9, "rationale": "r"}}')

    with patch.object(council, "get_client", return_value=_mock_client(AsyncMock(side_effect=create))):
        result = await run_council(prompt="Debate please", debate=True, use_cache=False, on_event=on_event)

    names = [name for name, _ in events]
    assert names.index("debate_started") < names.index("synthesis_started")
    consensus = [data for name, data in events if name == "consensus_update"]
    assert [data["round"] for data in consensus] == [1, 2]
    assert consensus[-1]["agreement_score"] == result.agreement_score
    started = [data for name, data in events if name == "member_started"]
    done = [data for name, data in events if name == "member_done"]
    assert len(started) == len(done) == len(result.round1) + len(result.round2)
    # Every member_done is preceded by that member's member_started for the same round.
    for data in done:
        start_index = next(i for i, (n, d) in enumerate(events)
                           if n == "member_started" and d["key"] == data["key"] and d["round"] == data["round"])
        done_index = next(i for i, (n, d) in enumerate(events) if n == "member_done" and d is data)
        assert start_index < done_index
    assert result.round2
    assert all(member.challenges for member in result.round2)
    assert all(c.member != member.key for member in result.round2 for c in member.challenges)


async def test_run_council_emits_progress_events():
    events: list[str] = []

    async def on_event(event, data):
        events.append(event)

    create = AsyncMock(return_value=_completion())
    with patch.object(council, "get_client", return_value=_mock_client(create)):
        await run_council(prompt="Should we test events?", debate=False, use_cache=False, on_event=on_event)

    assert events[0] == "charter_ready"
    assert "member_done" in events
    assert events[-2:] == ["synthesis_started", "final"]


async def test_run_council_serves_cached_result_second_time():
    create = AsyncMock(return_value=_completion())
    with patch.object(council, "get_client", return_value=_mock_client(create)):
        first = await run_council(prompt="Cache me please", debate=False)
        calls_after_first = create.await_count
        second = await run_council(prompt="Cache me please", debate=False)

    assert first.cached is False
    assert second.cached is True
    assert second.request_id != first.request_id
    assert create.await_count == calls_after_first


async def test_degraded_result_is_not_cached():
    member_ok = _completion()
    auth_error = _status_error(openai.AuthenticationError, 401)
    call_count = {"n": 0}

    async def create(**kwargs):
        call_count["n"] += 1
        if "final decision authority" in kwargs["messages"][0]["content"]:
            raise auth_error  # chairman fails
        return member_ok

    client = _mock_client(AsyncMock(side_effect=create))
    with patch.object(council, "get_client", return_value=client):
        first = await run_council(prompt="Chairman will fail", debate=False)
        second = await run_council(prompt="Chairman will fail", debate=False)

    assert first.degraded is True
    assert first.final_answer == CHAIRMAN_FALLBACK_ANSWER
    assert second.cached is False  # the partial result was not replayed from cache


async def test_run_council_raises_when_no_member_responds():
    create = AsyncMock(side_effect=_status_error(openai.AuthenticationError, 401))
    with patch.object(council, "get_client", return_value=_mock_client(create)), \
            pytest.raises(CouncilUnavailableError):
        await run_council(prompt="Nobody answers", debate=False, use_cache=False)
