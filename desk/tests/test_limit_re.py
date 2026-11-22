"""The limit pattern must catch every wording the CLI has used (a missed one cost the doctor's 2026-11-01 run)."""
from desk.runner import LIMIT_RE


def test_limit_wordings_match():
    for s in ("You've hit your 5-hour limit · resets 7:10am",
              "You've hit your weekly limit · resets 5pm (Europe/Berlin)",
              "You've hit your limit",
              "you have hit your session usage limit"):
        assert LIMIT_RE.search(s), s


def test_plain_text_does_not_match():
    for s in ("no limit here", "the daily loss limit was hit", "limit orders"):
        assert not LIMIT_RE.search(s), s
