#!/usr/bin/env python3
"""
Cluster a capture.py digital.csv's sparse transition list into discrete
SPI transactions ("bursts"), and report the idle gap between each burst -
i.e. the Flipper RX thread's actual poll period on the bus.

Usage:
    python3 find_burst.py <digital.csv> [gap_threshold_ms]

gap_threshold_ms (default 5.0): any inter-transition gap larger than this
closes the current burst and opens a new one. Must be smaller than the
fastest real poll period you're trying to measure, or back-to-back polls
collapse into one burst.
"""
import sys
import csv


def load_transitions(path):
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        for row in reader:
            yield float(row[0])


def cluster_bursts(times, gap_threshold_s):
    bursts = []
    burst_start = burst_end = None
    n = 0
    for t in times:
        if burst_start is None:
            burst_start = burst_end = t
            n = 1
            continue
        if t - burst_end > gap_threshold_s:
            bursts.append((burst_start, burst_end, n))
            burst_start = t
            n = 0
        burst_end = t
        n += 1
    if burst_start is not None:
        bursts.append((burst_start, burst_end, n))
    return bursts


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    csv_path = sys.argv[1]
    gap_threshold_ms = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    times = list(load_transitions(csv_path))
    bursts = cluster_bursts(times, gap_threshold_ms / 1000.0)

    print(f"{len(bursts)} bursts (gap threshold {gap_threshold_ms}ms)\n")
    print(f"{'#':>4}  {'start_s':>12}  {'dur_ms':>8}  {'edges':>6}  {'gap_to_next_ms':>15}")
    for i, (start, end, n) in enumerate(bursts):
        dur_ms = (end - start) * 1000.0
        if i + 1 < len(bursts):
            gap_ms = (bursts[i + 1][0] - end) * 1000.0
            gap_str = f"{gap_ms:.3f}"
        else:
            gap_str = "-"
        print(f"{i:>4}  {start:>12.6f}  {dur_ms:>8.3f}  {n:>6}  {gap_str:>15}")

    gaps_ms = [
        (bursts[i + 1][0] - bursts[i][1]) * 1000.0 for i in range(len(bursts) - 1)
    ]
    if gaps_ms:
        print(f"\ninter-burst gap stats: min={min(gaps_ms):.3f}ms "
              f"max={max(gaps_ms):.3f}ms mean={sum(gaps_ms)/len(gaps_ms):.3f}ms")
        buckets = {"<15ms": 0, "15-50ms": 0, "50-150ms": 0, ">150ms": 0}
        for g in gaps_ms:
            if g < 15:
                buckets["<15ms"] += 1
            elif g < 50:
                buckets["15-50ms"] += 1
            elif g < 150:
                buckets["50-150ms"] += 1
            else:
                buckets[">150ms"] += 1
        print("histogram:", buckets)


if __name__ == "__main__":
    main()
