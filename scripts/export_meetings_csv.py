#!/usr/bin/env python3
"""Write data/meetings.csv from every data/*/snapshot.json.

One row is one document listed on an agenda (role agenda_paper).
Minutes and voting sheets are not agenda listings, so they are left out.
"""

import csv
import json
from pathlib import Path

COLUMNS = ("日期", "時間", "地點", "委員會名稱", "議程項目", "文件名稱", "網址", "本地路徑")


def agenda_subject(meeting, item_key):
    if not item_key:
        return ""
    for item in meeting.get("agenda_items") or []:
        if item.get("item_key") == item_key:
            title = (item.get("title") or "").strip()
            return f"{item_key} {title}".strip()
    return str(item_key)


def rows_from(snapshot):
    rows = []
    for meeting in snapshot.get("meetings", []):
        start = meeting.get("start_time") or ""
        clock = start.split("T", 1)[-1][:5] if "T" in start else ""
        for doc in meeting.get("documents", []):
            if doc.get("role") != "agenda_paper":
                continue
            rows.append(
                {
                    "日期": meeting.get("meeting_date") or "",
                    "時間": clock,
                    "地點": meeting.get("venue_name") or "",
                    "委員會名稱": meeting.get("committee_name") or "",
                    "議程項目": agenda_subject(meeting, doc.get("item_key")),
                    "文件名稱": doc.get("title") or doc.get("paper_label") or "",
                    "網址": doc.get("url") or "",
                    "本地路徑": doc.get("local_path") or "",
                }
            )
    return rows


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
    path, count = write_meetings_csv(root / "data")
    print(f"{path} {count}")


if __name__ == "__main__":
    main()
