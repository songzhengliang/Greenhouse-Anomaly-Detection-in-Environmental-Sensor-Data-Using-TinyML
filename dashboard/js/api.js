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

export function loadAnomalyPresets() {
  return fetchJson("/api/presets");
}

export function applyAnomalyPreset(presetId) {
  return fetchJson("/api/preset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset_id: presetId }),
  });
}

export function loadLiveScenario() {
  return fetchJson("/api/live");
}

export function connectLiveStream({ onMessage, onError } = {}) {
  const eventSource = new EventSource("/api/live/stream");

  eventSource.addEventListener("live", (event) => {
    try {
      const payload = JSON.parse(event.data);
      onMessage?.(payload);
    } catch (error) {
      onError?.(error);
    }
  });

  eventSource.onerror = (error) => {
    onError?.(error);
  };

  return eventSource;
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

export function sendBoardConsoleInput(payload) {
  return fetchJson("/api/serial/write", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
