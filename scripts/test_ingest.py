#!/usr/bin/env python3
"""Local checks for the daily ingest. No network."""

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import fetch_day
import ingest
from export_meetings_csv import rows_from, sha256_of, stamp_downloads


class PathTest(unittest.TestCase):
    def test_kind_follows_the_agenda_url(self):
        self.assertEqual(fetch_day.meeting_kind("立法會會議", "https://www.legco.gov.hk/yr2026/chinese/counmtg/agenda/cm20261118.htm"), "大會")
        self.assertEqual(fetch_day.meeting_kind("2026年11月18日立法會會議的延續", "https://www.legco.gov.hk/yr2026/chinese/counmtg/agenda/cm20261118.htm"), "大會")
        self.assertEqual(fetch_day.meeting_kind("工務小組委員會會議", "https://www.legco.gov.hk/yr2026/chinese/fc/pwsc/agenda/pwsc20261118.htm"), "財務委員會")
        self.assertEqual(fetch_day.meeting_kind("福利事務委員會會議", "https://www.legco.gov.hk/yr2026/chinese/panels/ws/agenda/ws20261109.htm"), "事務委員會")
        self.assertEqual(fetch_day.meeting_kind("《2026年醫生註冊(修訂)條例草案》委員會會議", "https://www.legco.gov.hk/yr2026/chinese/bc/bc105/agenda/bc10520261109.htm"), "法案委員會")
        self.assertEqual(fetch_day.meeting_kind("內務委員會會議", "https://www.legco.gov.hk/yr2026/chinese/hc/agenda/hc20261106.htm"), "內務委員會")
        self.assertEqual(
            fetch_day.meeting_kind(
                "《2026年印花税(修訂)(第3號)條例草案》委員會會議(下午3時30分或在當天的立法會會議結束後15分鐘，以較後者為準)",
                "https://www.legco.gov.hk/yr2026/chinese/bc/bc107/agenda/bc10720261119.htm",
            ),
            "法案委員會",
        )
        path = fetch_day.pdf_path(
            "福利事務委員會會議",
            "2026-11-09",
            "https://www.legco.gov.hk/yr2026/chinese/panels/ws/papers/ws20261109cb1-1387-1-c.pdf",
            True,
            "https://www.legco.gov.hk/yr2026/chinese/panels/ws/agenda/ws20261109.htm",
        )
        self.assertEqual(path, "data/事務委員會/福利事務委員會會議/2026-11-09/ws20261109cb1-1387-1-c.pdf")

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


class StampTest(unittest.TestCase):
    def test_hash_is_filled_only_when_the_pdf_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            day = data / "2026-11-09"
            day.mkdir(parents=True)
            pdf = data / "事務委員會" / "福利事務委員會會議" / "2026-11-09" / "ws.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4 stamp")
            rel = "data/事務委員會/福利事務委員會會議/2026-11-09/ws.pdf"
            snapshot = {
                "meetings": [
                    {
                        "documents": [
                            {"role": "agenda_paper", "local_path": rel, "title": "有檔"},
                            {"role": "agenda_paper", "local_path": None, "title": "無檔"},
                        ]
                    }
                ]
            }
            (day / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
            when = datetime(2026, 11, 21, 12, 0, tzinfo=HKT)
            stamp_downloads(data, freshly_saved=[rel], now=when)
            stored = json.loads((day / "snapshot.json").read_text(encoding="utf-8"))
            docs = stored["meetings"][0]["documents"]
            self.assertEqual(docs[0]["sha256"], sha256_of(pdf))
            self.assertEqual(docs[0]["downloaded_at"], "2026-11-21T12:00:00+08:00")
            self.assertIsNone(docs[1].get("sha256"))
            rows = rows_from(stored)
            self.assertEqual(rows[0]["SHA256"], docs[0]["sha256"])
            self.assertEqual(rows[0]["下載時間"], "2026-11-21T12:00:00+08:00")
            self.assertEqual(rows[1]["SHA256"], "")
            self.assertEqual(rows[1]["下載時間"], "")


class CsvRowsTest(unittest.TestCase):
    def test_decision_row_follows_the_paper_without_members(self):
        snapshot = {
            "meetings": [
                {
                    "meeting_date": "2026-11-18",
                    "start_time": "2026-11-18T11:00:00",
                    "venue_name": "立法會綜合大樓會議廳",
                    "committee_name": "立法會會議",
                    "agenda_items": [{"item_key": "I", "title": "法案"}],
                    "documents": [
                        {
                            "role": "agenda_paper",
                            "item_key": "I",
                            "title": "法案報告",
                            "url": "https://example.test/a.pdf",
                            "local_path": "data/立法會會議/2026-11-18/a.pdf",
                        }
                    ],
                    "motions": [
                        {
                            "vote_number": 1,
                            "motion_title": "二讀",
                            "result": "Passed",
                            "vote_time": "2026-11-18T14:20:10+08:00",
                            "members": [
                                {"name_ch": "李慧琼", "vote": "Present"},
                            ],
                        }
                    ],
                }
            ]
        }
        rows = rows_from(snapshot)
        self.assertEqual([row["紀錄種類"] for row in rows], ["議程文件", "表決結果"])
        self.assertNotIn("議員", rows[0])
        self.assertEqual(rows[0]["文件名稱"], "法案報告")
        self.assertEqual(rows[1]["議案"], "二讀")
        self.assertEqual(rows[1]["整體結果"], "通過")
        self.assertEqual(rows[1]["表決時間"], "14:20:10")
        self.assertEqual(rows[0]["下載時間"], "")
        self.assertEqual(rows[0]["SHA256"], "")
        self.assertEqual(rows[1]["SHA256"], "")


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

    def test_due_day_is_today_at_the_cutoff_and_yesterday_before_it(self):
        self.assertEqual(ingest.due_day(datetime(2026, 11, 25, 14, 30, tzinfo=HKT)).isoformat(), "2026-11-25")
        self.assertEqual(ingest.due_day(datetime(2026, 11, 25, 14, 29, tzinfo=HKT)).isoformat(), "2026-11-24")

    def test_open_after_cutoff_ingests_today_only_when_the_snapshot_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            now = datetime(2026, 11, 25, 15, 0, tzinfo=HKT)
            seen = []

            def fake_build(day, now=None):
                seen.append(day.isoformat())
                return {
                    "as_of": "2026-11-25T14:30:00+08:00",
                    "observed_at": "2026-11-25T07:00:00+00:00",
                    "meetings": [],
                    "votes_after_cutoff": [],
                }

            original_build = fetch_day.build_snapshot
            fetch_day.build_snapshot = fake_build
            try:
                first = ingest.open_ingest(now, data, follow=False)
                second = ingest.open_ingest(now, data, follow=False)
            finally:
                fetch_day.build_snapshot = original_build
            self.assertEqual(seen, ["2026-11-25"])
            self.assertFalse(first["skipped"])
            self.assertEqual(first["date"], "2026-11-25")
            self.assertTrue(second["skipped"])
            self.assertEqual(second["reason"], "already ingested")
            self.assertEqual(second["date"], "2026-11-25")

    def test_open_before_cutoff_catches_up_yesterday(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            now = datetime(2026, 11, 25, 2, 4, tzinfo=HKT)
            seen = []

            def fake_build(day, now=None):
                seen.append(day.isoformat())
                return {
                    "as_of": "2026-11-24T14:30:00+08:00",
                    "observed_at": "2026-11-24T18:04:00+00:00",
                    "meetings": [],
                    "votes_after_cutoff": [],
                }

            original_build = fetch_day.build_snapshot
            fetch_day.build_snapshot = fake_build
            try:
                missing = ingest.open_ingest(now, data, follow=False)
                (data / "2026-11-24" / "snapshot.json").write_text("{}\n", encoding="utf-8")
                stored = ingest.open_ingest(now, data, follow=False)
            finally:
                fetch_day.build_snapshot = original_build
            self.assertEqual(seen, ["2026-11-24"])
            self.assertEqual(missing["date"], "2026-11-24")
            self.assertFalse((data / "2026-11-25").exists())
            self.assertTrue(stored["skipped"])
            self.assertEqual(stored["date"], "2026-11-24")


if __name__ == "__main__":
    unittest.main()
