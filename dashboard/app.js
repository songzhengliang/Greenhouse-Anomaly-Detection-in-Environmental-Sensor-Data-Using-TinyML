const form = document.getElementById("control-form");
const demoButton = document.getElementById("demo-button");
const liveButton = document.getElementById("live-button");
const autoplayButton = document.getElementById("autoplay-button");
const resetOffsetsButton = document.getElementById("reset-offsets-button");
const applyOverrideButton = document.getElementById("apply-override-button");
const clearOverrideButton = document.getElementById("clear-override-button");

const statePill = document.getElementById("state-pill");
const modePill = document.getElementById("mode-pill");
const summaryText = document.getElementById("summary-text");
const scenarioNote = document.getElementById("scenario-note");
const actionGrid = document.getElementById("action-grid");
const alertList = document.getElementById("alert-list");

const metricTemperature = document.getElementById("metric-temperature");
const metricHumidity = document.getElementById("metric-humidity");
const metricCo2 = document.getElementById("metric-co2");
const rawTemperature = document.getElementById("raw-temperature");
const rawHumidity = document.getElementById("raw-humidity");
const rawCo2 = document.getElementById("raw-co2");
const liveSourceNote = document.getElementById("live-source-note");
const offsetTemperature = document.getElementById("offset-temperature");
const offsetHumidity = document.getElementById("offset-humidity");
const offsetCo2 = document.getElementById("offset-co2");
const presentationNote = document.getElementById("presentation-note");
const overrideTemperature = document.getElementById("override_temperature_c");
const overrideHumidity = document.getElementById("override_humidity_pct");
const overrideCo2 = document.getElementById("override_co2_ppm");

let autoplayTimer = null;
let liveTimer = null;
let currentPresentation = {
  offsets: {
    temperature_c: 0,
    humidity_pct: 0,
    co2_ppm: 0,
  },
  override: null,
  active: false,
  override_active: false,
};

function readNumber(id) {
  return Number(document.getElementById(id).value);
}

function readPayload() {
  return {
    temperature_c: readNumber("temperature_c"),
    humidity_pct: readNumber("humidity_pct"),
    co2_ppm: readNumber("co2_ppm"),
    thresholds: {
      temperature_low: readNumber("temperature_low"),
      temperature_high: readNumber("temperature_high"),
      humidity_low: readNumber("humidity_low"),
      humidity_high: readNumber("humidity_high"),
      co2_high: readNumber("co2_high"),
    },
  };
}

function applySensors(sensors) {
  document.getElementById("temperature_c").value = sensors.temperature_c;
  document.getElementById("humidity_pct").value = sensors.humidity_pct;
  document.getElementById("co2_ppm").value = sensors.co2_ppm;
}

function titleCase(text) {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatSigned(value, decimals = 1) {
  const numeric = Number(value);
  const fixed = numeric.toFixed(decimals);
  return numeric >= 0 ? `+${fixed}` : fixed;
}

function maybeSetInputValue(element, value) {
  if (document.activeElement !== element) {
    element.value = value;
  }
}

function readOverridePayload() {
  return {
    temperature_c: Number(overrideTemperature.value),
    humidity_pct: Number(overrideHumidity.value),
    co2_ppm: Number(overrideCo2.value),
  };
}

function renderActions(actions) {
  actionGrid.innerHTML = actions.map((action) => `
    <article class="action-card ${action.active ? "active" : ""}">
      <span class="status-chip ${action.active ? "active" : "idle"}">
        ${titleCase(action.status)}
      </span>
      <h3>${action.label}</h3>
      <p class="action-reason">${action.reason}</p>
    </article>
  `).join("");
}

function renderAlerts(alerts) {
  if (!alerts.length) {
    alertList.innerHTML = `
      <div class="empty-state">
        No thresholds were breached. The greenhouse can stay in a stable virtual state.
      </div>
    `;
    return;
  }

  alertList.innerHTML = alerts.map((alert) => `
    <article class="alert-card">
      <div class="alert-head">
        <h3>${alert.label}</h3>
        <span class="severity-chip ${alert.severity}">${titleCase(alert.severity)}</span>
      </div>
      <p>${alert.detail}</p>
      <p><strong>Recommended action:</strong> ${alert.recommended_action}</p>
    </article>
  `).join("");
}

function renderPresentation(data) {
  if (!data.raw_sensors || !data.presentation) {
    return;
  }

  currentPresentation = data.presentation;

  rawTemperature.textContent = `${data.raw_sensors.temperature_c.toFixed(1)} C`;
  rawHumidity.textContent = `${data.raw_sensors.humidity_pct.toFixed(1)}%`;
  rawCo2.textContent = `${data.raw_sensors.co2_ppm} ppm`;

  offsetTemperature.textContent = `Offset: ${formatSigned(data.presentation.offsets.temperature_c)} C`;
  offsetHumidity.textContent = `Offset: ${formatSigned(data.presentation.offsets.humidity_pct)} %`;
  offsetCo2.textContent = `Offset: ${formatSigned(data.presentation.offsets.co2_ppm, 0)} ppm`;

  if (data.connected) {
    liveSourceNote.textContent = `Board ${data.device_id || "device"} last updated ${data.age_seconds.toFixed(1)} s ago.`;
  } else if (data.received_at) {
    liveSourceNote.textContent = `Live feed is stale. Last ESP32-S3 sample from ${data.device_id || "device"} arrived ${data.age_seconds.toFixed(1)} s ago.`;
  } else {
    liveSourceNote.textContent = "Waiting for the first board sample.";
  }

  if (data.presentation.override_active && data.presentation.override) {
    presentationNote.textContent = "Exact override is active. Decisions are currently based on your manual presentation values.";
    maybeSetInputValue(overrideTemperature, data.presentation.override.temperature_c.toFixed(1));
    maybeSetInputValue(overrideHumidity, data.presentation.override.humidity_pct.toFixed(1));
    maybeSetInputValue(overrideCo2, data.presentation.override.co2_ppm);
  } else if (data.presentation.active) {
    presentationNote.textContent = "Presentation offsets are active. Raw ESP32-S3 data is still being received underneath.";
    maybeSetInputValue(overrideTemperature, data.sensors.temperature_c.toFixed(1));
    maybeSetInputValue(overrideHumidity, data.sensors.humidity_pct.toFixed(1));
    maybeSetInputValue(overrideCo2, data.sensors.co2_ppm);
  } else {
    presentationNote.textContent = "Override replaces the live feed values until you clear it.";
    maybeSetInputValue(overrideTemperature, data.sensors.temperature_c.toFixed(1));
    maybeSetInputValue(overrideHumidity, data.sensors.humidity_pct.toFixed(1));
    maybeSetInputValue(overrideCo2, data.sensors.co2_ppm);
  }
}

function renderDecision(data) {
  const stateClass = data.overall_state === "stable" ? "stable" : data.overall_state;
  statePill.className = `state-pill ${stateClass}`;
  statePill.textContent = titleCase(data.overall_state);
  modePill.textContent = titleCase(data.mode);
  summaryText.textContent = data.summary;

  metricTemperature.textContent = `${data.sensors.temperature_c.toFixed(1)} C`;
  metricHumidity.textContent = `${data.sensors.humidity_pct.toFixed(1)}%`;
  metricCo2.textContent = `${data.sensors.co2_ppm} ppm`;

  if (data.mode === "demo") {
    scenarioNote.textContent = `Dataset demo row ${data.demo_row} is driving the virtual actuator recommendation.`;
  } else if (data.mode === "live") {
    if (data.connected && data.presentation?.override_active) {
      scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} • exact presentation override is active.`;
    } else if (data.connected && data.presentation?.active) {
      scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} • presentation offsets are changing the displayed values.`;
    } else if (data.connected) {
      scenarioNote.textContent = `Live ESP32-S3 feed from ${data.device_id || "device"} • last update ${data.age_seconds.toFixed(1)} s ago.`;
    } else if (data.received_at) {
      scenarioNote.textContent = `The live ESP32-S3 feed is stale. Last sample from ${data.device_id || "device"} arrived ${data.age_seconds.toFixed(1)} s ago.`;
    } else {
      scenarioNote.textContent = "Waiting for live ESP32-S3 telemetry over Wi-Fi.";
    }
    renderPresentation(data);
  } else {
    scenarioNote.textContent = "Manual values are driving the current recommendation.";
  }

  renderActions(data.actions);
  renderAlerts(data.triggered_conditions);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Request failed");
  }
  return payload;
}

async function evaluateManualScenario() {
  const data = await fetchJson("/api/recommend", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(readPayload()),
  });
  renderDecision(data);
}

async function loadDemoScenario() {
  const data = await fetchJson("/api/demo");
  applySensors(data.sensors);
  renderDecision(data);
}

async function loadLiveScenario() {
  const data = await fetchJson("/api/live");
  applySensors(data.sensors);
  renderDecision(data);
}

async function pushPresentationState(presentation) {
  const data = await fetchJson("/api/live/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(presentation),
  });
  applySensors(data.sensors);
  renderDecision(data);
}

function stopAutoplay() {
  if (!autoplayTimer) {
    return;
  }

  clearInterval(autoplayTimer);
  autoplayTimer = null;
  autoplayButton.textContent = "Start Demo Stream";
}

function stopLiveFeed() {
  if (!liveTimer) {
    return;
  }

  clearInterval(liveTimer);
  liveTimer = null;
  liveButton.textContent = "Watch ESP32-S3 Feed";
}

function toggleAutoplay() {
  if (autoplayTimer) {
    stopAutoplay();
    return;
  }

  stopLiveFeed();
  loadDemoScenario();
  autoplayTimer = window.setInterval(loadDemoScenario, 2500);
  autoplayButton.textContent = "Stop Demo Stream";
}

function toggleLiveFeed() {
  if (liveTimer) {
    stopLiveFeed();
    return;
  }

  stopAutoplay();
  loadLiveScenario();
  liveTimer = window.setInterval(loadLiveScenario, 3000);
  liveButton.textContent = "Stop ESP32-S3 Feed";
}

async function nudgeLiveField(field, delta) {
  stopAutoplay();
  const nextOffsets = {
    ...currentPresentation.offsets,
    [field]: Number(currentPresentation.offsets[field]) + Number(delta),
  };
  await pushPresentationState({
    offsets: nextOffsets,
    override: currentPresentation.override,
  });
}

async function resetOffsets() {
  stopAutoplay();
  await pushPresentationState({
    offsets: {
      temperature_c: 0,
      humidity_pct: 0,
      co2_ppm: 0,
    },
    override: currentPresentation.override,
  });
}

async function applyOverride() {
  stopAutoplay();
  await pushPresentationState({
    offsets: currentPresentation.offsets,
    override: readOverridePayload(),
  });
}

async function clearOverride() {
  stopAutoplay();
  await pushPresentationState({
    offsets: currentPresentation.offsets,
    override: null,
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await evaluateManualScenario();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

demoButton.addEventListener("click", async () => {
  try {
    await loadDemoScenario();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

autoplayButton.addEventListener("click", toggleAutoplay);
liveButton.addEventListener("click", async () => {
  try {
    toggleLiveFeed();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

document.querySelectorAll("[data-adjust-field]").forEach((button) => {
  button.addEventListener("click", async () => {
    try {
      await nudgeLiveField(
        button.dataset.adjustField,
        Number(button.dataset.adjustDelta),
      );
    } catch (error) {
      scenarioNote.textContent = error.message;
    }
  });
});

resetOffsetsButton.addEventListener("click", async () => {
  try {
    await resetOffsets();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

applyOverrideButton.addEventListener("click", async () => {
  try {
    await applyOverride();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

clearOverrideButton.addEventListener("click", async () => {
  try {
    await clearOverride();
  } catch (error) {
    scenarioNote.textContent = error.message;
  }
});

loadDemoScenario().catch((error) => {
  scenarioNote.textContent = error.message;
});
