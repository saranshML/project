# Solar Monitoring Project (Arduino + Raspberry Pi)

This repository contains a complete local solar panel monitoring stack:

- `arduino/solar_monitor.ino`: Reads ADS1115 voltage, Hall current sensor, and two DS18B20 temperatures. Streams JSON at ~2 Hz.
- `pi/app.py`: Flask app with a background collector thread that parses serial JSON, applies calibration, computes power and daily Wh, and logs CSV.
- `pi/templates/index.html` + `pi/static/*`: Real-time dashboard with Chart.js.
- `pi/calibrate.py`: Calibration helper utility.
- `pi/config.sample.yaml`: Editable runtime configuration template.

## 1) Arduino wiring notes

- ADS1115 A0 <= voltage divider output from panel positive (panel negative common ground).
- Current sensor analog output => Arduino `A0`.
- DS18B20 data => Arduino `D2` (with pull-up resistor).
- Keep sensor and ADC grounds shared.
- Add 15–20 A DC fuse on panel positive line.

## 2) Arduino output format

Sample line emitted over serial:

```json
{"type":"sample","uptime_ms":123456,"voltage_v":41.234,"current_a":7.893,"power_w":325.511,"temp_front_c":48.25,"temp_back_c":52.50}
```

## 3) Raspberry Pi setup

```bash
cd pi
python3 -m venv .venv
source .venv/bin/activate
pip install flask pyserial pyyaml
cp config.sample.yaml config.yaml
python app.py
```

Open `http://<pi-ip>:5000` from your laptop on the same LAN.

## 4) Calibration flow

1. With no current flowing, run:
   ```bash
   python pi/calibrate.py --port /dev/ttyACM0 --zero-current
   ```
2. Compare dashboard voltage to a multimeter and compute gain:
   ```bash
   python pi/calibrate.py --measured-voltage 38.40 --reported-voltage 37.90
   ```
3. Compare current against reference and compute gain:
   ```bash
   python pi/calibrate.py --measured-current 8.30 --reported-current 7.90
   ```
4. Write suggested gains into `pi/config.yaml` under `calibration`.

## 5) API endpoint

- `GET /api/latest` returns:
  - `latest`: newest sample
  - `history`: in-memory time-series buffer
  - `status`: stale flag and last collector error

## 6) Notes

- Daily energy (`Wh`) is integrated from power over sample time deltas.
- Counter resets automatically at local date rollover.
- No cloud dependency; all processing/logging is local.
