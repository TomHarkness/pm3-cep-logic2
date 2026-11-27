"""Saleae High-Level Analyzer: Proxmark3 NG command/response frames layered
on the built-in SPI analyzer (PM5 <-> Flipper Zero CEP link).

Attach to an SPI analyzer (mode 0, MSB first, 8 bits, CS active low). MOSI
carries commands (Flipper -> PM5), MISO carries responses (PM5 -> Flipper).
"""
from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame

import pm3_frames


class Pm3Hla(HighLevelAnalyzer):
    result_types = {
        "pm3_cmd": {"format": "CMD {{data.name}} len={{data.length}}"},
        "pm3_resp": {"format": "RESP {{data.name}} st={{data.status}} len={{data.length}}"},
    }

    def __init__(self):
        self._reset()

    def _reset(self):
        # Per-CS-burst accumulators; the SPI analyzer resets alignment each
        # time CS asserts, so do we.
        self._mosi = bytearray()
        self._miso = bytearray()
        self._mosi_t = []   # (start, end) per MOSI byte
        self._miso_t = []
        self._emitted = {"c": 0, "r": 0}  # offset past the last frame already annotated

    def decode(self, frame):
        if frame.type == "enable":
            self._reset()
            return None
        if frame.type != "result":
            return None

        out = []
        mosi = frame.data.get("mosi")
        miso = frame.data.get("miso")
        if mosi is not None:
            self._mosi += bytes(mosi)
            self._mosi_t.append((frame.start_time, frame.end_time))
            out += self._emit(self._mosi, self._mosi_t, False)
        if miso is not None:
            self._miso += bytes(miso)
            self._miso_t.append((frame.start_time, frame.end_time))
            out += self._emit(self._miso, self._miso_t, True)
        return out or None

    def _emit(self, buf, times, is_response):
        key = "r" if is_response else "c"
        emitted_until = self._emitted[key]
        out = []
        for f in pm3_frames.scan_frames(bytes(buf), is_response):
            if (not f["complete"]) or f["off"] < emitted_until:
                continue
            last = f["off"] + f["total"] - 1
            if last >= len(times):
                continue  # frame not fully clocked in / timestamped yet
            emitted_until = f["off"] + f["total"]
            data = {"name": f["name"], "cmd": "0x%04X" % f["cmd"], "length": f["length"]}
            if is_response:
                data["status"] = f["status"]
                data["reason"] = f["reason"]
                out.append(AnalyzerFrame("pm3_resp", times[f["off"]][0], times[last][1], data))
            else:
                out.append(AnalyzerFrame("pm3_cmd", times[f["off"]][0], times[last][1], data))
        self._emitted[key] = emitted_until
        return out
