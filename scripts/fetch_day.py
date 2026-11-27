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
import time
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
    delay = 2
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60, context=CTX) as res:
                body = res.read() if method == "GET" else b""
                return res.status, res.headers, body
        except urllib.error.HTTPError as err:
            return err.code, err.headers, b""
        except urllib.error.URLError:
            if attempt == 3:
                raise
            time.sleep(delay)
            delay *= 2


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
                "$select": "type,vote_number,motion_ch,overall_result,vote_time",
                "$orderby": "vote_number",
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
            grouped[key] = row
        skip += 400
    kept, later = [], []
    for (vote_type, number), row in sorted(grouped.items(), key=lambda item: item[0][1] or 0):
        stamp = datetime.fromisoformat(row["vote_time"]).replace(tzinfo=HKT)
        item = {
            "vote_type": vote_type,
            "vote_number": number,
            "motion_title": row.get("motion_ch"),
            "result": row.get("overall_result"),
            "vote_time": stamp.isoformat(),
        }
        (kept if stamp <= cutoff_local else later).append(item)
    return kept, later


def meeting_kind(committee_name, agenda_url=""):
    """Top folder for a meeting. The agenda URL decides; the name is only a fallback."""
    url = agenda_url or ""
    name = committee_name or ""
    if "/counmtg/" in url:
        return "大會"
    if "/fc/" in url:
        return "財務委員會"
    if "/panels/" in url:
        return "事務委員會"
    if "/bc/" in url:
        return "法案委員會"
    if "/hc/" in url:
        return "內務委員會"
    if "立法會會議" in name:
        return "大會"
    if "財務委員會" in name or "工務小組委員會" in name or "人事編制小組委員會" in name:
        return "財務委員會"
    if "事務委員會" in name:
        return "事務委員會"
    if "條例草案" in name:
        return "法案委員會"
    if "內務委員會" in name or "小組委員會" in name:
        return "內務委員會"
    return "其他"


# Longer fragments are matched first. A paper lives under the committee that
# published it, not under every meeting that links to it.
HOMES = (
    ("/hc/sub_leg/sc104/", "內務委員會", "與控煙措施有關的3項附屬法例小組委員會會議", "sc104"),
    ("/hc/sub_leg/sc56/", "內務委員會", "與實施業權註冊制度有關的8項附屬法例小組委員會會議", "sc56"),
    ("/hc/sub_com/hs01/", "內務委員會", "研究“生態+旅遊”事宜小組委員會會議", "hs01"),
    ("/hc/sub_com/hs51/", "內務委員會", "發展新質生產力小組委員會會議", "hs51"),
    ("/hc/sub_com/hs52/", "內務委員會", "人工智能及機械人技術發展事宜小組委員會會議", "hs52"),
    ("/hc/", "內務委員會", "內務委員會會議", "hc"),
    ("/fc/pwsc/", "財務委員會", "工務小組委員會會議", "pwsc"),
    ("/fc/esc/", "財務委員會", "人事編制小組委員會會議", "esc"),
    ("/fc/", "財務委員會", "財務委員會會議", "fc"),
    ("/panels/se/", "事務委員會", "保安事務委員會和經濟發展事務委員會聯席會議", "se"),
    ("/panels/ajls/", "事務委員會", "司法及法律事務委員會會議", "ajls"),
    ("/panels/ca/", "事務委員會", "政制事務委員會會議", "ca"),
    ("/panels/ci/", "事務委員會", "工商及創新科技事務委員會會議", "ci"),
    ("/panels/dev/", "事務委員會", "發展事務委員會會議", "dev"),
    ("/panels/ea/", "事務委員會", "環境事務委員會會議", "ea"),
    ("/panels/ed/", "事務委員會", "教育事務委員會會議", "ed"),
    ("/panels/edev/", "事務委員會", "經濟發展事務委員會會議", "edev"),
    ("/panels/fa/", "事務委員會", "財經事務委員會會議", "fa"),
    ("/panels/fseh/", "事務委員會", "食物安全及環境衞生事務委員會會議", "fseh"),
    ("/panels/ha/", "事務委員會", "民政及文化體育事務委員會會議", "ha"),
    ("/panels/hg/", "事務委員會", "房屋事務委員會會議", "hg"),
    ("/panels/hs/", "事務委員會", "衞生事務委員會會議", "hs"),
    ("/panels/itb/", "事務委員會", "資訊科技及廣播事務委員會會議", "itb"),
    ("/panels/mp/", "事務委員會", "人力事務委員會會議", "mp"),
    ("/panels/ps/", "事務委員會", "公務員及資助機構員工事務委員會會議", "ps"),
    ("/panels/tp/", "事務委員會", "交通事務委員會會議", "tp"),
    ("/panels/ws/", "事務委員會", "福利事務委員會會議", "ws"),
    ("/bc/bc105/", "法案委員會", "《2026年醫生註冊(修訂)條例草案》委員會會議", "bc105"),
    ("/bc/bc106/", "法案委員會", "《2026年調解(修訂)條例草案》委員會會議", "bc106"),
    ("/bc/bc107/", "法案委員會", "《2026年印花税(修訂)(第3號)條例草案》委員會會議", "bc107"),
    ("/bc/bc52/", "法案委員會", "《2026年税務(修訂)(知識產權開支的税項扣除)條例草案》委員會會議", "bc52"),
    ("/counmtg/", "大會", "立法會會議", "cm"),
    ("/bills/", "大會", "立法會會議", "b"),
    ("/subleg/", "大會", "立法會會議", ""),
    ("/brief/", "大會", "立法會會議", ""),
    ("/sec/", "大會", "立法會會議", ""),
)


def stable_committee(name):
    name = re.sub(r"[（(].*?[）)]", "", name or "").strip()
    name = name.replace("特別會議", "會議")
    if "延續" in name:
        return "立法會會議"
    return name or "其他"


def is_council_meeting(committee_name, agenda_url=""):
    """Council business only. A time note that mentions 立法會會議 is not a council meeting."""
    if "/counmtg/" in (agenda_url or ""):
        return True
    return stable_committee(committee_name) == "立法會會議"


def match_home(url):
    path = urllib.parse.urlparse(url or "").path
    for fragment, kind, committee, code in HOMES:
        if fragment in path:
            return kind, committee, code
    report = re.search(r"/bc/([a-z0-9]+)/reports/", path)
    if report:
        return "大會", "立法會會議", report.group(1)
    return None


def date_after_code(filename, code):
    if not code:
        return None
    found = re.search(re.escape(code) + r"(20\d{2})(\d{2})(\d{2})", filename or "", re.I)
    if not found:
        return None
    year, month, day = int(found.group(1)), int(found.group(2)), int(found.group(3))
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def agenda_day(agenda_url):
    found = re.search(r"(20\d{2})(\d{2})(\d{2})\.htm", agenda_url or "")
    if not found:
        return None
    year, month, day = int(found.group(1)), int(found.group(2)), int(found.group(3))
    try:
        datetime(year, month, day)
    except ValueError:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"


def find_existing(kind, committee, filename, root):
    base = Path(root) / "data" / kind / committee
    if not base.is_dir():
        return None
    matches = sorted(path.relative_to(root).as_posix() for path in base.glob(f"*/{filename}") if path.is_file())
    return matches[0] if matches else None


def pdf_path(committee_name, meeting_date, url, ready, agenda_url="", root=None):
    path = urllib.parse.urlparse(url or "").path
    if not ready or not path.lower().endswith(".pdf"):
        return None
    filename = path.rsplit("/", 1)[-1]
    home = match_home(url)
    if home:
        kind, committee, code = home
    else:
        kind = meeting_kind(committee_name, agenda_url)
        committee = stable_committee(committee_name)
        code = ""
    if root is None:
        root = Path(__file__).resolve().parents[1]
    found = find_existing(kind, committee, filename, root)
    if found:
        return found
    dated = date_after_code(filename, code)
    agenda_home = match_home(agenda_url)
    if dated is None and home and agenda_home and agenda_home[:2] == home[:2]:
        dated = agenda_day(agenda_url)
    return f"data/{kind}/{committee}/{dated or meeting_date}/{filename}"


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
    if is_council_meeting(row.get("subject_chi") or "", agenda_url):
        voting_sheet = probe(
            f"{ROOT}/yr2026/chinese/counmtg/voting/v{day.strftime('%Y%m%d')}.pdf",
            cutoff_utc,
        )
        voting_sheet.update({"role": "voting_sheet", "paper_label": None, "title": "表決結果", "item_key": None})
    motions = kept_votes if is_council_meeting(row.get("subject_chi") or "", agenda_url) else []
    stored_minutes = bool(minutes and minutes["on_site_at_cutoff"])
    committee = row["subject_chi"]
    docs = documents + [d for d in (minutes, voting_sheet) if d]
    for doc in docs:
        doc["local_path"] = pdf_path(committee, day.isoformat(), doc["url"], doc["on_site_at_cutoff"], agenda_url)
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
