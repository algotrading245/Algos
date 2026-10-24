# Mirrors the agent definitions in .claude/agents/ into .qwen/agents/ so Qwen Code can delegate to the same
# subagents (its `agent` tool reads .qwen/agents/<name>.md; there is no --agent flag for a top-level run, so
# run-agent.ps1 inlines the role definitions into the prompt instead). Owner 2026-10-18.
#
#   python tools/autopilot/mirror_agents.py            # rewrite .qwen/agents/ from .claude/agents/
#   python tools/autopilot/mirror_agents.py --check     # say which mirrors are out of date (exit 1 if any)
#
# Run it after any change to .claude/agents/. Two frontmatter fields are rewritten, because they mean different
# things to the two CLIs:
#   model: haiku|sonnet|opus  ->  model: inherit   (Qwen selectors are inherit|fast|<model id>; the router picks
#                                                    the model for the whole run, so a subagent follows it)
#   tools: Read, Bash, ...    ->  dropped          (Qwen's tool names differ; the subagent inherits the session's
#                                                    tools and .qwen/settings.json's deny list still gates them)
# The body is copied unchanged, so a definition edited for Claude takes effect for Qwen on the next mirror.
import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / ".claude" / "agents"
DST = REPO / ".qwen" / "agents"
# The note goes inside the frontmatter: a definition whose first line is not "---" is not recognised as one.
NOTE = "# Mirrored from .claude/agents/{name} by tools/autopilot/mirror_agents.py: edit the Claude file, then rerun\n# that script. model and tools are rewritten for Qwen Code.\n"


def mirror_text(src_path):
    text = src_path.read_text(encoding="utf-8-sig").lstrip("\ufeff")
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n?(.*)$", text, re.S)
    if not m:
        return "---\n" + NOTE.format(name=src_path.name) + "---\n" + text
    front, body = m.group(1), m.group(2)
    kept = []
    for line in front.splitlines():
        key = line.split(":", 1)[0].strip().lower()
        if key == "tools":
            continue
        if key == "model":
            kept.append("model: inherit")
            continue
        kept.append(line)
    if not any(l.split(":", 1)[0].strip().lower() == "model" for l in kept):
        kept.append("model: inherit")
    return "---\n" + NOTE.format(name=src_path.name) + "\n".join(kept) + "\n---\n" + body


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only report which mirrors are out of date")
    a = ap.parse_args()

    if not SRC.exists():
        sys.exit(f"no {SRC}")
    stale = []
    for src in sorted(SRC.glob("*.md")):
        want = mirror_text(src)
        dst = DST / src.name
        have = dst.read_text(encoding="utf-8-sig") if dst.exists() else None
        if have == want:
            continue
        stale.append(src.name)
        if not a.check:
            DST.mkdir(parents=True, exist_ok=True)
            dst.write_text(want, encoding="utf-8")
    if a.check:
        print("out of date: " + (", ".join(stale) if stale else "nothing, the mirrors match") )
        sys.exit(1 if stale else 0)
    print(f"mirrored {len(list(SRC.glob('*.md')))} agent definitions into {DST.relative_to(REPO)}"
          + (f" (changed: {', '.join(stale)})" if stale else " (no change)"))


if __name__ == "__main__":
    main()
