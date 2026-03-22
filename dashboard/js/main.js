import {
  loadBoardLogs,
  evaluateManualScenario,
  loadDemoScenario,
  loadLiveScenario,
  pushPresentationState,
} from "./api.js";
import { initializeCharts, renderCharts } from "./charts.js";
import {
  initializeUi,
  readManualPayload,
  readOverridePayload,
  renderBoardConsole,
  renderDashboard,
  showBoardConsoleError,
  showError,
  updateModeButtons,
  getDom,
} from "./ui.js";
import { addHistoryPoint, appState, setBoardConsole, setCurrentData } from "./store.js";

let demoTimer = null;
let liveTimer = null;
let boardLogTimer = null;

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

function stopDemoStream() {
  if (demoTimer) {
    clearInterval(demoTimer);
    demoTimer = null;
    updateModeButtons({ liveActive: Boolean(liveTimer), demoActive: false });
  }
}

function stopLiveFeed() {
  if (liveTimer) {
    clearInterval(liveTimer);
    liveTimer = null;
    updateModeButtons({ liveActive: false, demoActive: Boolean(demoTimer) });
  }
}

async function handleManualEvaluate() {
  stopDemoStream();
  stopLiveFeed();
  const data = await evaluateManualScenario(readManualPayload());
  applyData(data);
}

async function handleDemoLoad() {
  stopLiveFeed();
  const data = await loadDemoScenario();
  applyData(data);
}

async function handleLiveLoad() {
  const data = await loadLiveScenario();
  applyData(data);
}

async function handleToggleDemoStream() {
  if (demoTimer) {
    stopDemoStream();
    return;
  }

  stopLiveFeed();
  await handleDemoLoad();
  demoTimer = window.setInterval(async () => {
    try {
      await handleDemoLoad();
    } catch (error) {
      showError(error.message);
    }
  }, 2500);
  updateModeButtons({ liveActive: false, demoActive: true });
}

async function handleToggleLiveFeed() {
  if (liveTimer) {
    stopLiveFeed();
    return;
  }

  stopDemoStream();
  await handleLiveLoad();
  liveTimer = window.setInterval(async () => {
    try {
      await handleLiveLoad();
    } catch (error) {
      showError(error.message);
    }
  }, 3000);
  updateModeButtons({ liveActive: true, demoActive: false });
}

function currentPresentationPayload(override = appState.currentPresentation.override) {
  return {
    offsets: appState.currentPresentation.offsets,
    override,
  };
}

async function handleAdjust(field, delta) {
  stopDemoStream();
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
  stopDemoStream();
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
  stopDemoStream();
  const data = await pushPresentationState(currentPresentationPayload(readOverridePayload()));
  applyData(data);
}

async function handleClearOverride() {
  stopDemoStream();
  const data = await pushPresentationState(currentPresentationPayload(null));
  applyData(data);
}

async function bootstrap() {
  initializeUi();
  initializeCharts();
  renderBoardConsole();
  updateModeButtons({ liveActive: false, demoActive: false });

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

  dom.form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await handleManualEvaluate();
    } catch (error) {
      showError(error.message);
    }
  });

  dom.demoButton.addEventListener("click", async () => {
    try {
      await handleDemoLoad();
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

  dom.autoplayButton.addEventListener("click", async () => {
    try {
      await handleToggleDemoStream();
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

  try {
    await handleDemoLoad();
  } catch (error) {
    showError(error.message);
  }
}

bootstrap();
