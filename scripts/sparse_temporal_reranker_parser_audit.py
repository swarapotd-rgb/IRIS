"""Parser audit for every val_tune question + a stratified human-review sample.

Pure parsing: no retrieval, no GPU, no index, no gold spans. Gold spans are not
read at all by this script -- it is a description of the parser's behaviour on
question text only.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from iris.query_reformulation import (  # noqa: E402
    TYPE_CODE_RELATION, build_query_plan_v2, all_embedding_texts,
)
from iris.query_reformulation_v3 import (  # noqa: E402
    all_embedding_texts_v3, build_query_plan_v3, extract_structure,
    parser_status, seed_embedding_texts,
)

OUT_DIR = REPO / "tuning" / "sparse_temporal_reranker_v1"
AUDIT_CSV = OUT_DIR / "parser_audit.csv"
SAMPLE_CSV = OUT_DIR / "parser_human_review_sample.csv"
DIAG_JSON = OUT_DIR / "parser_diagnostics.json"

TYPE_CODES = ["CW", "CH", "TN", "TP", "TC"]


class _NoAliasConfig:
    action_aliases_enabled = False
    typo_normalization_enabled = True


def load_questions() -> list[dict]:
    split = json.loads((REPO / "split_manifest.json").read_text())
    tune = set(split["tune_videos"])
    gsub = json.loads((REPO / "eval/data/nextqa/gsub_val.json").read_text())
    rows = []
    with open(REPO / "eval/data/nextqa/val.csv", newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["video"] not in tune:
                continue
            if not gsub.get(r["video"], {}).get("location", {}).get(r["qid"]):
                continue
            rows.append({"video": r["video"], "qid": r["qid"],
                         "question": r["question"], "type": r["type"]})
    return rows


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _NoAliasConfig()
    questions = load_questions()

    fields = [
        "qid", "video", "question", "type_code",
        "relation_from_type", "relation_from_lexical", "relation_final",
        "relation_disagreement", "extraction_status", "anchor_clause",
        "target_entity", "query_roles", "query_texts", "seed_texts",
        "fallback_reason", "n_text_embeddings", "n_seed_queries",
        "subject_prepended", "head_form",
        "v2_fallback_reason", "v2_texts",
    ]
    rows_out = []
    status_counts = Counter()
    per_type_status = defaultdict(Counter)
    v2_fallback = Counter()
    per_type_v2_fallback = defaultdict(Counter)
    disagreements = 0
    embed_hist = Counter()

    for q in questions:
        tc = q["type"]
        p3 = build_query_plan_v3(q["question"], type_code=tc, family=tc[0], config=cfg)
        p2 = build_query_plan_v2(q["question"], type_code=tc, family=tc[0], config=cfg)
        info = extract_structure(q["question"].lower(), type_code=tc)
        seeds, _ = seed_embedding_texts(p3)
        texts = all_embedding_texts_v3(p3)

        rel_type = TYPE_CODE_RELATION.get(tc.upper())
        rel_lex = info["lexical_relation"]
        disagree = bool(rel_type and rel_lex and rel_type != rel_lex)
        disagreements += disagree
        status = parser_status(p3)
        status_counts[status] += 1
        per_type_status[tc][status] += 1
        v2_fallback[p2.fallback_reason or "<none>"] += 1
        per_type_v2_fallback[tc][p2.fallback_reason or "<none>"] += 1
        embed_hist[len(texts)] += 1

        rows_out.append({
            "qid": q["qid"], "video": q["video"], "question": q["question"], "type_code": tc,
            "relation_from_type": rel_type or "",
            "relation_from_lexical": rel_lex or "",
            "relation_final": p3.relation,
            "relation_disagreement": int(disagree),
            "extraction_status": status,
            "anchor_clause": info["anchor_event"] or "",
            "target_entity": info["target_entity"] or "",
            "query_roles": json.dumps(list(p3.query_roles)),
            "query_texts": json.dumps(list(texts)),
            "seed_texts": json.dumps(list(seeds)),
            "fallback_reason": p3.fallback_reason or "",
            "n_text_embeddings": len(texts),
            "n_seed_queries": len(seeds),
            "subject_prepended": int(bool(info["subject_prepended"])),
            "head_form": info["head_form"],
            "v2_fallback_reason": p2.fallback_reason or "",
            "v2_texts": json.dumps(list(all_embedding_texts(p2))),
        })

    with open(AUDIT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows_out)

    # ── stratified human-review sample (>=200) ───────────────────────────
    rng = random.Random(20260725)
    by_type = defaultdict(list)
    for r in rows_out:
        by_type[r["type_code"]].append(r)

    picked: list[dict] = []
    picked_keys: set[tuple[str, str]] = set()

    def take(pool, n, reason):
        rng.shuffle(pool)
        added = 0
        for r in pool:
            key = (r["video"], r["qid"])
            if key in picked_keys:
                continue
            row = dict(r)
            row["sample_reason"] = reason
            picked.append(row)
            picked_keys.add(key)
            added += 1
            if added >= n:
                break

    for tc in TYPE_CODES:
        take(list(by_type.get(tc, [])), 30, f"stratified_{tc}")
    take([r for r in rows_out if r["extraction_status"] in {"no_structure", "entity_only",
                                                            "negated_no_anchor"}], 30, "parser_failure")
    take([r for r in rows_out if r["relation_disagreement"]], 30, "type_lexical_disagreement")
    take([r for r in rows_out if r["extraction_status"] == "clause_extracted"
          and not r["subject_prepended"]], 20, "explicit_subject_clause")
    take([r for r in rows_out if any(
        p in r["anchor_clause"].split()[:1] for p in ("he", "she", "it", "they"))], 20, "pronoun_clause")

    sample_fields = fields + ["sample_reason", "human_label_anchor_ok",
                              "human_label_relation_ok", "human_notes"]
    with open(SAMPLE_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=sample_fields)
        w.writeheader()
        for r in picked:
            # Human label columns are deliberately EMPTY -- no fabricated labels.
            w.writerow({**r, "human_label_anchor_ok": "", "human_label_relation_ok": "",
                        "human_notes": ""})

    diag = {
        "n_questions": len(questions),
        "v3_status_counts": dict(status_counts),
        "v3_status_rate": {k: v / len(questions) for k, v in status_counts.items()},
        "v3_anchor_emitted": sum(v for k, v in status_counts.items()
                                 if k in {"clause_extracted", "head_event"}),
        "v3_anchor_emitted_rate": sum(v for k, v in status_counts.items()
                                      if k in {"clause_extracted", "head_event"}) / len(questions),
        "v2_fallback_counts": dict(v2_fallback),
        "v2_fallback_rate": v2_fallback["no_clause_pattern_matched"] / len(questions),
        "per_type_v3_status": {k: dict(v) for k, v in per_type_status.items()},
        "per_type_v2_fallback": {k: dict(v) for k, v in per_type_v2_fallback.items()},
        "type_lexical_disagreements": disagreements,
        "type_lexical_disagreement_rate": disagreements / len(questions),
        "embedding_count_histogram": {str(k): v for k, v in sorted(embed_hist.items())},
        "max_embeddings": max(embed_hist),
        "human_review_sample_size": len(picked),
    }
    DIAG_JSON.write_text(json.dumps(diag, indent=2))
    print(json.dumps(diag, indent=2))
    print(f"\nwrote {AUDIT_CSV} ({len(rows_out)} rows)")
    print(f"wrote {SAMPLE_CSV} ({len(picked)} rows, human label columns empty)")


if __name__ == "__main__":
    main()
