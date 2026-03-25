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

function maybeSetNumericValue(element, value, digits = 1) {
  if (!element || value === undefined || value === null) {
    return;
  }
  const formatted = Number(value).toFixed(digits);
  maybeSetInputValue(element, formatted);
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
  } else if (mode === "preset") {
    dom.modePill.classList.add("bg-secondary-subtle", "text-secondary-emphasis");
    dom.modePill.textContent = "Preset";
  } else if (mode === "demo") {
    dom.modePill.classList.add("bg-warning-subtle", "text-warning-emphasis");
    dom.modePill.textContent = "Demo";
  } else {
    dom.modePill.classList.add("bg-info-subtle", "text-info-emphasis");
    dom.modePill.textContent = "Manual";
  }
}

function setAnomalyPill(severity) {
  dom.anomalyPill.className = "badge rounded-pill";
  if (severity === "critical") {
    dom.anomalyPill.classList.add("bg-danger-subtle", "text-danger-emphasis");
  } else if (severity === "warning") {
    dom.anomalyPill.classList.add("bg-warning-subtle", "text-warning-emphasis");
  } else {
    dom.anomalyPill.classList.add("bg-success-subtle", "text-success-emphasis");
  }
  dom.anomalyPill.textContent = titleCase(severity || "stable");
}

function renderLiveMessaging(data) {
  if (data.mode === "preset") {
    dom.scenarioNote.textContent = `${data.preset_label || "Presentation preset"} is driving a simulated anomaly window for the dashboard.`;
  } else if (data.mode === "demo") {
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

  if (data.mode === "preset") {
    dom.liveSourceNote.textContent = `${data.preset_label || "Presentation preset"} is active. Click Watch ESP32-S3 Feed to return to the live board.`;
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = `${data.preset_label || "Presentation preset"} is active. The shared result cards now show simulated scenario output.`;
    }
  } else if (data.mode === "demo") {
    dom.liveSourceNote.textContent = "Dataset demo mode is active. Live board updates are paused in the UI.";
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = "Demo mode is active. Live board updates are paused in the UI.";
    }
  } else if (data.mode === "manual") {
    dom.liveSourceNote.textContent = "Manual mode is active. Click Watch ESP32-S3 Feed to return to the live board.";
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = "Manual mode is active. Adjust the form values or load a preset scenario.";
    }
  } else if (data.connected) {
    dom.liveSourceNote.textContent = `Board ${data.device_id || "device"} last updated ${data.age_seconds.toFixed(1)} s ago.`;
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = `Live board ${data.device_id || "device"} is available. Switch back to Live whenever you want to resume the real feed.`;
    }
  } else if (data.received_at) {
    dom.liveSourceNote.textContent = `Last ESP32-S3 sample from ${data.device_id || "device"} arrived ${data.age_seconds.toFixed(1)} s ago.`;
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = `The last live board sample arrived ${data.age_seconds.toFixed(1)} s ago.`;
    }
  } else {
    dom.liveSourceNote.textContent = "Waiting for the first ESP32-S3 board sample.";
    if (dom.presetSourceNote) {
      dom.presetSourceNote.textContent = "Waiting for the first ESP32-S3 board sample.";
    }
  }
}

function renderControlInputs(data) {
  if (data.mode === "live") {
    return;
  }

  maybeSetNumericValue(dom.manualInputs.temperature_c, data.sensors?.temperature_c, 1);
  maybeSetNumericValue(dom.manualInputs.humidity_pct, data.sensors?.humidity_pct, 1);
  maybeSetNumericValue(dom.manualInputs.co2_ppm, data.sensors?.co2_ppm, 0);

  if (!data.thresholds) {
    return;
  }

  maybeSetNumericValue(dom.thresholdInputs.temperature_low, data.thresholds.temperature_low, 1);
  maybeSetNumericValue(dom.thresholdInputs.temperature_high, data.thresholds.temperature_high, 1);
  maybeSetNumericValue(dom.thresholdInputs.humidity_low, data.thresholds.humidity_low, 1);
  maybeSetNumericValue(dom.thresholdInputs.humidity_high, data.thresholds.humidity_high, 1);
  maybeSetNumericValue(dom.thresholdInputs.co2_high, data.thresholds.co2_high, 0);
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
        No action alerts are active. The greenhouse can remain in a stable virtual state.
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
        ${action.confidence !== undefined ? `
          <p class="mb-0 mt-2 small text-uppercase text-secondary fw-semibold">
            ${escapeHtml(action.source || "AI")} confidence: ${(Number(action.confidence) * 100).toFixed(0)}%
          </p>
        ` : ""}
      </article>
    </div>
  `).join("");
}

function renderAnomaly(anomaly = {}) {
  const severity = anomaly.severity || "stable";
  const topPredictions = Array.isArray(anomaly.top_predictions) ? anomaly.top_predictions : [];
  const confidence = Number(anomaly.confidence);

  setAnomalyPill(severity);
  dom.anomalyLabel.textContent = anomaly.display_label || "No anomaly";
  dom.anomalySummary.textContent = anomaly.summary || "AI anomaly monitoring is ready.";
  dom.anomalyDetail.textContent = anomaly.detail || "The model will describe the latest anomaly hypothesis here.";

  if (Number.isFinite(confidence)) {
    dom.anomalyConfidence.textContent = `${anomaly.decision_engine === "rule_fallback" ? "Fallback" : "AI"} confidence: ${(confidence * 100).toFixed(0)}%`;
  } else {
    dom.anomalyConfidence.textContent = "AI confidence: --";
  }

  if (!topPredictions.length) {
    dom.anomalyTopList.innerHTML = `
      <div class="anomaly-hypothesis">
        <span class="fw-semibold">No hypotheses yet</span>
        <span>--</span>
      </div>
    `;
    return;
  }

  dom.anomalyTopList.innerHTML = topPredictions.map((prediction) => `
    <div class="anomaly-hypothesis">
      <span class="fw-semibold">${escapeHtml(prediction.display_label || prediction.label || "Unknown")}</span>
      <span>${(Number(prediction.confidence) * 100).toFixed(0)}%</span>
    </div>
  `).join("");
}

function updatePresetPreview(presetId = dom.presetSelect?.value) {
  const preset = (dom.presetCatalog || []).find((entry) => entry.id === presetId);
  if (!preset) {
    dom.presetCategory.textContent = "Preset";
    dom.presetLabel.textContent = "No preset selected";
    dom.presetDescription.textContent = "Choose a preset to preview its anomaly target and ending sensor snapshot.";
    dom.presetTargetBadge.textContent = "Waiting";
    dom.presetTargetBadge.className = "badge rounded-pill bg-light text-dark";
    dom.presetPreview.innerHTML = `
      <span>-- C</span>
      <span>--%</span>
      <span>-- ppm</span>
    `;
    return;
  }

  dom.presetCategory.textContent = preset.category || "Preset";
  dom.presetLabel.textContent = preset.label || "Presentation preset";
  dom.presetDescription.textContent = preset.description || "";
  dom.presetTargetBadge.textContent = `Target: ${(preset.target_anomaly || "normal").replaceAll("_", " ")}`;
  dom.presetTargetBadge.className = "badge rounded-pill bg-dark-subtle text-dark-emphasis";
  dom.presetPreview.innerHTML = `
    <span>${Number(preset.preview?.temperature_c ?? 0).toFixed(1)} C</span>
    <span>${Number(preset.preview?.humidity_pct ?? 0).toFixed(1)}%</span>
    <span>${Number(preset.preview?.co2_ppm ?? 0).toFixed(0)} ppm</span>
  `;
}

export function renderPresetCatalog(presets = []) {
  dom.presetCatalog = Array.isArray(presets) ? presets : [];

  if (!presets.length) {
    dom.presetSelect.innerHTML = `<option value="">No presets available</option>`;
    dom.presetSelect.disabled = true;
    updatePresetPreview("");
    return;
  }

  dom.presetSelect.disabled = false;
  dom.presetSelect.innerHTML = presets.map((preset) => `
    <option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)} (${escapeHtml(preset.category || "Preset")})</option>
  `).join("");
  updatePresetPreview(dom.presetSelect.value);
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
  dom.liveButton = document.getElementById("live-button");
  dom.evaluateButton = document.getElementById("evaluate-button");
  dom.resetOffsetsButton = document.getElementById("reset-offsets-button");
  dom.applyOverrideButton = document.getElementById("apply-override-button");
  dom.clearOverrideButton = document.getElementById("clear-override-button");
  dom.navLiveButton = document.getElementById("nav-live-button");
  dom.navPresetButton = document.getElementById("nav-preset-button");
  dom.navConsoleButton = document.getElementById("nav-console-button");
  dom.pagePanels = [...document.querySelectorAll("[data-page-panel]")];
  dom.hideOnConsolePanels = [...document.querySelectorAll("[data-hide-on-console]")];
  dom.consolePage = document.getElementById("console-page");
  dom.statePill = document.getElementById("state-pill");
  dom.modePill = document.getElementById("mode-pill");
  dom.summaryText = document.getElementById("summary-text");
  dom.scenarioNote = document.getElementById("scenario-note");
  dom.liveSourceNote = document.getElementById("live-source-note");
  dom.presetSourceNote = document.getElementById("preset-source-note");
  dom.overrideNote = document.getElementById("override-note");
  dom.anomalyLabel = document.getElementById("anomaly-label");
  dom.anomalyPill = document.getElementById("anomaly-pill");
  dom.anomalySummary = document.getElementById("anomaly-summary");
  dom.anomalyDetail = document.getElementById("anomaly-detail");
  dom.anomalyConfidence = document.getElementById("anomaly-confidence");
  dom.anomalyTopList = document.getElementById("anomaly-top-list");
  dom.alertList = document.getElementById("alert-list");
  dom.actionGrid = document.getElementById("action-grid");
  dom.boardConsoleOutput = document.getElementById("board-console-output");
  dom.boardConsoleStatus = document.getElementById("board-console-status");
  dom.boardConsoleNote = document.getElementById("board-console-note");
  dom.consoleCommandInput = document.getElementById("console-command-input");
  dom.consoleSendButton = document.getElementById("console-send-button");
  dom.consoleInterruptButton = document.getElementById("console-interrupt-button");
  dom.consoleResetButton = document.getElementById("console-reset-button");
  dom.presetSelect = document.getElementById("preset-select");
  dom.applyPresetButton = document.getElementById("apply-preset-button");
  dom.presetCategory = document.getElementById("preset-category");
  dom.presetLabel = document.getElementById("preset-label");
  dom.presetDescription = document.getElementById("preset-description");
  dom.presetTargetBadge = document.getElementById("preset-target-badge");
  dom.presetPreview = document.getElementById("preset-preview");
  dom.presetCatalog = [];
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
  dom.manualInputs = {
    temperature_c: document.getElementById("temperature_c"),
    humidity_pct: document.getElementById("humidity_pct"),
    co2_ppm: document.getElementById("co2_ppm"),
  };
  dom.thresholdInputs = {
    temperature_low: document.getElementById("temperature_low"),
    temperature_high: document.getElementById("temperature_high"),
    humidity_low: document.getElementById("humidity_low"),
    humidity_high: document.getElementById("humidity_high"),
    co2_high: document.getElementById("co2_high"),
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

export function readSelectedPresetId() {
  return dom.presetSelect.value;
}

export function renderSelectedPresetPreview() {
  updatePresetPreview(dom.presetSelect.value);
}

export function updateModeButtons({ liveActive, demoActive }) {
  if (dom.liveButton) {
    dom.liveButton.textContent = liveActive ? "Pause Live Feed" : "Watch ESP32-S3 Feed";
  }
}

export function setActivePage(page) {
  dom.pagePanels.forEach((panel) => {
    panel.classList.toggle("d-none", panel.dataset.pagePanel !== page);
  });
  dom.hideOnConsolePanels.forEach((panel) => {
    panel.classList.toggle("d-none", page === "console");
  });

  dom.navLiveButton.className = "btn nav-switch-button";
  dom.navPresetButton.className = "btn nav-switch-button";
  dom.navConsoleButton.className = "btn nav-switch-button";

  if (page === "live") {
    dom.navLiveButton.classList.add("btn-dark");
    dom.navPresetButton.classList.add("btn-outline-dark");
    dom.navConsoleButton.classList.add("btn-outline-dark");
  } else if (page === "preset") {
    dom.navLiveButton.classList.add("btn-outline-dark");
    dom.navPresetButton.classList.add("btn-dark");
    dom.navConsoleButton.classList.add("btn-outline-dark");
  } else {
    dom.navLiveButton.classList.add("btn-outline-dark");
    dom.navPresetButton.classList.add("btn-outline-dark");
    dom.navConsoleButton.classList.add("btn-dark");
  }
}

export function readConsoleCommand() {
  return dom.consoleCommandInput.value;
}

export function clearConsoleCommand() {
  dom.consoleCommandInput.value = "";
}

export function renderDashboard(data) {
  setStatePill(data.overall_state);
  setModePill(data.mode);
  dom.summaryText.textContent = data.summary;
  renderLiveMessaging(data);
  renderControlInputs(data);
  renderSensors(data);
  renderAnomaly(data.anomaly);
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

export function showPresetCatalogError(message) {
  dom.presetSelect.disabled = true;
  dom.presetSelect.innerHTML = `<option value="">Preset catalog unavailable</option>`;
  dom.presetCategory.textContent = "Preset";
  dom.presetLabel.textContent = "Preset catalog unavailable";
  dom.presetDescription.textContent = message;
  dom.presetTargetBadge.textContent = "Error";
  dom.presetTargetBadge.className = "badge rounded-pill bg-danger-subtle text-danger-emphasis";
  dom.presetPreview.innerHTML = `
    <span>-- C</span>
    <span>--%</span>
    <span>-- ppm</span>
  `;
}

export function getDom() {
  return dom;
}
