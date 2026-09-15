// Parse the Chairman's directive into its fixed sections, and build the exportable brief.

export const DIRECTIVE_HEADINGS = [
  "Recommendation",
  "Why this wins",
  "Execution plan",
  "Guardrails and reversal triggers",
  "Confidence and key uncertainty",
];

const HEADING_PATTERN = new RegExp(
  `^(?:#{1,6}\\s*)?(?:\\*\\*)?(${DIRECTIVE_HEADINGS.join("|")})\\s*:?\\s*(?:\\*\\*)?\\s*:?\\s*$`,
  "i",
);

export function parseDirective(text) {
  const sections = [];
  let current = null;
  let preamble = [];

  for (const line of String(text ?? "").replace(/\r/g, "").split("\n")) {
    const match = line.trim().match(HEADING_PATTERN);
    if (match) {
      const heading = DIRECTIVE_HEADINGS.find((name) => name.toLowerCase() === match[1].toLowerCase());
      current = { heading, lines: [] };
      sections.push(current);
    } else if (current) {
      current.lines.push(line);
    } else {
      preamble.push(line);
    }
  }

  const preambleText = preamble.join("\n").trim();
  if (!sections.length) {
    return [{ heading: "Recommendation", content: preambleText || "No directive was returned." }];
  }
  if (preambleText) sections[0].lines.unshift(preambleText, "");
  return sections.map(({ heading, lines }) => ({
    heading,
    content: lines.join("\n").trim() || "No details returned.",
  }));
}

/** Web sources from a result's research that are safe to link to (http and https only), numbered as the council cited them. */
export function webSources(result) {
  const sources = result?.research?.status === "ok" ? result.research.sources ?? [] : [];
  return sources
    .map((source, index) => ({ ...source, number: index + 1 }))
    .filter((source) => /^https?:\/\//i.test(String(source.url ?? "")));
}

export function briefMarkdown(result) {
  const lines = [`# ${result.question || "Council decision"}`, ""];
  for (const { heading, content } of parseDirective(result.final_answer)) {
    lines.push(`## ${heading}`, "", content, "");
  }
  const sources = webSources(result);
  if (sources.length) {
    lines.push(`## Web sources (checked ${result.research.searched_on})`, "");
    for (const source of sources) {
      lines.push(`${source.number}. [${source.title.replace(/[[\]]/g, "")}](${source.url})${source.published ? `, published ${source.published}` : ""}`);
    }
    lines.push("");
  }
  if (result.attachments?.length) {
    lines.push("## Evidence reviewed", "");
    for (const file of result.attachments) lines.push(`- ${file.filename}`);
    lines.push("");
  }
  if (result.decision_charter) lines.push("## Decision charter", "", result.decision_charter, "");
  return `${lines.join("\n").trim()}\n`;
}
