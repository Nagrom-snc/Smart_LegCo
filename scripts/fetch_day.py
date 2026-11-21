#!/usr/bin/env python3
"""One 14:30 HKT run of the daily LegCo ingest, for a single date.

Writes the rows that run would store. A file is stored only when its
Last-Modified is at or before 14:30 that day. A vote is stored only when
vote_time is at or before 14:30. This does not download PDF bytes.

Every run rewrites data/meetings.csv from every snapshot under data/.
A snapshot without that rewrite is an unfinished run.
"""

import argparse
import email.utils
import json
import re
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

HKT = timezone(timedelta(hours=8))
ROOT = "https://www.legco.gov.hk"
CTX = ssl._create_unverified_context()
UA = {"User-Agent": "SmartLegCo/fetch-day"}


def get(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60, context=CTX) as res:
            body = res.read() if method == "GET" else b""
            return res.status, res.headers, body
    except urllib.error.HTTPError as err:
        return err.code, err.headers, b""


def clean(html):
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def absolute(href):
    if href.startswith("http"):
        return href
    return ROOT + href


def last_modified(headers):
    raw = headers.get("Last-Modified") if headers else None
    if not raw:
        return None
    return email.utils.parsedate_to_datetime(raw)


def meetings_on(day):
    filt = (
        f"year(start_date_time) eq {day.year} and "
        f"month(start_date_time) eq {day.month} and "
        f"day(start_date_time) eq {day.day}"
    )
    url = "https://app.legco.gov.hk/ScheduleDB/odata/Tmeeting?" + urllib.parse.urlencode(
        {"$format": "json", "$filter": filt, "$orderby": "start_date_time"}
    )
    _, _, body = get(url)
    return json.loads(body)["value"]


def votes_on(day, cutoff_local):
    filt = f"vote_date eq datetime'{day.isoformat()}T00:00:00'"
    grouped = {}
    skip = 0
    while True:
        url = "https://app.legco.gov.hk/vrdb/odata/vVotingResult?" + urllib.parse.urlencode(
            {
                "$format": "json",
                "$filter": filt,
                "$select": "type,vote_number,motion_ch,overall_result,vote_time,name_ch,name_en,constituency,vote,display_order",
                "$orderby": "vote_number,display_order",
                "$skip": str(skip),
                "$top": "400",
            }
        )
        _, _, body = get(url)
        rows = json.loads(body).get("value", [])
        if not rows:
            break
        for row in rows:
            key = (row.get("type"), row.get("vote_number"))
            bucket = grouped.setdefault(key, {"row": row, "members": []})
            bucket["members"].append(
                {
                    "name_ch": row.get("name_ch"),
                    "name_en": row.get("name_en"),
                    "constituency": row.get("constituency"),
                    "vote": row.get("vote"),
                    "display_order": row.get("display_order"),
                }
            )
        skip += 400
    kept, later = [], []
    for (vote_type, number), bucket in sorted(grouped.items(), key=lambda item: item[0][1] or 0):
        row = bucket["row"]
        stamp = datetime.fromisoformat(row["vote_time"]).replace(tzinfo=HKT)
        members = sorted(bucket["members"], key=lambda member: (member.get("display_order") or 0, member.get("name_ch") or ""))
        item = {
            "vote_type": vote_type,
            "vote_number": number,
            "motion_title": row.get("motion_ch"),
            "result": row.get("overall_result"),
            "vote_time": stamp.isoformat(),
            "members": members,
        }
        (kept if stamp <= cutoff_local else later).append(item)
    return kept, later


def pdf_path(committee_name, meeting_date, url, ready):
    path = urllib.parse.urlparse(url).path
    if not ready or not path.lower().endswith(".pdf"):
        return None
    return f"data/{committee_name}/{meeting_date}/{path.rsplit('/', 1)[-1]}"


def probe(url, cutoff_utc):
    code, headers, _ = get(url, method="HEAD")
    modified = last_modified(headers)
    ready = code == 200 and modified is not None and modified <= cutoff_utc
    return {
        "url": url,
        "http_status": code,
        "last_modified": modified.isoformat() if modified else None,
        "bytes": int(headers.get("Content-Length") or 0) if code == 200 else None,
        "on_site_at_cutoff": ready,
    }


def parse_agenda(html, cutoff_utc):
    items = []
    documents = []
    parts = re.split(r'<div data-lang="chi" data-unit="', html)
    current = None
    for part in parts[1:]:
        unit = part.split('"', 1)[0]
        number = re.search(r'item[-_]num">(.*?)</div>', part)
        title = re.search(r'data-unit="text">(.*?)</div>', part[number.end():]) if number else None
        if not title:
            title = re.search(r'data-unit="title"><div>(.*?)</div>', part)
        if number and title and unit.startswith("section."):
            current = {"item_key": clean(number.group(1)).replace(".", ""), "title": clean(title.group(1))}
            items.append(current)
        if unit == "section.cm-present-paper" and not number:
            current = next((item for item in items if item["item_key"] == "I"), current)
        if unit == "question-details":
            question = clean(part.split(">", 1)[-1][:2500])
            key = f"II-{len([i for i in items if str(i['item_key']).startswith('II-')]) + 1:02d}"
            items.append({"item_key": key, "title": question[:80], "text": question})
        for href, label in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', part):
            if href.startswith("#") or href.endswith((".css", ".js", ".png", ".json")):
                continue
            info = probe(absolute(href), cutoff_utc)
            info.update(
                {
                    "role": "agenda_paper",
                    "paper_label": clean(label)[:80],
                    "title": clean(label),
                    "item_key": current["item_key"] if current else None,
                }
            )
            documents.append(info)
    return items, documents


def cutoff_for(day):
    return datetime(day.year, day.month, day.day, 14, 30, tzinfo=HKT)


def one_meeting(row, day, cutoff, kept_votes):
    cutoff_utc = cutoff.astimezone(timezone.utc)
    agenda_url = row["agenda_url_chi"]
    code, headers, body = get(agenda_url)
    page_modified = last_modified(headers)
    page_ready = code == 200 and page_modified is not None and page_modified <= cutoff_utc
    items, documents = ([], [])
    if page_ready:
        items, documents = parse_agenda(body.decode("utf-8", "replace"), cutoff_utc)
    minutes = probe(minutes_url(agenda_url, day), cutoff_utc) if minutes_url(agenda_url, day) else None
    if minutes:
        minutes.update({"role": "minutes", "paper_label": None, "title": "會議紀要", "item_key": None})
    voting_sheet = None
    if "立法會會議" in (row.get("subject_chi") or ""):
        voting_sheet = probe(
            f"{ROOT}/yr2026/chinese/counmtg/voting/v{day.strftime('%Y%m%d')}.pdf",
            cutoff_utc,
        )
        voting_sheet.update({"role": "voting_sheet", "paper_label": None, "title": "表決結果", "item_key": None})
    motions = kept_votes if row.get("subject_chi") == "立法會會議" else []
    stored_minutes = bool(minutes and minutes["on_site_at_cutoff"])
    committee = row["subject_chi"]
    docs = documents + [d for d in (minutes, voting_sheet) if d]
    for doc in docs:
        doc["local_path"] = pdf_path(committee, day.isoformat(), doc["url"], doc["on_site_at_cutoff"])
    return {
        "meet_id": row["meet_id"],
        "meeting_date": day.isoformat(),
        "start_time": row["start_date_time"],
        "committee_name": committee,
        "agenda_url": agenda_url,
        "venue_name": row.get("venue_name_chi"),
        "meeting_type": row.get("meeting_type_chi"),
        "follow_up_until": (day + timedelta(days=21)).isoformat(),
        "status": "complete" if stored_minutes else "open",
        "agenda_page": {
            "http_status": code,
            "last_modified": page_modified.isoformat() if page_modified else None,
            "on_site_at_cutoff": page_ready,
        },
        "agenda_items": items,
        "documents": docs,
        "motions": motions,
    }


def build_snapshot(day, now=None):
    cutoff = cutoff_for(day)
    rows = meetings_on(day)
    kept_votes, later_votes = votes_on(day, cutoff)
    observed = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    return {
        "as_of": cutoff.isoformat(),
        "observed_at": observed.isoformat(),
        "meetings": [one_meeting(row, day, cutoff, kept_votes) for row in rows],
        "votes_after_cutoff": later_votes,
    }


def minutes_url(agenda_url, day):
    stamp = day.strftime("%Y%m%d")
    if "/counmtg/" in agenda_url:
        return f"{ROOT}/yr2026/chinese/counmtg/floor/cm{stamp}-confirm-ec.pdf"
    match = re.search(r"/chinese/(.+)/agenda/([a-z0-9]+)\d{8}\.htm", agenda_url)
    if not match:
        return None
    folder, code = match.group(1), match.group(2)
    return f"{ROOT}/yr2026/chinese/{folder}/minutes/{code}{stamp}.pdf"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    day = datetime.fromisoformat(args.date).date()
    out = build_snapshot(day)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(path)
    data_dir = Path(__file__).resolve().parents[1] / "data"
    if data_dir not in path.resolve().parents:
        raise SystemExit(f"{path} is outside {data_dir}; the CSV only reads snapshots there")
    from export_meetings_csv import write_meetings_csv

    csv_path, count = write_meetings_csv(data_dir)
    print(f"{csv_path} {count}")


if __name__ == "__main__":
    main()
