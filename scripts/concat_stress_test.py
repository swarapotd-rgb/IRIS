"""Concatenation stress test: is 4*ceil(sqrt(N)) a real fix for the scene-
shortlist bottleneck, or an artifact of NExT-GQA's short videos?

Holds everything constant except scene count, by concatenating real val_tune
videos into longer ones, ingesting them through the real iris.ingest.ingest(),
and re-measuring scene-shortlist recall with the verified reconstruction from
scripts/scene_shortlist_recall.py (commit 6039807).

MEASUREMENT ONLY. Does not tune, does not write tuning/frozen_state.json or
any config, does not modify iris/*.py or any pre-existing cached index. The
width sweep is a diagnostic curve, not a search for a value to adopt.

Concatenated videos are genuinely encoded and genuinely ingested -- merging
cached indexes by offsetting scene_id/frame_idx is explicitly forbidden here,
since it would fake the very scene structure this experiment measures.

Subcommands:
  structural  PART 1 -- fraction_kept vs n_scenes over every cache on the box
  build       PART 2.1/2.2/2.3 -- sample groups, encode, probe, remap gold
  ingest      PART 2.4 -- real ingest of each concatenated video
  measure     PART 2.4/3 -- recall + width sweep at each k, both gates
  report      PART 5 -- summary.json, manifest, report tables
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

OUT = REPO / "tuning" / "concat_stress"
WORK = Path("/home/ccbd/concat_stress_work")   # videos + indexes, NOT committed
VIDEO_DIR = REPO / "eval" / "data" / "nextqa" / "NExTVideo_flat"
SEED = 20260817
KS = [1, 2, 4, 8, 16]
MIN_QUESTIONS_PER_K = 400
CANONICAL = {"cab2bac1628012a3": "nextqa_val_tune", "4edae64ed40256e3": "nextqa_val_confirm"}


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ══ PART 1 ═══════════════════════════════════════════════════════════════
def read_scene_structure(npz_path: Path) -> dict | None:
    """Scene structure straight from the stored manifest -- no embedding
    decompression, no re-ingest. scene_id is read from the FrameRecord dicts
    (never AsphodelNode, whose id _refresh_scene_ids overwrites)."""
    import numpy as np
    try:
        z = np.load(npz_path, allow_pickle=True)
        d = json.loads(str(z["__manifest__"].item()))
        z.close()
    except Exception:
        return None
    frames = d.get("frames") or []
    sids = {fr.get("scene_id") for fr in frames}
    scenes = sorted(s for s in sids if s is not None and s >= 0)
    return {
        "n_survivors": len(frames),
        "n_scenes": len(scenes),
        "frames_processed": d.get("frames_processed"),
        "video_path": d.get("video_path", ""),
    }


def cmd_structural(args) -> None:
    cache_dirs = []
    for root in [REPO, Path("/home/ccbd/IRIS"), Path("/home/ccbd/IRIS-t0-integrity-gpu")]:
        if not root.exists():
            continue
        for p in root.rglob("*.npz"):
            cache_dirs.append(p.parent)
            break
    # enumerate properly: every dir containing .npz under the IRIS checkouts
    dirs: set[Path] = set()
    for root in [REPO, Path("/home/ccbd/IRIS"), Path("/home/ccbd/IRIS-t0-integrity-gpu")]:
        if root.exists():
            for p in root.rglob("*.npz"):
                dirs.add(p.parent)

    rows, skipped = [], []
    for d in sorted(dirs):
        for p in sorted(d.glob("*.npz")):
            st = read_scene_structure(p)
            if st is None or st["n_scenes"] == 0:
                skipped.append({"path": str(p), "reason": "unreadable" if st is None else "zero_scenes"})
                continue
            stem = p.stem
            vid, _, cfg = stem.partition("__")
            n = st["n_scenes"]
            w = max(4, math.ceil(math.sqrt(n)))
            rows.append({
                "video_id": vid,
                "corpus": CANONICAL.get(cfg, "nextqa_other"),
                "cache_dir": str(d),
                "config_hash": cfg or "",
                "is_canonical": cfg in CANONICAL,
                "n_survivors": st["n_survivors"],
                "n_scenes": n,
                "shortlist_width": min(w, n),
                "fraction_kept": round(min(w, n) / n, 6),
            })
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "structural_table.csv", "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        wr.writerows(rows)

    def bucket(n):
        for lo, hi in [(0, 10), (10, 20), (20, 40), (40, 80), (80, 160), (160, 320), (320, 10 ** 9)]:
            if lo <= n < hi:
                return f"{lo}-{hi if hi < 10**9 else '+'}"
        return "?"

    summ = {"n_rows": len(rows), "n_cache_dirs": len(dirs),
            "skipped": skipped[:50], "n_skipped": len(skipped),
            "corpora_found": sorted({r["corpus"] for r in rows}),
            "by_scene_bucket": {}, "by_corpus": {}}
    bb = defaultdict(list)
    for r in rows:
        bb[bucket(r["n_scenes"])].append(r)
    for k in sorted(bb, key=lambda s: int(s.split("-")[0])):
        v = bb[k]
        summ["by_scene_bucket"][k] = {
            "n": len(v),
            "mean_n_scenes": round(statistics.mean(x["n_scenes"] for x in v), 2),
            "mean_fraction_kept": round(statistics.mean(x["fraction_kept"] for x in v), 4),
        }
    cc = defaultdict(list)
    for r in rows:
        cc[r["corpus"]].append(r)
    for k, v in cc.items():
        summ["by_corpus"][k] = {
            "n": len(v),
            "mean_n_scenes": round(statistics.mean(x["n_scenes"] for x in v), 2),
            "max_n_scenes": max(x["n_scenes"] for x in v),
            "mean_fraction_kept": round(statistics.mean(x["fraction_kept"] for x in v), 4),
        }
    smallest = min(rows, key=lambda r: r["n_scenes"])
    largest = max(rows, key=lambda r: r["n_scenes"])
    summ["extremes"] = {
        "smallest": {k: smallest[k] for k in ("video_id", "n_scenes", "shortlist_width", "fraction_kept")},
        "largest": {k: largest[k] for k in ("video_id", "n_scenes", "shortlist_width", "fraction_kept")},
    }
    (OUT / "structural_summary.json").write_text(json.dumps(summ, indent=2))
    print(json.dumps(summ, indent=2)[:4000])


# ══ PART 2 -- shared setup ═══════════════════════════════════════════════
# One fixed encode setting, used identically for EVERY arm including k=1, so
# the encode effect is isolated from the concatenation effect. The pool is
# heterogeneous (multiple resolutions, several frame rates, some vp6f), so
# concat-demuxer stream copy on the RAW sources is impossible. Instead each
# source is normalised once through this invocation, and the concat demuxer
# then runs with -c copy over already-identical segments. k=1 goes through
# both stages too (a one-entry concat list), so no arm skips a step.
NORM_VF = ("scale=640:480:force_original_aspect_ratio=decrease,"
           "pad=640:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30")
NORM_ARGS = ["-vf", NORM_VF, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-g", "30", "-keyint_min", "30", "-sc_threshold", "0",
             "-an", "-movflags", "+faststart"]
NORM_FPS = 30.0

FFMPEG_CMDLINES = {
    "normalise": "ffmpeg -nostdin -y -loglevel error -i <SRC> " + " ".join(NORM_ARGS) + " <DST>",
    "concat": "ffmpeg -nostdin -y -loglevel error -f concat -safe 0 -i <LIST> -c copy <DST>",
    "probe": ("ffprobe -v error -select_streams v:0 -count_frames "
              "-show_entries stream=nb_read_frames,r_frame_rate,width,height,codec_name "
              "-show_entries format=duration -of json <FILE>"),
}


def probe(path) -> dict:
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
             "-show_entries", "stream=nb_read_frames,r_frame_rate,width,height,codec_name",
             "-show_entries", "format=duration", "-of", "json", str(path)])
    d = json.loads(r.stdout)
    s = d["streams"][0]
    n = int(s["nb_read_frames"])
    return {"n_frames": n, "fps": s["r_frame_rate"], "w": s["width"], "h": s["height"],
            "codec": s["codec_name"], "container_duration": float(d["format"]["duration"]),
            "decoded_duration": n / NORM_FPS}


def ingest_config():
    """The exact ingest config the val_tune cache (cab2bac1628012a3) was built
    under, read from a cached index's own stored config_snapshot rather than
    from today's DEFAULTS, which have drifted."""
    import numpy as np
    import part3_tune as pt
    ref = REPO / "tuning" / "index_cache" / "10001787725__cab2bac1628012a3.npz"
    snap = json.loads(str(np.load(ref, allow_pickle=True)["__manifest__"].item()))["config_snapshot"]
    cfg = pt.make_config({"retrieval_strategy": "hybrid"})
    for k, v in snap.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg, snap


def load_pool() -> tuple[list[str], dict]:
    """val_tune videos present locally, with their questions -- same filter
    chain scripts/scene_shortlist_recall.py uses."""
    from scene_shortlist_recall import load_questions
    qs = load_questions("val_tune")
    by_video = defaultdict(list)
    for q in qs:
        by_video[q["video"]].append(q)
    pool = sorted(v for v in by_video if (VIDEO_DIR / f"{v}.mp4").exists())
    return pool, by_video


def make_groups(pool: list[str], n_videos: int) -> dict:
    """Same n_videos sampled once, then re-partitioned for every k. A paired
    design: every arm measures the SAME question set, so differences across k
    come from concatenation alone, not from which videos were drawn. Ordering
    is reshuffled per k so a host video appears at varied positions."""
    rng = random.Random(SEED)
    chosen = rng.sample(pool, n_videos)
    groups = {}
    for k in KS:
        order = list(chosen)
        random.Random(SEED + k).shuffle(order)
        groups[k] = [order[i:i + k] for i in range(0, len(order), k)]
    return {"chosen": chosen, "groups": groups}


# ══ PART 2.1-2.3 -- build ════════════════════════════════════════════════
def cmd_build(args) -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "videos").mkdir(exist_ok=True)
    (WORK / "norm").mkdir(exist_ok=True)
    pool, by_video = load_pool()
    print(f"[build] pool = {len(pool)} val_tune videos with local .mp4", flush=True)
    spec = make_groups(pool, args.n_videos)
    chosen = spec["chosen"]
    nq = sum(len(by_video[v]) for v in chosen)
    print(f"[build] chose {len(chosen)} videos carrying {nq} questions "
          f"(target >= {MIN_QUESTIONS_PER_K} per arm)", flush=True)

    # ── normalise every chosen source once (the encode control) ──────────
    norm_info, failures = {}, []
    for i, v in enumerate(chosen):
        src, dst = VIDEO_DIR / f"{v}.mp4", WORK / "norm" / f"{v}.norm.mp4"
        if not dst.exists():
            r = run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src)]
                    + NORM_ARGS + [str(dst)])
            if r.returncode != 0 or not dst.exists():
                failures.append({"video": v, "stage": "normalise", "stderr": r.stderr[-400:]})
                continue
        orig, norm = probe(src), probe(dst)
        norm_info[v] = {"orig": orig, "norm": norm,
                        "duration_delta_s": round(norm["decoded_duration"] - orig["container_duration"], 6),
                        "delta_gt_one_frame": abs(norm["decoded_duration"] - orig["container_duration"]) > 1.0 / NORM_FPS}
        if (i + 1) % 20 == 0:
            print(f"  [normalise] {i+1}/{len(chosen)}", flush=True)
    print(f"[build] normalised {len(norm_info)}/{len(chosen)}, {len(failures)} failures", flush=True)

    # ── concat each group, then remap every question's gold span ─────────
    manifest, questions_out, remap_fail = [], [], []
    for k in KS:
        for gi, grp in enumerate(spec["groups"][k]):
            grp = [v for v in grp if v in norm_info]
            if not grp:
                continue
            name = f"k{k}_g{gi:03d}"
            dst = WORK / "videos" / f"{name}.mp4"
            lst = WORK / "videos" / f"{name}.txt"
            lst.write_text("".join(f"file '{WORK/'norm'/(v+'.norm.mp4')}'\n" for v in grp))
            if not dst.exists():
                r = run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "concat",
                         "-safe", "0", "-i", str(lst), "-c", "copy", str(dst)])
                if r.returncode != 0 or not dst.exists():
                    failures.append({"group": name, "stage": "concat", "stderr": r.stderr[-400:]})
                    continue
            cat = probe(dst)

            # Offsets from ACTUAL DECODED duration of each preceding segment
            # (n_frames / 30, exact for CFR), never from nominal container
            # duration. Both are recorded and compared.
            offsets, cum_dec, cum_nom = {}, 0.0, 0.0
            for v in grp:
                offsets[v] = {"decoded": cum_dec, "nominal": cum_nom}
                cum_dec += norm_info[v]["norm"]["decoded_duration"]
                cum_nom += norm_info[v]["norm"]["container_duration"]
            seg_frames = sum(norm_info[v]["norm"]["n_frames"] for v in grp)
            manifest.append({
                "name": name, "k": k, "group_index": gi, "members": grp,
                "path": str(dst), "bytes": dst.stat().st_size,
                "concat_frames": cat["n_frames"], "sum_segment_frames": seg_frames,
                "frames_match": cat["n_frames"] == seg_frames,
                "concat_decoded_duration": cat["decoded_duration"],
                "concat_container_duration": cat["container_duration"],
                "sum_decoded_duration": round(cum_dec, 6),
                "sum_nominal_duration": round(cum_nom, 6),
                "duration_disagreement_s": round(cum_dec - cum_nom, 6),
            })
            for pos, v in enumerate(grp, start=1):
                off = offsets[v]["decoded"]
                seg_dur = norm_info[v]["norm"]["decoded_duration"]
                for q in by_video[v]:
                    spans, dropped = [], 0
                    for (a, b) in q["gold_spans"]:
                        a2, b2 = a + off, min(b, seg_dur) + off
                        if b2 <= a2:
                            dropped += 1
                            continue
                        spans.append([round(a2, 6), round(b2, 6)])
                    if not spans:
                        remap_fail.append({"k": k, "group": name, "video": v, "qid": q["qid"],
                                           "reason": "all_spans_empty_after_clip"})
                        continue
                    questions_out.append({
                        "k": k, "group": name, "concat_video": str(dst),
                        "source_video": v, "qid": q["qid"], "question": q["question"],
                        "type": q["type"], "family": q["family"],
                        "host_position": pos, "n_segments": len(grp),
                        "offset_s": round(off, 6), "segment_duration_s": round(seg_dur, 6),
                        "gold_spans": spans, "orig_gold_spans": [list(g) for g in q["gold_spans"]],
                        "spans_clipped": dropped,
                    })
        print(f"[build] k={k}: {len([m for m in manifest if m['k']==k])} groups", flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (WORK / "build_manifest.json").write_text(json.dumps({
        "seed": SEED, "n_videos": args.n_videos, "chosen": chosen,
        "ffmpeg_cmdlines": FFMPEG_CMDLINES,
        "norm_info": norm_info, "groups": manifest,
        "failures": failures, "remap_failures": remap_fail,
    }, indent=2))
    (WORK / "questions.json").write_text(json.dumps(questions_out))
    per_k = defaultdict(int)
    for q in questions_out:
        per_k[q["k"]] += 1
    print(f"[build] questions per k: {dict(sorted(per_k.items()))}", flush=True)
    print(f"[build] remap failures: {len(remap_fail)} "
          f"({100*len(remap_fail)/max(1,len(questions_out)+len(remap_fail)):.3f}%)", flush=True)
    bad = [m for m in manifest if not m["frames_match"]]
    print(f"[build] groups whose concat frame count != sum of segments: {len(bad)}", flush=True)
    nf = [v for v, i in norm_info.items() if i["delta_gt_one_frame"]]
    print(f"[build] normalised videos differing from source by > 1 frame: {len(nf)} {nf[:10]}", flush=True)


# ══ PART 2.4 -- real ingest ══════════════════════════════════════════════
def _ingest_one(task):
    """Worker: real iris.ingest.ingest() on a concatenated video. No index
    merging, no scene_id offsetting -- the whole point is that the scene
    structure is discovered by the real pipeline on the real pixels."""
    import iris.ingest as iris_ingest
    name, path, out_path = task
    t0 = time.time()
    try:
        cfg, _ = ingest_config()
        idx = iris_ingest.ingest(path, cfg)
        iris_ingest.save_index(idx, out_path)
        scenes = {fr.scene_id for fr in idx.frames if fr.scene_id is not None and fr.scene_id >= 0}
        import numpy as np
        z = np.load(out_path if str(out_path).endswith(".npz") else str(out_path) + ".npz",
                    allow_pickle=True)
        d = json.loads(str(z["__manifest__"].item()))
        z.close()
        return {"name": name, "ok": True, "wall_s": round(time.time() - t0, 2),
                "survivors": len(idx.frames), "scenes": len(scenes),
                "frames_processed": d.get("frames_processed"),
                "retention_pct": round(100 * len(idx.frames) / max(1, d.get("frames_processed") or 1), 4),
                "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"name": name, "ok": False, "wall_s": round(time.time() - t0, 2),
                "survivors": 0, "scenes": 0, "frames_processed": 0,
                "retention_pct": 0.0, "error": repr(e)[:500]}


def cmd_ingest(args) -> None:
    from concurrent.futures import ProcessPoolExecutor
    bm = json.loads((WORK / "build_manifest.json").read_text())
    (WORK / "indexes").mkdir(parents=True, exist_ok=True)
    tasks = []
    for g in bm["groups"]:
        out = WORK / "indexes" / f"{g['name']}.npz"
        if out.exists() and not args.force:
            continue
        tasks.append((g["name"], g["path"], str(WORK / "indexes" / g["name"])))
    print(f"[ingest] {len(tasks)} concatenated videos to ingest "
          f"({len(bm['groups'])} total, {len(bm['groups'])-len(tasks)} already cached)", flush=True)

    rows = []
    log = WORK / "ingest_log.jsonl"
    done = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for r in ex.map(_ingest_one, tasks):
            rows.append(r)
            done += 1
            with open(log, "a") as f:
                f.write(json.dumps(r) + "\n")
            if not r["ok"]:
                print(f"  [ingest FAIL] {r['name']}: {r['error'][:200]}", flush=True)
            if done % 10 == 0:
                print(f"  [ingest] {done}/{len(tasks)}", flush=True)

    prev = []
    if (OUT / "ingest_log.csv").exists():
        prev = list(csv.DictReader(open(OUT / "ingest_log.csv")))
    byname = {r["name"]: r for r in prev}
    kof = {g["name"]: g["k"] for g in bm["groups"]}
    nseg = {g["name"]: len(g["members"]) for g in bm["groups"]}
    for r in rows:
        byname[r["name"]] = r
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "ingest_log.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "k", "n_segments", "ok", "wall_s", "survivors",
                                          "scenes", "frames_processed", "retention_pct", "error"])
        w.writeheader()
        for n in sorted(byname, key=lambda s: (kof.get(s, 0), s)):
            r = dict(byname[n])
            r["k"] = kof.get(n, "")
            r["n_segments"] = nseg.get(n, "")
            w.writerow({k: r.get(k, "") for k in w.fieldnames})
    ok = sum(1 for r in byname.values() if str(r["ok"]).lower() in ("true", "1"))
    print(f"[ingest] {ok}/{len(byname)} succeeded; wrote {OUT/'ingest_log.csv'}", flush=True)


# ══ PART 2.4 / 3 -- measure ══════════════════════════════════════════════
def cmd_measure(args) -> None:
    """Recall via the VERIFIED reconstruction in scripts/scene_shortlist_recall.py
    (commit 6039807) -- imported, not reimplemented. Its own verification is
    re-run here against retrieve_scene_sparse on the concatenated indexes."""
    import numpy as np
    import iris.ingest as iris_ingest
    from scene_shortlist_recall import analyse_question, production_width, wilson
    from iris.scene_retrieval import LinearScanScorer, retrieve_scene_sparse
    from iris.query import _call_embed_query

    bm = json.loads((WORK / "build_manifest.json").read_text())
    questions = json.loads((WORK / "questions.json").read_text())
    cfg, _ = ingest_config()
    scorer = LinearScanScorer()

    by_group = defaultdict(list)
    for q in questions:
        by_group[q["group"]].append(q)

    rows, missing_idx, verify_pool = [], [], []
    t0 = time.time()
    for gi, (gname, qs) in enumerate(sorted(by_group.items())):
        ipath = WORK / "indexes" / f"{gname}.npz"
        if not ipath.exists():
            missing_idx.append(gname)
            continue
        index = iris_ingest.load_index(str(ipath))
        for q in qs:
            # analyse_question's contract: primary_span = longest gold span,
            # gold_spans = all of them, both already remapped onto the
            # concatenated timeline.
            spans = [(a, b) for a, b in q["gold_spans"]]
            qq = {"video": gname, "qid": q["qid"], "question": q["question"],
                  "type": q["type"], "family": q["family"], "gold_spans": spans,
                  "primary_span": max(spans, key=lambda g: g[1] - g[0]),
                  "span_len": max(g[1] - g[0] for g in spans)}
            emb, _ = _call_embed_query(q["question"], cfg)
            res = analyse_question(index, qq, emb, scorer)
            if res.get("error"):
                continue
            res.update({"k": q["k"], "group": gname, "source_video": q["source_video"],
                        "host_position": q["host_position"], "n_segments": q["n_segments"],
                        "offset_s": q["offset_s"]})
            res.pop("_sweep", None)
            rows.append(res)
            if len(verify_pool) < 25 and len(rows) % 37 == 0:
                verify_pool.append((str(ipath), qq, res))
        del index
        if (gi + 1) % 20 == 0:
            print(f"  [measure] {gi+1}/{len(by_group)} groups, {len(rows)} rows, "
                  f"{time.time()-t0:.0f}s", flush=True)

    # ── re-run the 6039807 reconstruction verification on THIS data ──────
    n_match, verify_detail = 0, []
    for ipath, qq, res in verify_pool:
        index = iris_ingest.load_index(ipath)
        emb, _ = _call_embed_query(qq["question"], cfg)
        trace: dict = {}
        try:
            retrieve_scene_sparse(index, emb, cfg, trace=trace)
        except Exception as e:  # noqa: BLE001
            verify_detail.append({"group": qq["video"], "qid": qq["qid"], "match": False, "error": repr(e)})
            continue
        prod = set(trace.get("shortlisted_scene_ids") or [])
        ranking = scorer.score(emb, index._scene_centroids)
        exp = (set(index._scene_centroids)
               if (res["fallback_all_scenes_fired"] or res["fallback_empty_pool_fired"])
               else {sid for sid, _ in ranking[:res["shortlist_width"]]})
        ok = prod == exp
        n_match += ok
        verify_detail.append({"group": qq["video"], "qid": qq["qid"], "match": bool(ok)})
        del index
    print(f"[measure] reconstruction verification: {n_match}/{len(verify_pool)}", flush=True)
    if n_match != len(verify_pool):
        raise SystemExit(f"GUARD: reconstruction {n_match}/{len(verify_pool)}: "
                         f"{json.dumps(verify_detail, indent=1)}")

    OUT.mkdir(parents=True, exist_ok=True)
    fields = [c for c in rows[0] if not c.startswith("_")]
    for k in KS:
        sub = [r for r in rows if r["k"] == k]
        if not sub:
            continue
        with open(OUT / f"k{k}_per_question.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(sub)

    (WORK / "measure_rows.json").write_text(json.dumps(rows))
    (WORK / "verify_detail.json").write_text(json.dumps(
        {"n_matched": n_match, "n_sampled": len(verify_pool), "detail": verify_detail}, indent=2))
    print(f"[measure] {len(rows)} rows; missing indexes: {len(missing_idx)} {missing_idx[:5]}", flush=True)


# ══ STEP 3/4 -- gates, width curves, verdict ═════════════════════════════
def recall_at(rows, width_fn) -> tuple[float, int, float]:
    """A question hits at width w iff its best gold scene ranks within
    min(w, n_scenes). best_gold_rank and n_scenes come straight from the
    verified analyse_question output, so no shortlist logic is re-derived."""
    hit = 0
    widths = []
    for r in rows:
        n = int(r["n_scenes"])
        w = min(max(1, width_fn(n)), n)
        widths.append(w)
        br = r["best_gold_rank"]
        if br != "" and br is not None and int(br) <= w:
            hit += 1
    return hit / len(rows), hit, statistics.mean(widths)


def smallest_c_sqrt(rows, target=0.98, cmax=64.0):
    """Smallest c with recall(ceil(c*sqrt(N))) >= target, bisected on a grid."""
    lo, hi = 0.0, cmax
    if recall_at(rows, lambda n: math.ceil(cmax * math.sqrt(n)))[0] < target:
        return None, None, None
    for _ in range(40):
        mid = (lo + hi) / 2
        if recall_at(rows, lambda n, c=mid: math.ceil(c * math.sqrt(n)))[0] >= target:
            hi = mid
        else:
            lo = mid
    rec, hit, mw = recall_at(rows, lambda n: math.ceil(hi * math.sqrt(n)))
    return round(hi, 4), rec, mw


def smallest_f_frac(rows, target=0.98):
    """Smallest f with recall(ceil(f*N)) >= target."""
    lo, hi = 0.0, 1.0
    if recall_at(rows, lambda n: n)[0] < target:
        return None, None, None
    for _ in range(40):
        mid = (lo + hi) / 2
        if recall_at(rows, lambda n, f=mid: math.ceil(f * n))[0] >= target:
            hi = mid
        else:
            lo = mid
    rec, hit, mw = recall_at(rows, lambda n: math.ceil(hi * n))
    return round(hi, 4), rec, mw


RULES = [
    ("ceil_sqrt_N__production", lambda n: max(4, math.ceil(math.sqrt(n)))),
    ("2x_ceil_sqrt_N", lambda n: 2 * math.ceil(math.sqrt(n))),
    ("4x_ceil_sqrt_N", lambda n: 4 * math.ceil(math.sqrt(n))),
    ("ceil_N_over_4", lambda n: math.ceil(n / 4)),
    ("ceil_N_over_2", lambda n: math.ceil(n / 2)),
    ("N_all_scenes", lambda n: n),
]


def cmd_analyse(args) -> None:
    rows = json.loads((WORK / "measure_rows.json").read_text())
    bm = json.loads((WORK / "build_manifest.json").read_text())
    chosen = set(bm["chosen"])
    by_k = defaultdict(list)
    for r in rows:
        by_k[r["k"]].append(r)

    # ── GATE A: k=1 on the ORIGINAL cached indexes, same questions ───────
    orig_csv = REPO / "tuning" / "scene_shortlist_recall" / "val_tune_per_question.csv"
    orig = [r for r in csv.DictReader(open(orig_csv)) if r["video_id"] in chosen]
    orig_hit = sum(1 for r in orig if r["hit_at_shortlist"] == "True")
    orig_rate = orig_hit / len(orig) if orig else 0.0
    k1 = by_k.get(1, [])
    k1_rate, k1_hit, _ = recall_at(k1, RULES[0][1]) if k1 else (0.0, 0, 0)
    qid_orig = {(r["video_id"], r["qid"]) for r in orig}
    qid_k1 = {(r["source_video"], r["qid"]) for r in k1}
    lo, hi = wilson_ci(orig_hit, len(orig))
    gate_a = {
        "reference_full_split": 0.7359,
        "original_cache_same_questions": {"rate": orig_rate, "n_hit": orig_hit, "n": len(orig),
                                          "ci95": [round(lo, 4), round(hi, 4)]},
        "k1_reencoded_arm": {"rate": k1_rate, "n_hit": k1_hit, "n": len(k1)},
        "question_overlap": len(qid_orig & qid_k1),
        "question_overlap_pct": round(100 * len(qid_orig & qid_k1) / max(1, len(qid_orig)), 2),
        # PASS iff the ORIGINAL-cache figure on these questions covers 0.7359
        # in its 95% CI. The re-encoded arm is reported alongside, not gated,
        # so the encode effect stays visible rather than being absorbed.
        "pass": bool(lo <= 0.7359 <= hi),
    }

    # ── GATE B: full-width recall must stay at the L1 ceiling for every k ─
    gate_b, gate_b_pass = {}, True
    for k in sorted(by_k):
        rec, hit, _ = recall_at(by_k[k], lambda n: n)
        gate_b[str(k)] = {"rate": rec, "n_hit": hit, "n": len(by_k[k])}
        if rec < 0.97:
            gate_b_pass = False

    # ── width sweep + the three width columns at every k ─────────────────
    sweep_rows, three = [], {}
    for k in sorted(by_k):
        sub = by_k[k]
        ns = [int(r["n_scenes"]) for r in sub]
        for name, fn in RULES:
            rec, hit, mw = recall_at(sub, fn)
            lo2, hi2 = wilson_ci(hit, len(sub))
            sweep_rows.append({"k": k, "rule": name, "mean_width": round(mw, 3),
                               "recall": round(rec, 6), "n_hit": hit, "n_total": len(sub),
                               "ci95_lo": round(lo2, 4), "ci95_hi": round(hi2, 4),
                               "mean_n_scenes": round(statistics.mean(ns), 2)})
        c, c_rec, c_w = smallest_c_sqrt(sub)
        f, f_rec, f_w = smallest_f_frac(sub)
        three[str(k)] = {
            "n_questions": len(sub),
            "mean_n_scenes": round(statistics.mean(ns), 2),
            "median_n_scenes": statistics.median(ns),
            "max_n_scenes": max(ns),
            "width98_absolute": round(c_w, 2) if c_w else None,
            "width98_x_sqrtN": c,
            "width98_fraction_of_N": f,
            "width98_fraction_rule_mean_width": round(f_w, 2) if f_w else None,
            "recall_at_c": round(c_rec, 4) if c_rec else None,
            "recall_at_f": round(f_rec, 4) if f_rec else None,
        }

    with open(OUT / "width_sweep_by_k.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sweep_rows[0].keys()))
        w.writeheader()
        w.writerows(sweep_rows)

    # ── positional bias ──────────────────────────────────────────────────
    pos = {}
    for k in sorted(by_k):
        if k == 1:
            continue
        pb = defaultdict(list)
        for r in by_k[k]:
            pb[int(r["host_position"])].append(r)
        pos[str(k)] = {str(p): {"n": len(v),
                                "recall_production": round(recall_at(v, RULES[0][1])[0], 4)}
                       for p, v in sorted(pb.items())}

    # ── verdict from the pre-registered table ────────────────────────────
    cs = [three[str(k)]["width98_x_sqrtN"] for k in sorted(by_k) if three[str(k)]["width98_x_sqrtN"]]
    fs = [three[str(k)]["width98_fraction_of_N"] for k in sorted(by_k) if three[str(k)]["width98_fraction_of_N"]]
    def spread(xs):
        return (max(xs) - min(xs)) / statistics.mean(xs) if xs and statistics.mean(xs) else None
    c_spread, f_spread = spread(cs), spread(fs)
    if not (gate_a["pass"] and gate_b_pass):
        verdict = "INCONCLUSIVE"
    elif c_spread is not None and c_spread <= 0.25:
        verdict = "SCALE_INVARIANT"
    elif f_spread is not None and f_spread <= 0.25 and (c_spread or 0) > 0.25:
        verdict = "SHORT_VIDEO_ARTIFACT"
    else:
        verdict = "INCONCLUSIVE"

    summary = {
        "seed": SEED, "ks": sorted(by_k), "n_videos_sampled": len(chosen),
        "gate_a": gate_a, "gate_b": {"by_k": gate_b, "pass": gate_b_pass},
        "three_width_columns": three,
        "sqrtN_multiple_spread": round(c_spread, 4) if c_spread is not None else None,
        "fraction_of_N_spread": round(f_spread, 4) if f_spread is not None else None,
        "positional_bias": pos,
        "verdict": verdict,
        "reconstruction_verification": json.loads((WORK / "verify_detail.json").read_text()),
        "build_failures": bm["failures"], "remap_failures": bm["remap_failures"],
        "n_remap_failures": len(bm["remap_failures"]),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in
                      ("gate_a", "gate_b", "three_width_columns",
                       "sqrtN_multiple_spread", "fraction_of_N_spread", "verdict")}, indent=2))


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("structural")
    b = sub.add_parser("build"); b.add_argument("--n-videos", type=int, default=80)
    i = sub.add_parser("ingest"); i.add_argument("--workers", type=int, default=6); i.add_argument("--force", action="store_true")
    sub.add_parser("measure")
    sub.add_parser("analyse")
    a = ap.parse_args()
    {"structural": cmd_structural, "build": cmd_build, "ingest": cmd_ingest,
     "measure": cmd_measure, "analyse": cmd_analyse}[a.cmd](a)
