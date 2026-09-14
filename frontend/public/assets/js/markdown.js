// A small, safe markdown subset for model output.
// parseMarkdown() returns plain data; dom.js turns it into nodes with textContent only,
// so model output can never inject HTML.

const ORDERED = /^\s*(\d+)[.)]\s+(.*)$/;
const UNORDERED = /^\s*[-*•]\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*)$/;
const TABLE_DIVIDER = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

export function parseInline(text) {
  const nodes = [];
  // Order matters: code first so its contents are not treated as emphasis.
  const pattern = /(`[^`]+`)|(\*\*[^*]+?\*\*|__[^_]+?__)|(\*[^*\s][^*]*?\*|_[^_\s][^_]*?_)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) nodes.push({ type: "text", text: text.slice(last, match.index) });
    const token = match[0];
    if (match[1]) nodes.push({ type: "code", text: token.slice(1, -1) });
    else if (match[2]) nodes.push({ type: "strong", children: parseInline(token.slice(2, -2)) });
    else nodes.push({ type: "em", children: parseInline(token.slice(1, -1)) });
    last = match.index + token.length;
  }
  if (last < text.length) nodes.push({ type: "text", text: text.slice(last) });
  return nodes;
}

function splitRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => parseInline(cell.trim()));
}

export function parseMarkdown(source) {
  const lines = String(source ?? "").replace(/\r/g, "").split("\n");
  const blocks = [];
  let paragraph = [];
  let list = null;

  const flushParagraph = () => {
    if (paragraph.length) blocks.push({ type: "p", children: parseInline(paragraph.join(" ")) });
    paragraph = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      flushParagraph();
      flushList();
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "pre", text: code.join("\n") });
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      flushList();
      continue;
    }

    if (trimmed.includes("|") && index + 1 < lines.length && TABLE_DIVIDER.test(lines[index + 1])) {
      flushParagraph();
      flushList();
      const header = splitRow(trimmed);
      const rows = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(splitRow(lines[index]));
        index += 1;
      }
      index -= 1;
      blocks.push({ type: "table", header, rows });
      continue;
    }

    const heading = trimmed.match(HEADING);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ type: "h", level: heading[1].length, children: parseInline(heading[2]) });
      continue;
    }

    const ordered = line.match(ORDERED);
    const unordered = ordered ? null : line.match(UNORDERED);
    if (ordered || unordered) {
      flushParagraph();
      const type = ordered ? "ol" : "ul";
      if (!list || list.type !== type) {
        flushList();
        list = { type, items: [] };
        if (ordered) list.start = Number(ordered[1]);
      }
      list.items.push(parseInline(ordered ? ordered[2] : unordered[1]));
      continue;
    }

    if (trimmed.startsWith(">")) {
      flushParagraph();
      flushList();
      blocks.push({ type: "quote", children: parseInline(trimmed.replace(/^>\s?/, "")) });
      continue;
    }

    if (list && /^\s{2,}\S/.test(line)) {
      // Continuation of the previous list item.
      const last = list.items[list.items.length - 1];
      last.push({ type: "text", text: " " }, ...parseInline(trimmed));
      continue;
    }

    flushList();
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  return blocks;
}

export function plainText(source) {
  const walk = (nodes) => nodes.map((node) => (node.children ? walk(node.children) : node.text)).join("");
  return parseMarkdown(source)
    .map((block) => {
      if (block.type === "pre") return block.text;
      if (block.type === "ul" || block.type === "ol") return block.items.map(walk).join(" ");
      if (block.type === "table") return [block.header, ...block.rows].map((row) => row.map(walk).join(" ")).join(" ");
      return walk(block.children);
    })
    .join(" ");
}
