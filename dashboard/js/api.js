async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();

  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }

  return payload;
}

export function evaluateManualScenario(payload) {
  return fetchJson("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function loadDemoScenario() {
  return fetchJson("/api/demo");
}

export function loadLiveScenario() {
  return fetchJson("/api/live");
}

export function loadBoardLogs() {
  return fetchJson("/api/board/logs");
}

export function pushPresentationState(presentation) {
  return fetchJson("/api/live/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(presentation),
  });
}
