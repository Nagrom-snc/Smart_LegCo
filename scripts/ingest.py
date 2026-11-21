#!/usr/bin/env python3
"""Daily LegCo ingest.

One run is the 14:30 HKT job for a Hong Kong date. It stores four tables in
data/legco.sqlite, saves PDFs that were already on the site, and rewrites
data/meetings.csv. There is no scheduler in this repo. Call this program at
14:30 Asia/Hong_Kong from cron or another clock.

    python3 scripts/ingest.py
    python3 scripts/ingest.py --date 2026-11-20

Before 14:30 on the chosen date the run reads nothing and writes nothing.
A past date is a replay of that day's 14:30 cutoff. Open meetings from
earlier dates are read again until minutes are stored or 21 days have passed.
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import fetch_day
from export_meetings_csv import write_meetings_csv

HKT = fetch_day.HKT
DB_NAME = "legco.sqlite"


def doc_key(doc):
    label = (doc.get("paper_label") or "").strip()
    if label:
        return label
    url = (doc.get("url") or "").strip()
    if url:
        return url
    return (doc.get("title") or "").strip()


def connect(db_path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meeting (
            meet_id INTEGER PRIMARY KEY,
            meeting_date TEXT NOT NULL,
            start_time TEXT,
            committee_name TEXT NOT NULL,
            agenda_url TEXT,
            venue_name TEXT,
            meeting_type TEXT,
            follow_up_until TEXT NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS agenda_item (
            meet_id INTEGER NOT NULL,
            item_key TEXT NOT NULL,
            title TEXT,
            PRIMARY KEY (meet_id, item_key)
        );
        CREATE TABLE IF NOT EXISTS document (
            meet_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            doc_key TEXT NOT NULL,
            paper_label TEXT,
            title TEXT,
            url TEXT,
            local_path TEXT,
            item_key TEXT,
            on_site_at_cutoff INTEGER,
            PRIMARY KEY (meet_id, role, doc_key)
        );
        CREATE TABLE IF NOT EXISTS motion (
            meet_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL,
            vote_number INTEGER NOT NULL,
            motion_title TEXT,
            result TEXT,
            vote_time TEXT,
            PRIMARY KEY (meet_id, vote_type, vote_number)
        );
        DROP TABLE IF EXISTS member_vote;
        """
    )
    return conn


def next_status(previous, proposed):
    if previous == "complete" or proposed == "complete":
        return "complete"
    if previous == "expired" or proposed == "expired":
        return "expired"
    return "open"


def upsert_meeting(conn, meeting):
    previous = conn.execute(
        "SELECT status FROM meeting WHERE meet_id = ?", (meeting["meet_id"],)
    ).fetchone()
    status = next_status(previous["status"] if previous else None, meeting["status"])
    conn.execute(
        """
        INSERT INTO meeting (
            meet_id, meeting_date, start_time, committee_name, agenda_url,
            venue_name, meeting_type, follow_up_until, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(meet_id) DO UPDATE SET
            meeting_date = excluded.meeting_date,
            start_time = excluded.start_time,
            committee_name = excluded.committee_name,
            agenda_url = excluded.agenda_url,
            venue_name = excluded.venue_name,
            meeting_type = excluded.meeting_type,
            follow_up_until = excluded.follow_up_until,
            status = excluded.status
        """,
        (
            meeting["meet_id"],
            meeting["meeting_date"],
            meeting.get("start_time"),
            meeting["committee_name"],
            meeting.get("agenda_url"),
            meeting.get("venue_name"),
            meeting.get("meeting_type"),
            meeting["follow_up_until"],
            status,
        ),
    )
    for item in meeting.get("agenda_items") or []:
        conn.execute(
            """
            INSERT INTO agenda_item (meet_id, item_key, title)
            VALUES (?, ?, ?)
            ON CONFLICT(meet_id, item_key) DO UPDATE SET title = excluded.title
            """,
            (meeting["meet_id"], item["item_key"], item.get("title")),
        )
    for doc in meeting.get("documents") or []:
        conn.execute(
            """
            INSERT INTO document (
                meet_id, role, doc_key, paper_label, title, url, local_path,
                item_key, on_site_at_cutoff
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(meet_id, role, doc_key) DO UPDATE SET
                paper_label = excluded.paper_label,
                title = excluded.title,
                url = COALESCE(excluded.url, document.url),
                local_path = COALESCE(excluded.local_path, document.local_path),
                item_key = excluded.item_key,
                on_site_at_cutoff = excluded.on_site_at_cutoff
            """,
            (
                meeting["meet_id"],
                doc.get("role"),
                doc_key(doc),
                doc.get("paper_label"),
                doc.get("title"),
                doc.get("url"),
                doc.get("local_path"),
                doc.get("item_key"),
                1 if doc.get("on_site_at_cutoff") else 0,
            ),
        )
    for motion in meeting.get("motions") or []:
        conn.execute(
            """
            INSERT INTO motion (
                meet_id, vote_type, vote_number, motion_title, result, vote_time
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(meet_id, vote_type, vote_number) DO UPDATE SET
                motion_title = excluded.motion_title,
                result = excluded.result,
                vote_time = excluded.vote_time
            """,
            (
                meeting["meet_id"],
                motion.get("vote_type") or "",
                motion.get("vote_number") or 0,
                motion.get("motion_title"),
                motion.get("result"),
                motion.get("vote_time"),
            ),
        )
    meeting["status"] = status
    return status


def load_snapshots(conn, data_dir):
    count = 0
    for path in sorted(Path(data_dir).glob("*/snapshot.json")):
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        for meeting in snapshot.get("meetings") or []:
            upsert_meeting(conn, meeting)
            count += 1
    conn.commit()
    return count


def minutes_ready(meeting):
    return any(
        doc.get("role") == "minutes" and doc.get("on_site_at_cutoff")
        for doc in meeting.get("documents") or []
    )


def apply_window(meeting, run_day):
    if minutes_ready(meeting):
        meeting["status"] = "complete"
    elif run_day.isoformat() >= meeting["follow_up_until"]:
        meeting["status"] = "expired"
    else:
        meeting["status"] = "open"
    return meeting


def patch_snapshot(data_dir, meeting, observed):
    path = Path(data_dir) / meeting["meeting_date"] / "snapshot.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    else:
        payload = {
            "as_of": fetch_day.cutoff_for(
                datetime.fromisoformat(meeting["meeting_date"]).date()
            ).isoformat(),
            "observed_at": observed.astimezone(timezone.utc).isoformat(),
            "meetings": [],
            "votes_after_cutoff": [],
        }
    replaced = False
    for index, stored in enumerate(payload.get("meetings") or []):
        if stored.get("meet_id") == meeting["meet_id"]:
            payload["meetings"][index] = meeting
            replaced = True
            break
    if not replaced:
        payload.setdefault("meetings", []).append(meeting)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def raw_row(stored):
    return {
        "meet_id": stored["meet_id"],
        "agenda_url_chi": stored["agenda_url"],
        "subject_chi": stored["committee_name"],
        "start_date_time": stored["start_time"],
        "venue_name_chi": stored["venue_name"],
        "meeting_type_chi": stored["meeting_type"],
    }


def follow_up(conn, run_day, data_dir, now, refresh):
    cutoff = fetch_day.cutoff_for(run_day)
    rows = conn.execute(
        """
        SELECT * FROM meeting
        WHERE status = 'open' AND meeting_date < ? AND follow_up_until >= ?
        ORDER BY meeting_date, meet_id
        """,
        (run_day.isoformat(), run_day.isoformat()),
    ).fetchall()
    touched = []
    for stored in rows:
        meeting_day = datetime.fromisoformat(stored["meeting_date"]).date()
        meeting = refresh(raw_row(stored), meeting_day, cutoff)
        meeting["follow_up_until"] = stored["follow_up_until"]
        apply_window(meeting, run_day)
        upsert_meeting(conn, meeting)
        patch_snapshot(data_dir, meeting, now)
        touched.append(meeting["meet_id"])
    conn.commit()
    return touched


def download_pdfs(conn, repo_root):
    saved, skipped, failed = [], [], []
    rows = conn.execute(
        "SELECT url, local_path FROM document WHERE local_path IS NOT NULL AND local_path != ''"
    )
    for row in rows:
        dest = Path(repo_root) / row["local_path"]
        if dest.is_file() and dest.read_bytes()[:4] == b"%PDF":
            skipped.append(row["local_path"])
            continue
        code, _headers, body = fetch_day.get(row["url"])
        if code != 200 or not body.startswith(b"%PDF"):
            failed.append((row["local_path"], code))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        saved.append(row["local_path"])
    return saved, skipped, failed


def write_snapshot(data_dir, day, snapshot):
    path = Path(data_dir) / day.isoformat() / "snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def run(day, now, data_dir, refresh=None):
    data_dir = Path(data_dir)
    cutoff = fetch_day.cutoff_for(day)
    if now < cutoff:
        return {"skipped": True, "reason": "before 14:30 HKT", "cutoff": cutoff.isoformat()}
    snapshot = fetch_day.build_snapshot(day, now=now)
    for meeting in snapshot["meetings"]:
        apply_window(meeting, day)
    snap_path = write_snapshot(data_dir, day, snapshot)
    conn = connect(data_dir / DB_NAME)
    try:
        loaded = load_snapshots(conn, data_dir)
        if refresh is None:
            def refresh(row, meeting_day, run_cutoff):
                kept, _later = fetch_day.votes_on(meeting_day, run_cutoff)
                return fetch_day.one_meeting(row, meeting_day, run_cutoff, kept)

        followed = follow_up(conn, day, data_dir, now, refresh)
        saved, skipped, failed = download_pdfs(conn, data_dir.parent)
    finally:
        conn.close()
    csv_path, csv_rows = write_meetings_csv(data_dir)
    return {
        "skipped": False,
        "snapshot": str(snap_path),
        "loaded": loaded,
        "followed": followed,
        "downloaded": saved,
        "already_stored": skipped,
        "download_failures": failed,
        "csv": str(csv_path),
        "csv_rows": csv_rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one 14:30 HKT LegCo ingest.")
    parser.add_argument("--date", help="Hong Kong date YYYY-MM-DD. Default: today in Asia/Hong_Kong.")
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args(argv)
    now = datetime.now(HKT)
    day = datetime.fromisoformat(args.date).date() if args.date else now.date()
    root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir) if args.data_dir else root / "data"
    result = run(day, now, data_dir)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("download_failures"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
