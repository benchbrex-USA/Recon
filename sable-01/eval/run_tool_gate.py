#!/usr/bin/env python3
"""Sable-01 tool-emission gate - frozen 10-case suite (run 3 acceptance).

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

Pass bar: >= 7/10 emit a well-formed tool call (or a no-call prose answer for
the discrimination cases T-09/T-10).
Usage: venv/bin/python3 eval/run_tool_gate.py <adapter-path>
"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
THINK_OPEN = "<" + "think>"
THINK_CLOSE = "<" + "/think>"


def strip_thinking(text: str) -> str:
    m = re.search(re.escape(THINK_CLOSE) + r"\s*(.*)", text, re.S)
    return (m.group(1) if m else text).strip()


def parse_call(text: str):
    """Return (tool, arguments) from the first JSON object with a tool key.

    Uses json.JSONDecoder.raw_decode scanning — correct even when argument
    string values contain braces (Goldfish-A P0-2). Nested objects and
    braces-in-strings both parse correctly.
    """
    dec = json.JSONDecoder()
    idx = text.find("{")
    while idx != -1:
        try:
            obj, _ = dec.raw_decode(text, idx)
        except json.JSONDecodeError:
            idx = text.find("{", idx + 1)
            continue
        if isinstance(obj, dict) and "tool" in obj:
            return obj.get("tool"), obj.get("arguments") or {}
        idx = text.find("{", idx + 1)
    return None, None


def main() -> int:
    adapter = sys.argv[1] if len(sys.argv) > 1 else "adapters/r16-run3"
    cases = [json.loads(l) for l in (HERE / "tool_gate.jsonl").read_text().splitlines() if l.strip()]
    from mlx_lm import generate, load
    print(f"[gate] base + adapter {adapter}, {len(cases)} cases")
    model, tokenizer = load(str(HERE.parent / "base"), adapter_path=adapter)
    passed = 0
    out_path = HERE / "predictions-toolgate.jsonl"
    with out_path.open("w") as out:
        for i, case in enumerate(cases, 1):
            expect = case["expect"]
            user = ("Available tools:\n" + json.dumps(case["tools"], indent=1)
                    + "\n\n" + case["prompt"])
            ids = tokenizer.apply_chat_template([{"role": "user", "content": user}],
                                                add_generation_prompt=True)
            t0 = time.monotonic()
            text = generate(model, tokenizer, prompt=ids, max_tokens=512)
            answer = strip_thinking(text)
            tool, args = parse_call(answer)
            ok = (tool == expect["tool"]) if expect["tool"] else (tool is None)
            if ok and expect["tool"]:
                ok = all(a in (args or {}) for a in expect["args"])
            passed += ok
            line = {"id": case["id"], "ok": ok, "emitted_tool": tool,
                    "expected": expect["tool"], "answer": answer}
            out.write(json.dumps(line, ensure_ascii=False) + "\n"); out.flush()
            print(f"[{i}/{len(cases)}] {case['id']} {'PASS' if ok else 'FAIL'} "
                  f"(emitted: {tool}, expected: {expect['tool']}) {time.monotonic()-t0:.1f}s")
    print(f"[gate] {passed}/{len(cases)} - {'PASS (>=7)' if passed >= 7 else 'FAIL'}")
    return 0 if passed >= 7 else 1


if __name__ == "__main__":
    raise SystemExit(main())
