#!/usr/bin/env python3
"""Local checks for the daily ingest. No network."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import fetch_day
import ingest

HKT = fetch_day.HKT


def meeting(meet_id, day, status="open", minutes=False, local_path=None):
    documents = []
    if minutes or local_path:
        documents.append(
            {
                "role": "minutes" if minutes else "agenda_paper",
                "paper_label": None if minutes else "CB(1)1/2026(01)",
                "title": "會議紀要" if minutes else "CB(1)1/2026(01)",
                "url": "https://example.test/paper.pdf",
                "local_path": local_path,
                "item_key": None,
                "on_site_at_cutoff": True,
            }
        )
    return {
        "meet_id": meet_id,
        "meeting_date": day,
        "start_time": f"{day}T09:00:00",
        "committee_name": "福利事務委員會會議",
        "agenda_url": "https://example.test/agenda.htm",
        "venue_name": "會議室1",
        "meeting_type": "開放",
        "follow_up_until": "2026-11-27",
        "status": "complete" if minutes else status,
        "agenda_items": [{"item_key": "I", "title": "其他事項"}],
        "documents": documents,
        "motions": [],
    }


class IngestTest(unittest.TestCase):
    def test_before_cutoff_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            now = datetime(2026, 11, 21, 14, 29, tzinfo=HKT)
            result = ingest.run(now.date(), now, data)
            self.assertTrue(result["skipped"])
            self.assertFalse((data / "legco.sqlite").exists())
            self.assertFalse((data / "meetings.csv").exists())

    def test_upsert_keeps_a_stored_path_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = ingest.connect(Path(tmp) / "legco.sqlite")
            first = meeting(7, "2026-11-06", local_path="data/福利事務委員會會議/2026-11-06/a.pdf")
            first["status"] = "complete"
            ingest.upsert_meeting(conn, first)
            again = meeting(7, "2026-11-06", local_path="data/福利事務委員會會議/2026-11-06/a.pdf")
            again["documents"][0]["local_path"] = None
            again["documents"][0]["on_site_at_cutoff"] = False
            again["status"] = "open"
            ingest.upsert_meeting(conn, again)
            row = conn.execute("SELECT status, local_path FROM meeting JOIN document USING (meet_id)").fetchone()
            self.assertEqual(row["status"], "complete")
            self.assertEqual(row["local_path"], "data/福利事務委員會會議/2026-11-06/a.pdf")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM meeting").fetchone()[0], 1)

    def test_window_expires_without_minutes(self):
        row = meeting(3, "2026-11-06")
        ingest.apply_window(row, datetime(2026, 11, 27).date())
        self.assertEqual(row["status"], "expired")

    def test_run_saves_pdf_and_rewrites_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            ready = meeting(
                9,
                "2026-11-09",
                local_path="data/福利事務委員會會議/2026-11-09/ws.pdf",
            )
            snapshot = {
                "as_of": "2026-11-09T14:30:00+08:00",
                "observed_at": "2026-11-09T06:30:00+00:00",
                "meetings": [ready],
                "votes_after_cutoff": [],
            }

            def fake_build(day, now=None):
                self.assertEqual(day.isoformat(), "2026-11-09")
                return snapshot

            def fail_refresh(*_args):
                raise AssertionError("no open meeting to follow")

            original_build = fetch_day.build_snapshot
            original_get = fetch_day.get
            fetch_day.build_snapshot = fake_build
            fetch_day.get = lambda url, method="GET": (200, {}, b"%PDF-1.4 test")
            try:
                now = datetime(2026, 11, 9, 15, 0, tzinfo=HKT)
                result = ingest.run(now.date(), now, data, refresh=fail_refresh)
                second = ingest.run(now.date(), now, data, refresh=fail_refresh)
            finally:
                fetch_day.build_snapshot = original_build
                fetch_day.get = original_get
            self.assertFalse(result["skipped"])
            self.assertEqual(result["download_failures"], [])
            self.assertEqual(len(result["downloaded"]), 1)
            stored = Path(tmp) / "data/福利事務委員會會議/2026-11-09/ws.pdf"
            self.assertTrue(stored.read_bytes().startswith(b"%PDF"))
            text = (data / "meetings.csv").read_text(encoding="utf-8-sig")
            self.assertIn("福利事務委員會會議", text)
            self.assertIn("ws.pdf", text)
            self.assertEqual(second["downloaded"], [])
            self.assertEqual(len(second["already_stored"]), 1)
            self.assertTrue((data / "legco.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
