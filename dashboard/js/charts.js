import { SENSOR_CONFIG } from "./config.js";
import { appState } from "./store.js";

const charts = {};

function chartOptions(config) {
  return {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          data: [],
          borderColor: config.color,
          backgroundColor: config.fill,
          borderWidth: 3,
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHitRadius: 10,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          displayColors: false,
          callbacks: {
            label(context) {
              const value = Number(context.parsed.y);
              const digits = config.decimals;
              return `${config.label}: ${value.toFixed(digits)} ${config.unit}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: {
            display: false,
          },
          ticks: {
            color: "#6b7a70",
            maxTicksLimit: 5,
          },
        },
        y: {
          beginAtZero: false,
          grid: {
            color: "rgba(35, 49, 37, 0.08)",
          },
          ticks: {
            color: "#6b7a70",
          },
        },
      },
    },
  };
}

export function initializeCharts() {
  Object.entries(SENSOR_CONFIG).forEach(([field, config]) => {
    const canvas = document.getElementById(config.chartId);
    const context = canvas.getContext("2d");
    charts[field] = new Chart(context, chartOptions(config));
  });
}

export function renderCharts() {
  Object.keys(SENSOR_CONFIG).forEach((field) => {
    const chart = charts[field];
    const history = appState.history[field];
    chart.data.labels = history.map((point) => point.label);
    chart.data.datasets[0].data = history.map((point) => point.value);
    chart.update("none");
  });
}
