#!/usr/bin/env python3
"""
Timed 8-channel/24MHz Logic 2 capture of the CEP SPI bus, with the SPI
analyzer and the PM3 CEP Frames HLA attached, exported as digital.csv into
./la_captures/<timestamp>_<label>/ (override with LA_CAPTURE_DIR).

Usage:
    python3 capture.py <label> [duration_seconds]

Requires Logic 2 running with Settings -> "Enable Automation Server"
checked (127.0.0.1:10430) and `pip install logic2-automation`.
"""
import sys
import datetime
import os
import time
from saleae import automation

OUTPUT_ROOT = os.environ.get("LA_CAPTURE_DIR", os.path.abspath("la_captures"))
HLA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    label = sys.argv[1]
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(OUTPUT_ROOT, f"{stamp}_{label}")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "README.txt"), "w") as f:
        f.write(f"{label}\ncaptured {stamp}, duration {duration}s\n")

    m = automation.Manager.connect(address="127.0.0.1", port=10430)
    dev = m.get_devices()[0]
    device_config = automation.LogicDeviceConfiguration(
        enabled_digital_channels=[0, 1, 2, 3, 4, 5, 6, 7],
        digital_sample_rate=24_000_000,
    )
    capture_config = automation.CaptureConfiguration(
        capture_mode=automation.TimedCaptureMode(duration_seconds=duration)
    )
    print(f"Capturing {duration}s to {outdir} ...")
    capture = m.start_capture(
        device_id=dev.device_id,
        device_configuration=device_config,
        capture_configuration=capture_config,
    )
    # Analyzers can't be added while recording, and the automation API
    # can't load a GUI preset, so attach them after the capture ends.
    capture.wait()
    spi = capture.add_analyzer(
        "SPI",
        label="SPI",
        settings={
            "MOSI": 0,
            "MISO": 1,
            "Clock": 2,
            "Enable": 3,
            "Significant Bit": 0,
            "Bits per Transfer": 8,
            "Clock State": 0,
            "Clock Phase": 0,
            "Enable Line": 0,
        },
    )
    time.sleep(1.0)
    capture.add_high_level_analyzer(
        os.path.abspath(HLA_DIR),
        "PM3 CEP Frames",
        input_analyzer=spi,
        label="PM3 CEP Frames",
    )
    capture.export_raw_data_csv(outdir, digital_channels=[0, 1, 2, 3, 4, 5, 6, 7])
    print(f"EXPORTED TO {outdir}")
    # Capture tab is left open on purpose so the decoded result can be
    # inspected in the GUI; Ctrl+C this script once it prints EXPORTED.


if __name__ == "__main__":
    main()
