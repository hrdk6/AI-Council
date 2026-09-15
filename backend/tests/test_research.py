"""Tests for live web research, with every network call mocked."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import openai
import pytest

import app.research as research
from app.council import CallResult, current_date_note
from app.research import (
    Findings,
    PageText,
    SearchHit,
    build_research_context,
    extract_page,
    fetch_page,
    find,
    find_with_groq,
    find_with_tavily,
    merge_hits,
    parse_browser_tools,
    parse_duckduckgo,
    parse_plan,
    plan_research,
    run_research,
    select_passages,
)
from app.routing import MODEL_HEALTH, ModelRef
from app.schemas import ResearchSummary, WebSource


def _events():
    events: list[tuple[str, dict]] = []

    async def on_event(name, data):
        events.append((name, data))

    return events, on_event


def _call(text: str) -> CallResult:
    return CallResult(text, 10, "qwen/qwen3.8-27b", "groq")


class TestPlan:
    def test_no_search_needed(self):
        assert parse_plan('{"search": false, "queries": []}') == []

    def test_queries_are_cleaned_deduplicated_and_limited(self):
        text = '```json\n{"search": true, "queries": ["  GPT  latest ", "GPT latest", "b", "c", "d"]}\n```'
        assert parse_plan(text) == ["GPT latest", "b", "c"]

    def test_search_without_queries_uses_the_question(self):
        assert parse_plan('{"search": true}', "whats openai latest model") == ["whats openai latest model"]

    def test_unparseable_plan(self):
        assert parse_plan("I think we should search") is None

    async def test_planner_decides(self, monkeypatch):
        monkeypatch.setattr(research, "_call_text", AsyncMock(return_value=_call(
            '{"search": true, "queries": ["Claude Code pricing 2026", "Codex pricing 2026"]}'
        )))
        assert await plan_research("claude code or codex subscription?") == ["Claude Code pricing 2026", "Codex pricing 2026"]

    async def test_planner_failure_falls_back_to_recency_words(self, monkeypatch):
        monkeypatch.setattr(research, "_call_text", AsyncMock(side_effect=RuntimeError("all models paused")))
        assert await plan_research("What is OpenAI's latest model?") == ["What is OpenAI's latest model?"]
        assert await plan_research("Should I confront my cofounder?") == []


class TestParsing:
    def test_duckduckgo_results(self):
        page = """
        <div class="result results_links results_links_deep result--ad "><a class="result__a" href="https://ads.example">Ad</a></div>
        <div class="result results_links results_links_deep web-result ">
          <h2 class="result__title"><a rel="nofollow" class="result__a" href="https://openai.com/index/gpt-6/">GPT-6 &amp; you</a></h2>
          <a class="result__snippet" href="https://openai.com/index/gpt-6/">Introducing <b>GPT-6</b>.</a>
        </div>
        <div class="result results_links results_links_deep web-result ">
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews&amp;rut=x">News</a>
        </div>
        """
        hits = parse_duckduckgo(page)
        assert [(hit.title, hit.url) for hit in hits] == [
            ("GPT-6 & you", "https://openai.com/index/gpt-6/"), ("News", "https://example.com/news"),
        ]
        assert hits[0].snippet == "Introducing GPT-6 ."

    def test_extract_page_keeps_content_and_finds_dates(self):
        markup = """<html><head><title>Plans &amp; Pricing</title>
        <meta property="article:published_time" content="2026-09-03T10:00:00Z">
        <script>var secret = "ignore me";</script><style>.x{}</style></head>
        <body><nav>Home Products</nav><main><h1>Pricing</h1><p>Pro costs $20 per month.</p>
        <p>Pro costs $20 per month.</p><svg><text>icon</text></svg></main><footer>Legal</footer></body></html>"""
        page = extract_page(markup)
        assert page.title == "Plans & Pricing"
        assert page.published == "2026-09-03"
        assert page.text == "Pricing\nPro costs $20 per month."

    def test_extract_page_reads_json_ld_date(self):
        page = extract_page('<script type="application/ld+json">{"datePublished": "2026-08-01"}</script><p>Hi</p>')
        assert page.published == "2026-08-01"

    def test_select_passages_prefers_relevant_figures_within_budget(self):
        filler = "\n".join(f"Company history paragraph {n} about our founding story and culture." * 5 for n in range(20))
        text = f"{filler}\nThe Codex Pro plan costs $200 per month and includes higher usage limits for Codex.\n{filler}"
        excerpt = select_passages(text, {"codex", "pricing"}, budget=400)
        assert "$200 per month" in excerpt
        assert len(excerpt) <= 420

    def test_merge_hits_interleaves_and_deduplicates(self):
        a = [SearchHit("A1", "https://www.a.com/x/"), SearchHit("A2", "https://a.com/y")]
        b = [SearchHit("B1", "https://a.com/x"), SearchHit("B2", "javascript:alert(1)"), SearchHit("B3", "https://b.com")]
        assert [hit.title for hit in merge_hits([a, b], limit=5)] == ["A1", "A2", "B3"]

    def test_browser_tool_output(self):
        tools = [
            {"type": "browser_search", "search_results": {"results": [
                {"title": "Plans &amp; Pricing | Claude", "url": "https://claude.com/pricing", "content": ""},
                {"title": "Codex Pricing", "url": "https://chatgpt.com/codex/pricing/", "content": ""},
            ]}},
            {"type": "browser.open", "search_results": {"results": [{
                "title": "claude.com - viewing lines [0 - 3] of 3", "url": "https://claude.com/pricing",
                "content": "L0: \nL1: URL: https://claude.com/pricing\nL2: Plans \\| Claude\nL3: Pro is $20 per month. "
                           "See 【4†the Max plan†claude.com】 for more. " + "Details about usage limits. " * 10,
            }]}},
            {"type": "browser.open", "search_results": {"results": [
                {"title": "x", "url": "https://tiny.example", "content": "L0: too short"},
            ]}},
        ]
        hits, pages = parse_browser_tools(tools, limit=6)
        assert [hit.url for hit in hits] == ["https://claude.com/pricing", "https://chatgpt.com/codex/pricing/"]
        assert hits[0].title == "Plans & Pricing | Claude"
        page = pages["https://claude.com/pricing"]
        assert page.text.startswith("Pro is $20 per month. See the Max plan for more.")
        assert "L3" not in page.text and "URL:" not in page.text
        assert "https://tiny.example" not in pages


class TestFetchPage:
    @pytest.fixture
    def public(self, monkeypatch):
        monkeypatch.setattr(research, "_resolves_publicly", AsyncMock(return_value=True))

    async def test_private_addresses_are_never_fetched(self):
        requests = []
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: requests.append(request)))
        for url in ("http://127.0.0.1/admin", "http://10.0.0.8/", "http://localhost:8000/", "http://[::1]/"):
            assert await fetch_page(client, url) is None
        assert await fetch_page(client, "https://example.com:8443/") is None  # non-standard port
        assert await fetch_page(client, "file:///etc/passwd") is None
        assert requests == []

    async def test_reads_html(self, public):
        def handler(request):
            return httpx.Response(200, headers={"content-type": "text/html"}, text="<title>T</title><p>Body text</p>")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            page = await fetch_page(client, "https://example.com/")
        assert page == PageText(title="T", text="Body text", published=None)

    async def test_redirects_are_rechecked(self, monkeypatch):
        async def resolves(host, port):
            return host == "example.com"

        monkeypatch.setattr(research, "_resolves_publicly", resolves)

        def handler(request):
            return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await fetch_page(client, "https://example.com/") is None

    async def test_non_html_is_skipped(self, public):
        def handler(request):
            return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert await fetch_page(client, "https://example.com/a.pdf") is None


class TestEngines:
    async def test_tavily_returns_page_text(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
        seen = {}

        def handler(request):
            seen["auth"] = request.headers["authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"results": [{
                "title": "Codex pricing", "url": "https://openai.com/codex", "content": "Plus $20",
                "raw_content": "Codex is included in Plus at $20 per month.", "published_date": "2026-09-01",
            }]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            findings = await find_with_tavily(client, ["codex pricing"])
        assert seen["auth"] == "Bearer tvly-test"
        assert seen["body"]["include_raw_content"] == "text"
        assert findings.hits[0].published == "2026-09-01"
        assert findings.pages["https://openai.com/codex"].text.startswith("Codex is included")

    async def test_groq_browser_search_moves_past_a_rate_limited_model(self, monkeypatch):
        message = MagicMock()
        message.model_dump.return_value = {"executed_tools": [
            {"type": "browser.open", "search_results": {"results": [
                {"url": "https://openai.com/index/gpt-6/", "content": "L0: GPT-6\nL1: " + "Introducing GPT-6. " * 20},
            ]}},
        ]}
        response = MagicMock(choices=[MagicMock(message=message)], usage=MagicMock(total_tokens=9000))
        error = openai.RateLimitError(
            "Error code: 429", body=None,
            response=httpx.Response(429, request=httpx.Request("POST", "https://api.groq.com"), headers={"retry-after": "20"}),
        )
        create = AsyncMock(side_effect=[error, response])
        client = MagicMock()
        client.chat.completions.create = create
        monkeypatch.setattr(research, "get_client", lambda provider: client)

        findings = await find_with_groq("latest openai model?", ["OpenAI latest model 2026"])
        assert [call.kwargs["model"] for call in create.await_args_list] == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        assert create.await_args_list[0].kwargs["extra_body"]["tools"] == [{"type": "browser_search"}]
        assert findings.engine == "groq"
        assert findings.hits[0].url == "https://openai.com/index/gpt-6/"
        assert MODEL_HEALTH.cooldown(ModelRef("groq", "openai/gpt-oss-120b"))[1] == "rate_limit"

    async def test_engines_are_tried_in_order_and_failures_pause_them(self, monkeypatch):
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setenv("GROQ_API_KEY", "gsk-test")
        tavily = AsyncMock()
        groq = AsyncMock(side_effect=research.SearchError("no browser"))
        duck = AsyncMock(return_value=Findings("duckduckgo", [SearchHit("A", "https://a.com")]))
        monkeypatch.setattr(research, "find_with_tavily", tavily)
        monkeypatch.setattr(research, "find_with_groq", groq)
        monkeypatch.setattr(research, "find_with_duckduckgo", duck)

        assert (await find("q", ["q"])).engine == "duckduckgo"
        tavily.assert_not_called()  # no key
        assert (await find("q", ["q"])).engine == "duckduckgo"
        assert groq.await_count == 1  # paused after failing

    async def test_nothing_found_anywhere(self, monkeypatch):
        monkeypatch.setattr(research, "_engine_available", lambda engine: engine == "duckduckgo")
        monkeypatch.setattr(research, "find_with_duckduckgo", AsyncMock(return_value=Findings("duckduckgo", [])))
        assert await find("q", ["q"]) is None


class TestRunResearch:
    async def test_full_run_builds_a_cited_brief(self, monkeypatch):
        monkeypatch.setattr(research, "plan_research", AsyncMock(return_value=["OpenAI latest model 2026"]))
        monkeypatch.setattr(research, "find", AsyncMock(return_value=Findings(
            "groq",
            [SearchHit("GPT-6 Astra | OpenAI", "https://openai.com/index/gpt-6-astra/"),
             SearchHit("Axios story", "https://www.axios.com/2026/09/03/astra", snippet="OpenAI releases GPT-6 Astra")],
            {"https://openai.com/index/gpt-6-astra/": PageText("GPT-6 Astra", "We're introducing GPT-6 Astra.", "2026-09-03")},
        )))
        brief_call = AsyncMock(return_value=_call("- GPT-6 Astra is OpenAI's newest model [1].\nNot established: price."))
        monkeypatch.setattr(research, "_call_text", brief_call)
        events, on_event = _events()

        summary = await run_research("whats openai's latest llm?", on_event, "req")
        assert [name for name, _ in events] == ["research_started", "research_searching", "research_reading", "research_ready"]
        assert summary.status == "ok" and summary.engine == "groq"
        assert [(source.domain, source.read, source.published) for source in summary.sources] == [
            ("openai.com", True, "2026-09-03"), ("axios.com", False, None),
        ]
        brief_prompt = brief_call.await_args.args[2]
        assert "[1] GPT-6 Astra | OpenAI" in brief_prompt and "We're introducing GPT-6 Astra." in brief_prompt
        assert "[2] Axios story" in brief_prompt and "OpenAI releases GPT-6 Astra" in brief_prompt

        context = build_research_context(summary)
        assert context.startswith("LIVE WEB RESEARCH (searched ")
        assert "GPT-6 Astra is OpenAI's newest model [1]." in context
        assert "[1] GPT-6 Astra | OpenAI (openai.com, published 2026-09-03) https://openai.com/index/gpt-6-astra/" in context

    async def test_brief_falls_back_to_snippets(self, monkeypatch):
        monkeypatch.setattr(research, "_call_text", AsyncMock(side_effect=RuntimeError("paused")))
        sources = [WebSource(title="Codex Pricing", url="https://x.com", domain="x.com", snippet="Plus is $20")]
        assert await research.write_brief("q", ["q"], sources, {}) == "- Codex Pricing: Plus is $20 [1]"

    async def test_questions_that_need_no_research_are_skipped(self, monkeypatch):
        monkeypatch.setattr(research, "plan_research", AsyncMock(return_value=[]))
        find_mock = AsyncMock()
        monkeypatch.setattr(research, "find", find_mock)
        events, on_event = _events()
        assert await run_research("Should I move cities?", on_event) is None
        assert [name for name, _ in events] == ["research_started", "research_skipped"]
        find_mock.assert_not_called()

    async def test_unavailable_search_is_reported(self, monkeypatch):
        monkeypatch.setattr(research, "plan_research", AsyncMock(return_value=["codex pricing"]))
        monkeypatch.setattr(research, "find", AsyncMock(return_value=None))
        events, on_event = _events()
        summary = await run_research("codex pricing?", on_event)
        assert summary.status == "unavailable" and summary.note == research.UNAVAILABLE_NOTE
        assert events[-1][0] == "research_ready" and events[-1][1]["status"] == "unavailable"
        assert "possibly out of date" in build_research_context(summary)

    async def test_crash_during_research_does_not_break_the_council(self, monkeypatch):
        monkeypatch.setattr(research, "plan_research", AsyncMock(return_value=["q"]))
        monkeypatch.setattr(research, "find", AsyncMock(side_effect=ValueError("boom")))
        summary = await run_research("q")
        assert summary.status == "unavailable"

    def test_no_context_without_research(self):
        assert build_research_context(None) is None
        assert build_research_context(ResearchSummary(status="ok", searched_on="2026-09-14", brief=None)).startswith(
            "LIVE WEB RESEARCH: a web search was attempted"
        )


def test_every_model_call_is_told_the_date(monkeypatch):
    from datetime import UTC, datetime

    note = current_date_note(datetime(2026, 9, 14, tzinfo=UTC))
    assert note.startswith("Today's date is Monday, 14 September 2026 (UTC).")
    assert "may be out of date" in note


async def test_call_text_includes_the_date_in_the_system_prompt():
    from app.config import ModelConfig
    from app.council import _call_text

    create = AsyncMock(return_value=MagicMock(
        choices=[MagicMock(message=MagicMock(content="ok"), finish_reason="stop")], usage=MagicMock(total_tokens=5),
    ))
    client = MagicMock()
    client.chat.completions.create = create
    with patch("app.council.get_client", return_value=client):
        await _call_text("t", ModelConfig(provider="groq", model="m", role_name="R", system_prompt="Be brief."), "hi", max_tokens=50)
    system = create.await_args.kwargs["messages"][0]["content"]
    assert system.startswith("Be brief.\n\nToday's date is ")
