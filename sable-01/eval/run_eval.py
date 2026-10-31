#!/usr/bin/env python3
"""Sable-01 baseline/adapter eval runner — loads the MLX model ONCE, runs the
frozen holdout set, writes predictions.jsonl for score.py.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Usage:
    python3 run_eval.py <model-or-adapter-path> [--out predictions.jsonl] [--max-tokens 200]

Runs with the mlx venv:  ~/sable-01/venv/bin/python3 eval/run_eval.py ...
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


THINK_OPEN = "<" + "think>"          # built by concat so tool transport can't eat the tag
THINK_CLOSE = "<" + "/think>"


def strip_thinking(text: str) -> tuple[str, bool]:
    """Qwen3 reasons inside a thinking region before answering; graders must
    only see the final answer. Returns (answer, was_truncated)."""
    open_t, close_t = text.count(THINK_OPEN), text.count(THINK_CLOSE)
    truncated = open_t > close_t  # budget ran out mid-thinking
    pattern = re.escape(THINK_CLOSE) + r"\s*(.*)"
    match = re.search(pattern, text, re.S)
    return (match.group(1).strip() if match else text.strip()), truncated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("model", help="MLX model or adapter path (adapter via --adapter)")
    ap.add_argument("--adapter", default=None, help="LoRA adapter path on top of --model base")
    ap.add_argument("--out", default=str(HERE / "predictions.jsonl"))
    ap.add_argument("--max-tokens", type=int, default=1024,
                    help="generous default: thinking must finish or the answer never appears")
    args = ap.parse_args()

    from mlx_lm import generate, load

    cases = [json.loads(line) for line in (HERE / "holdout.jsonl").read_text().splitlines() if line.strip()]
    print(f"[eval] loading {args.model}" + (f" + adapter {args.adapter}" if args.adapter else ""))
    model, tokenizer = load(args.model, adapter_path=args.adapter)
    print(f"[eval] {len(cases)} cases")

    out_path = Path(args.out)
    with out_path.open("w") as out:
        for index, case in enumerate(cases, 1):
            start = time.monotonic()
            messages = [{"role": "user", "content": case["prompt"]}]
            prompt_ids = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True
            )
            text = generate(
                model, tokenizer, prompt=prompt_ids, max_tokens=args.max_tokens
            )
            seconds = time.monotonic() - start
            answer, truncated = strip_thinking(text)
            out.write(json.dumps(
                {"id": case["id"], "output": answer, "truncated": truncated, "raw_len": len(text)},
                ensure_ascii=False,
            ) + "\n")
            out.flush()
            flag = "  [truncated!]" if truncated else ""
            print(f"[{index}/{len(cases)}] {case['id']} {seconds:.1f}s {len(answer)} chars{flag}")
    print(f"[eval] predictions -> {out_path}")
    print(f"[eval] now: venv/bin/python3 eval/score.py {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
