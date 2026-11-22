# Archived EAs

The project runs two EAs: AurumHydra (5x) and AurumFunded (prop accounts). Both are thin wrappers around the
shared leg library in `mql5/Include/Aurum/` (Inputs.mqh, Legs.mqh). Breakout and Noise are library legs now.

Moved here 2026-10-18 (no terminal links them): AurumBell, AurumBurst, AurumLattice, AurumLegion, AurumMeridian,
AurumOrient, AurumQuartet, AurumSnap, AurumTokyo.

Archived but left in place, because other terminals' MQL5\Experts junctions point at these folders and moving them
would break those terminals' EA files: AurumBreakout, AurumNoise, AurumDawn, AurumFix, AurumLadder, AurumRebound,
AurumTrend. Do not develop them further; move them here once those terminals no longer link them.
