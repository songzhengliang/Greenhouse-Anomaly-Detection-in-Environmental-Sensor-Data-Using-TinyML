import { HISTORY_WINDOW_MS, SENSOR_CONFIG } from "./config.js";

export function defaultPresentationState() {
  return {
    offsets: {
      temperature_c: 0,
      humidity_pct: 0,
      co2_ppm: 0,
    },
    override: null,
    active: false,
    override_active: false,
  };
}

export function defaultBoardConsoleState() {
  return {
    logs: [],
    connected: false,
    device_id: null,
    received_at: null,
    age_seconds: null,
  };
}

export const appState = {
  currentData: null,
  currentPresentation: defaultPresentationState(),
  boardConsole: defaultBoardConsoleState(),
  history: Object.fromEntries(
    Object.keys(SENSOR_CONFIG).map((field) => [field, []]),
  ),
};

export function setCurrentData(data) {
  appState.currentData = data;
  if (data.presentation) {
    appState.currentPresentation = data.presentation;
  }
}

export function setBoardConsole(boardConsole) {
  appState.boardConsole = {
    ...defaultBoardConsoleState(),
    ...boardConsole,
    logs: Array.isArray(boardConsole?.logs) ? boardConsole.logs : [],
  };
}

export function addHistoryPoint(data) {
  const now = Date.now();
  const cutoff = now - HISTORY_WINDOW_MS;

  Object.keys(SENSOR_CONFIG).forEach((field) => {
    const history = appState.history[field];
    history.push({
      timestamp: now,
      label: new Date(now).toLocaleTimeString([], {
        minute: "2-digit",
        second: "2-digit",
      }),
      value: Number(data.sensors[field]),
    });

    appState.history[field] = history.filter((point) => point.timestamp >= cutoff);
  });
}
