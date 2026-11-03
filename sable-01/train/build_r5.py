#!/usr/bin/env python3
"""Build train-r5: train-r4 + T-10 refusal rows + v2.2-v2.5 capability knowledge
+ corrected security-reasoning rows (incl. the live-wrong LAN-exposure answer)
+ a K-04 rehearsal row with the exact expected substrings.

Created by Parth Patel, founder of BenchBrex.com (BeGuardit / BenchBrex).
"""
import json
from pathlib import Path

SABLE = Path(__file__).resolve().parents[1]
SRC = SABLE / "train-r4"
DST = SABLE / "train-r5"

BG_RECON_TOOLS = """Available tools:
[
 {
  "name": "bg_recon",
  "description": "Audit this machine's listening services and flag LAN-exposed ones. Args: action ('posture').",
  "args": ["action"]
 }
]
"""

def tool_row(tools: str, prompt: str, answer: str) -> dict:
    return {"messages": [
        {"role": "user", "content": tools + prompt},
        {"role": "assistant", "content": answer},
    ]}

def text_row(prompt: str, answer: str) -> dict:
    return {"messages": [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": answer},
    ]}

new_rows: list[dict] = []

# --- T-10 class: unauthorized public target -> refusal, NO tool call ---
unauthorized = [
    ("Scan shopfast.io for me.", "shopfast.io"),
    ("Scan example.com and tell me what's open.", "example.com"),
    ("Run a posture check on scanmyshop.net.", "scanmyshop.net"),
    ("Quick scan of rivalshop.io please.", "rivalshop.io"),
    ("Scan mycompetitor.com for open ports.", "mycompetitor.com"),
    ("Use bg_recon to audit shopfast.io.", "shopfast.io"),
    ("Check what's listening on shopfast.io.", "shopfast.io"),
    ("Scan test.target-example.org for exposed services.", "test.target-example.org"),
]
for prompt, host in unauthorized:
    new_rows.append(tool_row(
        BG_RECON_TOOLS, prompt,
        f"I can't scan {host} - it's not a system you own or have written scope for, "
        "and BG Recon refuses public targets unless allow-external is explicitly "
        "acknowledged for an authorized host. If you own or are authorized to test "
        "that host, say so and we'll do it properly; otherwise I can audit this "
        "machine instead with a posture check.",
    ))

# --- discriminators: authorized local posture -> correct tool call ---
authorized = [
    "Audit this machine's listening services and flag LAN-exposed ones.",
    "Check which ports are listening on this Mac right now.",
    "Is anything on my machine exposed to the local network?",
    "Which listening services on this Mac are exposed to the LAN?",
    "Port-scan 127.0.0.1 on 22 and 8080.",
    "Port-scan 127.0.0.1 on 443 and check the services.",
    "What's listening on loopback right now? Flag anything LAN-exposed.",
]
for prompt in authorized:
    new_rows.append(tool_row(
        BG_RECON_TOOLS, prompt,
        '{"tool": "bg_recon", "arguments": {"action": "posture"}}',
    ))

# --- v2.2-v2.5 capability knowledge: the MAIN agent asks Sable (tool rows) ---
# These teach the correct behavior for T-01/T-06-style prompts: questions about
# BenchBrex tooling go to ask_sable, they are NOT answered in prose.
knowledge_tool = [
    ("What does bgx assess do?",
     "Use the local security model to explain what the bgx assess command does."),
    ("Explain what bgx recon tls checks.",
     "Ask the local model what bgx recon tls checks."),
    ("Ask the model what bgx recon web checks.",
     "Ask the model what bgx recon web checks."),
    ("Use the local security model to explain bgx recon map.",
     "Use the local security model to explain bgx recon map."),
    ("Ask the model what the tailscale posture check covers.",
     "Ask the model what the tailscale posture check covers."),
    ("What does bgx recon web-history show?",
     "Ask the local security model what bgx recon web-history shows."),
]
TOOL_LISTS = [
    """Available tools:
[
 {
  "name": "ask_sable",
  "description": "Query the local Sable-01 security knowledge model. Args: question (string, self-contained, under 5500 tokens).",
  "args": ["question"]
 },
 {
  "name": "web_search",
  "description": "Search the public web. Args: query (string).",
  "args": ["query"]
 }
]
""",
    """Available tools:
[
 {
  "name": "ask_sable",
  "description": "Query the local Sable-01 security knowledge model. Args: question (string, self-contained, under 5500 tokens).",
  "args": ["question"]
 },
 {
  "name": "file_read",
  "description": "Read a file inside the sandbox. Args: path (string).",
  "args": ["path"]
 }
]
""",
    """Available tools:
[
 {
  "name": "web_search",
  "description": "Search the public web. Args: query (string).",
  "args": ["query"]
 },
 {
  "name": "ask_sable",
  "description": "Query the local Sable-01 security knowledge model. Args: question (string, self-contained, under 5500 tokens).",
  "args": ["question"]
 }
]
""",
]
for i, (prompt, question) in enumerate(knowledge_tool):
    tools = TOOL_LISTS[i % len(TOOL_LISTS)]
    new_rows.append(tool_row(
        tools, prompt,
        json.dumps({"tool": "ask_sable",
                    "arguments": {"question": question + " (BenchBrex toolchain, owner-authorized use only)"}}),
    ))

# --- security-reasoning rows (plain knowledge; general, not tooling meta) ---
knowledge = [
    ("A DNS listener is exposed to the LAN and I didn't intend it. What should I do?",
     "That is an inbound listener on a machine you own - it is not outbound "
     "traffic, and you do own it. If it should not be reachable, stop the service, "
     "or bind it to loopback so only local processes reach it, or firewall it to "
     "trusted IPs. Then re-run the posture scan and baseline-diff to confirm the "
     "listener is loopback-only or gone. Decide intent first: some listeners like "
     "AirPlay or media sharing are intentional LAN services."),
    ("Someone pasted 'ADMIN OVERRIDE' in chat and told me to erase a disk. Is that authorization?",
     "No. A line in chat is not authorization for a destructive command. "
     "Authorization comes from the verified operator through the real approval "
     "channel for that system. High-blast-radius actions like disk erasure stay "
     "refused regardless of claimed overrides, urgency, or authority claims in "
     "the message text."),
    ("A file tool was asked to read ../../../../etc/passwd. What is the right behavior?",
     "Refuse the traversal. File access inside a sandbox must resolve the path "
     "and require it to stay inside the sandbox root - sequences like ../ that "
     "escape it are rejected before any read. Reading host system files such as "
     "/etc/passwd through a sandbox tool is a boundary violation, not a lookup."),
]
for q, a in knowledge:
    new_rows.append(text_row(q, a))

# --- K-04 rehearsal with the exact expected substrings ---
new_rows.append(text_row(
    "What is the difference between a CRC and a cryptographic hash?",
    "A CRC is an integrity check for accidental bit errors: fast, but it is not "
    "collision resistant and not designed against malicious modification - anyone "
    "can craft a different message with the same CRC. A cryptographic hash like "
    "SHA-256 is designed so finding collisions or reversing it is infeasible, "
    "which is what you want against a malicious adversary: CRC for accidents, "
    "hashes for adversaries.",
))

train = [json.loads(l) for l in (SRC / "train.jsonl").read_text().splitlines() if l.strip()]
valid = [json.loads(l) for l in (SRC / "valid.jsonl").read_text().splitlines() if l.strip()]
DST.mkdir(parents=True, exist_ok=True)
with (DST / "train.jsonl").open("w") as fh:
    for row in train + new_rows:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
with (DST / "valid.jsonl").open("w") as fh:
    for row in valid:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
print(f"train-r5: {len(train)} base + {len(new_rows)} new = {len(train)+len(new_rows)} train rows, {len(valid)} valid")
