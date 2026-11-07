import datetime as dt

import pandas as pd

from desk import fetch_crypto
from desk.edges import base


def test_server_time_follows_new_york():
    winter = int(dt.datetime(2024, 1, 15, 12, tzinfo=dt.timezone.utc).timestamp())
    summer = int(dt.datetime(2024, 7, 15, 12, tzinfo=dt.timezone.utc).timestamp())
    out = fetch_crypto.to_server(pd.Series([winter, summer]))
    assert list(out - [winter, summer]) == [2 * 3600, 3 * 3600]


def test_nothing_fetched_at_or_after_the_holdout():
    spans = list(fetch_crypto._spans(dt.date(2025, 8, 1)))
    assert spans[0] == ("monthly", "2025-08") and ("monthly", "2025-09") in spans
    assert max(s for k, s in spans if k == "daily") < base.HOLDOUT.isoformat()
