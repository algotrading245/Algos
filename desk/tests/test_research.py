"""The desk-research link (owner 2026-11-01): pod briefs show the finder's ideas and the book's gaps, and the pods'
week of knowledge and board posts is written to docs/ideas/desk_notes.md for the finder."""
import json

from desk import memory, paths, research


def _docs(root):
    d = root / "docs" / "ideas"
    d.mkdir(parents=True)
    rows = [{"id": "a", "title": "Gold carry", "status": "queued", "added": "2026-10-20"},
            {"id": "b", "title": "Old fail", "status": "fail", "added": "2026-09-01", "result": "PF 0.9"},
            {"id": "c", "title": "Ger40 noise", "status": "fail", "added": "2026-10-19", "result": "PF 1.05 " * 50}]
    (d / "queue.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (d / "backlog.jsonl").write_text(json.dumps({"title": "JPY intraday", "gap": "asia", "kind": "paper",
                                                 "status": "open"}) + "\n" +
                                     json.dumps({"title": "done one", "status": "closed"}) + "\n", encoding="utf-8")
    (d / "steer.md").write_text("# Steer\n> Top gap: Asia session.\nbody\n", encoding="utf-8")
    (root / "docs" / "gaps.json").write_text(json.dumps({"gaps": {"markets": ["USDJPY"]}, "aim": "5x",
                                                         "when": "2026-10-21"}), encoding="utf-8")


def test_ideas_and_gaps(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    _docs(tmp_path)
    i = research.ideas()
    assert [r["id"] for r in i["waiting"]] == ["a"]
    assert [r["id"] for r in i["recent_results"]] == ["c"] and len(i["recent_results"][0]["result"]) == 200
    assert i["open_leads"] == [{"title": "JPY intraday", "gap": "asia", "kind": "paper"}]
    g = research.gaps()
    assert g["gaps"] == {"markets": ["USDJPY"]} and g["steer_status"] == "Top gap: Asia session."


def test_missing_docs_are_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    assert research.ideas() == {"waiting": [], "recent_results": [], "open_leads": []}
    assert research.gaps()["steer_status"] == ""


def test_desk_notes_written_for_the_finder(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    memory.learn("fxmacro", "USDJPY fades the Tokyo fix", "USDJPY")
    memory.learn("metals", "private note", "XAUUSD", share="pod")
    memory.ask("metals", "fxmacro", "Does the fix fade hold in risk-off?", "USDJPY")
    text = research.desk_notes().read_text(encoding="utf-8")
    assert "- USDJPY: 2" in text and "USDJPY fades the Tokyo fix" in text
    assert "private note" not in text
    assert "metals -> fxmacro: Does the fix fade hold" in text
    assert "## Head trader book notes\n- (none)" in text


def test_pod_brief_has_research_section(tmp_path, monkeypatch):
    monkeypatch.setenv("AURUM_DESK_DRY", "1")
    monkeypatch.setattr(paths, "ROOT", tmp_path)
    _docs(tmp_path)
    from desk import brief
    text = brief.build("metals")
    sec = text.split("## Research desk")[1].split("\n## ")[0]
    assert "Gold carry" in sec and "Asia session" in sec and "JPY intraday" in sec
