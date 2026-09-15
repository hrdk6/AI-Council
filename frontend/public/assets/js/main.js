import { ApiError, fetchConfig, fetchHistory, fetchTelemetry, getAccessKey, setAccessKey, streamDecision } from "./api.js";
import { Chamber } from "./chamber.js";
import { h, prefersReducedMotion, wait } from "./dom.js";
import { EvidenceTray } from "./evidence.js";
import { HistoryDrawer } from "./history.js";
import { Transcript } from "./transcript.js";
import { downloadBrief, recommendationLine, renderVerdict } from "./verdict.js";

const $ = (id) => document.getElementById(id);

const DEFAULT_CONFIG = {
  auth_required: false,
  members: [
    { key: "operator", role_name: "The Operator" },
    { key: "analyst", role_name: "The Decision Analyst" },
    { key: "risk", role_name: "The Risk Officer" },
    { key: "researcher", role_name: "The Evidence Reviewer" },
  ],
  chairman: { key: "chairman", role_name: "Chairman" },
  limits: { max_prompt_chars: 12000, max_files: 5, max_pdf_mb: 15, max_image_mb: 8 },
};

// What each seat is listening for, shown on the roster before anyone has spoken.
const ROLE_FOCUS = {
  chairman: "Weighs the debate and issues one directive, with guardrails and reversal triggers.",
  operator: "Tests whether the plan can actually be executed, and what the first steps are.",
  analyst: "Compares the options against the criteria that matter most to you.",
  risk: "Looks for irreversible downside and sets the conditions for stopping.",
  researcher: "Separates what is known from what is assumed, including in your evidence.",
};
const TAGS = { chairman: "CHR", operator: "OPR", analyst: "ANL", risk: "RSK", researcher: "EVD", web: "WEB" };
const STREAM_LENGTH = 4;

const PHASES = {
  evidence: { pill: "Reading evidence", stage: "Reading the evidence" },
  research: { pill: "Live web research", stage: "Checking current sources" },
  framing: { pill: "Framing", stage: "Framing the decision" },
  opening: { pill: "Round 1 · Opening statements", stage: "Round 1: opening statements", round: 1 },
  cross: { pill: "Round 2 · Cross-examination", stage: "Round 2: cross-examination", round: 2 },
  directive: { pill: "Chairman · Synthesis", stage: "The Chairman is drafting the directive" },
};

const state = {
  config: DEFAULT_CONFIG,
  running: false,
  controller: null,
  result: null,
  record: null,
  debate: true,
  research: true,
  phase: null,
  progress: { done: 0, total: 1, seats: 3, files: 0, research: 0 },
  stream: [],
  turn: 0,
  tokens: 0,
  startedAt: 0,
  clock: null,
  typicalRun: null,
};

const els = {
  form: $("decision-form"),
  question: $("question"),
  questionCard: $("question-card"),
  lockedHead: $("locked-head"),
  consensusNote: $("consensus-note"),
  tokensNote: $("tokens-note"),
  elapsed: $("progress-elapsed"),
  catchUp: $("catch-up-button"),
  statMembers: $("stat-members"),
  statTimeLabel: $("stat-time-label"),
  statTime: $("stat-time"),
  footerLatency: $("footer-latency"),
  footerModels: $("footer-models"),
  footerResearch: $("footer-research"),
  footerResearchSep: $("footer-research-sep"),
  charCount: $("char-count"),
  debate: $("debate-toggle"),
  research: $("research-toggle"),
  researchRow: $("research-row"),
  formError: $("form-error"),
  convene: $("convene-button"),
  progressCard: $("progress-card"),
  progressTitle: $("progress-title"),
  progressValue: $("progress-value"),
  progressBar: $("progress-bar"),
  progressFill: $("progress-fill"),
  progressStage: $("progress-stage"),
  halt: $("halt-button"),
  streamCard: $("stream-card"),
  streamList: $("stream-list"),
  streamMeta: $("stream-meta"),
  sessionStatus: $("session-status"),
  sessionText: $("session-status-text"),
  exportButton: $("export-button"),
  historyCount: $("history-count"),
  roster: $("roster"),
  directive: $("directive"),
  floor: $("floor"),
  skip: $("skip-button"),
  replay: $("replay-button"),
  announcer: $("announcer"),
  keyDialog: $("key-dialog"),
  keyForm: $("key-form"),
  keyInput: $("key-input"),
  keyRemember: $("key-remember"),
  lock: $("lock-button"),
};

function names() {
  const map = { chairman: state.config.chairman.role_name };
  for (const member of state.config.members) map[member.key] = member.role_name;
  return map;
}

function shortName(key) {
  return (names()[key] ?? key).replace(/^The /, "");
}

function shortModel(model) {
  return String(model ?? "").split("/").pop();
}

function announce(message) {
  els.announcer.textContent = message;
}

function showFormError(message) {
  els.formError.textContent = message || "";
  els.formError.hidden = !message;
}

/* ── Session status (top bar) ── */

function setSession(kind, parts) {
  els.sessionStatus.classList.toggle("is-live", kind === "live");
  els.sessionStatus.classList.toggle("is-done", kind === "done");
  els.sessionStatus.classList.toggle("is-error", kind === "error");
  const nodes = [];
  parts.filter(Boolean).forEach((part, index) => {
    if (index) nodes.push(h("span", { class: "status-sep", "aria-hidden": "true", text: " • " }));
    const { text, tone } = typeof part === "string" ? { text: part } : part;
    nodes.push(h("span", { class: tone ? `status-${tone}` : "", text }));
  });
  els.sessionText.replaceChildren(...nodes);
}

/* ── Roster ── */

function renderRoster() {
  const seats = [state.config.chairman, ...state.config.members];
  els.roster.replaceChildren(...seats.map(({ key, role_name: roleName }) => h("li", {
    class: "roster-card", dataset: { key }, id: `roster-${key}`,
  },
  h("div", { class: "roster-card-head" },
    h("span", { class: "roster-name" }, h("span", { class: "roster-dot", "aria-hidden": "true" }), roleName.replace(/^The /, "")),
    h("span", { class: "roster-badge", text: key === "chairman" ? "Presiding" : "Seated" })),
  h("p", { class: "roster-text", text: ROLE_FOCUS[key] ?? "" }))));
}

function setRosterText(key, text) {
  const node = $(`roster-${key}`)?.querySelector(".roster-text");
  if (node && text) node.textContent = text;
}

function onSeatState(key, { state: seatState, label }) {
  const card = $(`roster-${key}`);
  if (!card) return;
  const defaults = { idle: key === "chairman" ? "Presiding" : "Seated", absent: "Not seated" };
  card.classList.toggle("is-absent", seatState === "absent");
  card.classList.toggle("is-active", seatState === "thinking" || seatState === "speaking");
  card.classList.toggle("is-failed", seatState === "failed");
  let badge = label || defaults[seatState] || "Seated";
  if (seatState === "thinking") {
    badge = label.startsWith("Backup model") ? "Backup model" : key === "chairman" ? "Synthesizing" : "Thinking";
  }
  card.querySelector(".roster-badge").textContent = badge;
}

/* ── Live argument stream ── */

function pushStream(key, text) {
  if (!text) return;
  state.turn += 1;
  state.stream = [...state.stream, { key, text }].slice(-STREAM_LENGTH);
  els.streamList.replaceChildren(...state.stream.map((entry) => {
    const item = h("li", { class: "stream-item" },
      h("span", { class: "stream-tag", text: `[${TAGS[entry.key] ?? "???"}]` }),
      h("span", { text: entry.text }));
    item.style.setProperty("--voice", `var(--${entry.key})`);
    return item;
  }));
  els.streamCard.hidden = false;
}

function updateStreamMeta(round) {
  els.streamMeta.textContent = `Turn ${state.turn}${round ? `, round ${round}` : ""}`;
}

function clip(text, max = 150) {
  const clean = String(text ?? "").replace(/\s+/g, " ").trim();
  return clean.length > max ? `${clean.slice(0, max - 1).trimEnd()}…` : clean;
}

/** Keep the seat bubble, roster, and stream in step with the statement that has the floor. */
function onStatement(member) {
  const { key } = member;
  if (!member.success) {
    setRosterText(key, member.error ?? "Couldn’t take part in this round.");
    return;
  }
  const challenges = member.challenges ?? [];
  if (member.round === 2 && challenges.length) {
    const first = challenges[0];
    chamber.setBubble(key, `Challenges ${shortName(first.member)}`, clip(first.point, 120));
    for (const challenge of challenges) {
      pushStream(key, `→ ${TAGS[challenge.member] ?? challenge.member}: ${clip(challenge.point, 110)}`);
    }
  } else {
    chamber.setBubble(key, member.round === 2 ? "Revised position" : "Opening statement", clip(member.recommendation || member.content, 120));
    pushStream(key, clip(member.recommendation || member.content, 110));
  }
  setRosterText(key, clip(member.recommendation || member.content, 220));
  updateStreamMeta(member.round);
}

/* ── Progress ── */

function resetProgress(files, debate, research = false) {
  // Research counts as three steps (plan, search and read, brief) since it can take a while.
  state.progress = { done: 0, files, seats: 3, rounds: debate ? 2 : 1, research: research ? 3 : 0 };
  renderProgress();
}

function bumpProgress(steps = 1) {
  state.progress.done += steps;
  renderProgress();
}

function renderProgress() {
  const { done, files, seats, rounds, research } = state.progress;
  const total = files + research + 1 + seats * rounds + 1;
  const value = Math.min(100, Math.round((Math.min(done, total) / total) * 100));
  els.progressFill.style.width = `${value}%`;
  els.progressValue.textContent = `${value}%`;
  els.progressBar.setAttribute("aria-valuenow", String(value));
}

/* ── Run telemetry: elapsed time, tokens, and the stat tiles ── */

function formatSeconds(seconds) {
  const whole = Math.max(0, Math.round(seconds));
  return whole < 60 ? `${whole} sec` : `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

function setTokens(tokens) {
  state.tokens = tokens;
  els.tokensNote.hidden = !tokens;
  els.tokensNote.textContent = tokens ? `Tokens used: ${tokens.toLocaleString()}` : "";
}

function resultTokens(result) {
  return [...(result.round1 ?? []), ...(result.round2 ?? [])].reduce((sum, member) => sum + (member.tokens_used || 0), 0);
}

function setStatTime(label, value) {
  els.statTimeLabel.textContent = label;
  els.statTime.textContent = value;
}

function setMembersStat(seated) {
  const total = state.config.members.length;
  els.statMembers.textContent = seated ? `${seated} of ${total}` : `${total} on call`;
}

function showIdleStats() {
  setMembersStat(0);
  setStatTime("Typical run", state.typicalRun ? `~${formatSeconds(state.typicalRun)}` : "—");
}

function startClock() {
  stopClock();
  state.startedAt = performance.now();
  const tick = () => {
    const seconds = (performance.now() - state.startedAt) / 1000;
    els.elapsed.textContent = `Elapsed ${formatSeconds(seconds)}`;
    setStatTime("Elapsed", formatSeconds(seconds));
  };
  tick();
  state.clock = setInterval(tick, 1000);
}

function stopClock() {
  if (state.clock) clearInterval(state.clock);
  state.clock = null;
}

async function refreshTelemetry() {
  try {
    const { latencyMs, ready, paused } = await fetchTelemetry();
    els.footerLatency.textContent = `Latency: ${latencyMs}ms`;
    els.footerModels.textContent = paused ? `Models: ${ready} ready · ${paused} paused` : `Models: ${ready} ready`;
    els.footerModels.className = paused ? "is-amber" : "is-green";
  } catch {
    els.footerLatency.textContent = "Latency: —";
    els.footerModels.textContent = "Server unreachable";
    els.footerModels.className = "is-amber";
  }
}

/* ── Phases ── */

function setPhase(id) {
  state.phase = id;
  const phase = PHASES[id];
  if (!phase) return;
  chamber.setPill(phase.pill);
  els.progressStage.textContent = phase.stage;
  const rounds = state.debate ? 2 : 1;
  setSession("live", [
    "Deliberation in progress",
    phase.round ? { text: `Round ${phase.round} of ${rounds}`, tone: "accent" } : null,
    { text: phase.round ? phase.pill.split(" · ")[1] : phase.pill, tone: "green" },
  ]);
}

/* ── Running a decision ── */

function setRunning(running) {
  state.running = running;
  els.convene.hidden = running;
  els.progressCard.hidden = !running;
  els.questionCard.classList.toggle("is-locked", running);
  els.lockedHead.hidden = !running;
  els.question.readOnly = running;
  els.debate.disabled = running;
  els.research.disabled = running;
  evidence.lock(running);
  chamber.setActive(running);
}

function resetStage() {
  transcript.clear();
  chamber.reset();
  renderRoster();
  state.stream = [];
  state.turn = 0;
  els.streamList.replaceChildren();
  els.streamCard.hidden = true;
  els.consensusNote.hidden = true;
  els.directive.hidden = true;
  els.directive.replaceChildren();
  els.floor.hidden = true;
  els.replay.hidden = true;
  els.skip.hidden = true;
}

function showConsensus(score, { final = false } = {}) {
  if (score === null || score === undefined) return;
  chamber.setConsensus(score);
  els.consensusNote.hidden = false;
  els.consensusNote.replaceChildren(
    h("span", { class: "pulse-dot", "aria-hidden": "true" }),
    `${final ? "Final consensus" : "Consensus converging"} (${Math.round(score * 100)}%)`,
  );
}

function handleEvent(name, data) {
  switch (name) {
    case "evidence_started":
      setPhase("evidence");
      evidence.markReading(data.index);
      chamber.setStatus("Reading the evidence", data.filename);
      break;
    case "evidence_ready":
      evidence.markRead(data.index, data);
      bumpProgress();
      announce(`${data.filename} ${data.method === "unreadable" ? "couldn’t be read" : "was read"}.`);
      break;
    case "research_started":
      setPhase("research");
      chamber.setStatus("Checking what may have changed", "Does this question need current information?");
      break;
    case "research_skipped":
      bumpProgress(3);
      setPhase("framing");
      chamber.setStatus("Framing the decision", "No current information needed");
      break;
    case "research_searching": {
      bumpProgress();
      const queries = data.queries ?? [];
      chamber.setStatus("Searching the web", clip(queries[0], 90));
      for (const query of queries) pushStream("web", `Searching: ${clip(query, 100)}`);
      updateStreamMeta();
      announce(`Searching the web for ${queries.join("; ")}.`);
      break;
    }
    case "research_reading": {
      bumpProgress();
      const sources = data.sources ?? [];
      const read = sources.filter((source) => source.read);
      for (const source of (read.length ? read : sources).slice(0, 3)) {
        pushStream("web", `${source.read ? "Read" : "Found"} ${source.domain}: ${clip(source.title, 80)}`);
      }
      updateStreamMeta();
      chamber.setStatus("Condensing what the sources say", [...new Set(sources.map((source) => source.domain))].slice(0, 3).join(" · "));
      break;
    }
    case "research_ready": {
      bumpProgress(data.status === "ok" ? 1 : 2);
      const sources = data.sources ?? [];
      if (data.status === "ok") {
        const domains = [...new Set(sources.map((source) => source.domain))].slice(0, 4).join(", ");
        pushStream("web", `Brief ready: ${sources.length} ${sources.length === 1 ? "source" : "sources"} for the council`);
        transcript.enqueueInterlude(`Before debating, the council checked ${sources.length} current web ${sources.length === 1 ? "source" : "sources"}: ${domains}.`);
        announce("The web research is ready.");
      } else {
        pushStream("web", "Web search unavailable: relying on training knowledge");
        transcript.enqueueInterlude("Live web search was unavailable, so the council is relying on training knowledge that may be out of date.");
      }
      updateStreamMeta();
      setPhase("framing");
      chamber.setStatus("Framing the decision", "Choosing who should sit on the council");
      break;
    }
    case "cache_hit":
      transcript.enqueueInterlude("This exact question was put to the council recently, so its earlier deliberation is shown.");
      break;
    case "charter_ready": {
      const council = data.council ?? [];
      setMembersStat(council.length);
      state.progress.seats = council.length || state.progress.seats;
      bumpProgress();
      setPhase("opening");
      chamber.seatCouncil(council);
      chamber.setStatus("Opening statements", `${council.length} members seated`);
      els.floor.hidden = false;
      transcript.enqueueInterlude(`The question was framed and ${council.map((key) => names()[key] ?? key).join(", ")} took their seats.`);
      announce("The council is seated. Opening statements have begun.");
      break;
    }
    case "member_started":
      chamber.setLive(data.key, "thinking", data.round === 2 ? "Preparing a challenge" : "Preparing a statement");
      break;
    case "model_switched": {
      // A backup model took over; keep the seat thinking but say why.
      const label = `Backup model · ${shortModel(data.from_model)} ${data.reason}`;
      chamber.setLive(data.key, "thinking", label);
      announce(`${names()[data.key] ?? data.key} switched to ${shortModel(data.to_model)} because ${shortModel(data.from_model)} was ${data.reason}.`);
      break;
    }
    case "member_done":
      bumpProgress();
      setTokens(state.tokens + (data.tokens_used || 0));
      if (!data.success) chamber.setLive(data.key, "failed", "Unavailable");
      transcript.enqueueStatement(data);
      break;
    case "consensus_update":
      transcript.enqueueAction(() => showConsensus(data.agreement_score));
      break;
    case "debate_skipped":
      state.progress.rounds = 1;
      renderProgress();
      transcript.enqueueAction(() => setPhase("directive"));
      transcript.enqueueInterlude("The opening statements already agreed, so cross-examination was skipped.");
      break;
    case "debate_started":
      transcript.enqueueAction(async ({ instant }) => {
        setPhase("cross");
        chamber.setStatus("Cross-examination", "Members are challenging each other");
        announce("Cross-examination has begun.");
        if (!instant) await wait(400);
      });
      transcript.enqueueInterlude("Cross-examination: each member challenges the positions of the others.");
      break;
    case "synthesis_started":
      chamber.setLive("chairman", "thinking", "Weighing the debate");
      transcript.enqueueAction(() => {
        setPhase("directive");
        chamber.setStatus("The Chairman is weighing the debate", "Drafting one directive");
      });
      break;
    default:
      break;
  }
}

async function deliver(result, { animate }) {
  await transcript.whenIdle();
  state.result = result;
  els.exportButton.disabled = false;
  setTokens(resultTokens(result));
  setMembersStat(result.council_composition?.length || result.round1?.length || 0);
  if (result.total_latency_s) setStatTime(result.cached ? "Recalled in" : "Last run", formatSeconds(result.total_latency_s));
  const recommendation = recommendationLine(result, 130);

  if (animate && !prefersReducedMotion()) {
    setPhase("directive");
    chamber.setSpeaking("chairman");
    chamber.setBubble("chairman", "Directive", recommendation);
    chamber.setStatus("The Chairman has the floor");
    await wait(1200);
  }
  chamber.setSpeaking(null);
  chamber.setLive("chairman", result.degraded ? "failed" : "spoke", result.degraded ? "Incomplete" : "Directive issued");
  chamber.setBubble("chairman", result.degraded ? "Directive incomplete" : "Directive", recommendation);
  setRosterText("chairman", recommendationLine(result, 220));
  if (result.agreement_score !== null && result.agreement_score !== undefined) {
    showConsensus(result.agreement_score, { final: true });
  }
  chamber.setPill(result.degraded ? "Partial deliberation" : "Directive issued");
  chamber.setStatus(result.degraded ? "The directive is incomplete" : "The council has decided",
    result.total_latency_s ? `${Math.round(result.total_latency_s)} seconds` : "");
  chamber.setActive(false);
  chamber.settleLines();
  bumpProgress(1000);

  const aligned = result.agreement_score !== null && result.agreement_score !== undefined
    ? { text: `${Math.round(result.agreement_score * 100)}% aligned`, tone: "green" } : null;
  setSession(result.degraded ? "error" : "done", [result.degraded ? "Partial deliberation" : "Directive issued", aligned]);

  renderVerdict(els.directive, result, { animate, record: state.record });
  els.floor.hidden = !(result.round1?.length);
  els.replay.hidden = !(result.round1?.length);
  if (animate) els.directive.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
  announce("The council has issued its directive.");
}

async function convene(event) {
  event?.preventDefault();
  if (state.running) return;
  showFormError("");

  const prompt = els.question.value.trim();
  if (!prompt) {
    showFormError("Describe the decision first: what are the options, and what matters most?");
    els.question.focus();
    return;
  }
  if (prompt.length > state.config.limits.max_prompt_chars) {
    showFormError(`Shorten the question to ${state.config.limits.max_prompt_chars.toLocaleString()} characters or fewer.`);
    return;
  }
  if (state.config.auth_required && !getAccessKey()) {
    if (!(await requestAccessKey())) return;
  }

  const files = evidence.files;
  state.record = null;
  state.result = null;
  state.debate = els.debate.checked;
  state.research = Boolean(state.config.web_research) && els.research.checked;
  els.exportButton.disabled = true;
  resetStage();
  setTokens(0);
  evidence.resetStates();
  resetProgress(files.length, state.debate, state.research);
  setRunning(true);
  startClock();
  setPhase(files.length ? "evidence" : state.research ? "research" : "framing");
  if (files.length) chamber.setStatus("Reading the evidence");
  else if (state.research) chamber.setStatus("Checking what may have changed", "Does this question need current information?");
  else chamber.setStatus("Framing the decision", "Choosing who should sit on the council");
  state.controller = new AbortController();

  try {
    const result = await streamDecision({
      prompt,
      debate: state.debate,
      research: state.research,
      files,
      signal: state.controller.signal,
      onEvent: handleEvent,
    });
    if (!transcript.busy && !document.querySelector(".statement")) {
      // Cached answers arrive without live events: play the stored debate instead.
      playResult(result, { animate: true });
    }
    await deliver(result, { animate: true });
  } catch (error) {
    transcript.skip();
    await transcript.whenIdle();
    const halted = error.name === "AbortError";
    chamber.reset({ status: halted ? "The session was halted" : "The session ended early", detail: "Nothing was decided" });
    renderRoster();
    setTokens(0);
    stopClock();
    showIdleStats();
    setSession("error", [halted ? "Session halted" : "Session ended early"]);
    if (!halted) showFormError(error.message);
    if (error instanceof ApiError && error.status === 401) {
      setAccessKey("", false);
      requestAccessKey().then((unlocked) => unlocked && showFormError(""));
    }
  } finally {
    stopClock();
    setRunning(false);
    state.controller = null;
    refreshHistoryCount();
    refreshTelemetry();
  }
}

/* ── Replaying stored results ── */

function playResult(result, { animate }) {
  const council = result.council_composition?.length ? result.council_composition : (result.round1 ?? []).map((m) => m.key);
  els.floor.hidden = false;
  const checked = result.research?.status === "ok" ? result.research.sources?.length ?? 0 : 0;
  if (checked) {
    transcript.enqueueInterlude(`Before debating, the council checked ${checked} current web ${checked === 1 ? "source" : "sources"} (searched ${result.research.searched_on}).`);
  }
  transcript.enqueueAction(() => {
    if (animate) setPhase("opening");
    else chamber.setPill("Round 1 · Opening statements");
    chamber.seatCouncil(council);
    chamber.setStatus("Opening statements", animate ? "Replaying the debate" : "");
  });
  for (const member of result.round1 ?? []) transcript.enqueueStatement(member);
  if (result.debate_skipped) {
    transcript.enqueueInterlude("The opening statements already agreed, so cross-examination was skipped.");
  }
  if (result.round2?.length) {
    transcript.enqueueAction(() => {
      if (animate) setPhase("cross");
      chamber.setStatus("Cross-examination", animate ? "Replaying the debate" : "");
    });
    transcript.enqueueInterlude("Cross-examination: each member challenges the positions of the others.");
    for (const member of result.round2) transcript.enqueueStatement(member);
  }
  if (!animate) transcript.skip();
}

async function showPastDecision(record) {
  if (state.running) return;
  state.record = record;
  const result = record.result;
  els.question.value = record.question;
  updateCharCount();
  resetStage();
  playResult(result, { animate: false });
  await deliver(result, { animate: false });
  window.scrollTo({ top: 0, behavior: "auto" });
}

async function replay() {
  if (state.running || !state.result) return;
  const result = state.result;
  const record = state.record;
  resetStage();
  state.record = record;
  state.debate = Boolean(result.round2?.length);
  resetProgress(0, state.debate);
  setRunning(true);
  els.progressTitle.textContent = "Replaying…";
  els.halt.hidden = true;
  chamber.setStatus("Replaying the debate");
  document.querySelector(".chamber").scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" });
  try {
    playResult(result, { animate: true });
    await deliver(result, { animate: true });
  } finally {
    setRunning(false);
    els.progressTitle.textContent = "Deliberating…";
    els.halt.hidden = false;
  }
}

/* ── History and access key ── */

async function refreshHistoryCount() {
  if (state.config.auth_required && !getAccessKey()) return;
  try {
    const records = await fetchHistory(40);
    els.historyCount.hidden = !records.length;
    els.historyCount.textContent = records.length >= 40 ? "40+" : String(records.length);
    // The median of recent complete deliberations; recalled or partial runs would drag it toward zero.
    const times = records
      .map((record) => record.result)
      .filter((result) => result && !result.cached && !result.degraded && result.total_latency_s > 0)
      .map((result) => result.total_latency_s)
      .sort((a, b) => a - b);
    state.typicalRun = times.length ? times[Math.floor(times.length / 2)] : null;
    if (!state.running && !state.result) showIdleStats();
  } catch {
    els.historyCount.hidden = true;
  }
}

function requestAccessKey() {
  return new Promise((resolve) => {
    els.keyInput.value = "";
    els.keyDialog.showModal();
    const onClose = () => {
      els.keyDialog.removeEventListener("close", onClose);
      const unlocked = Boolean(getAccessKey());
      if (unlocked) refreshHistoryCount();
      resolve(unlocked);
    };
    els.keyDialog.addEventListener("close", onClose);
  });
}

els.keyForm.addEventListener("submit", () => {
  const key = els.keyInput.value.trim();
  if (key) setAccessKey(key, els.keyRemember.checked);
});

/* ── Wiring ── */

const chamber = new Chamber({
  chamberEl: $("chamber"),
  seatsEl: $("seats"),
  linesEl: $("debate-lines"),
  statusEl: $("table-status"),
  detailEl: $("table-detail"),
  tilesEl: $("hud-tiles"),
  pillEl: $("hud-pill"),
  pillTextEl: $("hud-pill-text"),
  onStateChange: onSeatState,
  onSeatSelect: (key) => {
    const statements = document.querySelectorAll(`.statement[data-key="${key}"]`);
    statements[statements.length - 1]?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "center" });
  },
});

let transcript;

const evidence = new EvidenceTray({
  dropzone: $("dropzone"),
  input: $("file-input"),
  browseButton: $("browse-button"),
  list: $("evidence-list"),
  pasteTarget: els.form,
  onError: (message) => showFormError(message),
});

const history = new HistoryDrawer({
  dialog: $("history-drawer"),
  list: $("history-list"),
  onSelect: (record) => showPastDecision(record),
  onAuthError: () => requestAccessKey(),
});

function updateCharCount() {
  const length = els.question.value.length;
  const limit = state.config.limits.max_prompt_chars;
  els.charCount.textContent = length > limit * 0.8 ? `${length.toLocaleString()} / ${limit.toLocaleString()}` : "";
  els.charCount.classList.toggle("is-over", length > limit);
}

els.form.addEventListener("submit", convene);
els.question.addEventListener("input", updateCharCount);
els.question.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) convene(event);
});
els.halt.addEventListener("click", () => state.controller?.abort());
els.skip.addEventListener("click", () => transcript.skip());
els.catchUp.addEventListener("click", () => transcript.skip());
els.replay.addEventListener("click", replay);
els.exportButton.addEventListener("click", () => state.result && downloadBrief(state.result));
$("history-button").addEventListener("click", () => history.open());
els.lock.addEventListener("click", () => requestAccessKey());

if (/Mac|iPhone|iPad/.test(navigator.platform)) {
  document.querySelector(".shortcut").textContent = "⌘ ↵";
}

async function start() {
  try {
    state.config = { ...DEFAULT_CONFIG, ...(await fetchConfig()) };
  } catch (error) {
    showFormError(error.message);
  }
  transcript = new Transcript({
    listEl: $("transcript"),
    chamber,
    names: names(),
    onPlaybackChange: (playing) => {
      els.skip.hidden = !playing;
      els.catchUp.disabled = !playing;
    },
    onStatement,
  });
  chamber.render(state.config.members, state.config.chairman);
  renderRoster();
  evidence.setLimits(state.config.limits);
  els.lock.hidden = !state.config.auth_required;
  els.researchRow.hidden = !state.config.web_research;
  els.footerResearch.hidden = !state.config.web_research;
  els.footerResearchSep.hidden = !state.config.web_research;
  showIdleStats();
  refreshTelemetry();
  $("evidence-hint").textContent = state.config.limits.max_files
    ? `PDFs up to ${state.config.limits.max_pdf_mb} MB and images up to ${state.config.limits.max_image_mb} MB. The Evidence Reviewer reads every file before the council deliberates.`
    : "";
  setSession("idle", ["Ready to deliberate"]);
  if (state.config.auth_required && !getAccessKey()) requestAccessKey();
  else refreshHistoryCount();
}

start();
