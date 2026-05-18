"""CFL-001 -- pre/post fingerprint diff utility for spec §6.2 acceptance #3 + #5.

Purpose
-------
Spec §6.2 requires that CFL-001 introduce ZERO numeric drift on any pre-CFL
field (#3) and ZERO verdict change on any ticker (#5). This script automates
the comparison between an engine JSON output captured BEFORE CFL-001 was
merged (i.e., on master) and an engine JSON output captured AFTER CFL-001
was merged (i.e., on feat/CFL-001-confluence-detection or a later master).

The script strips every `confluence` sub-object recursively, then deep-diffs
the remainder. Anything other than the additive `confluence` keys appearing
as a difference is a CFL-001 regression candidate.

Usage
-----
    python layers/cfl001_fingerprint_diff.py PRE.json POST.json
    python layers/cfl001_fingerprint_diff.py --cohort PRE_DIR POST_DIR

`PRE_DIR` and `POST_DIR` should contain identically named JSON files (one
per ticker), e.g. NVDA_A.json, OXY_A.json, AAPL_B.json. The script pairs
them by filename.

Float tolerance
---------------
A small relative tolerance (1e-9 relative + 1e-12 absolute) is applied when
comparing floats to absorb harmless IEEE-754 noise from re-runs on the same
input (rare but possible if upstream uses pandas reductions). This is the
SAME order of magnitude as `_CFL_BOUNDARY_TOLERANCE` in transform.py; it
does NOT mask any operator-meaningful drift.

Exit codes
----------
    0 -- verdict matches AND no non-confluence diffs across all pairs
    1 -- mismatch (verdict change OR non-confluence field drift)
    2 -- usage / IO error

Workflow for §6.2 acceptance
----------------------------
    1. git checkout master  (or commit pre-CFL-001: 0062ac2)
    2. For each ticker in the cohort, run:
           python layers/tbs_engine_cli.py --ticker=X --profile=Y --mode=LIVE
       redirected to PRE/X_Y.json
    3. git checkout feat/CFL-001-confluence-detection
       (or whichever commit you're validating)
    4. Same runs as step 2, redirected to POST/X_Y.json
    5. python layers/cfl001_fingerprint_diff.py --cohort PRE POST
    6. Exit code 0 -> §6.2 #3 + #5 pass for this cohort

Caveat: LIVE-mode runs at different wall-clock times will see different
market data and will NOT compare cleanly. Use a frozen/cached/replay data
source for true acceptance. The script's diff output will surface ANY
non-confluence field difference, including those caused by market drift
between runs; the operator interprets the report accordingly.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Tolerance for float comparisons -- absorbs harmless IEEE-754 noise only.
# Same order of magnitude as transform._CFL_BOUNDARY_TOLERANCE. Two floats
# are considered equal if either:
#     abs(a - b) <= ABS_TOL                                (near zero), or
#     abs(a - b) <= REL_TOL * max(abs(a), abs(b))          (general case)
# ---------------------------------------------------------------------------
_ABS_TOL = 1e-12
_REL_TOL = 1e-9


def _strip_confluence(obj: Any) -> Any:
    """Return a deep copy of `obj` with every `confluence` key removed
    from every nested dict. Non-dict / non-list values pass through."""
    if isinstance(obj, dict):
        return {k: _strip_confluence(v) for k, v in obj.items() if k != "confluence"}
    if isinstance(obj, list):
        return [_strip_confluence(v) for v in obj]
    return obj


def _floats_equal(a: float, b: float) -> bool:
    """Tolerance-aware float comparison. Booleans pass through unchanged
    because in Python `isinstance(True, int) is True` -- callers must
    type-check before calling this."""
    diff = abs(a - b)
    if diff <= _ABS_TOL:
        return True
    return diff <= _REL_TOL * max(abs(a), abs(b))


def _diff(pre: Any, post: Any, path: str = "$") -> list[str]:
    """Recursive deep-diff. Returns a list of human-readable diff entries.
    Empty list means equal. Each entry is `<path>: <pre> != <post>`."""
    # Type mismatch (treat int/float as compatible; bool is its own type
    # because Python's bool is an int subclass but distinct semantically)
    pre_is_num = isinstance(pre, (int, float)) and not isinstance(pre, bool)
    post_is_num = isinstance(post, (int, float)) and not isinstance(post, bool)

    if pre_is_num and post_is_num:
        return [] if _floats_equal(float(pre), float(post)) else [f"{path}: {pre!r} != {post!r}"]

    if type(pre) is not type(post):
        return [f"{path}: type {type(pre).__name__} != {type(post).__name__} ({pre!r} != {post!r})"]

    if isinstance(pre, dict):
        diffs: list[str] = []
        pre_keys = set(pre.keys())
        post_keys = set(post.keys())
        for k in sorted(pre_keys - post_keys):
            diffs.append(f"{path}.{k}: present pre, absent post (pre value: {pre[k]!r})")
        for k in sorted(post_keys - pre_keys):
            diffs.append(f"{path}.{k}: absent pre, present post (post value: {post[k]!r})")
        for k in sorted(pre_keys & post_keys):
            diffs.extend(_diff(pre[k], post[k], f"{path}.{k}"))
        return diffs

    if isinstance(pre, list):
        diffs = []
        if len(pre) != len(post):
            diffs.append(f"{path}: list length {len(pre)} != {len(post)}")
            # Still diff the common prefix to surface what changed.
        for i, (a, b) in enumerate(zip(pre, post)):
            diffs.extend(_diff(a, b, f"{path}[{i}]"))
        return diffs

    # Strings, None, etc.
    return [] if pre == post else [f"{path}: {pre!r} != {post!r}"]


def _verdict_of(obj: Any) -> str | None:
    """Best-effort verdict extraction."""
    try:
        return obj["action_summary"]["verdict"]
    except (KeyError, TypeError):
        return None


def _compare_pair(pre_path: str, post_path: str, label: str) -> tuple[bool, list[str], str | None, str | None]:
    """Returns (passed, diff_lines, pre_verdict, post_verdict)."""
    with open(pre_path) as f:
        pre = json.load(f)
    with open(post_path) as f:
        post = json.load(f)

    pre_verdict = _verdict_of(pre)
    post_verdict = _verdict_of(post)
    verdict_ok = (pre_verdict == post_verdict)

    pre_stripped = _strip_confluence(pre)
    post_stripped = _strip_confluence(post)
    diffs = _diff(pre_stripped, post_stripped, label)

    return (verdict_ok and not diffs, diffs, pre_verdict, post_verdict)


def _format_pair_report(label: str, passed: bool, diffs: list[str], pre_v: str | None, post_v: str | None) -> str:
    out: list[str] = []
    out.append(f"=== {label} ===")
    out.append(f"  Verdict pre={pre_v!r} post={post_v!r} match={'YES' if pre_v == post_v else 'NO'}")
    if not diffs:
        out.append("  Non-confluence fields: IDENTICAL")
    else:
        out.append(f"  Non-confluence fields: {len(diffs)} differences")
        for d in diffs[:50]:
            out.append(f"    {d}")
        if len(diffs) > 50:
            out.append(f"    ... and {len(diffs) - 50} more")
    out.append(f"  Result: {'PASS' if passed else 'FAIL'}")
    return "\n".join(out)


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="CFL-001 pre/post fingerprint diff.")
    p.add_argument("pre", nargs="?", help="Pre-CFL JSON file (single-pair mode)")
    p.add_argument("post", nargs="?", help="Post-CFL JSON file (single-pair mode)")
    p.add_argument("--cohort", nargs=2, metavar=("PRE_DIR", "POST_DIR"),
                   help="Compare every .json file present in both directories (paired by filename)")
    args = p.parse_args(argv)

    pairs: list[tuple[str, str, str]] = []  # (label, pre_path, post_path)

    if args.cohort:
        pre_dir, post_dir = args.cohort
        if not os.path.isdir(pre_dir) or not os.path.isdir(post_dir):
            print(f"ERROR: cohort dirs must exist: {pre_dir!r}, {post_dir!r}", file=sys.stderr)
            return 2
        pre_files = {f for f in os.listdir(pre_dir) if f.endswith(".json")}
        post_files = {f for f in os.listdir(post_dir) if f.endswith(".json")}
        common = sorted(pre_files & post_files)
        only_pre = sorted(pre_files - post_files)
        only_post = sorted(post_files - pre_files)
        if only_pre:
            print(f"WARN: files in PRE only: {only_pre}", file=sys.stderr)
        if only_post:
            print(f"WARN: files in POST only: {only_post}", file=sys.stderr)
        if not common:
            print("ERROR: no paired .json files found", file=sys.stderr)
            return 2
        for fname in common:
            pairs.append((fname, os.path.join(pre_dir, fname), os.path.join(post_dir, fname)))
    elif args.pre and args.post:
        pairs.append((os.path.basename(args.pre), args.pre, args.post))
    else:
        p.print_help()
        return 2

    all_passed = True
    cohort_summary: list[tuple[str, bool]] = []
    for label, pre_path, post_path in pairs:
        passed, diffs, pre_v, post_v = _compare_pair(pre_path, post_path, label)
        print(_format_pair_report(label, passed, diffs, pre_v, post_v))
        print()
        all_passed = all_passed and passed
        cohort_summary.append((label, passed))

    if len(cohort_summary) > 1:
        print("=== COHORT SUMMARY ===")
        for label, passed in cohort_summary:
            print(f"  {'PASS' if passed else 'FAIL'}  {label}")
        print(f"Total: {sum(p for _, p in cohort_summary)}/{len(cohort_summary)} pass")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))