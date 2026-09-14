// The debate transcript. Statements arrive from the server as each member finishes; this module
// plays them back one speaker at a time so the table, the arcs, and the text stay in step.

import { h, percent, prefersReducedMotion, renderMarkdown, wait } from "./dom.js";

const MONOGRAMS = { chairman: "C", operator: "O", analyst: "A", risk: "R", researcher: "E" };
const WORDS_PER_SECOND = 70;
const COLLAPSE_AFTER_WORDS = 90;

export class Transcript {
  constructor({ listEl, chamber, names, onPlaybackChange, onStatement }) {
    this.listEl = listEl;
    this.chamber = chamber;
    this.names = names; // key -> role name
    this.onPlaybackChange = onPlaybackChange;
    this.onStatement = onStatement; // called as each statement takes the floor
    this.queue = [];
    this.running = false;
    this.fast = false;
    this.idleWaiters = [];
    this.generation = 0;
  }

  clear() {
    this.generation += 1; // abandons any playback in progress
    this.queue = [];
    this.running = false;
    this.fast = false;
    this.listEl.replaceChildren();
    this.resolveIdle();
  }

  /** Finish the current and queued items immediately. */
  skip() {
    this.fast = true;
  }

  get busy() {
    return this.running || this.queue.length > 0;
  }

  whenIdle() {
    if (!this.busy) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  resolveIdle() {
    const waiters = this.idleWaiters;
    this.idleWaiters = [];
    waiters.forEach((resolve) => resolve());
  }

  /** Queue an arbitrary step (phase change, table status) to run in order with the statements. */
  enqueueAction(action) {
    this.queue.push({ type: "action", action });
    this.pump();
  }

  enqueueInterlude(text) {
    this.queue.push({ type: "interlude", text });
    this.pump();
  }

  enqueueStatement(member) {
    if (member.success && this.chamber.speaking !== member.key) {
      this.chamber.setLive(member.key, "ready", "Ready to speak");
    }
    this.queue.push({ type: "statement", member });
    this.pump();
  }

  async pump() {
    if (this.running) return;
    this.running = true;
    this.onPlaybackChange?.(true);
    const generation = this.generation;
    while (this.queue.length && generation === this.generation) {
      const item = this.queue.shift();
      if (item.type === "action") await item.action({ instant: this.instant() });
      else if (item.type === "interlude") this.listEl.append(h("li", { class: "interlude", text: item.text }));
      else await this.playStatement(item.member, generation);
    }
    if (generation !== this.generation) return;
    this.running = false;
    this.fast = false;
    this.onPlaybackChange?.(false);
    this.resolveIdle();
  }

  instant() {
    return this.fast || prefersReducedMotion() || document.hidden;
  }

  async playStatement(member, generation) {
    const { key } = member;
    const name = this.names[key] ?? member.role_name ?? "A member";
    const entry = h("li", {
      class: `statement${member.success ? "" : " is-failed"}`,
      dataset: { key, round: member.round },
      id: `statement-${key}-${member.round}`,
    });
    const avatar = h("span", { class: "statement-avatar", "aria-hidden": "true", text: MONOGRAMS[key] ?? name[0] });
    const body = h("div", { class: "statement-main" },
      h("div", { class: "statement-head" },
        h("span", { class: "statement-name", text: name }),
        h("span", { class: "statement-round", text: member.round === 2 ? "Cross-examination" : "Opening statement" }),
      ));
    entry.append(avatar, body);
    this.listEl.append(entry);

    if (!member.success) {
      body.append(h("p", { class: "statement-error", text: `Couldn’t take part: ${member.error ?? "the model was unavailable."}` }));
      this.chamber.setLive(key, "failed", "Unavailable");
      this.onStatement?.(member);
      return;
    }

    this.chamber.setSpeaking(key);
    this.chamber.setStatus(`${name} has the floor`);
    this.onStatement?.(member);

    for (const challenge of member.challenges ?? []) {
      const target = (this.names[challenge.member] ?? challenge.member).replace(/^The /, "the ");
      const box = h("div", { class: "challenge" },
        h("span", { class: "challenge-to", text: `Challenges ${target}` }),
        h("span", { class: "challenge-point" }));
      box.style.setProperty("--target", `var(--${challenge.member})`);
      body.append(box);
      await this.chamber.drawChallenge(key, challenge.member, { instant: this.instant() });
      await this.type(box.querySelector(".challenge-point"), document.createTextNode(challenge.point), generation);
    }

    if (member.recommendation) {
      const recommendation = h("p", { class: "statement-recommendation" });
      body.append(recommendation);
      await this.type(recommendation, document.createTextNode(member.recommendation), generation);
    }

    const prose = h("div", { class: "statement-body prose" });
    body.append(prose);
    await this.type(prose, renderMarkdown(member.content ?? ""), generation);

    const words = (member.content ?? "").split(/\s+/).length;
    if (words > COLLAPSE_AFTER_WORDS) {
      entry.classList.add("is-collapsed");
      const toggle = h("button", {
        type: "button", class: "statement-more", text: "Read the full statement", "aria-expanded": "false",
        onclick: () => {
          const expanded = entry.classList.toggle("is-collapsed") === false;
          toggle.textContent = expanded ? "Show less" : "Read the full statement";
          toggle.setAttribute("aria-expanded", String(expanded));
        },
      });
      body.append(toggle);
    }

    const foot = h("div", { class: "statement-foot" });
    if (member.confidence !== null && member.confidence !== undefined) {
      const fill = h("span", { class: "confidence-fill" });
      fill.style.width = "0%";
      foot.append(h("span", { class: "confidence" },
        h("span", { text: `Confidence ${percent(member.confidence)}` }),
        h("span", { class: "confidence-bar", "aria-hidden": "true" }, fill)));
      requestAnimationFrame(() => { fill.style.width = percent(member.confidence); });
    }
    if (member.key_risk) {
      foot.append(h("span", { class: "statement-risk" }, h("strong", { text: "Key risk: " }), member.key_risk));
    }
    if (member.switched_from_model) {
      foot.append(h("span", { text: `Answered by ${member.model} after ${member.switched_from_model} was busy` }));
    }
    body.append(foot);

    if (generation !== this.generation) return;
    this.chamber.setSpeaking(null);
    this.chamber.setLive(key, "spoke", member.round === 2 ? "Challenged" : "Spoke");
    this.chamber.settleLines();
    if (!this.instant()) await wait(260);
  }

  /** Reveal a fragment word by word, unhiding each element as the text reaches it. */
  async type(container, content, generation) {
    const fragment = content instanceof DocumentFragment ? content : (() => {
      const wrapper = document.createDocumentFragment();
      wrapper.append(content);
      return wrapper;
    })();

    if (this.instant()) {
      container.append(fragment);
      return;
    }

    const elements = [...fragment.querySelectorAll("*")];
    const walker = document.createTreeWalker(fragment, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    const texts = nodes.map((node) => node.data);
    nodes.forEach((node) => { node.data = ""; });
    elements.forEach((element) => { element.hidden = true; });
    container.append(fragment);
    const typingHost = container.closest(".statement-recommendation, .statement-main") ?? container;
    typingHost.classList.add("is-typing");

    const finish = () => {
      nodes.forEach((node, index) => { node.data = texts[index]; });
      elements.forEach((element) => { element.hidden = false; });
      typingHost.classList.remove("is-typing");
    };

    for (let index = 0; index < nodes.length; index += 1) {
      if (generation !== this.generation) return;
      const node = nodes[index];
      for (let parent = node.parentElement; parent && parent !== container; parent = parent.parentElement) {
        parent.hidden = false;
      }
      const words = texts[index].split(/(\s+)/);
      let shown = 0;
      let last = performance.now();
      while (shown < words.length) {
        if (this.instant() || generation !== this.generation) {
          finish();
          return;
        }
        await new Promise((resolve) => requestAnimationFrame(resolve));
        const now = performance.now();
        // Speed up when other speakers are waiting, so playback never falls far behind the council.
        const rate = WORDS_PER_SECOND * (1 + this.queue.filter((item) => item.type === "statement").length);
        const step = Math.max(1, Math.round(((now - last) / 1000) * rate * 2)); // words + separators
        last = now;
        shown = Math.min(words.length, shown + step);
        node.data = words.slice(0, shown).join("");
      }
    }
    finish();
  }
}
