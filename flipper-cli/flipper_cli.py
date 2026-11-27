#!/usr/bin/env python3
"""One-shot Flipper CLI command sender (no interactive miniterm needed).
Usage: FLIPPER_PORT=/dev/cu.usbmodemflip_<name>1 flipper_cli.py "loader close"
       flipper_cli.py "loader open /ext/apps/rfid/fmps_cxt.fap"
Needs pyserial. Without FLIPPER_PORT, uses the first /dev/cu.usbmodemflip_*.
"""
import glob
import os
import sys
import time
import serial

PORT = os.environ.get("FLIPPER_PORT") or next(iter(sorted(glob.glob("/dev/cu.usbmodemflip_*"))), "")
BAUD = 230400


def send(cmd, wait=0.6):
    s = serial.Serial(PORT, BAUD, timeout=2)
    time.sleep(0.3)
    s.write(b"\r\n")
    time.sleep(0.2)
    s.read(s.in_waiting or 1)
    s.write(cmd.encode() + b"\r\n")
    time.sleep(wait)
    out = s.read(s.in_waiting or 1)
    s.close()
    return out.decode(errors="replace")


if __name__ == "__main__":
    print(send(" ".join(sys.argv[1:])))
