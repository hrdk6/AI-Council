// The Chairman's directive: recommendation, reasoning, plan, guardrails, and outcome feedback.

import { saveFeedback } from "./api.js";
import { briefMarkdown, parseDirective } from "./directive.js";
import { h, inlineNodes, percent, prefersReducedMotion, renderMarkdown } from "./dom.js";
import { parseMarkdown, plainText } from "./markdown.js";

function section(result, heading) {
  return parseDirective(result.final_answer).find((item) => item.heading === heading)?.content ?? null;
}

function summarySentence(result) {
  const size = result.council_composition?.length || result.round1?.length || 0;
  const parts = [];
  if (size) parts.push(`${size} ${size === 1 ? "member" : "members"} deliberated`);
  if (result.round2?.length) parts.push("with cross-examination");
  let sentence = parts.join(" ");
  const figures = [];
  if (result.agreement_score !== null && result.agreement_score !== undefined) {
    figures.push(`their recommendations were ${percent(result.agreement_score)} aligned`);
  }
  if (result.confidence_score !== null && result.confidence_score !== undefined) {
    figures.push(`average confidence ${percent(result.confidence_score)}`);
  }
  if (figures.length) sentence += `${sentence ? "; " : ""}${figures.join(", ")}`;
  if (result.total_latency_s) sentence += ` in ${Math.round(result.total_latency_s)} seconds`;
  if (result.cached) sentence += ". This question was answered recently, so the earlier deliberation is shown";
  return sentence ? `${sentence.charAt(0).toUpperCase()}${sentence.slice(1)}.` : "";
}

function planSteps(content) {
  const blocks = parseMarkdown(content);
  const list = blocks.find((block) => block.type === "ol" || block.type === "ul");
  if (!list || blocks.length > 2) return h("div", { class: "prose" }, renderMarkdown(content));
  const intro = blocks.filter((block) => block !== list && block.type === "p");
  return h("div", {},
    intro.length ? h("div", { class: "prose" }, intro.map((block) => h("p", {}, inlineNodes(block.children)))) : null,
    h("ol", { class: "plan-steps" }, list.items.map((item) => h("li", {}, h("div", { class: "prose" }, inlineNodes(item))))));
}

/** Download the decision brief as a markdown file. */
export function downloadBrief(result) {
  const safeName = (result.question || "decision").toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 50).replace(/-$/, "");
  const url = URL.createObjectURL(new Blob([briefMarkdown(result)], { type: "text/markdown;charset=utf-8" }));
  const link = h("a", { href: url, download: `council-${safeName || "decision"}.md` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** The recommendation as a single plain-text line, for bubbles and summaries. */
export function recommendationLine(result, maxLength = 180) {
  const text = plainText(section(result, "Recommendation") ?? result.final_answer ?? "").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1).trimEnd()}…` : text;
}

function feedbackControls(result, record) {
  let rating = record?.rating ?? null;
  const status = h("span", { class: "feedback-status", role: "status" });
  const note = h("textarea", {
    class: "feedback-note", rows: 2, maxlength: 2000,
    placeholder: "What happened after you acted on it? (optional)", "aria-label": "Outcome note",
  });
  note.value = record?.outcome_note ?? "";
  note.hidden = rating === null;
  const save = h("button", { type: "button", class: "secondary-button", text: "Save outcome", hidden: rating === null });

  const buttons = [1, 2, 3, 4, 5].map((value) => h("button", {
    type: "button",
    text: String(value),
    "aria-pressed": String(value === rating),
    "aria-label": `${value} out of 5`,
    onclick: () => {
      rating = value;
      buttons.forEach((button, index) => button.setAttribute("aria-pressed", String(index + 1 === value)));
      note.hidden = false;
      save.hidden = false;
      status.textContent = "";
    },
  }));

  save.addEventListener("click", async () => {
    save.disabled = true;
    status.textContent = "";
    try {
      await saveFeedback(result.request_id, rating, note.value.trim());
      status.textContent = "Outcome saved";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      save.disabled = false;
    }
  });

  return h("div", { class: "feedback" },
    h("span", { class: "feedback-label", id: "rating-label", text: "How did it turn out?" }),
    h("div", { class: "rating", role: "group", "aria-labelledby": "rating-label" }, buttons),
    save, status, note);
}

export function renderVerdict(container, result, { animate = true, record = null } = {}) {
  const recommendation = section(result, "Recommendation");
  const why = section(result, "Why this wins");
  const plan = section(result, "Execution plan");
  const guardrails = section(result, "Guardrails and reversal triggers");
  const confidence = section(result, "Confidence and key uncertainty");

  const failed = [...(result.round1 ?? []), ...(result.round2 ?? [])].filter((member) => !member.success);
  const notice = result.degraded
    ? h("p", { class: "notice", role: "note" },
      failed.length
        ? `Part of the council couldn’t take part (${[...new Set(failed.map((m) => m.role_name))].join(", ")}). Weigh this directive with extra care, or convene again.`
        : "The Chairman couldn’t complete the directive. Convene the council again in a moment.")
    : null;

  const copyButton = h("button", { type: "button", class: "secondary-button", text: "Copy brief" });
  copyButton.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(briefMarkdown(result));
      copyButton.textContent = "Copied";
    } catch {
      copyButton.textContent = "Couldn’t copy";
    }
    setTimeout(() => { copyButton.textContent = "Copy brief"; }, 1800);
  });

  const body = h("div", { class: "directive-body" },
    why && h("section", { class: "directive-section is-wide" }, h("h3", { text: "Why this wins" }), h("div", { class: "prose" }, renderMarkdown(why))),
    plan && h("section", { class: "directive-section is-wide" }, h("h3", { text: "Execution plan" }), planSteps(plan)),
    guardrails && h("section", { class: "directive-section" }, h("h3", { text: "Guardrails and reversal triggers" }), h("div", { class: "prose" }, renderMarkdown(guardrails))),
    confidence && h("section", { class: "directive-section" }, h("h3", { text: "Confidence and key uncertainty" }), h("div", { class: "prose" }, renderMarkdown(confidence))),
  );

  const evidence = result.attachments?.length
    ? h("div", { class: "evidence-used" },
      h("h3", { text: "Evidence the council read" }),
      h("ul", {}, result.attachments.map((file) => h("li", {
        text: file.method === "unreadable" ? `${file.filename} (couldn’t be read)` : file.filename,
      }))))
    : null;

  const actions = h("div", { class: "directive-actions" },
    copyButton,
    result.request_id ? feedbackControls(result, record) : null);

  container.replaceChildren(...[
    h("h2", { class: "directive-kicker", id: "directive-title", text: "The council recommends" }),
    h("div", { class: "directive-recommendation" }, renderMarkdown(recommendation ?? result.final_answer ?? "")),
    h("p", { class: "directive-summary", text: summarySentence(result) }),
    notice,
    body,
    evidence,
    actions,
  ].filter(Boolean));
  container.hidden = false;
  container.classList.toggle("is-revealing", animate && !prefersReducedMotion());
}
