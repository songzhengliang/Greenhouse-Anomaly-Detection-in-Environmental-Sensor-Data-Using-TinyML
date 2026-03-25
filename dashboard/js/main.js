import {
  applyAnomalyPreset,
  loadBoardLogs,
  loadAnomalyPresets,
  evaluateManualScenario,
  loadLiveScenario,
  sendBoardConsoleInput,
  pushPresentationState,
} from "./api.js";
import { initializeCharts, renderCharts } from "./charts.js";
import {
  clearConsoleCommand,
  initializeUi,
  readConsoleCommand,
  readManualPayload,
  readOverridePayload,
  readSelectedPresetId,
  renderBoardConsole,
  renderDashboard,
  renderPresetCatalog,
  renderSelectedPresetPreview,
  setActivePage,
  showBoardConsoleError,
  showError,
  showPresetCatalogError,
  updateModeButtons,
  getDom,
} from "./ui.js";
import { addHistoryPoint, appState, setBoardConsole, setCurrentData } from "./store.js";

let liveTimer = null;
let boardLogTimer = null;
let currentPage = "live";

function applyData(data) {
  setCurrentData(data);
  addHistoryPoint(data);
  renderDashboard(data);
  renderCharts();
}

async function refreshBoardConsole() {
  const boardConsole = await loadBoardLogs();
  setBoardConsole(boardConsole);
  renderBoardConsole();
}

function stopLiveFeed() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
    updateModeButtons({ liveActive: false });
  }
}

async function handleManualEvaluate() {
  stopLiveFeed();
  const data = await evaluateManualScenario(readManualPayload());
  applyData(data);
}

async function handleLiveLoad() {
  const data = await loadLiveScenario();
  applyData(data);
}

async function startLiveFeed() {
  await handleLiveLoad();
  if (!liveTimer) {
    liveTimer = window.setInterval(async () => {
      try {
        await handleLiveLoad();
      } catch (error) {
        showError(error.message);
      }
    }, 3000);
  }
  updateModeButtons({ liveActive: true });
}

async function handleToggleLiveFeed() {
  if (liveTimer) {
    stopLiveFeed();
    return;
  }
  await startLiveFeed();
}

async function handlePresetApply(presetId) {
  if (!presetId) {
    throw new Error("Choose a preset first.");
  }
  stopLiveFeed();
  const data = await applyAnomalyPreset(presetId);
  applyData(data);
}

async function handleConsoleSend(text) {
  const command = String(text || "").trim();
  if (!command) {
    throw new Error("Enter a console command first.");
  }
  await sendBoardConsoleInput({
    text: command,
    append_newline: true,
  });
  clearConsoleCommand();
  await refreshBoardConsole();
}

async function handleConsoleControl(control) {
  await sendBoardConsoleInput({ control });
  await refreshBoardConsole();
}

function currentPresentationPayload(override = appState.currentPresentation.override) {
  return {
    offsets: appState.currentPresentation.offsets,
    override,
  };
}

async function handleAdjust(field, delta) {
  const nextOffsets = {
    ...appState.currentPresentation.offsets,
    [field]: Number(appState.currentPresentation.offsets[field]) + Number(delta),
  };
  const data = await pushPresentationState({
    offsets: nextOffsets,
    override: appState.currentPresentation.override,
  });
  applyData(data);
}

async function handleResetOffsets() {
  const data = await pushPresentationState({
    offsets: {
      temperature_c: 0,
      humidity_pct: 0,
      co2_ppm: 0,
    },
    override: appState.currentPresentation.override,
  });
  applyData(data);
}

async function handleApplyOverride() {
  const data = await pushPresentationState(currentPresentationPayload(readOverridePayload()));
  applyData(data);
}

async function handleClearOverride() {
  const data = await pushPresentationState(currentPresentationPayload(null));
  applyData(data);
}

async function showPage(page) {
  currentPage = page;
  setActivePage(page);

  if (page === "live") {
    try {
      await startLiveFeed();
    } catch (error) {
      showError(error.message);
    }
    return;
  }

  if (page === "console") {
    stopLiveFeed();
    const dom = getDom();
    window.requestAnimationFrame(() => {
      dom.consolePage?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return;
  }

  stopLiveFeed();
  if (!appState.currentData || appState.currentData.mode === "live") {
    try {
      await handleManualEvaluate();
    } catch (error) {
      showError(error.message);
    }
  } else if (appState.currentData) {
    renderDashboard(appState.currentData);
  }
}

async function bootstrap() {
  initializeUi();
  initializeCharts();
  renderBoardConsole();
  setActivePage(currentPage);
  updateModeButtons({ liveActive: false });

  try {
    const presetCatalog = await loadAnomalyPresets();
    renderPresetCatalog(presetCatalog.presets || []);
  } catch (error) {
    showPresetCatalogError(error.message);
  }

  try {
    await refreshBoardConsole();
  } catch (error) {
    showBoardConsoleError(error.message);
  }

  boardLogTimer = window.setInterval(async () => {
    try {
      await refreshBoardConsole();
    } catch (error) {
      showBoardConsoleError(error.message);
    }
  }, 2000);

  const dom = getDom();

  dom.navLiveButton.addEventListener("click", async () => {
    await showPage("live");
  });

  dom.navPresetButton.addEventListener("click", async () => {
    await showPage("preset");
  });

  dom.navConsoleButton.addEventListener("click", async () => {
    await showPage("console");
  });

  dom.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await handleManualEvaluate();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.liveButton.addEventListener("click", async () => {
    try {
      await handleToggleLiveFeed();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.resetOffsetsButton.addEventListener("click", async () => {
    try {
      await handleResetOffsets();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.applyOverrideButton.addEventListener("click", async () => {
    try {
      await handleApplyOverride();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.clearOverrideButton.addEventListener("click", async () => {
    try {
      await handleClearOverride();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.adjustButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await handleAdjust(button.dataset.adjustField, button.dataset.adjustDelta);
      } catch (error) {
        showError(error.message);
      }
    });
  });

  dom.presetSelect.addEventListener("change", () => {
    renderSelectedPresetPreview();
  });

  dom.applyPresetButton.addEventListener("click", async () => {
    try {
      await handlePresetApply(readSelectedPresetId());
    } catch (error) {
      showError(error.message);
    }
  });

  dom.consoleSendButton.addEventListener("click", async () => {
    try {
      await handleConsoleSend(readConsoleCommand());
    } catch (error) {
      showError(error.message);
    }
  });

  dom.consoleInterruptButton.addEventListener("click", async () => {
    try {
      await handleConsoleControl("interrupt");
    } catch (error) {
      showError(error.message);
    }
  });

  dom.consoleResetButton.addEventListener("click", async () => {
    try {
      await handleConsoleControl("soft_reset");
    } catch (error) {
      showError(error.message);
    }
  });

  dom.consoleCommandInput.addEventListener("keydown", async (event) => {
    if (event.key !== "Enter") {
      return;
    }
    event.preventDefault();
    try {
      await handleConsoleSend(readConsoleCommand());
    } catch (error) {
      showError(error.message);
    }
  });

  await showPage("live");
}

bootstrap();
