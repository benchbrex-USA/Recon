"""Tool handlers - the code that runs when the LLM calls each tool.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).

ask_sable sends ONLY the question to the local envelope-guarded Sable-01 endpoint
(127.0.0.1:8001, per designs/sable-agent-integration.md r3). 120 s total timeout.
All failures return readable text - never raw tracebacks.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

GUARD_URL = "http://127.0.0.1:8001/v1/chat/completions"
TOTAL_TIMEOUT_S = 120
START_HINT = "~/sable-01/serve.sh start"


def ask_sable(question, max_tokens: int = 512, temperature: float = 0.3) -> str:
    # models occasionally emit the question as a nested object; coerce to text
    if not isinstance(question, str):
        question = json.dumps(question, ensure_ascii=False)
    body = json.dumps({
        "model": "default_model",
        "messages": [{"role": "user", "content": question}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }).encode()
    req = urllib.request.Request(GUARD_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TOTAL_TIMEOUT_S) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get("error", "")
        except Exception:
            detail = f"HTTP {exc.code}"
        return f"Sable-01 unavailable: {detail}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError) \
                or "timed out" in str(reason).lower():
            return (f"Sable-01 timed out after {TOTAL_TIMEOUT_S} s - the model may be "
                    f"thinking; retry once, and if it persists run {START_HINT} and start again.")
        return (f'Sable-01 unavailable: {{"error": "connection refused - '
                f'run {START_HINT}"}} ({exc.__class__.__name__})')
    message = (data.get("choices") or [{}])[0].get("message", {})
    content = (message.get("content") or "").strip()
    if not content:
        # verified mlx behavior: thinking consumed the budget -> content null
        return ("Sable-01 ran out of tokens while thinking - "
                "retry with a higher max_tokens value.")
    return content
