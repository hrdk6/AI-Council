// Evidence tray: choose, drop, or paste PDFs and images; show what the council made of each file.

import { formatBytes, h } from "./dom.js";

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"];

function kindOf(file) {
  if (file.type === "application/pdf" || /\.pdf$/i.test(file.name)) return "pdf";
  if (IMAGE_TYPES.includes(file.type) || /\.(png|jpe?g|webp|gif)$/i.test(file.name)) return "image";
  return null;
}

export class EvidenceTray {
  constructor({ dropzone, input, browseButton, list, pasteTarget, onError }) {
    this.dropzone = dropzone;
    this.input = input;
    this.list = list;
    this.onError = onError;
    this.items = [];
    this.locked = false;
    this.limits = { max_files: 5, max_pdf_mb: 15, max_image_mb: 8 };

    browseButton.addEventListener("click", () => this.input.click());
    dropzone.addEventListener("click", (event) => {
      if (!this.locked && !event.target.closest("button, li, input")) this.input.click();
    });
    input.addEventListener("change", () => {
      this.add(input.files);
      input.value = "";
    });

    let depth = 0;
    dropzone.addEventListener("dragenter", (event) => {
      event.preventDefault();
      depth += 1;
      dropzone.classList.add("is-dragging");
    });
    dropzone.addEventListener("dragover", (event) => event.preventDefault());
    dropzone.addEventListener("dragleave", () => {
      depth = Math.max(0, depth - 1);
      if (!depth) dropzone.classList.remove("is-dragging");
    });
    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      depth = 0;
      dropzone.classList.remove("is-dragging");
      this.add(event.dataTransfer.files);
    });

    pasteTarget.addEventListener("paste", (event) => {
      const files = [...(event.clipboardData?.files ?? [])];
      if (files.length) {
        event.preventDefault();
        this.add(files);
      }
    });
  }

  setLimits(limits) {
    this.limits = { ...this.limits, ...limits };
    this.dropzone.hidden = !this.limits.max_files;
  }

  get count() {
    return this.items.length;
  }

  get files() {
    return this.items.map((item) => item.file);
  }

  add(fileList) {
    if (this.locked) return;
    const problems = [];
    for (const file of fileList) {
      const kind = kindOf(file);
      if (!kind) {
        problems.push(`${file.name} isn’t a PDF or image.`);
        continue;
      }
      const limitMb = kind === "pdf" ? this.limits.max_pdf_mb : this.limits.max_image_mb;
      if (file.size > limitMb * 1_048_576) {
        problems.push(`${file.name} is ${formatBytes(file.size)}. ${kind === "pdf" ? "PDFs" : "Images"} can be up to ${limitMb} MB.`);
        continue;
      }
      if (this.items.some((item) => item.file.name === file.name && item.file.size === file.size)) continue;
      if (this.items.length >= this.limits.max_files) {
        problems.push(`You can attach up to ${this.limits.max_files} files.`);
        break;
      }
      this.items.push({
        id: crypto.randomUUID(),
        file,
        kind,
        preview: kind === "image" ? URL.createObjectURL(file) : null,
        state: "ready",
        meta: formatBytes(file.size),
      });
    }
    this.onError?.(problems.join(" "));
    this.render();
  }

  remove(id) {
    const index = this.items.findIndex((item) => item.id === id);
    if (index === -1) return;
    const [item] = this.items.splice(index, 1);
    if (item.preview) URL.revokeObjectURL(item.preview);
    this.render();
  }

  clear() {
    this.items.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
    this.items = [];
    this.render();
  }

  lock(locked) {
    this.locked = locked;
    this.input.disabled = locked;
    this.render();
  }

  resetStates() {
    for (const item of this.items) {
      item.state = "ready";
      item.meta = formatBytes(item.file.size);
    }
    this.render();
  }

  markReading(index) {
    const item = this.items[index];
    if (!item) return;
    item.state = "reading";
    item.meta = item.kind === "pdf" ? "Reading the document…" : "Reading the image…";
    this.render();
  }

  markRead(index, summary) {
    const item = this.items[index];
    if (!item) return;
    if (summary.method === "unreadable") {
      item.state = "unreadable";
      item.meta = summary.note || "Couldn’t be read";
    } else {
      item.state = "read";
      const pages = summary.pages ? `${summary.pages} ${summary.pages === 1 ? "page" : "pages"}, ` : "";
      const how = summary.method === "vision" ? "read by the vision model" : "text extracted";
      item.meta = `${pages}${how}${summary.truncated ? ", shortened to fit" : ""}`;
    }
    this.render();
  }

  render() {
    this.list.replaceChildren(
      ...this.items.map((item) => {
        const thumb = item.preview
          ? h("img", { class: "evidence-thumb", src: item.preview, alt: "" })
          : h("span", { class: "evidence-thumb is-pdf", "aria-hidden": "true", text: "PDF" });
        return h("li", { class: `evidence-item is-${item.state}` },
          thumb,
          h("div", { class: "evidence-text" },
            h("span", { class: "evidence-name", text: item.file.name, title: item.file.name }),
            h("span", { class: "evidence-meta", text: item.meta })),
          h("button", {
            type: "button",
            class: "evidence-remove",
            "aria-label": `Remove ${item.file.name}`,
            disabled: this.locked,
            onclick: () => this.remove(item.id),
          }, removeIcon()));
      }),
    );
  }
}

function removeIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M6 6l12 12M18 6L6 18");
  icon.append(path);
  return icon;
}
