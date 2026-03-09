# autoresearch

This is an experiment to have the LLM do its own research.

## Setup

To set up a new experiment, work with the user to:

1. **Agree on a run tag**: propose a tag based on today's date (e.g. `mar5`). The branch `autoresearch/<tag>` must not already exist — this is a fresh run.
2. **Create the branch**: `git checkout -b autoresearch/<tag>` from current master.
3. **Read the in-scope files**: The repo is small. Read these files for full context:
   - `README.md` — repository context.
   - `prepare.py` — fixed constants, data prep, tokenizer, dataloader, evaluation. Do not modify.
   - `train.py` — the file you modify. Model architecture, optimizer, training loop.
4. **Verify data exists**: Check that `~/.cache/autoresearch/` contains data shards and a tokenizer. If not, tell the human to run `uv run prepare.py`.
5. **Initialize results.tsv**: Create `results.tsv` with just the header row. The baseline will be recorded after the first run.
6. **Confirm and go**: Confirm setup looks good.

Once you get confirmation, kick off the experimentation.

## Experimentation

Each experiment runs on a single GPU. The training script runs for a **fixed time budget of 5 minutes** (wall clock training time, excluding startup/compilation). You launch it simply as: `uv run train.py`.

**What you CAN do:**
- Modify `train.py` — this is the only file you edit. Everything is fair game: model architecture, optimizer, hyperparameters, training loop, batch size, model size, etc.

**What you CANNOT do:**
- Modify `prepare.py`. It is read-only. It contains the fixed evaluation, data loading, tokenizer, and training constants (time budget, sequence length, etc).
- Install new packages or add dependencies. You can only use what's already in `pyproject.toml`.
- Modify the evaluation harness. The `evaluate_bpb` function in `prepare.py` is the ground truth metric.

**The goal is simple: get the lowest val_bpb.** Since the time budget is fixed, you don't need to worry about training time — it's always 5 minutes. Everything is fair game: change the architecture, the optimizer, the hyperparameters, the batch size, the model size. The only constraint is that the code runs without crashing and finishes within the time budget.

**VRAM** is a soft constraint. Some increase is acceptable for meaningful val_bpb gains, but it should not blow up dramatically.

**Simplicity criterion**: All else being equal, simpler is better. A small improvement that adds ugly complexity is not worth it. Conversely, removing something and getting equal or better results is a great outcome — that's a simplification win. When evaluating whether to keep a change, weigh the complexity cost against the improvement magnitude. A 0.001 val_bpb improvement that adds 20 lines of hacky code? Probably not worth it. A 0.001 val_bpb improvement from deleting code? Definitely keep. An improvement of ~0 but much simpler code? Keep.

**The first run**: Your very first run should always be to establish the baseline, so you will run the training script as is.

## Output format

Once the script finishes it prints a summary like this:

```
---
val_bpb:          0.997900
training_seconds: 300.1
total_seconds:    325.9
peak_vram_mb:     45060.2
mfu_percent:      39.80
total_tokens_M:   499.6
num_steps:        953
num_params_M:     50.3
depth:            8
```

Note that the script is configured to always stop after 5 minutes, so depending on the computing platform of this computer the numbers might look different. You can extract the key metric from the log file:

```
grep "^val_bpb:" run.log
```

## Logging results

**Use `log_experiment.py` for ALL experiment logging.** It handles everything atomically — ledger, memory, and results.tsv in one command. Never manually edit these files.

After each experiment, run:

```bash
# Successful experiment (KEEP or DISCARD):
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

# Crashed experiment:
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
```

Verdict options: `KEEP`, `DISCARD`, `CONFIRM_PASS`, `CONFIRM_FAIL`

The script automatically:
- Appends a full JSON record to `experiment_ledger.jsonl`
- Updates per-tag stats in `intervention_memory.json`
- Appends a row to `results.tsv`
- Reads the current git branch and commit

You can also view `results.tsv` directly. It has 5 columns:

```
commit	val_bpb	memory_gb	status	description
a1b2c3d	0.997900	44.0	keep	baseline
b2c3d4e	0.993200	44.2	keep	increase LR to 0.04
c3d4e5f	1.005000	44.0	discard	switch to GeLU activation
d4e5f6g	0.000000	0.0	crash	double model width (OOM)
```

To see a full experiment summary at any time: `python report.py`

## The experiment loop

The experiment runs on a dedicated branch (e.g. `autoresearch/mar5` or `autoresearch/mar5-gpu0`).

LOOP FOREVER:

1. **Read context**: Read `experiment_ledger.jsonl` (last 10 entries) and `intervention_memory.json` to see what's been tried and what works.
2. **Write hypothesis**: Write a hypothesis block (see Scientist Layer section below) BEFORE touching any code.
3. **Edit train.py**: Make the code change.
4. **git commit**: `git add train.py && git commit -m "<short description>"`
5. **Run**: `uv run train.py > run.log 2>&1` (redirect everything — do NOT use tee or let output flood your context)
6. **Read results**: `grep "^val_bpb:\|^peak_vram_mb:" run.log`
7. **Handle crashes**: If grep output is empty, the run crashed. Run `tail -n 50 run.log` to read the stack trace. If it's a dumb bug, fix and rerun. If fundamentally broken, give up on this idea.
8. **Judge**: Apply the verdict rules (see Scientist Layer section below). Decide KEEP, DISCARD, or CONFIRM (rerun borderline wins once).
9. **Log**: Run `python log_experiment.py` with the appropriate arguments. This handles ledger, memory, AND results.tsv atomically.
10. **Act on verdict**:
    - KEEP → branch advances, the git commit stays
    - DISCARD → `git reset --hard <parent_commit>` to revert train.py
    - CONFIRM → rerun step 5, then decide KEEP or DISCARD

The idea is that you are a completely autonomous researcher trying things out. If they work, keep. If they don't, discard. And you're advancing the branch so that you can iterate. If you feel like you're getting stuck in some way, you can rewind but you should probably do this very very sparingly (if ever).

**Timeout**: Each experiment should take ~5 minutes total (+ a few seconds for startup and eval overhead). If a run exceeds 10 minutes, kill it and treat it as a failure (discard and revert).

**Crashes**: If a run crashes (OOM, or a bug, or etc.), use your judgment: If it's something dumb and easy to fix (e.g. a typo, a missing import), fix it and re-run. If the idea itself is fundamentally broken, just skip it, log "crash" as the status in the tsv, and move on.

**NEVER STOP**: Once the experiment loop has begun (after the initial setup), do NOT pause to ask the human if you should continue. Do NOT ask "should I keep going?" or "is this a good stopping point?". The human might be asleep, or gone from a computer and expects you to continue working *indefinitely* until you are manually stopped. You are autonomous. If you run out of ideas, think harder — read papers referenced in the code, re-read the in-scope files for new angles, try combining previous near-misses, try more radical architectural changes. The loop runs until the human interrupts you, period.

As an example use case, a user might leave you running while they sleep. If each experiment takes you ~5 minutes then you can run approx 12/hour, for a total of about 100 over the duration of the average human sleep. The user then wakes up to experimental results, all completed by you while they slept!

## Scientist Layer (autoresearch extension)

Before proposing any code change, you MUST write a hypothesis block first. Use this format:

```
HYPOTHESIS: <what you predict will happen>
MECHANISM: <why you think this change has the effect you predict>
TAG: <architecture|optimizer|schedule|batching|attention|initialization|numerical|other>
CONFIDENCE: <low|medium|high>
FOLLOWUP_WIN: <what to test next if val_bpb improves>
FOLLOWUP_LOSS: <what to test next if val_bpb does not improve>
```

Then make your code change. Then run. Then read the result.

When judging whether to keep a change:
- Do NOT keep changes with delta > -0.001 (less than 0.001 improvement)
- Be extra skeptical of changes that only touch a single number (could be seed luck)
- Prefer changes that have a mechanistic reason behind them
- Check intervention_memory.json before proposing: avoid tags with high crash rates
- Check experiment_ledger.jsonl for the last 10 experiments before proposing: avoid repeating failed directions

The ledger and memory are your research log. Read them at the start of every session.
