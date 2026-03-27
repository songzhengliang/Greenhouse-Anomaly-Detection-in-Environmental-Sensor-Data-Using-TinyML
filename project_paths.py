from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
MODELS_DIR = ROOT / "models"
DASHBOARD_DIR = ROOT / "dashboard"
DOCUMENTS_DIR = ROOT / "documents"

ACTION_DATASET_FILE = DATA_DIR / "greenhouse_action_control_dataset.csv"
ANOMALY_DATASET_FILE = DATA_DIR / "greenhouse_anomaly_dataset.csv"
LEGACY_AIR_QUALITY_DATASET_FILE = DATA_DIR / "greenhouse_air_quality_dataset.csv"

ACTION_MODEL_FILE = MODELS_DIR / "action_model.pkl"
ACTION_MODEL_METRICS_FILE = MODELS_DIR / "action_model_metrics.json"
ANOMALY_MODEL_FILE = MODELS_DIR / "anomaly_model.pkl"
ANOMALY_MODEL_METRICS_FILE = MODELS_DIR / "anomaly_model_metrics.json"
BOARD_MODEL_METRICS_FILE = MODELS_DIR / "board_model_metrics.json"


def ensure_parent_dir(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_standard_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
