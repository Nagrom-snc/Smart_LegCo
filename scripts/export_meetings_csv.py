#!/usr/bin/env python3
"""Write data/meetings.csv from every data/*/snapshot.json.

Three row kinds share one file. 紀錄種類 tells them apart.

- 議程文件: one document listed on an agenda (role agenda_paper).
- 表決結果: one motion kept at the 14:30 cutoff, with the overall result.
- 議員表決: one member's vote on that motion.

Minutes and voting-sheet PDFs are not agenda listings, so they are left out.
Votes stored under votes_after_cutoff are left out too.
"""

import csv
import json
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
    "議員",
    "議員投票",
    "選區",
)

RESULT_LABEL = {"Passed": "通過", "Negatived": "否決"}
VOTE_LABEL = {
    "Yes": "贊成",
    "No": "反對",
    "Abstain": "棄權",
    "Present": "出席",
    "Absent": "缺席",
}


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
            rows.append(row)
        for motion in meeting.get("motions") or []:
            decision = meeting_base(meeting, clock)
            decision["紀錄種類"] = "表決結果"
            decision["表決編號"] = "" if motion.get("vote_number") is None else str(motion.get("vote_number"))
            decision["議案"] = motion.get("motion_title") or ""
            decision["整體結果"] = label(RESULT_LABEL, motion.get("result"))
            decision["表決時間"] = vote_clock(motion.get("vote_time") or "")
            rows.append(decision)
            for member in motion.get("members") or []:
                cast = meeting_base(meeting, clock)
                cast["紀錄種類"] = "議員表決"
                cast["表決編號"] = decision["表決編號"]
                cast["議案"] = decision["議案"]
                cast["整體結果"] = decision["整體結果"]
                cast["表決時間"] = decision["表決時間"]
                cast["議員"] = member.get("name_ch") or member.get("name_en") or ""
                cast["議員投票"] = label(VOTE_LABEL, member.get("vote"))
                cast["選區"] = member.get("constituency") or ""
                rows.append(cast)
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
