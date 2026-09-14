// The council chamber: seats with speech bubbles, live seat states, the table HUD,
// and challenge beams drawn between the seats' real on-screen positions.

import { h, prefersReducedMotion, svg, wait } from "./dom.js";

const MONOGRAMS = { chairman: "C", operator: "O", analyst: "A", risk: "R", researcher: "E" };
const SHORT_NAMES = { chairman: "Chairman", operator: "Operator", analyst: "Analyst", risk: "Risk Officer", researcher: "Evidence" };
const SVG_NS = "http://www.w3.org/2000/svg";

export class Chamber {
  constructor({ chamberEl, seatsEl, linesEl, statusEl, detailEl, pillEl, pillTextEl, onSeatSelect, onStateChange }) {
    this.chamberEl = chamberEl;
    this.seatsEl = seatsEl;
    this.linesEl = linesEl;
    this.statusEl = statusEl;
    this.detailEl = detailEl;
    this.pillEl = pillEl;
    this.pillTextEl = pillTextEl;
    this.onSeatSelect = onSeatSelect;
    this.onStateChange = onStateChange;
    this.seats = new Map();
    this.live = new Map(); // key -> { state, label }
    this.speaking = null;
    this.seated = new Set();
    this.challenges = []; // { from, to } in the order they were drawn
    this.hud = { status: "", detail: "", consensus: null };
    this.lineId = 0;

    new ResizeObserver(() => this.redrawLines()).observe(chamberEl);
  }

  render(members, chairman) {
    this.seatsEl.replaceChildren();
    this.seats.clear();
    for (const { key, role_name: roleName } of [chairman, ...members]) {
      const bubble = h("div", { class: "bubble", hidden: true },
        h("span", { class: "bubble-label" }),
        h("p", { class: "bubble-text" }));
      const seat = h("div", { class: "seat", dataset: { key } },
        bubble,
        h("button", {
          type: "button", class: "seat-body", "aria-label": `${roleName}: jump to their latest statement`,
          onclick: () => this.onSeatSelect?.(key),
        },
        h("span", { class: "seat-avatar-wrap" },
          h("span", { class: "seat-halo", "aria-hidden": "true" }),
          h("span", { class: "seat-avatar", "aria-hidden": "true", text: MONOGRAMS[key] ?? roleName[0] })),
        h("span", { class: "seat-name", text: SHORT_NAMES[key] ?? roleName.replace(/^The /, "") })));
      this.seatsEl.append(seat);
      this.seats.set(key, seat);
    }
    this.reset();
  }

  reset({ status = "The council is waiting for a question.", detail = "" } = {}) {
    this.live.clear();
    this.speaking = null;
    this.seated = new Set(this.seats.keys());
    this.challenges = [];
    this.hud.consensus = null;
    for (const [key, seat] of this.seats) {
      seat.classList.remove("is-absent", "is-thinking", "is-speaking", "is-failed");
      this.clearBubble(key);
      this.onStateChange?.(key, { state: "idle", label: "" });
    }
    this.clearLines();
    this.setPill(null);
    this.setActive(false);
    this.setStatus(status, detail);
  }

  /* ── Table HUD ── */

  setActive(active) {
    this.chamberEl.classList.toggle("is-live", active);
  }

  setPill(text) {
    this.pillEl.hidden = !text;
    this.pillTextEl.textContent = text ?? "";
  }

  setConsensus(score) {
    this.hud.consensus = score ?? null;
    this.renderHud();
  }

  setStatus(status, detail = "") {
    this.hud.status = status;
    this.hud.detail = detail;
    this.renderHud();
  }

  renderHud() {
    const { status, detail, consensus } = this.hud;
    if (consensus === null) {
      this.statusEl.textContent = status;
      this.detailEl.textContent = detail;
      return;
    }
    this.statusEl.replaceChildren("Consensus index: ", h("span", { class: "hud-figure", text: `${Math.round(consensus * 100)}%` }));
    this.detailEl.textContent = [status, detail].filter(Boolean).join(". ");
  }

  /* ── Seats ── */

  /** Seat only the experts the Decision Architect chose; the Chairman always presides. */
  seatCouncil(keys) {
    this.seated = new Set(["chairman", ...keys]);
    for (const [key, seat] of this.seats) {
      const present = this.seated.has(key);
      seat.classList.toggle("is-absent", !present);
      if (!present) {
        this.clearBubble(key);
        this.onStateChange?.(key, { state: "absent", label: "Not seated" });
      }
    }
  }

  isSeated(key) {
    return this.seated.has(key);
  }

  setBubble(key, label, text = "") {
    const bubble = this.seats.get(key)?.querySelector(".bubble");
    if (!bubble) return;
    bubble.querySelector(".bubble-label").textContent = label;
    const textEl = bubble.querySelector(".bubble-text");
    textEl.textContent = text;
    textEl.hidden = !text;
    bubble.hidden = false;
    // Replay the entrance animation for each new line of dialogue.
    bubble.style.animation = "none";
    void bubble.offsetWidth;
    bubble.style.animation = "";
  }

  clearBubble(key) {
    const bubble = this.seats.get(key)?.querySelector(".bubble");
    if (bubble) bubble.hidden = true;
  }

  bubbleText(key) {
    return this.seats.get(key)?.querySelector(".bubble-text")?.textContent ?? "";
  }

  /** Record what the backend says a member is doing. Speaking (driven by the transcript) takes priority. */
  setLive(key, state, label = "") {
    this.live.set(key, { state, label });
    if (this.speaking !== key) this.apply(key);
  }

  setSpeaking(key) {
    const previous = this.speaking;
    this.speaking = key;
    if (previous && previous !== key) this.apply(previous);
    if (key) this.apply(key);
  }

  apply(key) {
    const seat = this.seats.get(key);
    if (!seat || !this.seated.has(key)) return;
    seat.classList.remove("is-thinking", "is-speaking", "is-failed");
    if (this.speaking === key) {
      seat.classList.add("is-speaking");
      this.onStateChange?.(key, { state: "speaking", label: key === "chairman" ? "Delivering the directive" : "Has the floor" });
      return;
    }
    const { state = "idle", label = "" } = this.live.get(key) ?? {};
    if (state === "thinking") {
      seat.classList.add("is-thinking");
      const previous = this.bubbleText(key);
      this.setBubble(key, label, previous);
    }
    if (state === "failed") {
      seat.classList.add("is-failed");
      this.setBubble(key, "Unavailable", "");
    }
    this.onStateChange?.(key, { state, label });
  }

  /* ── Challenge beams ── */

  centreOf(key) {
    const avatar = this.seats.get(key)?.querySelector(".seat-avatar");
    if (!avatar) return null;
    const box = this.chamberEl.getBoundingClientRect();
    const rect = avatar.getBoundingClientRect();
    return { x: rect.left - box.left + rect.width / 2, y: rect.top - box.top + rect.height / 2, r: rect.width / 2 };
  }

  voiceOf(key) {
    return getComputedStyle(this.seats.get(key)).getPropertyValue("--voice").trim() || "#94a3b8";
  }

  clearLines() {
    this.linesEl.querySelectorAll(".debate-line").forEach((line) => line.remove());
    this.linesEl.querySelector("defs").replaceChildren();
  }

  settleLines() {
    this.linesEl.querySelectorAll(".debate-line.is-fresh").forEach((line) => {
      line.classList.remove("is-fresh");
      line.classList.add("is-settled");
    });
  }

  redrawLines() {
    const pairs = this.challenges;
    this.clearLines();
    for (const { from, to } of pairs) this.addLine(from, to, { settled: true });
  }

  addLine(from, to, { settled = false } = {}) {
    const start = this.centreOf(from);
    const end = this.centreOf(to);
    if (!start || !end) return null;
    const length = Math.hypot(end.x - start.x, end.y - start.y) || 1;
    const unit = { x: (end.x - start.x) / length, y: (end.y - start.y) / length };
    const a = { x: start.x + unit.x * (start.r + 10), y: start.y + unit.y * (start.r + 10) };
    const b = { x: end.x - unit.x * (end.r + 12), y: end.y - unit.y * (end.r + 12) };

    const id = `beam-${(this.lineId += 1)}`;
    const gradient = document.createElementNS(SVG_NS, "linearGradient");
    for (const [attribute, value] of Object.entries({ id, gradientUnits: "userSpaceOnUse", x1: a.x, y1: a.y, x2: b.x, y2: b.y })) {
      gradient.setAttribute(attribute, String(value));
    }
    gradient.append(
      svg("stop", { offset: "0%", "stop-color": this.voiceOf(from), "stop-opacity": "0.85" }),
      svg("stop", { offset: "100%", "stop-color": this.voiceOf(to), "stop-opacity": "0.85" }),
    );
    this.linesEl.querySelector("defs").append(gradient);

    const line = svg("line", {
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: `url(#${id})`,
      class: `debate-line ${settled ? "is-settled" : "is-fresh"}`,
    });
    this.linesEl.append(line);
    return { line, length: Math.hypot(b.x - a.x, b.y - a.y) };
  }

  /** Draw a beam from the challenger to the member being challenged. Resolves once drawn. */
  async drawChallenge(fromKey, toKey, { instant = false } = {}) {
    if (!this.seats.has(fromKey) || !this.seats.has(toKey) || fromKey === toKey) return;
    this.challenges.push({ from: fromKey, to: toKey });
    const drawn = this.addLine(fromKey, toKey);
    if (!drawn || instant || prefersReducedMotion()) return;

    const { line, length } = drawn;
    line.classList.add("is-drawing");
    const animation = line.animate(
      [{ strokeDasharray: `${length}`, strokeDashoffset: length }, { strokeDasharray: `${length}`, strokeDashoffset: 0 }],
      { duration: 750, easing: "cubic-bezier(0.22, 1, 0.36, 1)" },
    );
    await animation.finished.catch(() => {});
    line.classList.remove("is-drawing");
    await wait(120);
  }
}
