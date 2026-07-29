"""Snapshot SHA-256 of every protected artifact named by the task spec.

Written once, called before and after each phase. The output is a sorted
`<sha256>  <repo-relative-path>` listing, so `diff before after` is the whole
verification -- no separate comparison logic to get wrong.

Directory globs are expanded recursively and sorted, so a file ADDED to a
protected directory shows up as a new line in the diff rather than silently
passing. That matters: the phases below write new files, and a phase that
wrote into a protected dir must fail the check.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PROTECTED_FILES = [
    "tuning/frozen_state.json",
    "split_manifest.json",
    "dataset_manifest.json",
    "tuning/val_confirm_e2e_per_question.csv",
    "tuning/val_confirm_e2e_report.md",
    "eval/data/nextqa/val.csv",
    "eval/data/nextqa/test.csv",
    "eval/data/nextqa/gsub_val.json",
    "eval/data/nextqa/gsub_test.json",
]

PROTECTED_DIRS = [
    "tuning/blind_ablation",
    "tuning/determinism_gate",
    "tuning/span_sweep",
    "tuning/prerun_fixes",
]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def collect() -> list[str]:
    lines: list[str] = []
    for rel in PROTECTED_FILES:
        p = REPO / rel
        lines.append(f"{sha256(p) if p.exists() else 'MISSING':<64}  {rel}")
    for rel in PROTECTED_DIRS:
        root = REPO / rel
        if not root.exists():
            lines.append(f"{'MISSING':<64}  {rel}/")
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file():
                lines.append(f"{sha256(p):<64}  {p.relative_to(REPO)}")
    return sorted(lines)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: protected_hashes.py <output-path>")
    out = Path(sys.argv[1])
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = collect()
    out.write_text("\n".join(lines) + "\n")
    print(f"[protected] wrote {len(lines)} hashes to {out}")


if __name__ == "__main__":
    main()
