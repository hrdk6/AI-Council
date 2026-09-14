// Incremental parser for text/event-stream bodies read through fetch().
// EventSource can't send POST bodies or custom headers, so the stream is parsed by hand.

export function createSSEParser(onEvent) {
  let buffer = "";
  let eventName = "message";
  let dataLines = [];

  function dispatch() {
    const raw = dataLines.join("\n");
    const name = eventName;
    dataLines = [];
    eventName = "message";
    let payload = raw;
    try {
      payload = JSON.parse(raw);
    } catch {
      // Non-JSON data is passed through as a string.
    }
    onEvent(name, payload);
  }

  function handleLine(line) {
    if (line === "") {
      if (dataLines.length) dispatch();
      else eventName = "message";
      return;
    }
    if (line.startsWith(":")) return; // comment / keep-alive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? "" : line.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") eventName = value;
    else if (field === "data") dataLines.push(value);
  }

  return {
    push(chunk) {
      buffer += chunk.replace(/\r/g, "");
      let newline;
      while ((newline = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newline);
        buffer = buffer.slice(newline + 1);
        handleLine(line);
      }
    },
    end() {
      if (buffer) handleLine(buffer);
      buffer = "";
      if (dataLines.length) dispatch();
    },
  };
}
