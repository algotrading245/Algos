# Model routing (owner 2026-10-18)

The same cheap/strong split the autopilot uses (tools/autopilot/router.json), applied to chat sessions too.
Autopilot runs pass --model or --agent, so this file and the "opusplan" default in .claude/settings.json do not change them.

- Chat runs on `opusplan`: Opus in plan mode, Sonnet otherwise. Switch to `/model opus` only for hard judgment
  (a gate verdict, a research design, a tricky bug), then back with `/model opusplan`.
- Searches across many files: the Explore agent (Haiku), which returns the conclusion, not the file dumps.
- Delegate by role, on the role's own model (the 5-step loop, owner 2026-10-22): tester-operator, monitor
  (Haiku); finder and builder (Sonnet); judge, reviewer and the weekly portfolio-manager (Opus).
- Read only the part of a file you need (offset/limit, Grep), never re-read a file you just edited, and keep answers
  short: the result, the evidence, the next step.
