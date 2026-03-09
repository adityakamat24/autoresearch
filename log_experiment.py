"""Log an experiment result — handles all bookkeeping atomically.

Usage:
    python log_experiment.py \
        --tag architecture \
        --hypothesis "increasing n_layer from 8 to 12 will lower val_bpb" \
        --mechanism "deeper network captures longer-range dependencies" \
        --confidence medium \
        --val-bpb-before 0.9979 \
        --val-bpb-after 0.9951 \
        --peak-vram-mb 45060.2 \
        --verdict KEEP \
        --reason "meaningful improvement of -0.0028" \
        --followup-win "try n_layer=16" \
        --followup-loss "try wider instead"

    For crashes:
    python log_experiment.py \
        --tag architecture \
        --hypothesis "double model width" \
        --mechanism "more parameters" \
        --confidence low \
        --val-bpb-before 0.9979 \
        --crashed \
        --crash-snippet "RuntimeError: CUDA out of memory" \
        --verdict DISCARD \
        --reason "OOM crash"

This script:
    1. Appends a full record to experiment_ledger.jsonl
    2. Updates intervention_memory.json stats
    3. Appends a row to results.tsv
    4. Reads git branch/commit automatically
"""

import argparse
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
LEDGER_PATH = REPO_DIR / "experiment_ledger.jsonl"
MEMORY_PATH = REPO_DIR / "intervention_memory.json"
RESULTS_TSV = REPO_DIR / "results.tsv"

ALL_TAGS = [
    "architecture", "optimizer", "schedule", "batching",
    "attention", "initialization", "numerical", "seed_only", "other",
]


def git(*args: str) -> str:
    result = subprocess.run(
        ["git"] + list(args),
        cwd=REPO_DIR, capture_output=True, text=True, timeout=15,
    )
    return result.stdout.strip()


def load_memory() -> dict:
    if MEMORY_PATH.exists():
        return json.loads(MEMORY_PATH.read_text())
    mem = {}
    for tag in ALL_TAGS:
        mem[tag] = {
            "n_tried": 0, "n_improved": 0, "n_confirmed": 0,
            "n_crashed": 0, "avg_delta": 0.0, "best_delta": 0.0,
            "avg_vram_change_pct": 0.0,
        }
    return mem


def save_memory(mem: dict) -> None:
    MEMORY_PATH.write_text(json.dumps(mem, indent=2) + "\n")


def ensure_results_tsv():
    if not RESULTS_TSV.exists():
        RESULTS_TSV.write_text("commit\tval_bpb\tmemory_gb\tstatus\tdescription\n")


def main():
    parser = argparse.ArgumentParser(description="Log an experiment result")
    parser.add_argument("--tag", required=True, help="Intervention tag (architecture|optimizer|schedule|batching|attention|initialization|numerical|seed_only|other)")
    parser.add_argument("--hypothesis", required=True, help="What you predicted")
    parser.add_argument("--mechanism", default="", help="Why you predicted it")
    parser.add_argument("--confidence", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--val-bpb-before", type=float, required=True, help="val_bpb before this experiment")
    parser.add_argument("--val-bpb-after", type=float, default=None, help="val_bpb after (omit if crashed)")
    parser.add_argument("--peak-vram-mb", type=float, default=None, help="peak VRAM in MB (omit if crashed)")
    parser.add_argument("--crashed", action="store_true", help="Whether the run crashed")
    parser.add_argument("--crash-snippet", default=None, help="Last few lines of error output")
    parser.add_argument("--verdict", required=True, choices=["KEEP", "DISCARD", "CONFIRM_PASS", "CONFIRM_FAIL"])
    parser.add_argument("--reason", default="", help="Judge reason for verdict")
    parser.add_argument("--trust-score", type=float, default=0.5, help="Trust score 0.0-1.0")
    parser.add_argument("--confirmed", action="store_true", help="Whether this was confirmed via rerun")
    parser.add_argument("--followup-win", default="", help="What to try next if this worked")
    parser.add_argument("--followup-loss", default="", help="What to try next if this failed")
    args = parser.parse_args()

    # Git state
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    commit_sha = git("rev-parse", "HEAD")

    # Compute delta
    val_bpb_after = args.val_bpb_after if args.val_bpb_after is not None else 0.0
    delta = (val_bpb_after - args.val_bpb_before) if not args.crashed else 0.0
    improved = args.verdict in ("KEEP", "CONFIRM_PASS")

    # VRAM change
    baseline_vram = 45060.2
    vram_change_pct = 0.0
    if args.peak_vram_mb is not None:
        vram_change_pct = ((args.peak_vram_mb - baseline_vram) / baseline_vram) * 100

    # 1. Append to ledger
    record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "parent_commit": commit_sha,
        "candidate_commit": commit_sha if improved else None,
        "hypothesis": args.hypothesis,
        "mechanism": args.mechanism,
        "intervention_tag": args.tag,
        "confidence": args.confidence,
        "val_bpb_before": args.val_bpb_before,
        "val_bpb_after": val_bpb_after,
        "delta": round(delta, 6),
        "peak_vram_mb": args.peak_vram_mb or 0.0,
        "crashed": args.crashed,
        "crash_snippet": args.crash_snippet,
        "verdict": args.verdict,
        "judge_reason": args.reason,
        "trust_score": args.trust_score,
        "confirmed": args.confirmed,
        "followup_if_works": args.followup_win,
        "followup_if_fails": args.followup_loss,
    }
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    # 2. Update memory
    mem = load_memory()
    tags = [t.strip() for t in args.tag.split(",")]
    for t in tags:
        if t not in mem:
            mem[t] = {
                "n_tried": 0, "n_improved": 0, "n_confirmed": 0,
                "n_crashed": 0, "avg_delta": 0.0, "best_delta": 0.0,
                "avg_vram_change_pct": 0.0,
            }
        s = mem[t]
        n = s["n_tried"]
        s["n_tried"] = n + 1
        if args.crashed:
            s["n_crashed"] += 1
        if improved:
            s["n_improved"] += 1
        if args.confirmed:
            s["n_confirmed"] += 1
        s["avg_delta"] = (s["avg_delta"] * n + delta) / (n + 1)
        if delta < s["best_delta"]:
            s["best_delta"] = delta
        s["avg_vram_change_pct"] = (s["avg_vram_change_pct"] * n + vram_change_pct) / (n + 1)
    save_memory(mem)

    # 3. Append to results.tsv
    ensure_results_tsv()
    short_sha = commit_sha[:7]
    vbpb_str = f"{val_bpb_after:.6f}" if not args.crashed else "0.000000"
    mem_gb_str = f"{args.peak_vram_mb / 1024:.1f}" if args.peak_vram_mb else "0.0"
    status = "crash" if args.crashed else ("keep" if improved else "discard")
    desc = args.hypothesis[:80]
    with open(RESULTS_TSV, "a") as f:
        f.write(f"{short_sha}\t{vbpb_str}\t{mem_gb_str}\t{status}\t{desc}\n")

    # Print summary
    print(f"Logged experiment:")
    print(f"  Tag:      {args.tag}")
    print(f"  Verdict:  {args.verdict}")
    print(f"  Delta:    {delta:+.6f}")
    print(f"  Ledger:   {LEDGER_PATH.name} (appended)")
    print(f"  Memory:   {MEMORY_PATH.name} (updated)")
    print(f"  Results:  {RESULTS_TSV.name} (appended)")


if __name__ == "__main__":
    main()
