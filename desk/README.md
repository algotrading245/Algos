# The desk

A small trading desk that runs on this PC: six pods (systematic, FX macro, metals, indices, event, crypto) propose
trades as tickets, a head trader approves them, a code risk gate sizes and checks every ticket, and a one-minute clock
sends the orders to the desk's own MetaTrader 5 terminal (`C:\MetaTrader 5 - Desk`, portable). The design is
`docs/desk/DESIGN.md`. The desk never touches the autopilot, the EAs or the other MetaTrader installs.

## Set up (once)

```powershell
powershell -ExecutionPolicy Bypass -File desk\terminal.ps1    # desk terminal + "Aurum Desk Terminal" desktop shortcut
powershell -ExecutionPolicy Bypass -File desk\install.ps1     # scheduled tasks \AurumDesk\Clock and \AurumDesk\Watchdog
```

`install.ps1` needs Python with `MetaTrader5`, `psutil` and `pandas`. Run it again to update; `desk\uninstall.ps1`
removes the two tasks (halt first with `python -m desk.cli kill "why"` if positions are open).

## Log in the demo (the owner, once)

1. Open **Aurum Desk Terminal** from the desktop.
2. File > Open an Account: a demo with raw spreads (IC Markets Raw or Pepperstone Razor), USD, 10 000, 1:100, hedging.
3. Tick "Save password", log in, and turn **Algo Trading** on (toolbar).
4. Leave the terminal open. The watchdog reopens it after a restart once you are logged on to Windows.

Until an account is logged in the desk runs dry: no orders, no agents, phase 0. The first clock pass that sees the demo
records day 0 and starts phase 1 (systematic and FX macro, a quarter of normal risk); phase 2 adds the other pods on
day 14, phase 3 runs full risk from day 28. `desk/reports/live_gate.md` says when the desk has earned a funded account.

## Daily use

```powershell
python -m desk.cli status                       # phase, heartbeat, account, open tickets, queued jobs
python -m desk.cli view positions|tickets|limits|journal
python -m desk.cli board                        # what the pods posted
python -m desk.cli scores                       # weekly scores against the shadow benchmark
python -m desk.cli kill "why"                   # close every desk position now; the desk stays stopped
python -m desk.cli resume                       # owner only, after a kill
```

Read `desk/inbox/` first: `ALERT.md` (newest at the top) and any note a pod or the scorekeeper left for you. Daily
debriefs and weekly reports are in `desk/reports/`, the journal in `desk/journal/`, the playbooks in `desk/playbooks/`.

## Funded account (later, 5k or 10k)

1. Buy the challenge yourself; the desk never does.
2. Log the funded account in on the desk terminal (File > Login to Trade Account).
3. In `desk\risk.json` set `"active"` to `"prop_5k"` or `"prop_10k"` (the firm's 3% daily and 8% total loss limits,
   flat before the weekend, no crypto). If the terminal shows the account as real, also set that profile's
   `"allow_live": true`; without it the desk refuses to trade a real account.
4. `python -m desk.cli status` should show the new profile and account.

Only the owner edits `risk.json`; the agents cannot.
