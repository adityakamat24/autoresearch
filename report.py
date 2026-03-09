"""Report — reads experiment_ledger.jsonl and prints a human-readable summary."""

import json
import sys
from pathlib import Path
from collections import defaultdict

LEDGER_PATH = Path(__file__).resolve().parent / "experiment_ledger.jsonl"
BASELINE_VAL_BPB = 0.997900


def load_ledger() -> list[dict]:
    entries = []
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text().splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def print_report():
    ledger = load_ledger()

    if not ledger:
        print("No experiments recorded yet.")
        return

    total = len(ledger)
    keeps = [e for e in ledger if e.get("verdict") in ("KEEP", "CONFIRM_PASS")]
    discards = [e for e in ledger if e.get("verdict") in ("DISCARD", "CONFIRM_FAIL")]
    confirms = [e for e in ledger if e.get("verdict", "").startswith("CONFIRM")]
    crashes = [e for e in ledger if e.get("crashed")]

    best_entry = None
    best_bpb = BASELINE_VAL_BPB
    for e in ledger:
        if e.get("verdict") in ("KEEP", "CONFIRM_PASS"):
            if e.get("val_bpb_after", 999) < best_bpb:
                best_bpb = e["val_bpb_after"]
                best_entry = e

    # Per-tag stats
    tag_stats = defaultdict(lambda: {"tried": 0, "improved": 0, "crashed": 0, "total_delta": 0.0})
    for e in ledger:
        tags = [t.strip() for t in e.get("intervention_tag", "other").split(",")]
        for tag in tags:
            tag_stats[tag]["tried"] += 1
            if e.get("verdict") in ("KEEP", "CONFIRM_PASS"):
                tag_stats[tag]["improved"] += 1
            if e.get("crashed"):
                tag_stats[tag]["crashed"] += 1
            tag_stats[tag]["total_delta"] += e.get("delta", 0.0)

    # Sort tags by success rate (improved/tried)
    sorted_by_success = sorted(
        tag_stats.items(),
        key=lambda x: x[1]["improved"] / max(x[1]["tried"], 1),
        reverse=True,
    )

    # Sort tags by crash rate
    sorted_by_crash = sorted(
        tag_stats.items(),
        key=lambda x: x[1]["crashed"] / max(x[1]["tried"], 1),
        reverse=True,
    )

    # Print
    print("=" * 70)
    print("  EXPERIMENT REPORT")
    print("=" * 70)

    print(f"\n  Total experiments:  {total}")
    print(f"  Kept:               {len(keeps)}")
    print(f"  Discarded:          {len(discards)}")
    print(f"  Confirms attempted: {len(confirms)}")
    print(f"  Crashes:            {len(crashes)}")
    print(f"  Baseline val_bpb:   {BASELINE_VAL_BPB:.6f}")
    print(f"  Best val_bpb:       {best_bpb:.6f}")
    if best_entry:
        print(f"  Best improvement:   {BASELINE_VAL_BPB - best_bpb:.6f}")
        print(f"  Best hypothesis:    {best_entry.get('hypothesis', 'N/A')[:80]}")

    print(f"\n{'-' * 70}")
    print("  TOP 3 MOST PRODUCTIVE INTERVENTION TAGS")
    print(f"{'-' * 70}")
    print(f"  {'Tag':<20} {'Tried':>6} {'Improved':>9} {'Rate':>6} {'Avg Delta':>10}")
    print(f"  {'-'*20} {'-'*6} {'-'*9} {'-'*6} {'-'*10}")
    for tag, stats in sorted_by_success[:3]:
        rate = stats["improved"] / max(stats["tried"], 1)
        avg_d = stats["total_delta"] / max(stats["tried"], 1)
        print(f"  {tag:<20} {stats['tried']:>6} {stats['improved']:>9} {rate:>5.0%} {avg_d:>+10.6f}")

    print(f"\n{'-' * 70}")
    print("  TOP 3 MOST FAILED / CRASH-PRONE TAGS")
    print(f"{'-' * 70}")
    print(f"  {'Tag':<20} {'Tried':>6} {'Crashed':>8} {'Crash%':>7} {'Improved':>9}")
    print(f"  {'-'*20} {'-'*6} {'-'*8} {'-'*7} {'-'*9}")
    for tag, stats in sorted_by_crash[:3]:
        crash_rate = stats["crashed"] / max(stats["tried"], 1)
        warn = " *** HIGH" if crash_rate > 0.30 else ""
        print(f"  {tag:<20} {stats['tried']:>6} {stats['crashed']:>8} {crash_rate:>6.0%} {stats['improved']:>9}{warn}")

    # Recent experiments
    print(f"\n{'-' * 70}")
    print("  LAST 10 EXPERIMENTS")
    print(f"{'-' * 70}")
    print(f"  {'#':>3} {'Verdict':<13} {'Delta':>10} {'Tag':<18} {'Hypothesis':<30}")
    print(f"  {'-'*3} {'-'*13} {'-'*10} {'-'*18} {'-'*30}")
    for i, e in enumerate(ledger[-10:], start=max(1, total - 9)):
        verdict = e.get("verdict", "?")
        delta = e.get("delta", 0.0)
        tag = e.get("intervention_tag", "?")[:17]
        hyp = e.get("hypothesis", "?")[:29]
        print(f"  {i:>3} {verdict:<13} {delta:>+10.6f} {tag:<18} {hyp:<30}")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    print_report()
