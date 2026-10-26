"""Aurum Desk: a 24/7 AI trading desk, separate from the AurumHydra / AurumFunded system (docs/desk/DESIGN.md).

Agents decide, code executes: agents write tickets through desk.cli; the risk gate and the executor (code) place and
manage every order on the desk's own MT5 terminal.
"""
