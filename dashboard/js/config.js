export const HISTORY_WINDOW_MS = 5 * 60 * 1000;

export const SENSOR_CONFIG = {
  temperature_c: {
    label: "Temperature",
    unit: "C",
    decimals: 1,
    chartId: "temperatureChart",
    displayedId: "metric-temperature",
    rawId: "raw-temperature",
    offsetId: "offset-temperature",
    color: "#2e7d50",
    fill: "rgba(46, 125, 80, 0.16)",
  },
  humidity_pct: {
    label: "Humidity",
    unit: "%",
    decimals: 1,
    chartId: "humidityChart",
    displayedId: "metric-humidity",
    rawId: "raw-humidity",
    offsetId: "offset-humidity",
    color: "#0f6c85",
    fill: "rgba(15, 108, 133, 0.16)",
  },
  co2_ppm: {
    label: "CO2",
    unit: "ppm",
    decimals: 0,
    chartId: "co2Chart",
    displayedId: "metric-co2",
    rawId: "raw-co2",
    offsetId: "offset-co2",
    color: "#b86a1f",
    fill: "rgba(184, 106, 31, 0.16)",
  },
};
