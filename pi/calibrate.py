"""Calibration helper for the Arduino + Pi solar monitor.

Usage examples:
  python calibrate.py --port /dev/ttyACM0 --zero-current
  python calibrate.py --measured-voltage 38.4 --reported-voltage 37.9
  python calibrate.py --measured-current 8.3 --reported-current 7.9
"""

from __future__ import annotations

import argparse

import serial


def calc_gain(measured: float, reported: float) -> float:
    if reported == 0:
        raise ValueError("Reported value cannot be 0.")
    return measured / reported


def send_command(port: str, baudrate: int, command: str) -> None:
    with serial.Serial(port=port, baudrate=baudrate, timeout=2) as ser:
        ser.reset_input_buffer()
        ser.write((command + "\n").encode("utf-8"))
        reply = ser.readline().decode("utf-8", errors="replace").strip()
        print(f"Device reply: {reply}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--zero-current", action="store_true")
    parser.add_argument("--measured-voltage", type=float)
    parser.add_argument("--reported-voltage", type=float)
    parser.add_argument("--measured-current", type=float)
    parser.add_argument("--reported-current", type=float)
    args = parser.parse_args()

    if args.zero_current:
        send_command(args.port, args.baudrate, "CAL_ZERO")

    if args.measured_voltage is not None and args.reported_voltage is not None:
        v_gain = calc_gain(args.measured_voltage, args.reported_voltage)
        print(f"Suggested calibration.voltage_gain = {v_gain:.6f}")

    if args.measured_current is not None and args.reported_current is not None:
        i_gain = calc_gain(args.measured_current, args.reported_current)
        print(f"Suggested calibration.current_gain = {i_gain:.6f}")


if __name__ == "__main__":
    main()
