"""Which gold margin does the FTMO demo account get? Compare Terminal 16 with the tester install.

Lesson 19 (amended 2026-10-19): with the same EA, inputs and Leverage=33, Terminal 16's tester charged gold about
1:16.5 (j3) and the tester install about 1:50 (j12). Both terminals log in to FTMO-Demo. This script reads both
terminals' journals and tester-agent logs and reports, without printing any account number:
  - the server each terminal is authorized on,
  - whether the two terminals use the same account (set comparison only),
  - the deposit / leverage / account lines the tester agents logged.
"""
import builtins
import glob
import os
import re

OUT = open(os.path.join(os.path.dirname(__file__), "demo_margin_terminals.out.txt"), "w", encoding="utf-8")


def print(*args, **kwargs):  # console and the .out.txt file
    builtins.print(*args, **kwargs)
    builtins.print(*args, file=OUT, **kwargs)


ROOT = os.path.expandvars(r"%APPDATA%\MetaQuotes\Terminal")
TERMS = {"Terminal 16": "66FB7F5B174F9C3B2A690C49FF012FEB", "tester install": "4B6AE0EF129BDEB86D4347A7B58B42AB"}
MASK = re.compile(r"\d{6,}")


def lines(pattern):
    for f in sorted(glob.glob(pattern)):
        for enc in ("utf-16", "utf-8"):
            try:
                with open(f, encoding=enc) as fh:
                    text = fh.read()
                break
            except (UnicodeError, UnicodeDecodeError):
                continue
        else:
            continue
        for line in text.splitlines():
            yield f, line


accounts = {}
for name, folder in TERMS.items():
    base = os.path.join(ROOT, folder)
    servers, accs = set(), set()
    for _, line in lines(os.path.join(base, "logs", "2026*.log")):
        m = re.search(r"'(\d+)': authorized on (\S+)", line)
        if m:
            accs.add(m.group(1))
            servers.add(m.group(2))
    accounts[name] = accs
    print(f"{name}: servers {sorted(servers)}, distinct accounts {len(accs)}")

    agent_lines = set()
    for f, line in lines(os.path.join(base, "Tester", "logs", "*.log")):
        if "AurumFunded:" in line or "AurumHydra:" in line or "Inp" in line:
            continue
        if re.search(r"leverage|initial deposit|margin", line, re.I):
            body = re.sub(r"^\S+\s+\S+\s+\S+\s+", "", MASK.sub("<n>", line.strip()))
            body = re.sub(r"\d{4}\.\d\d\.\d\d \d\d:\d\d:\d\d\s*", "", body)
            agent_lines.add(os.path.basename(f)[:8] + " " + body[:160])
    print(f"  tester agent lines (distinct, numbers of 6+ digits masked): {len(agent_lines)}")
    for body in sorted(agent_lines)[:25]:
        print("   ", body)

print("\nEach tester run on 2026-10-17/18: the agent's start time, its expert and the leverage it applied")
for name, folder in TERMS.items():
    base = os.path.join(ROOT, folder)
    expert = None
    for f, line in lines(os.path.join(base, "Tester", "logs", "2026101[78].log")):
        m = re.search(r"testing of (Experts\\\S+)", line)
        if m:
            expert = m.group(1)
        m = re.search(r"(\d\d:\d\d:\d\d)\.\d+\s.*initial deposit ([\d.]+) USD, leverage (1:\d+)", line)
        if m:
            print(f"  {name:15s} {os.path.basename(f)[:8]} {m.group(1)} deposit {m.group(2):>9s} leverage {m.group(3):6s}"
                  f" last expert line before: {expert}")

a, b = accounts["Terminal 16"], accounts["tester install"]
print(f"shared accounts between the two terminals: {len(a & b)} (Terminal 16 {len(a)}, tester install {len(b)})")
