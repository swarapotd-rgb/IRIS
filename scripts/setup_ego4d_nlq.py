#!/usr/bin/env python3
"""Ego4D NLQ annotation summariser and val_tune/val_confirm split builder.

This script never downloads anything and never touches AWS credentials. It
operates purely on annotation JSON already fetched by the official `ego4d`
CLI (see docs/ego4d_dataset_setup.md section 4.2).

Usage
-----
  python3 scripts/setup_ego4d_nlq.py --summarize
  python3 scripts/setup_ego4d_nlq.py --make-split [--confirm-frac 0.2] [--seed N] [--force]
  python3 scripts/setup_ego4d_nlq.py --emit-uids --split val_tune --out FILE
  python3 scripts/setup_ego4d_nlq.py --verify-split

Design rules (mirrors scripts/setup_qvhighlights.py and split_manifest.json):
  * The split is over `video_uid`, never `clip_uid` and never query index,
    because Ego4D cuts multiple clips from one source video and the visual
    environment would leak across the boundary otherwise.
  * The split is seeded, sorted, and pinned to a sha256 of the source
    annotation file. A source-hash mismatch invalidates the split.
  * --make-split refuses to overwrite an existing split unless --force, so a
    stray rerun cannot reshuffle a split you have already reported against.
  * The schema is probed, not assumed. If Ego4D's layout differs from what is
    expected, the script fails loudly with the keys it actually found rather
    than silently producing zero counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "external_data" / "ego4d"

# Matches split_manifest.json's seed so both datasets are reproducible the
# same way. Override with --seed only for a deliberate, logged re-split.
DEFAULT_SEED = 20260721
DEFAULT_CONFIRM_FRAC = 0.20

SPLIT_FILES = {
    "train": "nlq_train.json",
    "val": "nlq_val.json",
    "test": "nlq_test_unannotated.json",
}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_rel(path: Path) -> str:
    """Repo-relative POSIX path when inside the repo, absolute otherwise."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def annotation_path(data_root: Path, split: str) -> Path:
    return data_root / "v2" / "annotations" / SPLIT_FILES[split]


def load_annotations(data_root: Path, split: str) -> dict:
    path = annotation_path(data_root, split)
    if not path.exists():
        sys.exit(
            f"ERROR: {path} not found.\n"
            "Fetch annotations first (docs/ego4d_dataset_setup.md 4.2):\n"
            "  ego4d --output_directory external_data/ego4d --datasets annotations "
            "--benchmarks nlq --aws_profile_name ego4d"
        )
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def walk(blob: dict, split: str):
    """Yield (video_uid, clip_uid, n_queries, n_queries_with_gold).

    Ego4D NLQ nests as videos -> clips -> annotations -> language_queries.
    The nesting is probed rather than assumed; a missing top-level "videos"
    key aborts with the keys that were actually present.
    """
    videos = blob.get("videos")
    if not isinstance(videos, list):
        sys.exit(
            "ERROR: expected a top-level 'videos' list in the NLQ annotation "
            f"file for split '{split}'. Found top-level keys: {sorted(blob)}.\n"
            "The Ego4D schema has changed; update walk() before trusting any "
            "count this script prints."
        )

    for video in videos:
        video_uid = video.get("video_uid")
        clips = video.get("clips") or []
        if not clips:
            yield video_uid, None, 0, 0
            continue
        for clip in clips:
            clip_uid = clip.get("clip_uid")
            n_q = 0
            n_gold = 0
            for ann in clip.get("annotations") or []:
                for q in ann.get("language_queries") or []:
                    n_q += 1
                    # Test is distributed unannotated: queries carry no gold
                    # temporal span. Anything that reports a local test metric
                    # is a bug -- see docs/ego4d_dataset_setup.md section 2.
                    if q.get("clip_start_sec") is not None and q.get("clip_end_sec") is not None:
                        n_gold += 1
            yield video_uid, clip_uid, n_q, n_gold


def summarize(data_root: Path) -> None:
    print(f"data root: {data_root}\n")
    header = f"{'split':<6} {'videos':>8} {'clips':>8} {'queries':>9} {'w/ gold':>9}  file sha256"
    print(header)
    print("-" * len(header))
    for split in ("train", "val", "test"):
        path = annotation_path(data_root, split)
        if not path.exists():
            print(f"{split:<6} {'--':>8} {'--':>8} {'--':>9} {'--':>9}  (not downloaded)")
            continue
        blob = load_annotations(data_root, split)
        videos, clips, n_q, n_gold = set(), set(), 0, 0
        for video_uid, clip_uid, q, g in walk(blob, split):
            videos.add(video_uid)
            if clip_uid is not None:
                clips.add(clip_uid)
            n_q += q
            n_gold += g
        print(
            f"{split:<6} {len(videos):>8} {len(clips):>8} {n_q:>9} {n_gold:>9}  "
            f"{sha256_of(path)[:16]}..."
        )
        if split == "test" and n_gold:
            print(
                "  WARNING: the test file reports gold spans. Ego4D distributes "
                "test unannotated; confirm you did not download an unofficial "
                "annotated mirror before using this for anything."
            )
    print(
        "\nCopy these numbers into docs/ego4d_dataset_setup.md section 2, "
        "replacing the VERIFY markers."
    )


def split_path(data_root: Path) -> Path:
    return data_root / "manifests" / "ego4d_nlq_val_split.json"


def make_split(data_root: Path, seed: int, confirm_frac: float, force: bool) -> None:
    out = split_path(data_root)
    if out.exists() and not force:
        sys.exit(
            f"ERROR: {out} already exists. Refusing to reshuffle a split that "
            "may already have been reported against. Pass --force only if you "
            "intend to invalidate every result computed under the old split, "
            "and log that in EXPERIMENT_LOG.md."
        )

    src = annotation_path(data_root, "val")
    blob = load_annotations(data_root, "val")

    # Split over video_uid, not clip_uid: Ego4D cuts several 5-minute clips
    # from one source video and they share scene, location, and camera-wearer.
    video_uids = sorted({v for v, _c, _q, _g in walk(blob, "val") if v})
    if not video_uids:
        sys.exit("ERROR: no video_uids parsed from nlq_val.json; refusing to write an empty split.")

    rng = random.Random(seed)
    shuffled = list(video_uids)
    rng.shuffle(shuffled)
    n_confirm = max(1, round(len(shuffled) * confirm_frac))
    confirm = sorted(shuffled[:n_confirm])
    tune = sorted(shuffled[n_confirm:])

    assert not (set(tune) & set(confirm)), "video_uid overlap between tune and confirm"
    assert len(tune) + len(confirm) == len(video_uids)

    manifest = {
        "dataset": "ego4d_nlq",
        "source_file": _repo_rel(src),
        "source_sha256": sha256_of(src),
        "seed": seed,
        "confirm_frac": confirm_frac,
        "split_level": "video_uid",
        "n_videos_total": len(video_uids),
        "n_videos_tune": len(tune),
        "n_videos_confirm": len(confirm),
        "tune_video_uids": tune,
        "confirm_video_uids": confirm,
        "policy": (
            "val_tune carries all hyperparameter search. val_confirm is opened "
            "exactly once, with every knob frozen, and that single look is "
            "logged in EXPERIMENT_LOG.md with the config hash."
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(
        f"wrote {out}\n"
        f"  total {len(video_uids)} videos -> tune {len(tune)} / confirm {len(confirm)} "
        f"(seed {seed})\n"
        "Commit this file."
    )


def load_split(data_root: Path) -> dict:
    out = split_path(data_root)
    if not out.exists():
        sys.exit(f"ERROR: {out} not found. Run --make-split first.")
    with out.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def verify_split(data_root: Path) -> None:
    manifest = load_split(data_root)
    src = Path(manifest["source_file"])
    if not src.is_absolute():
        src = REPO_ROOT / src
    if not src.exists():
        sys.exit(f"ERROR: source annotation file {src} is missing.")
    actual = sha256_of(src)
    if actual != manifest["source_sha256"]:
        sys.exit(
            "ERROR: nlq_val.json sha256 does not match the one the split was "
            f"built from.\n  expected {manifest['source_sha256']}\n  actual   {actual}\n"
            "The split is invalid. Regenerate it with --make-split --force and "
            "treat every result computed under it as void."
        )
    tune = set(manifest["tune_video_uids"])
    confirm = set(manifest["confirm_video_uids"])
    if tune & confirm:
        sys.exit(f"ERROR: {len(tune & confirm)} video_uids appear in both tune and confirm.")
    print(
        f"OK: source hash matches; {len(tune)} tune / {len(confirm)} confirm video_uids, "
        "no overlap."
    )


def emit_uids(data_root: Path, split: str, out_path: Path | None) -> None:
    if split in ("val_tune", "val_confirm"):
        manifest = load_split(data_root)
        key = "tune_video_uids" if split == "val_tune" else "confirm_video_uids"
        uids = manifest[key]
    elif split in SPLIT_FILES:
        blob = load_annotations(data_root, split)
        uids = sorted({v for v, _c, _q, _g in walk(blob, split) if v})
    else:
        sys.exit(f"ERROR: unknown split '{split}'.")

    text = "\n".join(uids) + "\n"
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"wrote {len(uids)} video_uids to {out_path}")
    else:
        sys.stdout.write(text)


# --- storage budgeting -------------------------------------------------------
#
# Two modes, because "exact" and "available right now" are not the same thing.
#
#   EXACT   : --storage-budget --s3-listing FILE, where FILE is the output of
#             aws s3 ls --recursive s3://<clips prefix>/ --profile ego4d
#             Byte-exact, and costs nothing but a LIST call -- no video moves.
#   ESTIMATE: --storage-budget with no listing. Multiplies clip count by a
#             GB/hour anchor. Use only to decide whether a download is even
#             plausible; never quote an estimate as the budget.

# Derived anchor, NOT measured on this box: the Ego4D corpus is commonly cited
# at ~3,670 hours and ~5 TB for the full_scale distribution, giving ~1.36 GB
# per hour of H.264 at canonical bitrate. Both inputs are VERIFY -- replace this
# with a measured number from --s3-listing before it reaches a budget or a paper.
DEFAULT_GB_PER_HOUR = 1.36
DEFAULT_CLIP_MINUTES = 8.0


def parse_s3_listing(path: Path) -> dict[str, int]:
    """Map basename-without-extension -> size in bytes from `aws s3 ls --recursive`.

    Expected line shape:  2021-11-01 12:00:00   123456789 public/v2/clips/<uid>.mp4
    Lines that do not parse are counted and reported, never silently dropped.
    """
    sizes: dict[str, int] = {}
    skipped = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 4:
            if line.strip():
                skipped += 1
            continue
        try:
            size = int(parts[2])
        except ValueError:
            skipped += 1
            continue
        key = parts[3]
        stem = key.rsplit("/", 1)[-1]
        if "." in stem:
            stem = stem.rsplit(".", 1)[0]
        sizes[stem] = size
    if skipped:
        print(f"note: {skipped} unparsable line(s) in {path} ignored", file=sys.stderr)
    if not sizes:
        sys.exit(f"ERROR: no sized objects parsed from {path}; is it an `aws s3 ls --recursive` dump?")
    return sizes


def _fmt(nbytes: float) -> str:
    return f"{nbytes / 1e9:,.1f} GB"


def clip_uids_for(data_root: Path, split: str) -> list[str]:
    """clip_uids belonging to a split. val_tune/val_confirm filter val by video_uid."""
    if split in ("val_tune", "val_confirm"):
        manifest = load_split(data_root)
        key = "tune_video_uids" if split == "val_tune" else "confirm_video_uids"
        keep = set(manifest[key])
        blob = load_annotations(data_root, "val")
        return sorted({c for v, c, _q, _g in walk(blob, "val") if c and v in keep})
    blob = load_annotations(data_root, split)
    return sorted({c for _v, c, _q, _g in walk(blob, split) if c})


def storage_budget(
    data_root: Path,
    listing: Path | None,
    gb_per_hour: float,
    clip_minutes: float,
) -> None:
    sizes = parse_s3_listing(listing) if listing else None
    mode = "EXACT (from S3 listing)" if sizes else "ESTIMATE (derived anchor -- do not quote as a budget)"
    print(f"storage budget -- {mode}\n")

    # Since IRIS is no longer training-free, train clips are required, not
    # optional: they are what the trained component is fitted on.
    wanted = ["train", "val", "val_tune", "val_confirm"]
    rows = []
    missing_total = 0
    for split in wanted:
        path = annotation_path(data_root, "val" if split.startswith("val_") else split)
        if not path.exists():
            rows.append((split, None, None, None))
            continue
        try:
            clips = clip_uids_for(data_root, split)
        except SystemExit:
            rows.append((split, None, None, None))
            continue
        if sizes:
            found = [sizes[c] for c in clips if c in sizes]
            missing = len(clips) - len(found)
            missing_total += missing
            rows.append((split, len(clips), sum(found), missing))
        else:
            est = len(clips) * (clip_minutes / 60.0) * gb_per_hour * 1e9
            rows.append((split, len(clips), est, None))

    header = f"{'split':<12} {'clips':>8} {'size':>14}"
    print(header)
    print("-" * len(header))
    for split, n, total, missing in rows:
        if n is None:
            print(f"{split:<12} {'--':>8} {'(annotations not downloaded)':>14}")
            continue
        note = f"   ({missing} clip(s) not in listing)" if missing else ""
        print(f"{split:<12} {n:>8} {_fmt(total):>14}{note}")

    dl = [r for r in rows if r[0] in ("train", "val") and r[1] is not None]
    if len(dl) == 2:
        total = sum(r[2] for r in dl)
        nclips = sum(r[1] for r in dl)
        print(f"\nDOWNLOAD TOTAL (train + val clips) = {_fmt(total)} across {nclips} clips")
        print("  val_tune / val_confirm are subsets of val and add nothing.")
        print("  test clips are NOT included: gold spans are held out, so test is")
        print("  only ever run once for an EvalAI submission -- pull it separately.")
        print("\nPlan for ~2x this at peak if any stage writes decoded frames or")
        print("caches alongside the source clips.")
    if not sizes:
        print(
            f"\nAssumptions: {gb_per_hour} GB/hour, {clip_minutes} min/clip. Both are"
            "\nunverified. Get the real number with --s3-listing (see docs section 4.3)."
        )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    p.add_argument("--summarize", action="store_true", help="print per-split video/clip/query counts")
    p.add_argument("--make-split", action="store_true", help="build the seeded val_tune/val_confirm split")
    p.add_argument("--verify-split", action="store_true", help="re-check the committed split against the source hash")
    p.add_argument("--emit-uids", action="store_true", help="print/write the video_uid list for a split")
    p.add_argument("--split", default="val", help="train|val|test|val_tune|val_confirm (for --emit-uids)")
    p.add_argument("--out", type=Path, default=None, help="output file for --emit-uids")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--confirm-frac", type=float, default=DEFAULT_CONFIRM_FRAC)
    p.add_argument("--force", action="store_true", help="allow --make-split to overwrite an existing split")
    p.add_argument("--storage-budget", action="store_true", help="report download size per split")
    p.add_argument("--s3-listing", type=Path, default=None, help="`aws s3 ls --recursive` dump; makes --storage-budget byte-exact")
    p.add_argument("--gb-per-hour", type=float, default=DEFAULT_GB_PER_HOUR)
    p.add_argument("--clip-minutes", type=float, default=DEFAULT_CLIP_MINUTES)
    args = p.parse_args()

    if not any([args.summarize, args.make_split, args.verify_split, args.emit_uids, args.storage_budget]):
        p.print_help()
        sys.exit(1)

    if args.summarize:
        summarize(args.data_root)
    if args.make_split:
        make_split(args.data_root, args.seed, args.confirm_frac, args.force)
    if args.verify_split:
        verify_split(args.data_root)
    if args.emit_uids:
        emit_uids(args.data_root, args.split, args.out)
    if args.storage_budget:
        storage_budget(args.data_root, args.s3_listing, args.gb_per_hour, args.clip_minutes)


if __name__ == "__main__":
    main()
