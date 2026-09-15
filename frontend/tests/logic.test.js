import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { friction, mostChallenged } from "../public/assets/js/chamber.js";
import { briefMarkdown, parseDirective, webSources } from "../public/assets/js/directive.js";
import { parseInline, parseMarkdown, plainText } from "../public/assets/js/markdown.js";
import { createSSEParser } from "../public/assets/js/sse.js";

describe("createSSEParser", () => {
  const collect = () => {
    const events = [];
    return { events, parser: createSSEParser((name, data) => events.push([name, data])) };
  };

  it("parses events split across arbitrary chunks and ignores comments", () => {
    const { events, parser } = collect();
    const body = ': stream-open\n\nevent: charter_ready\ndata: {"council": ["risk"]}\n\n: keep-alive\n\nevent: complete\ndata: {"final_answer": "Go"}\n\n';
    for (let i = 0; i < body.length; i += 7) parser.push(body.slice(i, i + 7));
    parser.end();
    assert.deepEqual(events, [
      ["charter_ready", { council: ["risk"] }],
      ["complete", { final_answer: "Go" }],
    ]);
  });

  it("handles CRLF line endings and a final event without a blank line", () => {
    const { events, parser } = collect();
    parser.push('event: error\r\ndata: {"detail": "Nope"}');
    parser.end();
    assert.deepEqual(events, [["error", { detail: "Nope" }]]);
  });

  it("joins multi-line data and falls back to raw strings", () => {
    const { events, parser } = collect();
    parser.push("data: line one\ndata: line two\n\n");
    assert.deepEqual(events, [["message", "line one\nline two"]]);
  });
});

describe("chamber telemetry", () => {
  it("grades friction from the agreement score", () => {
    assert.deepEqual(friction(0.82), ["Low", "low"]);
    assert.deepEqual(friction(0.7), ["Low", "low"]);
    assert.deepEqual(friction(0.5), ["Moderate", "moderate"]);
    assert.deepEqual(friction(0.41), ["High", "high"]);
  });

  it("finds the most challenged member, preferring the first on a tie", () => {
    assert.equal(mostChallenged([]), null);
    assert.equal(mostChallenged([{ from: "risk", to: "operator" }, { from: "analyst", to: "risk" }]), "operator");
    assert.equal(mostChallenged([
      { from: "risk", to: "operator" }, { from: "operator", to: "analyst" }, { from: "researcher", to: "analyst" },
    ]), "analyst");
  });
});

describe("parseMarkdown", () => {
  it("parses paragraphs, lists, and headings", () => {
    const blocks = parseMarkdown("## Plan\nFirst line\ncontinues\n\n1. Draft\n2. Review\n\n- risk a\n- risk b");
    assert.deepEqual(blocks.map((b) => b.type), ["h", "p", "ol", "ul"]);
    assert.equal(blocks[1].children[0].text, "First line continues");
    assert.equal(blocks[2].items.length, 2);
    assert.equal(blocks[2].start, 1);
  });

  it("parses inline emphasis and code without treating HTML specially", () => {
    const nodes = parseInline("Use **bold** and *em* with `<script>` here");
    assert.deepEqual(nodes.map((n) => n.type), ["text", "strong", "text", "em", "text", "code", "text"]);
    assert.equal(nodes[5].text, "<script>");
  });

  it("parses pipe tables", () => {
    const [table] = parseMarkdown("| Option | Cost |\n|---|---|\n| A | 10 |\n| B | 20 |");
    assert.equal(table.type, "table");
    assert.equal(table.rows.length, 2);
    assert.equal(table.header[1][0].text, "Cost");
  });

  it("keeps fenced code verbatim", () => {
    const [block] = parseMarkdown("```\n**not bold**\n```");
    assert.deepEqual(block, { type: "pre", text: "**not bold**" });
  });

  it("produces plain text for previews", () => {
    assert.equal(plainText("**Ship** the pilot\n\n- fast"), "Ship the pilot fast");
  });
});

describe("parseDirective", () => {
  it("splits the directive into known sections, tolerating markdown headings", () => {
    const sections = parseDirective("Recommendation\nPilot first.\n\n**Why this wins:**\nLower risk.\n\n## Execution plan\n1. Scope");
    assert.deepEqual(sections.map((s) => s.heading), ["Recommendation", "Why this wins", "Execution plan"]);
    assert.equal(sections[1].content, "Lower risk.");
  });

  it("keeps preamble text in the first section", () => {
    const [first] = parseDirective("After review:\nRecommendation\nPilot first.");
    assert.match(first.content, /^After review:/);
  });

  it("falls back to a single recommendation when no headings are present", () => {
    assert.deepEqual(parseDirective("Just do it."), [{ heading: "Recommendation", content: "Just do it." }]);
    assert.equal(parseDirective("")[0].content, "No directive was returned.");
  });

  it("builds a markdown brief including evidence", () => {
    const brief = briefMarkdown({
      question: "Hire or buy ads?",
      final_answer: "Recommendation\nHire.",
      attachments: [{ filename: "budget.pdf" }],
    });
    assert.match(brief, /^# Hire or buy ads\?/);
    assert.match(brief, /## Recommendation\n\nHire\./);
    assert.match(brief, /- budget\.pdf/);
  });

  it("lists web sources with their citation numbers and drops unsafe links", () => {
    const result = {
      question: "Latest model?",
      final_answer: "Recommendation\nUse it [2].",
      research: {
        status: "ok",
        searched_on: "2026-09-14",
        sources: [
          { title: "Bad", url: "javascript:alert(1)" },
          { title: "Launch [post]", url: "https://example.com/launch", published: "2026-09-03" },
        ],
      },
    };
    assert.deepEqual(webSources(result).map((s) => [s.number, s.url]), [[2, "https://example.com/launch"]]);
    const brief = briefMarkdown(result);
    assert.match(brief, /## Web sources \(checked 2026-09-14\)/);
    assert.match(brief, /2\. \[Launch post\]\(https:\/\/example\.com\/launch\), published 2026-09-03/);
    assert.doesNotMatch(brief, /javascript:/);
  });

  it("shows no web sources when research was unavailable", () => {
    assert.deepEqual(webSources({ research: { status: "unavailable", sources: [{ title: "x", url: "https://x.com" }] } }), []);
    assert.deepEqual(webSources({}), []);
  });
});
