// Backend client. The access key (when the server requires one) lives in session storage,
// or local storage if the user chooses to be remembered on this device.

import { createSSEParser } from "./sse.js";

const KEY_NAME = "ai-council.access-key";

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message);
    this.status = status;
  }
}

function storage(kind) {
  try {
    return kind === "local" ? window.localStorage : window.sessionStorage;
  } catch {
    return null;
  }
}

export function getAccessKey() {
  return storage("session")?.getItem(KEY_NAME) || storage("local")?.getItem(KEY_NAME) || "";
}

export function setAccessKey(key, remember) {
  storage("session")?.removeItem(KEY_NAME);
  storage("local")?.removeItem(KEY_NAME);
  if (key) storage(remember ? "local" : "session")?.setItem(KEY_NAME, key);
}

async function errorFrom(response) {
  let detail = "";
  try {
    const body = await response.json();
    detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg ?? item).join("; ") : body.detail;
  } catch {
    // Not JSON.
  }
  if (response.status === 401) return new ApiError("The access key wasn't accepted.", 401);
  if (response.status === 429) return new ApiError("Too many decisions in a short time. Wait a minute, then convene again.", 429);
  if (response.status === 413) return new ApiError(detail || "The upload is too large.", 413);
  return new ApiError(detail || `The server responded with ${response.status}.`, response.status);
}

async function request(path, { method = "GET", body, headers = {}, signal } = {}) {
  const key = getAccessKey();
  let response;
  try {
    response = await fetch(path, {
      method,
      body,
      signal,
      headers: { ...(key ? { "X-API-Key": key } : {}), ...headers },
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Can't reach the council server. Check that it's running.");
  }
  if (!response.ok) throw await errorFrom(response);
  return response;
}

export async function fetchConfig() {
  return (await request("/v1/config")).json();
}

export async function fetchHistory(limit = 30) {
  return (await request(`/v1/history?limit=${limit}`)).json();
}

export async function saveFeedback(decisionId, rating, outcomeNote) {
  await request(`/v1/history/${encodeURIComponent(decisionId)}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rating, outcome_note: outcomeNote || null }),
  });
}

/** Submit a decision and call onEvent(name, payload) for each progress event. Resolves with the result. */
export async function streamDecision({ prompt, debate, research = true, files, onEvent, signal }) {
  const form = new FormData();
  form.append("prompt", prompt);
  form.append("debate", String(debate));
  form.append("research", String(research));
  for (const file of files) form.append("files", file, file.name);

  const response = await request("/v1/ask/stream", { method: "POST", body: form, signal });
  let result = null;
  let failure = null;
  const parser = createSSEParser((name, payload) => {
    if (name === "complete") result = payload;
    else if (name === "error") failure = new ApiError(payload?.detail || "The council couldn't finish.");
    else onEvent(name, payload);
  });

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.push(value);
    if (failure) throw failure;
  }
  parser.end();
  if (failure) throw failure;
  if (!result) throw new ApiError("The connection closed before the council finished. Try again.");
  return result;
}
