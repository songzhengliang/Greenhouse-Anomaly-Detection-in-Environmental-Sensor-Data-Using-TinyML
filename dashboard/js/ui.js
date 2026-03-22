import { SENSOR_CONFIG } from "./config.js";
import { appState } from "./store.js";

const dom = {};

function maybeSetInputValue(element, value) {
  if (document.activeElement !== element) {
    element.value = value;
  }
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function titleCase(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatValue(field, value) {
  const config = SENSOR_CONFIG[field];
  return `${Number(value).toFixed(config.decimals)} ${config.unit}`;
}

function formatOffset(field, value) {
  const config = SENSOR_CONFIG[field];
  const numeric = Number(value);
  const digits = config.decimals;
  const fixed = numeric.toFixed(digits);
  const signed = numeric >= 0 ? `+${fixed}` : fixed;
  return `Offset ${signed} ${config.unit}`;
}

function setStatePill(state) {
  dom.statePill.className = "badge rounded-pill state-pill";
  if (state === "critical") {
    dom.statePill.classList.add("bg-danger-subtle", "text-danger-emphasis");
  } else if (state === "warning") {
    dom.statePill.classList.add("bg-warning-subtle", "text-warning-emphasis");
  } else {
    dom.statePill.classList.add("bg-success-subtle", "text-success-emphasis");
  }
  dom.statePill.textContent = titleCase(state);
}

function setModePill(mode) {
  dom.modePill.className = "badge rounded-pill mode-pill";
  if (mode === "live") {
    dom.modePill.classList.add("bg-primary-subtle", "text-primary-emphasis");
    dom.modePill.textContent = "Live";
  } else if (mode === "demo") {
    dom.modePill.classList.add("bg-warning-subtle", "text-warning-emphasis");
    dom.modePill.textContent = "Demo";
  } else {
    dom.modePill.classList.add("bg-info-subtle", "text-info-emphasis");
    dom.modePill.textContent = "Manual";
  }
}

function renderLiveMessaging(data) {
  if (data.mode === "demo") {
    dom.scenarioNote.textContent = `Dataset demo row ${data.demo_row} is driving the dashboard.`;
  } else if (data.mode === "live") {
    if (data.connected && data.presentation?.override_active) {
      dom.scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} with exact override active.`;
    } else if (data.connected && data.presentation?.active) {
      dom.scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} with offsets changing the displayed values.`;
    } else if (data.connected) {
      dom.scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} updated ${data.age_seconds.toFixed(1)} s ago.`;
    } else if (data.received_at) {
      dom.scenarioNote.textContent = `Live ESP32-S3 feed is stale. Last sample from ${data.device_id || "device"} arrived ${data.age_seconds.toFixed(1)} s ago.`;
    } else {
      dom.scenarioNote.textContent = "Waiting for live ESP32-S3 telemetry over USB serial or Wi-Fi.";
    }
  } else {
    dom.scenarioNote.textContent = "Manual values are driving the current decision.";
  }

  if (data.connected) {
    dom.liveSourceNote.textContent = `Board ${data.device_id || "device"} last updated ${data.age_seconds.toFixed(1)} s ago.`;
  } else if (data.received_at) {
    dom.liveSourceNote.textContent = `Last ESP32-S3 sample from ${data.device_id || "device"} arrived ${data.age_seconds.toFixed(1)} s ago.`;
  } else {
    dom.liveSourceNote.textContent = "Waiting for the first ESP32-S3 board sample.";
  }
}

function renderSensors(data) {
  const rawSensors = data.raw_sensors || data.sensors;
  const presentation = data.presentation || appState.currentPresentation;

  Object.entries(SENSOR_CONFIG).forEach(([field, config]) => {
    dom.displayed[field].textContent = formatValue(field, data.sensors[field]);
    dom.raw[field].textContent = formatValue(field, rawSensors[field]);
    dom.offsets[field].textContent = formatOffset(field, presentation.offsets[field] || 0);
  });

  if (presentation.override_active && presentation.override) {
    dom.overrideNote.textContent = "Exact override is active. Decisions are based on your presentation values.";
    maybeSetInputValue(dom.overrideInputs.temperature_c, Number(presentation.override.temperature_c).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.humidity_pct, Number(presentation.override.humidity_pct).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.co2_ppm, Number(presentation.override.co2_ppm).toFixed(0));
  } else if (presentation.active) {
    dom.overrideNote.textContent = "Offsets are active. The ESP32-S3 raw feed is still coming in underneath.";
    maybeSetInputValue(dom.overrideInputs.temperature_c, Number(data.sensors.temperature_c).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.humidity_pct, Number(data.sensors.humidity_pct).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.co2_ppm, Number(data.sensors.co2_ppm).toFixed(0));
  } else {
    dom.overrideNote.textContent = "Override lets you force a specific presentation scenario.";
    maybeSetInputValue(dom.overrideInputs.temperature_c, Number(data.sensors.temperature_c).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.humidity_pct, Number(data.sensors.humidity_pct).toFixed(1));
    maybeSetInputValue(dom.overrideInputs.co2_ppm, Number(data.sensors.co2_ppm).toFixed(0));
  }
}

function renderAlerts(alerts) {
  if (!alerts.length) {
    dom.alertList.innerHTML = `
      <div class="list-group-item trace-item border-0 rounded-4">
        No thresholds were breached. The greenhouse remains in a stable virtual state.
      </div>
    `;
    return;
  }

  dom.alertList.innerHTML = alerts.map((alert) => `
    <div class="list-group-item trace-item border-0 rounded-4">
      <div class="d-flex justify-content-between align-items-start gap-3">
        <div>
          <h3 class="h6 mb-1">${alert.label}</h3>
          <p class="mb-1 text-secondary">${alert.detail}</p>
          <p class="mb-0 small text-uppercase text-secondary fw-semibold">Recommended action: ${alert.recommended_action}</p>
        </div>
        <span class="badge rounded-pill ${alert.severity === "critical" ? "bg-danger-subtle text-danger-emphasis" : "bg-warning-subtle text-warning-emphasis"}">
          ${titleCase(alert.severity)}
        </span>
      </div>
    </div>
  `).join("");
}

function renderMachines(actions) {
  dom.actionGrid.innerHTML = actions.map((action) => `
    <div class="col-12 col-md-6 col-xl-3">
      <article class="machine-tile ${action.active ? "machine-active" : "machine-idle"} h-100">
        <div class="machine-status ${action.active ? "status-active" : "status-idle"}">
          ${titleCase(action.status)}
        </div>
        <h3 class="h5 mt-3 mb-2">${action.label}</h3>
        <p class="mb-0 text-secondary">${action.reason}</p>
      </article>
    </div>
  `).join("");
}

function setBoardConsoleStatus(boardConsole) {
  dom.boardConsoleStatus.className = "badge rounded-pill";

  if (boardConsole.connected) {
    dom.boardConsoleStatus.classList.add("bg-success-subtle", "text-success-emphasis");
    dom.boardConsoleStatus.textContent = "Live";
    return;
  }

  if (boardConsole.received_at) {
    dom.boardConsoleStatus.classList.add("bg-warning-subtle", "text-warning-emphasis");
    dom.boardConsoleStatus.textContent = "Stale";
    return;
  }

  dom.boardConsoleStatus.classList.add("bg-secondary-subtle", "text-secondary-emphasis");
  dom.boardConsoleStatus.textContent = "Waiting";
}

export function initializeUi() {
  dom.form = document.getElementById("control-form");
  dom.demoButton = document.getElementById("demo-button");
  dom.liveButton = document.getElementById("live-button");
  dom.autoplayButton = document.getElementById("autoplay-button");
  dom.evaluateButton = document.getElementById("evaluate-button");
  dom.resetOffsetsButton = document.getElementById("reset-offsets-button");
  dom.applyOverrideButton = document.getElementById("apply-override-button");
  dom.clearOverrideButton = document.getElementById("clear-override-button");
  dom.statePill = document.getElementById("state-pill");
  dom.modePill = document.getElementById("mode-pill");
  dom.summaryText = document.getElementById("summary-text");
  dom.scenarioNote = document.getElementById("scenario-note");
  dom.liveSourceNote = document.getElementById("live-source-note");
  dom.overrideNote = document.getElementById("override-note");
  dom.alertList = document.getElementById("alert-list");
  dom.actionGrid = document.getElementById("action-grid");
  dom.boardConsoleOutput = document.getElementById("board-console-output");
  dom.boardConsoleStatus = document.getElementById("board-console-status");
  dom.boardConsoleNote = document.getElementById("board-console-note");
  dom.displayed = Object.fromEntries(
    Object.entries(SENSOR_CONFIG).map(([field, config]) => [field, document.getElementById(config.displayedId)]),
  );
  dom.raw = Object.fromEntries(
    Object.entries(SENSOR_CONFIG).map(([field, config]) => [field, document.getElementById(config.rawId)]),
  );
  dom.offsets = Object.fromEntries(
    Object.entries(SENSOR_CONFIG).map(([field, config]) => [field, document.getElementById(config.offsetId)]),
  );
  dom.overrideInputs = {
    temperature_c: document.getElementById("override_temperature_c"),
    humidity_pct: document.getElementById("override_humidity_pct"),
    co2_ppm: document.getElementById("override_co2_ppm"),
  };
  dom.adjustButtons = [...document.querySelectorAll("[data-adjust-field]")];
}

export function readManualPayload() {
  return {
    temperature_c: Number(document.getElementById("temperature_c").value),
    humidity_pct: Number(document.getElementById("humidity_pct").value),
    co2_ppm: Number(document.getElementById("co2_ppm").value),
    thresholds: {
      temperature_low: Number(document.getElementById("temperature_low").value),
      temperature_high: Number(document.getElementById("temperature_high").value),
      humidity_low: Number(document.getElementById("humidity_low").value),
      humidity_high: Number(document.getElementById("humidity_high").value),
      co2_high: Number(document.getElementById("co2_high").value),
    },
  };
}

export function readOverridePayload() {
  return {
    temperature_c: Number(dom.overrideInputs.temperature_c.value),
    humidity_pct: Number(dom.overrideInputs.humidity_pct.value),
    co2_ppm: Number(dom.overrideInputs.co2_ppm.value),
  };
}

export function updateModeButtons({ liveActive, demoActive }) {
  dom.liveButton.textContent = liveActive ? "Stop ESP32-S3 Feed" : "Watch ESP32-S3 Feed";
  dom.autoplayButton.textContent = demoActive ? "Stop Demo Stream" : "Start Demo Stream";
}

export function renderDashboard(data) {
  setStatePill(data.overall_state);
  setModePill(data.mode);
  dom.summaryText.textContent = data.summary;
  renderLiveMessaging(data);
  renderSensors(data);
  renderAlerts(data.triggered_conditions);
  renderMachines(data.actions);
}

export function showError(message) {
  dom.scenarioNote.textContent = message;
}

export function renderBoardConsole(boardConsole = appState.boardConsole) {
  setBoardConsoleStatus(boardConsole);

  if (boardConsole.connected) {
    dom.boardConsoleNote.textContent = `Streaming ESP32-S3 console messages from ${boardConsole.device_id || "device"} over USB serial or Wi-Fi.`;
  } else if (boardConsole.logs.length && !boardConsole.received_at) {
    dom.boardConsoleNote.textContent = "Console messages are arriving before the first telemetry sample.";
  } else if (boardConsole.received_at) {
    dom.boardConsoleNote.textContent = `Showing the latest board console history. Last telemetry update was ${boardConsole.age_seconds?.toFixed?.(1) || boardConsole.age_seconds || "0.0"} s ago.`;
  } else {
    dom.boardConsoleNote.textContent = "Waiting for console messages from the ESP32-S3 over USB serial or Wi-Fi.";
  }

  if (!boardConsole.logs.length) {
    dom.boardConsoleOutput.innerHTML = `
      <div class="console-placeholder">
        No board console messages yet. Start the ESP32-S3 telemetry script to stream logs here.
      </div>
    `;
    return;
  }

  dom.boardConsoleOutput.innerHTML = boardConsole.logs.map((entry) => `
    <div class="console-line console-${escapeHtml(entry.level || "info")}">
      <span class="console-time">[${escapeHtml(entry.received_at_label || "--:--:--")}]</span>
      <span class="console-level">${escapeHtml((entry.level || "info").toUpperCase())}</span>
      <span class="console-device">${escapeHtml(entry.device_id || "esp32-s3")}</span>
      <span class="console-message">${escapeHtml(entry.message || "")}</span>
    </div>
  `).join("");
  dom.boardConsoleOutput.scrollTop = dom.boardConsoleOutput.scrollHeight;
}

export function showBoardConsoleError(message) {
  dom.boardConsoleNote.textContent = message;
  dom.boardConsoleStatus.className = "badge rounded-pill bg-danger-subtle text-danger-emphasis";
  dom.boardConsoleStatus.textContent = "Error";
}

export function getDom() {
  return dom;
}
