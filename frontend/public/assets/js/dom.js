// DOM helpers. Everything user- or model-supplied goes in through textContent, never innerHTML.

import { parseMarkdown } from "./markdown.js";

export function h(tag, props = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") element.className = value;
    else if (key === "dataset") Object.assign(element.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") element.addEventListener(key.slice(2), value);
    else if (key === "text") element.textContent = value;
    else if (value === true) element.setAttribute(key, "");
    else element.setAttribute(key, String(value));
  }
  append(element, children);
  return element;
}

export function append(parent, children) {
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

export function svg(tag, attributes = {}) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  return element;
}

export function inlineNodes(nodes) {
  return nodes.map((node) => {
    if (node.type === "text") return document.createTextNode(node.text);
    if (node.type === "code") return h("code", { text: node.text });
    return h(node.type, {}, inlineNodes(node.children));
  });
}

export function renderMarkdown(source) {
  const fragment = document.createDocumentFragment();
  for (const block of parseMarkdown(source)) {
    switch (block.type) {
      case "p":
        fragment.append(h("p", {}, inlineNodes(block.children)));
        break;
      case "h":
        fragment.append(h("p", { class: "md-heading" }, inlineNodes(block.children)));
        break;
      case "quote":
        fragment.append(h("blockquote", {}, inlineNodes(block.children)));
        break;
      case "pre":
        fragment.append(h("pre", {}, h("code", { text: block.text })));
        break;
      case "ul":
      case "ol":
        fragment.append(
          h(block.type, { start: block.type === "ol" && block.start !== 1 ? block.start : null },
            block.items.map((item) => h("li", {}, inlineNodes(item)))),
        );
        break;
      case "table":
        fragment.append(
          h("div", { class: "md-table" },
            h("table", {},
              h("thead", {}, h("tr", {}, block.header.map((cell) => h("th", {}, inlineNodes(cell))))),
              h("tbody", {}, block.rows.map((row) => h("tr", {}, row.map((cell) => h("td", {}, inlineNodes(cell)))))),
            )),
        );
        break;
      default:
        break;
    }
  }
  return fragment;
}

export function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1_048_576) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1_048_576).toFixed(1)} MB`;
}

export function percent(value) {
  return value === null || value === undefined ? null : `${Math.round(value * 100)}%`;
}
