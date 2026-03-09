"""Classify a git diff of train.py into intervention tags using keyword heuristics."""

import re

TAG_KEYWORDS = {
    "architecture": [
        "n_layer", "n_head", "n_embd", "FFN", "MLP", "Block", "expand", "dim",
        "n_layers", "n_heads", "hidden", "residual", "skip", "depth", "width",
    ],
    "optimizer": [
        "lr", "weight_decay", "AdamW", "Muon", "momentum", "beta",
        "learning_rate", "optimizer", "adam", "sgd", "betas", "beta1", "beta2",
    ],
    "schedule": [
        "warmup", "cosine", "scheduler", "decay", "cooldown",
        "schedule", "anneal", "cycle", "warmdown",
    ],
    "batching": [
        "batch_size", "TOTAL_BATCH", "grad_accum", "seq_len",
        "micro_batch", "gradient_accumulation", "batch",
    ],
    "attention": [
        "attn", "head", "rope", "kv", "flash", "causal", "mask",
        "attention", "qkv", "softmax", "scaled_dot",
    ],
    "initialization": [
        "init", "std", "xavier", "kaiming", "normal_",
        "zeros_", "ones_", "uniform_", "reset_parameters",
    ],
    "numerical": [
        "dtype", "bf16", "fp32", "clip", "norm", "eps", "inf",
        "float16", "float32", "bfloat16", "grad_clip", "max_norm",
    ],
}

SEED_KEYWORDS = ["seed", "torch.manual_seed", "random.seed", "np.random.seed"]


def _extract_changed_lines(diff_text: str) -> list[str]:
    """Extract only added/removed lines (starting with + or -) from a unified diff,
    excluding diff headers."""
    lines = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith("-"):
            lines.append(line[1:])  # strip the +/- prefix
    return lines


def classify_diff(diff_text: str) -> str:
    """Classify a git diff into intervention tags.

    Returns one of: architecture | optimizer | schedule | batching |
                    attention | initialization | numerical | seed_only | other

    If multiple tags match, returns a comma-separated string.
    """
    changed_lines = _extract_changed_lines(diff_text)
    if not changed_lines:
        return "other"

    changed_text = "\n".join(changed_lines)

    # Check seed_only first: if ONLY seed-related keywords appear
    has_seed = any(kw in changed_text for kw in SEED_KEYWORDS)
    has_other_tags = False

    matched_tags = []
    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            # Case-sensitive match for acronyms, case-insensitive for longer words
            if len(kw) <= 3:
                pattern = re.compile(r'\b' + re.escape(kw) + r'\b')
            else:
                pattern = re.compile(re.escape(kw), re.IGNORECASE)
            if pattern.search(changed_text):
                matched_tags.append(tag)
                has_other_tags = True
                break

    if not has_other_tags and has_seed:
        return "seed_only"

    if matched_tags:
        return ",".join(matched_tags)

    return "other"
