#!/usr/bin/env python3
"""
Offline byte-level SPI decoder for capture.py's digital.csv - reconstructs
CS-gated bursts into MOSI/MISO byte streams (mode 0, MSB-first, matching the
capture.py channel map: ch0=MOSI ch1=MISO ch2=CLK ch3=CS active-low),
then applies the real CEP wire framing to find badlen-equivalent events:
sync discard (0x55) -> 2-byte length prefix (LE) -> PM3a/PM3b magic expected
immediately after. See proxmark5_com.c for the real sender-side
framing this mirrors (Proxmark5_FlipperZero_FAP), and
../pm3_frames.py for the shared magic/length layout.

Usage:
    python3 spi_decode.py <digital.csv> [--all]

Without --all, only prints bursts where the MOSI stream's length-prefix
check fails (implausible length, or magic not found where expected) -
the wire-level equivalent of the firmware's own badlen check.
"""
import sys
import csv
import os
import struct

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import pm3_frames

CH_MOSI, CH_MISO, CH_CLK, CH_CS = 0, 1, 2, 3
SYNC_BYTE = 0x55
PM3_CMD_DATA_SIZE = 4064


def load_rows(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            t = float(row[0])
            chans = tuple(int(x) for x in row[1:9])
            yield t, chans


def extract_bursts(rows):
    """Yield (cs_low_start, cs_high_end, mosi_bytes, mosi_times, miso_bytes)
    per CS-low burst. mosi_times[i] = (start, end) for mosi_bytes[i]."""
    state = None
    in_burst = False
    burst_start = None
    mosi_bits = []
    miso_bits = []
    mosi_bit_times = []
    mosi_bytes = bytearray()
    miso_bytes = bytearray()
    mosi_byte_times = []
    bit_start_time = None

    for t, chans in rows:
        prev = state
        state = chans
        if prev is None:
            continue
        cs_prev, cs_now = prev[CH_CS], chans[CH_CS]
        clk_prev, clk_now = prev[CH_CLK], chans[CH_CLK]

        if cs_prev == 1 and cs_now == 0:
            in_burst = True
            burst_start = t
            mosi_bits.clear()
            miso_bits.clear()
            mosi_bytes = bytearray()
            miso_bytes = bytearray()
            mosi_byte_times = []
            bit_start_time = None
            continue

        if in_burst and clk_prev == 0 and clk_now == 1:
            if not mosi_bits:
                bit_start_time = t
            mosi_bits.append(chans[CH_MOSI])
            miso_bits.append(chans[CH_MISO])
            if len(mosi_bits) == 8:
                mbyte = 0
                sbyte = 0
                for b in mosi_bits:
                    mbyte = (mbyte << 1) | b
                for b in miso_bits:
                    sbyte = (sbyte << 1) | b
                mosi_bytes.append(mbyte)
                miso_bytes.append(sbyte)
                mosi_byte_times.append((bit_start_time, t))
                mosi_bits.clear()
                miso_bits.clear()

        if cs_prev == 0 and cs_now == 1:
            if in_burst:
                yield burst_start, t, bytes(mosi_bytes), mosi_byte_times, bytes(miso_bytes)
            in_burst = False


def check_frame(mosi_bytes):
    """Skip leading sync bytes, read the 2-byte length prefix, check the
    magic lands where it should. Returns a dict describing what happened."""
    i = 0
    n = len(mosi_bytes)
    while i < n and mosi_bytes[i] == SYNC_BYTE:
        i += 1
    sync_count = i
    if i + 2 > n:
        return {"ok": None, "reason": "truncated (no length prefix)", "sync_count": sync_count}
    declared_len = mosi_bytes[i] | (mosi_bytes[i + 1] << 8)
    if declared_len == 0xFFFF:
        # FAP's dummy-poll bytes when it has nothing to send - firmware
        # already treats this as benign (data_len == 0xFFFF check), not a
        # desync. Match that here so it doesn't drown out real corruption.
        return {"ok": True, "sync_count": sync_count, "declared_len": declared_len,
                "len_ok": True, "magic_off": None, "magic": None, "magic_ok": None,
                "dummy_poll": True}
    magic_off = i + 2
    magic = mosi_bytes[magic_off:magic_off + 4]
    magic_ok = magic == pm3_frames.CMD_MAGIC_LE
    len_ok = declared_len <= PM3_CMD_DATA_SIZE * 2
    ok = magic_ok and len_ok
    return {
        "ok": ok,
        "sync_count": sync_count,
        "declared_len": declared_len,
        "len_ok": len_ok,
        "magic_off": magic_off,
        "magic": magic,
        "magic_ok": magic_ok,
    }


def hexdump(b, start=0):
    return " ".join(f"{x:02x}" for x in b[start:start + 24])


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    show_all = "--all" in sys.argv[2:]

    rows = load_rows(path)
    total = 0
    bad = 0
    for start, end, mosi, mtimes, miso in extract_bursts(rows):
        total += 1
        if len(mosi) < 4:
            continue  # too short to be a real command burst (dummy-poll noise)
        result = check_frame(mosi)
        if result["ok"] and not show_all:
            continue
        if not result["ok"]:
            bad += 1
        tag = "OK" if result["ok"] else "BAD"
        print(f"\n=== burst #{total} [{tag}] t={start:.6f}-{end:.6f} "
              f"dur={1000*(end-start):.2f}ms mosi_bytes={len(mosi)} ===")
        print(f"  sync_count={result.get('sync_count')} "
              f"declared_len={result.get('declared_len')} "
              f"len_ok={result.get('len_ok')} magic={result.get('magic')!r} "
              f"magic_ok={result.get('magic_ok')}")
        sc = result.get("sync_count", 0)
        ctx_start = max(0, sc - 4)
        print(f"  mosi[{ctx_start}:{ctx_start+32}] = {hexdump(mosi, ctx_start)}")
        if mtimes:
            idx = min(sc, len(mtimes) - 1)
            print(f"  byte[{sc}] clocked at t={mtimes[idx][0]:.6f}")

    print(f"\n{total} bursts total ({total - bad}/{total} well-formed MOSI frames, {bad} bad)")


if __name__ == "__main__":
    main()
