from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Thresholds:
    temperature_low: float = 18.0
    temperature_high: float = 30.0
    humidity_low: float = 45.0
    humidity_high: float = 75.0
    co2_high: int = 1200

    @classmethod
    def from_mapping(cls, raw: dict | None) -> "Thresholds":
        defaults = cls()
        if not raw:
            return defaults

        return cls(
            temperature_low=float(raw.get("temperature_low", defaults.temperature_low)),
            temperature_high=float(raw.get("temperature_high", defaults.temperature_high)),
            humidity_low=float(raw.get("humidity_low", defaults.humidity_low)),
            humidity_high=float(raw.get("humidity_high", defaults.humidity_high)),
            co2_high=int(float(raw.get("co2_high", defaults.co2_high))),
        )


def _severity(level: str, gap: float, critical_gap: float) -> str:
    if level == "high":
        return "critical" if gap >= critical_gap else "warning"
    return "critical" if gap >= critical_gap else "warning"


def _promote_severity(current: str, incoming: str) -> str:
    rank = {"stable": 0, "warning": 1, "critical": 2}
    return incoming if rank[incoming] > rank[current] else current


def evaluate_greenhouse(
    temperature_c: float,
    humidity_pct: float,
    co2_ppm: float,
    thresholds: Thresholds | None = None,
) -> dict:
    thresholds = thresholds or Thresholds()
    sensors = {
        "temperature_c": round(float(temperature_c), 1),
        "humidity_pct": round(float(humidity_pct), 1),
        "co2_ppm": int(round(float(co2_ppm))),
    }

    actions = {
        "heater": {
            "key": "heater",
            "label": "Heater",
            "status": "idle",
            "active": False,
            "reason": "Temperature is inside the comfort band.",
        },
        "cooling_fan": {
            "key": "cooling_fan",
            "label": "Cooling Fan",
            "status": "idle",
            "active": False,
            "reason": "Cooling is not required.",
        },
        "ventilation": {
            "key": "ventilation",
            "label": "Ventilation",
            "status": "idle",
            "active": False,
            "reason": "Air exchange is not required right now.",
        },
        "mister": {
            "key": "mister",
            "label": "Misting System",
            "status": "idle",
            "active": False,
            "reason": "Humidity is inside the target band.",
        },
    }

    triggered_conditions = []
    overall_state = "stable"
    ventilation_reasons = []

    if sensors["temperature_c"] < thresholds.temperature_low:
        gap = thresholds.temperature_low - sensors["temperature_c"]
        severity = _severity("low", gap, critical_gap=4.0)
        overall_state = _promote_severity(overall_state, severity)
        actions["heater"].update(
            {
                "status": "heating",
                "active": True,
                "reason": (
                    f"Temperature is below {thresholds.temperature_low:.1f} C, "
                    "so the greenhouse should warm up."
                ),
            }
        )
        triggered_conditions.append(
            {
                "condition": "temperature_low",
                "label": "Temperature low",
                "severity": severity,
                "recommended_action": "Heating",
                "detail": f"{sensors['temperature_c']:.1f} C is below the configured minimum.",
            }
        )

    if sensors["temperature_c"] > thresholds.temperature_high:
        gap = sensors["temperature_c"] - thresholds.temperature_high
        severity = _severity("high", gap, critical_gap=4.0)
        overall_state = _promote_severity(overall_state, severity)
        actions["cooling_fan"].update(
            {
                "status": "cooling",
                "active": True,
                "reason": (
                    f"Temperature is above {thresholds.temperature_high:.1f} C, "
                    "so the fan should cool the greenhouse."
                ),
            }
        )
        ventilation_reasons.append("temperature is high")
        triggered_conditions.append(
            {
                "condition": "temperature_high",
                "label": "Temperature high",
                "severity": severity,
                "recommended_action": "Cooling / ventilation",
                "detail": f"{sensors['temperature_c']:.1f} C is above the configured maximum.",
            }
        )

    if sensors["humidity_pct"] < thresholds.humidity_low:
        gap = thresholds.humidity_low - sensors["humidity_pct"]
        severity = _severity("low", gap, critical_gap=10.0)
        overall_state = _promote_severity(overall_state, severity)
        actions["mister"].update(
            {
                "status": "misting",
                "active": True,
                "reason": (
                    f"Humidity is below {thresholds.humidity_low:.1f}%, "
                    "so the system should add moisture."
                ),
            }
        )
        triggered_conditions.append(
            {
                "condition": "humidity_low",
                "label": "Humidity low",
                "severity": severity,
                "recommended_action": "Misting",
                "detail": f"{sensors['humidity_pct']:.1f}% is below the configured minimum.",
            }
        )

    if sensors["humidity_pct"] > thresholds.humidity_high:
        gap = sensors["humidity_pct"] - thresholds.humidity_high
        severity = _severity("high", gap, critical_gap=10.0)
        overall_state = _promote_severity(overall_state, severity)
        ventilation_reasons.append("humidity is high")
        triggered_conditions.append(
            {
                "condition": "humidity_high",
                "label": "Humidity high",
                "severity": severity,
                "recommended_action": "Ventilation",
                "detail": f"{sensors['humidity_pct']:.1f}% is above the configured maximum.",
            }
        )

    if sensors["co2_ppm"] > thresholds.co2_high:
        gap = sensors["co2_ppm"] - thresholds.co2_high
        severity = _severity("high", gap, critical_gap=500.0)
        overall_state = _promote_severity(overall_state, severity)
        ventilation_reasons.append("CO2 is high")
        triggered_conditions.append(
            {
                "condition": "co2_high",
                "label": "CO2 high",
                "severity": severity,
                "recommended_action": "Ventilation",
                "detail": f"{sensors['co2_ppm']} ppm is above the configured ceiling.",
            }
        )

    if ventilation_reasons:
        actions["ventilation"].update(
            {
                "status": "ventilating",
                "active": True,
                "reason": "Ventilation is active because " + ", ".join(ventilation_reasons) + ".",
            }
        )

    active_actions = [item["status"] for item in actions.values() if item["active"]]
    if active_actions:
        summary = "Recommended virtual actions: " + ", ".join(active_actions) + "."
    else:
        summary = (
            "Conditions are within the configured greenhouse band. "
            "All virtual machines can remain idle."
        )

    return {
        "sensors": sensors,
        "thresholds": asdict(thresholds),
        "overall_state": overall_state,
        "summary": summary,
        "triggered_conditions": triggered_conditions,
        "actions": list(actions.values()),
    }
