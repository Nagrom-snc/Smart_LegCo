#!/usr/bin/env python3
"""Write data/meetings.csv from every data/*/snapshot.json.

Two row kinds share one file. 紀錄種類 tells them apart.

- 議程文件: one document listed on an agenda (role agenda_paper).
- 表決結果: one motion kept at the 14:30 cutoff, with 通過 or 否決.

Per-member votes are not stored or exported. Minutes and voting-sheet PDFs
are not agenda listings, so they are left out. Votes stored under
votes_after_cutoff are left out too.
"""

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

COLUMNS = (
    "紀錄種類",
    "日期",
    "時間",
    "地點",
    "委員會名稱",
    "議程項目",
    "文件名稱",
    "網址",
    "本地路徑",
    "表決編號",
    "議案",
    "整體結果",
    "表決時間",
    "下載時間",
    "SHA256",
)

RESULT_LABEL = {"Passed": "通過", "Negatived": "否決"}


def agenda_subject(meeting, item_key):
    if not item_key:
        return ""
    for item in meeting.get("agenda_items") or []:
        if item.get("item_key") == item_key:
            title = (item.get("title") or "").strip()
            return f"{item_key} {title}".strip()
    return str(item_key)


def blank():
    return {column: "" for column in COLUMNS}


def meeting_base(meeting, clock):
    row = blank()
    row["日期"] = meeting.get("meeting_date") or ""
    row["時間"] = clock
    row["地點"] = meeting.get("venue_name") or ""
    row["委員會名稱"] = meeting.get("committee_name") or ""
    return row


def vote_clock(value):
    if not value or "T" not in value:
        return ""
    return value.split("T", 1)[-1][:8]


def label(table, value):
    if value is None:
        return ""
    return table.get(value, str(value))


def rows_from(snapshot):
    rows = []
    for meeting in snapshot.get("meetings", []):
        start = meeting.get("start_time") or ""
        clock = start.split("T", 1)[-1][:5] if "T" in start else ""
        for doc in meeting.get("documents", []):
            if doc.get("role") != "agenda_paper":
                continue
            row = meeting_base(meeting, clock)
            row["紀錄種類"] = "議程文件"
            row["議程項目"] = agenda_subject(meeting, doc.get("item_key"))
            row["文件名稱"] = doc.get("title") or doc.get("paper_label") or ""
            row["網址"] = doc.get("url") or ""
            row["本地路徑"] = doc.get("local_path") or ""
            if row["本地路徑"]:
                row["下載時間"] = doc.get("downloaded_at") or ""
                row["SHA256"] = doc.get("sha256") or ""
            rows.append(row)
        for motion in meeting.get("motions") or []:
            decision = meeting_base(meeting, clock)
            decision["紀錄種類"] = "表決結果"
            decision["表決編號"] = "" if motion.get("vote_number") is None else str(motion.get("vote_number"))
            decision["議案"] = motion.get("motion_title") or ""
            decision["整體結果"] = label(RESULT_LABEL, motion.get("result"))
            decision["表決時間"] = vote_clock(motion.get("vote_time") or "")
            rows.append(decision)
    return rows


def sha256_of(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_added_at(repo, relpath):
    proc = subprocess.run(
        ["git", "log", "--follow", "-M100%", "--diff-filter=A", "--format=%cI", "--", relpath],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def stamp_downloads(data_dir, freshly_saved=None, now=None):
    """Fill sha256 and downloaded_at on snapshot documents that have a local PDF.

    A file saved during this run uses `now`. An older file uses the commit that
    added it. A row with no local file keeps both fields empty.
    """
    data_dir = Path(data_dir)
    repo = data_dir.parent
    fresh = set(freshly_saved or [])
    stamped_at = (now or datetime.now(timezone.utc)).isoformat()
    cache = {}
    written = 0
    for snap_path in sorted(data_dir.glob("*/snapshot.json")):
        snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
        changed = False
        for meeting in snapshot.get("meetings") or []:
            for doc in meeting.get("documents") or []:
                rel = doc.get("local_path") or ""
                if not rel or not (repo / rel).is_file():
                    if doc.get("sha256") or doc.get("downloaded_at"):
                        doc["sha256"] = None
                        doc["downloaded_at"] = None
                        changed = True
                    continue
                if rel not in cache:
                    sha = sha256_of(repo / rel)
                    when = stamped_at if rel in fresh else git_added_at(repo, rel)
                    cache[rel] = (sha, when)
                sha, when = cache[rel]
                if not when:
                    when = doc.get("downloaded_at") or ""
                if doc.get("sha256") != sha or (doc.get("downloaded_at") or "") != when:
                    doc["sha256"] = sha
                    doc["downloaded_at"] = when or None
                    changed = True
        if changed:
            snap_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written += 1
    return written


def write_meetings_csv(data_dir, out=None):
    data_dir = Path(data_dir)
    out = Path(out) if out else data_dir / "meetings.csv"
    rows = []
    for path in sorted(data_dir.glob("*/snapshot.json")):
        rows.extend(rows_from(json.loads(path.read_text(encoding="utf-8"))))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return out, len(rows)


def main():
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    stamp_downloads(data_dir)
    path, count = write_meetings_csv(data_dir)
    print(f"{path} {count}")


if __name__ == "__main__":
    main()
