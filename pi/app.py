from __future__ import annotations

import csv
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime, date
from pathlib import Path
from typing import Deque, Dict, Optional

import serial
import yaml
from flask import Flask, jsonify, render_template


@dataclass
class Sample:
    timestamp: str
    voltage_v: float
    current_a: float
    power_w: float
    temp_front_c: float
    temp_back_c: float
    energy_wh_day: float


class SolarCollector:
    def __init__(self, config: Dict):
        self.config = config
        self._lock = threading.Lock()
        self._latest: Optional[Sample] = None
        self._history: Deque[Sample] = deque(maxlen=config["sampling"]["max_buffer_points"])
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._energy_wh_day = 0.0
        self._last_sample_ts: Optional[datetime] = None
        self._day_marker = date.today()
        self._last_error: Optional[str] = None
        self._serial: Optional[serial.Serial] = None

        csv_path = Path(config["logging"]["csv_path"])
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.csv_path = csv_path
        self._ensure_csv_header()

    def _ensure_csv_header(self) -> None:
        if self.csv_path.exists() and self.csv_path.stat().st_size > 0:
            return
        with self.csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    "timestamp",
                    "voltage_v",
                    "current_a",
                    "power_w",
                    "temp_front_c",
                    "temp_back_c",
                    "energy_wh_day",
                ]
            )

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self._serial and self._serial.is_open:
            self._serial.close()

    def _connect(self) -> None:
        serial_cfg = self.config["serial"]
        self._serial = serial.Serial(
            port=serial_cfg["port"],
            baudrate=serial_cfg["baudrate"],
            timeout=serial_cfg["timeout_s"],
        )
        self._serial.reset_input_buffer()

    def _apply_calibration(self, payload: Dict) -> Dict:
        cal = self.config["calibration"]
        payload["voltage_v"] = payload["voltage_v"] * cal["voltage_gain"] + cal["voltage_offset"]
        payload["current_a"] = payload["current_a"] * cal["current_gain"] + cal["current_offset"]
        payload["power_w"] = payload["voltage_v"] * payload["current_a"]
        return payload

    def _integrate_energy(self, ts: datetime, power_w: float) -> float:
        if ts.date() != self._day_marker:
            self._day_marker = ts.date()
            self._energy_wh_day = 0.0
            self._last_sample_ts = None

        if self._last_sample_ts is not None:
            dt_h = (ts - self._last_sample_ts).total_seconds() / 3600.0
            if 0 <= dt_h <= 1:
                self._energy_wh_day += power_w * dt_h

        self._last_sample_ts = ts
        return self._energy_wh_day

    def _append_csv(self, sample: Sample) -> None:
        with self.csv_path.open("a", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [
                    sample.timestamp,
                    f"{sample.voltage_v:.4f}",
                    f"{sample.current_a:.4f}",
                    f"{sample.power_w:.4f}",
                    f"{sample.temp_front_c:.3f}",
                    f"{sample.temp_back_c:.3f}",
                    f"{sample.energy_wh_day:.6f}",
                ]
            )

    def _run(self) -> None:
        while self._running:
            try:
                if self._serial is None or not self._serial.is_open:
                    self._connect()

                raw = self._serial.readline().decode("utf-8", errors="replace").strip()
                if not raw:
                    continue

                payload = json.loads(raw)
                if payload.get("type") != "sample":
                    continue

                payload = self._apply_calibration(payload)
                ts = datetime.now()
                energy_wh = self._integrate_energy(ts, payload["power_w"])

                sample = Sample(
                    timestamp=ts.isoformat(timespec="seconds"),
                    voltage_v=payload["voltage_v"],
                    current_a=payload["current_a"],
                    power_w=payload["power_w"],
                    temp_front_c=payload["temp_front_c"],
                    temp_back_c=payload["temp_back_c"],
                    energy_wh_day=energy_wh,
                )

                with self._lock:
                    self._latest = sample
                    self._history.append(sample)
                    self._last_error = None

                self._append_csv(sample)

            except (json.JSONDecodeError, KeyError):
                continue
            except serial.SerialException as exc:
                self._last_error = f"Serial error: {exc}"
                time.sleep(2)
                if self._serial and self._serial.is_open:
                    self._serial.close()
            except Exception as exc:  # keep daemon alive
                self._last_error = f"Collector error: {exc}"
                time.sleep(1)

    def snapshot(self) -> Dict:
        with self._lock:
            latest = asdict(self._latest) if self._latest else None
            history = [asdict(s) for s in self._history]
            last_error = self._last_error

        stale = True
        if latest:
            ts = datetime.fromisoformat(latest["timestamp"])
            stale = (datetime.now() - ts).total_seconds() > self.config["sampling"]["stale_after_s"]

        return {
            "latest": latest,
            "history": history,
            "status": {
                "stale": stale,
                "last_error": last_error,
            },
        }


def load_config() -> Dict:
    config_path = Path(os.environ.get("SOLAR_CONFIG", "config.yaml"))
    with config_path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def create_app() -> Flask:
    config = load_config()
    app = Flask(__name__)
    collector = SolarCollector(config)
    collector.start()

    @app.route("/")
    def dashboard():
        return render_template("index.html")

    @app.route("/api/latest")
    def api_latest():
        return jsonify(collector.snapshot())

    @app.route("/health")
    def health():
        return jsonify({"ok": True})

    return app


if __name__ == "__main__":
    cfg = load_config()
    flask_app = create_app()
    flask_app.run(host=cfg["server"]["host"], port=cfg["server"]["port"], debug=cfg["server"]["debug"])
