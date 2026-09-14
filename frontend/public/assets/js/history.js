// Past decisions drawer.

import { fetchHistory } from "./api.js";
import { h } from "./dom.js";

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

export class HistoryDrawer {
  constructor({ dialog, list, onSelect, onAuthError }) {
    this.dialog = dialog;
    this.list = list;
    this.onSelect = onSelect;
    this.onAuthError = onAuthError;
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close(); // backdrop click
    });
  }

  async open() {
    this.dialog.showModal();
    this.list.replaceChildren(h("li", { class: "history-empty", text: "Loading past decisions…" }));
    try {
      const records = await fetchHistory(40);
      if (!records.length) {
        this.list.replaceChildren(h("li", { class: "history-empty", text: "No decisions yet. Your first one will appear here." }));
        return;
      }
      this.list.replaceChildren(...records.map((record) => this.item(record)));
      this.list.querySelector("button")?.focus();
    } catch (error) {
      if (error.status === 401) {
        this.dialog.close();
        this.onAuthError?.();
        return;
      }
      this.list.replaceChildren(h("li", { class: "history-empty", text: error.message }));
    }
  }

  item(record) {
    const created = new Date(record.created_at);
    const meta = [Number.isNaN(created.getTime()) ? "" : dateFormat.format(created)];
    if (record.rating) meta.push(`rated ${record.rating} of 5`);
    if (record.result?.attachments?.length) meta.push(`${record.result.attachments.length} evidence files`);
    return h("li", {},
      h("button", {
        type: "button",
        class: "history-item",
        onclick: () => {
          this.dialog.close();
          this.onSelect(record);
        },
      },
      h("span", { class: "history-question", text: record.question }),
      h("span", { class: "history-meta", text: meta.filter(Boolean).join(", ") })));
  }
}
