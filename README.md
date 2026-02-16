# Solar Monitoring Project (Arduino + Raspberry Pi)

This repository provides a **fully local**, **real-time** solar panel monitoring system for a single PV panel (such as your ~550W bifacial module), using:

- **Arduino** for sensor acquisition
- **Raspberry Pi** for parsing, calculations, data logging, API, and web dashboard
- **Flask + Chart.js** for the live LAN dashboard

No cloud services are required.

---

## Table of Contents

1. [What this project does](#what-this-project-does)
2. [System architecture](#system-architecture)
3. [Hardware checklist](#hardware-checklist)
4. [Repository layout](#repository-layout)
5. [Step-by-step: full setup from zero](#step-by-step-full-setup-from-zero)
   - [Step 0: safety first](#step-0-safety-first)
   - [Step 1: wire the hardware](#step-1-wire-the-hardware)
   - [Step 2: configure and upload Arduino firmware](#step-2-configure-and-upload-arduino-firmware)
   - [Step 3: prepare Raspberry Pi software environment](#step-3-prepare-raspberry-pi-software-environment)
   - [Step 4: create runtime config](#step-4-create-runtime-config)
   - [Step 5: run the monitor backend](#step-5-run-the-monitor-backend)
   - [Step 6: open and use the dashboard](#step-6-open-and-use-the-dashboard)
   - [Step 7: calibrate for accurate measurements](#step-7-calibrate-for-accurate-measurements)
   - [Step 8: verify logs and API](#step-8-verify-logs-and-api)
6. [Detailed calibration guide](#detailed-calibration-guide)
7. [API reference](#api-reference)
8. [Operational workflow (daily use)](#operational-workflow-daily-use)
9. [Troubleshooting](#troubleshooting)
10. [Extending the project](#extending-the-project)

---

## What this project does

The system continuously measures and displays:

- Panel **voltage** (V)
- Panel **current** (A)
- Instantaneous **power** (W = V × I)
- Two temperatures (front and back): **DS18B20 #1** and **DS18B20 #2**
- **Daily cumulative energy** (Wh), integrated in real time from power/time

It also:

- Logs data to CSV on the Pi
- Exposes a JSON API endpoint (`/api/latest`)
- Provides a browser dashboard accessible on your local network

---

## System architecture

1. Arduino reads sensors every ~500 ms (~2 Hz).
2. Arduino sends one JSON line per sample over USB serial.
3. Pi backend (`pi/app.py`) reads serial lines, parses JSON, applies calibration, and calculates power + daily Wh.
4. Pi stores samples in RAM history buffer and appends samples to CSV.
5. Flask serves the dashboard and API.
6. Browser polls API every second and updates live cards + charts.

---

## Hardware checklist

### Core devices

- Solar panel (example: ~550W bifacial)
- Raspberry Pi (any model that can run Python 3 and Flask)
- Arduino (Uno/Nano/etc.)

### Sensors and interface modules

- ADS1115 (I2C, 16-bit ADC) for voltage-divider reading
- Hall-effect current sensor (e.g., ACS712 30A or ACS758 50A)
- 2 × DS18B20 waterproof digital temperature sensors
- Precision voltage divider resistors (example in code: 180k / 10k)

### Wiring/safety

- 15–20 A DC fuse on panel positive line
- Proper solar-rated wiring and MC4 connectors
- Shared reference ground where required by your measurement chain

### Software libraries used

Arduino:

- `Wire`
- `Adafruit_ADS1X15`
- `OneWire`
- `DallasTemperature`

Raspberry Pi Python:

- `Flask`
- `pyserial`
- `PyYAML`

Frontend:

- `Chart.js` (loaded from CDN)

---

## Repository layout

- `arduino/solar_monitor.ino` → Arduino firmware
- `pi/app.py` → Flask app + background collector + CSV logging
- `pi/calibrate.py` → calibration helper script
- `pi/config.sample.yaml` → template runtime config
- `pi/templates/index.html` → dashboard HTML
- `pi/static/style.css` → dashboard styling
- `pi/static/app.js` → dashboard behavior/charts
- `pi/requirements.txt` → Python dependencies

---

## Step-by-step: full setup from zero

## Step 0: safety first

Before connecting or testing:

1. Disconnect panel from active load path while assembling measurement wiring.
2. Install the DC fuse on panel positive before the rest of downstream electronics.
3. Verify voltage divider output can **never** exceed your ADC safe input range.
4. Verify common grounds and isolation strategy according to your exact hardware.
5. Double-check all polarity before energizing.

> This project is software + integration guidance and does not replace electrical safety procedures for PV systems.

---

## Step 1: wire the hardware

Use this as the baseline wiring map.

### 1.1 ADS1115 voltage measurement path

- Panel voltage goes through your resistor divider.
- Divider output connects to **ADS1115 A0**.
- ADS1115 `VDD` and `GND` power as required by your controller setup.
- ADS1115 `SDA/SCL` connect to Arduino `SDA/SCL`.
- Ensure ADS1115 full-scale gain setting is appropriate (firmware uses `GAIN_ONE`, ±4.096V range).

### 1.2 Current sensor path

- Place Hall sensor in series with panel/load branch you want to monitor.
- Current sensor analog output -> Arduino `A0`.
- Sensor supply and ground wired per sensor datasheet.

### 1.3 Temperature sensors

- DS18B20 data line -> Arduino `D2` (`ONE_WIRE_BUS = 2` in firmware).
- Add required pull-up resistor for OneWire bus (typically 4.7k to Vcc).
- Use two probes physically mounted at:
  - Front glass edge area
  - Backsheet area

### 1.4 USB link

- Arduino USB -> Raspberry Pi USB
- This is the serial channel used by `pi/app.py`

---

## Step 2: configure and upload Arduino firmware

File: `arduino/solar_monitor.ino`

### 2.1 Open firmware

1. Launch Arduino IDE.
2. Open `arduino/solar_monitor.ino`.

### 2.2 Install Arduino libraries (if missing)

Install via Library Manager:

- Adafruit ADS1X15
- OneWire
- DallasTemperature

### 2.3 Check editable constants

In firmware, review these values and adjust for your hardware:

- `dividerRatio` (default 19.0 for 180k:10k divider)
- Current sensor parameters:
  - `currentZeroVolts`
  - `currentMvPerAmp` (default 66 mV/A for ACS712-30A style)
- Sample rate (`SAMPLE_INTERVAL_MS` = 500 ms)

### 2.4 Select board and port, then upload

1. Tools -> Board -> your Arduino model
2. Tools -> Port -> Arduino serial port
3. Upload

### 2.5 Verify serial output

Open serial monitor at **115200 baud**. You should see JSON lines like:

```json
{"type":"sample","uptime_ms":123456,"voltage_v":41.234,"current_a":7.893,"power_w":325.511,"temp_front_c":48.25,"temp_back_c":52.50}
```

You may also see startup events (sensor IDs, calibration events).

---

## Step 3: prepare Raspberry Pi software environment

### 3.1 Enter project folder

```bash
cd /workspace/project/pi
```

(Use your actual clone path on the Pi.)

### 3.2 Create a Python virtual environment

```bash
python3 -m venv .venv
```

### 3.3 Activate environment

```bash
source .venv/bin/activate
```

### 3.4 Install dependencies

```bash
pip install -r requirements.txt
```

If needed, equivalent explicit install:

```bash
pip install flask pyserial pyyaml
```

---

## Step 4: create runtime config

### 4.1 Copy sample config

```bash
cp config.sample.yaml config.yaml
```

### 4.2 Edit config

Open `config.yaml` and verify:

- `serial.port` (example `/dev/ttyACM0` or `/dev/ttyUSB0`)
- `baudrate` (`115200` should match Arduino)
- `sampling.max_buffer_points`
- Calibration fields (`voltage_gain`, `current_gain`, offsets)
- CSV path (`logging.csv_path`)
- Server bind (`host`, `port`)

Tip: on Linux, discover serial ports with:

```bash
ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

---

## Step 5: run the monitor backend

From `pi/` directory with venv active:

```bash
python app.py
```

Expected behavior:

- Flask starts listening (default `0.0.0.0:5000`)
- Background collector tries serial connection
- Incoming samples are logged to CSV

If serial is disconnected, app keeps running and reports stale/error status through API.

---

## Step 6: open and use the dashboard

### 6.1 Find Pi IP address

On Pi:

```bash
hostname -I
```

### 6.2 Open dashboard from laptop/phone on same LAN

Navigate to:

```text
http://<pi-ip>:5000
```

### 6.3 What you should see

- Live cards:
  - Voltage (V)
  - Current (A)
  - Power (W)
  - Front Temp (°C)
  - Back Temp (°C)
  - Daily Energy (Wh)
- Two live charts:
  - Power vs time
  - Voltage vs time
- Status message:
  - `Live` when data is fresh
  - stale warning when samples stop arriving

---

## Step 7: calibrate for accurate measurements

Use `pi/calibrate.py`.

### 7.1 Zero current (no current flowing)

```bash
python calibrate.py --port /dev/ttyACM0 --zero-current
```

This sends `CAL_ZERO` to Arduino; Arduino measures sensor midpoint and updates zero internally.

### 7.2 Voltage gain calibration

1. Measure true panel voltage with multimeter.
2. Compare against dashboard value.
3. Run:

```bash
python calibrate.py --measured-voltage <multimeter_value> --reported-voltage <dashboard_value>
```

4. Copy suggested gain into `config.yaml` under:

```yaml
calibration:
  voltage_gain: <suggested_value>
```

### 7.3 Current gain calibration

1. Measure true current with trusted meter/reference.
2. Compare against dashboard value.
3. Run:

```bash
python calibrate.py --measured-current <reference_value> --reported-current <dashboard_value>
```

4. Copy suggested gain into `config.yaml`:

```yaml
calibration:
  current_gain: <suggested_value>
```

### 7.4 Optional offset trims

If you observe consistent non-zero bias after gain tuning, use:

- `voltage_offset`
- `current_offset`

in `config.yaml`.

### 7.5 Restart backend after config changes

Stop and rerun:

```bash
python app.py
```

---

## Step 8: verify logs and API

### 8.1 Verify CSV log file

Default path: `pi/data/solar_log.csv` (relative to where you run app)

Check recent rows:

```bash
tail -n 5 data/solar_log.csv
```

### 8.2 Verify API endpoint

From Pi or any LAN machine that can reach Pi:

```bash
curl http://<pi-ip>:5000/api/latest
```

### 8.3 Verify health endpoint

```bash
curl http://<pi-ip>:5000/health
```

Expected:

```json
{"ok": true}
```

---

## Detailed calibration guide

Calibration happens in two places:

1. **Arduino-level sensor behavior**
   - Real-time sensor signal conversion (divider ratio, mV/A, zero current)
2. **Pi-level post-processing calibration**
   - Gain/offset correction in `config.yaml`

Recommended order:

1. Verify wiring and safe signal ranges.
2. Perform Arduino `CAL_ZERO` with no current.
3. Run system under stable known conditions.
4. Tune voltage gain.
5. Tune current gain.
6. Apply small offsets only if persistent bias remains.
7. Re-validate at low and high operating points.

---

## API reference

### `GET /api/latest`

Returns JSON with keys:

- `latest`: newest sample object or `null`
- `history`: list of buffered sample objects
- `status`:
  - `stale` (boolean)
  - `last_error` (string or `null`)

Sample shape:

```json
{
  "timestamp": "2026-01-01T12:34:56",
  "voltage_v": 41.2,
  "current_a": 8.1,
  "power_w": 333.72,
  "temp_front_c": 46.5,
  "temp_back_c": 51.2,
  "energy_wh_day": 1287.4
}
```

### `GET /health`

Basic liveness check.

---

## Operational workflow (daily use)

A practical daily routine:

1. Power up Arduino and Pi.
2. Confirm Arduino is connected to expected serial port.
3. Start backend (`python app.py`).
4. Open dashboard from laptop.
5. Confirm status is `Live` and values are changing.
6. Let system run; CSV accumulates throughout day.
7. At day rollover, energy counter resets automatically.
8. Archive CSV periodically if long-term storage is desired.

---

## Troubleshooting

### Problem: dashboard shows “Waiting for incoming samples...”

- Arduino may not be sending valid JSON sample lines.
- Serial port in `config.yaml` may be wrong.
- Baud mismatch (must be 115200 by default).

### Problem: stale warning

- Serial cable disconnected/intermittent.
- Arduino reset or locked.
- Collector serial exception (check terminal logs).

### Problem: voltage/current clearly off

- Wrong divider ratio.
- Wrong Hall sensor mV/A constant.
- Missing zero-current calibration.
- Gain/offset not tuned in `config.yaml`.

### Problem: DS18B20 invalid readings

- Check OneWire pull-up resistor.
- Check sensor wiring and address detection output.
- Confirm at least two sensors are detected at startup.

### Problem: cannot open dashboard from LAN

- Confirm Flask host is `0.0.0.0`.
- Verify Pi IP address and network connectivity.
- Check firewall/router restrictions on port 5000.

---

## Extending the project

Possible enhancements:

- Add persistent database (SQLite/InfluxDB) for long-term analytics
- Add daily/monthly report exports
- Add min/max/average stats cards
- Add watchdog/systemd service for auto-start on boot
- Add sensor fault flags and alerting logic

---

If you want, the next improvement can be a **systemd service setup guide** so the monitor auto-starts after every Pi reboot.
