# 每日會議抓取計劃

這份文件決定每日如何把立法會當日會議放進資料庫。

每日工作在香港時間下午 2 時 30 分跑一次。它先存當日議程和會前文件。會議紀要、表決和較後才出現的文件留到之後的日子補。

## 每日索引讀 Tmeeting

[立法會日誌](https://www.legco.gov.hk/tc/legco-business/useful-information/legco-calendar.html) 的 HTML 沒有會議清單。頁面留空，由 `/cs/scripts/legco-calendar-bundle.js` 在瀏覽器裡填上。該程式連到 `https://ws1.legco.gov.hk/signalr`。

開放數據 [Tmeeting](https://app.legco.gov.hk/ScheduleDB/odata/Tmeeting) 在 2026-11-17 回了兩筆。兩筆的中文議程網址就是這兩條。

- https://www.legco.gov.hk/yr2026/chinese/panels/ci/agenda/ci20261117.htm
- https://www.legco.gov.hk/yr2026/chinese/bc/bc106/agenda/bc10620261117.htm

每日索引讀 Tmeeting 裡 `start_date_time` 落在當日香港日期的列。委員會名稱只存 `subject_chi`。議程頁上的委員會名稱不另存一欄。

## 下午 2 時 30 分存議程，紀要留待補

工商及創新科技事務委員會 11 月 17 日議程的頁腳寫立法會秘書處 2026 年 11 月 16 日。《2026年調解(修訂)條例草案》委員會那份寫 2026 年 11 月 17 日。同一天才發出的議程，早上的工作會錯過。下午 2 時 30 分是為了接住當日發出的議程。文件在幾點放上網站，這次沒有量度。

當日議程頁有項目標題和會前文件連結。頁上沒有會議紀要，也沒有表決結果。

實測如下。

- `panels/ci/minutes/ci20261117.pdf` 在 2026-11-19 是 404。
- `panels/ci/minutes/ci20261020.pdf` 是 PDF。回應的 Last-Modified 是 2026-10-30。10 月 20 日的紀要，10 日後才在伺服器上。
- `bc/bc106/minutes/bc10620261030.pdf` 是 PDF。
- 立法會會議沒有對應的 minutes PDF。`counmtg/floor/cm20261111-confirm-ec.pdf` 是 PDF，約 17MB。這是會議過程紀錄，不是短紀要。
- [vVotingResult](https://app.legco.gov.hk/vrdb/odata/vVotingResult) 在 `vote_date` 為 2026-11-18 和 2026-11-19 時有 Council Meeting 列。每一列是一位議員。同一議案的 `motion_ch` 和 `overall_result` 在這些列上重複。
- `counmtg/voting/v20261111.pdf` 和 `v20261118.pdf` 是 PDF。`vote_date` 等於 2026-11-11 的查詢沒有列。延續會議是另一個 `meet_id`，共用第一天的議程網址。

未完成的會議會在其後的每天下午再讀一次。窗口是會議日起 21 日。21 來自上面那份 10 日後才出現的紀要，再留餘地。這是選擇，不是量到的上限。窗口最後一日仍沒有紀要，`status` 標成 `expired`。

## 為何分成四張表

第一種形狀是一場會議一列。議程、文件和議案都放在該列的清單裡。議程解析和表決解析都寫這一列。重跑要整列重寫。

第二種形狀是四張表。會議、議程項目、文件、議案各有一個寫入者。

用第二種。議程解析只寫議程項目和會前文件。表決解析只寫議案。重跑按主鍵更新。

不存每位議員一列。開放數據有議員姓名。這裡要的是議案名稱和結果，所以摺成一筆議案。

不抽取 PDF 文字。PDF 檔本身要存下來。來源網址仍寫在 `url`。

## 四張表

`meeting` 的主人是 Tmeeting 的 `meet_id`。

- `meet_id`
- `meeting_date`，香港日期
- `start_time`
- `committee_name`，即 `subject_chi`
- `agenda_url`
- `venue_name`
- `meeting_type`
- `follow_up_until`，`meeting_date` 加 21 日
- `status`，`open`、`complete` 或 `expired`

`agenda_item` 的主人是一場會議裡的一個項目。

- `meet_id`
- `item_key`，例如 I 或 II
- `title`

主鍵是 `meet_id` 加 `item_key`。

`document` 的主人是一場會議裡的一份文件。

- `meet_id`
- `role`，`agenda_paper`、`minutes`、`voting_sheet` 或 `later_paper`
- `paper_label`，例如 `CB(2)1517/2026(01)`。沒有編號就空着
- `title`
- `url`。只限委員參閱、頁上沒有連結時是空
- `local_path`。當日已在網站上的 PDF 才有值。否則是空

主鍵是 `meet_id`、`role`，再加 `paper_label` 或 `url`。

PDF 的路徑是 `data/` 加 `committee_name`，再加 `meeting_date`，再加網址最後一段檔名。`committee_name` 就是 `subject_chi`，包含結尾的「會議」。檔案跟所屬會議走，不跟網址裡的另一個委員會走。重跑寫入同一個路徑。

2026-11-09 下午 2 時 30 分會寫入的例子如下。

- `data/福利事務委員會會議/2026-11-09/ws20261109cb1-1387-1-c.pdf`
- `data/資訊科技及廣播事務委員會會議/2026-11-09/itb20261109cb2-1428-1-c.pdf`
- `data/民政及文化體育事務委員會會議/2026-11-09/ha20261109cb3-1314-1-c.pdf`

該日《2026年醫生註冊(修訂)條例草案》委員會沒有可存的 PDF。紀要要等到檔案在截止時間前已在網站上，才寫進同一個日期資料夾，例如 `data/福利事務委員會會議/2026-11-09/ws20261109.pdf`。

`motion` 的主人是一場會議裡的一次表決。

- `meet_id`
- `vote_type`
- `vote_number`
- `motion_title`
- `result`
- `vote_time`

主鍵是 `meet_id`、`vote_type`、`vote_number`。

11 月 17 日法案委員會議程有「只限委員參閱」而沒有連結的文件，例如 `CB(3)1397/2026(02)`。這一列仍存編號和標題，`url` 留空。

## 資料在邊界解析

HTTP 和 HTML 在邊界收成上面的列。邊界之內不再檢查空值。

- `parseMeeting` 讀 Tmeeting 一列，得到 `meeting`。
- `parseAgenda` 讀議程 HTML 的 `data-unit`，得到 `agenda_item`，以及 `role` 為 `agenda_paper` 的 `document`。以 `/` 開頭的連結補上 `https://www.legco.gov.hk`。
- `foldVotes` 把同一 `vote_type` 和 `vote_number` 的議員列摺成一筆 `motion`。
- `minutesUrl` 由議程網址和日期推出紀要位址，再請求確認。推不出或不是 200，就留空。
- `votingSheetUrl` 只對立法會會議試 `counmtg/voting/v` 加日期的 PDF。

紀要位址來自下面三個實測例子，不是從議程頁的連結讀到的。

- 事務委員會是 `/yr2026/chinese/panels/{code}/minutes/{code}{YYYYMMDD}.pdf`。`ci20261020.pdf` 曾回 200。
- 法案委員會是 `/yr2026/chinese/bc/{code}/minutes/{code}{YYYYMMDD}.pdf`。`bc10620261030.pdf` 曾回 200。
- 立法會會議用 `/yr2026/chinese/counmtg/floor/cm{YYYYMMDD}-confirm-ec.pdf` 當會議紀錄連結，`role` 仍是 `minutes`。`cm20261111-confirm-ec.pdf` 曾回 200。

新的委員會種類若得到 404，就留空，下一輪再試。不猜第二條路徑。

表決接到會議的規則如下。`vote_date` 的日期等於 `meeting_date`，而且 `vote_type` 是 Council Meeting 時，接到當日 `subject_chi` 含「立法會會議」的 `meet_id`。其他 `vote_type` 只在名稱能對上 `committee_name` 時才接。對不上就不掛。延續會議的表決掛在表決當日那一筆 `meet_id`，不掛回第一天。

## 每天下午的一輪

時區是 `Asia/Hong_Kong`。每日 14:30 跑一次。14:30 之前不讀議程。

一輪的順序如下。

1. 讀當日 Tmeeting。按 `meet_id` upsert `meeting`。新會議的 `status` 是 `open`。
2. 再取出 `status` 仍是 `open`、而且 `follow_up_until` 尚未過去的舊會議。
3. 對每一場讀 `agenda_url`。upsert 議程項目和 `agenda_paper`。主鍵已在就更新標題和 `url`。已在網站上的 PDF 寫入 `local_path`。
4. 試紀要位址。截止時間前已在網站上，就 upsert `role` 為 `minutes` 的文件，並把 PDF 寫入同一個日期資料夾。
5. 讀當日 `vVotingResult`，摺成 `motion`，掛到對得上的 `meet_id`。
6. 立法會會議再試表決 PDF。200 就 upsert `voting_sheet`。
7. 議程上新出現、又不是上面幾種的連結，用 `later_paper` 插入。
8. 這一輪存到紀要，就把 `status` 改為 `complete`。`follow_up_until` 已過而仍然沒有紀要，就改為 `expired`。沒有表決的會議也可以 `complete`。事務委員會常常沒有表決。

找到紀要的那一輪會先再讀議程，所以和紀要同一輪出現的新文件會一併寫入。紀要入庫之後才放上的文件，這一版不再回頭。表決通常早於紀要。11 月 18 日和 19 日的 Council Meeting 列在紀要 PDF 出現之前已經能查到。

同一 `meet_id` 再跑不會多一列會議。議程存了就留着，只做更新。中途停掉時，下一輪看資料庫裡已經有的列，不看上一輪打算做到哪裡。

## 會議文件 CSV

`data/meetings.csv` 把已抓取各日的議程文件合成一張表，方便直接打開。它不是第五張資料表。一列是議程上的一份文件，`role` 為 `agenda_paper`。會議紀要和表決結果 PDF 不在這張表。同一份檔在議程上出現兩次，就寫兩列。

欄位如下。

- `日期`
- `時間`，當日開始時間，寫成 `HH:MM`
- `地點`
- `委員會名稱`
- `議程項目`，項目編號加議程上的項目標題
- `文件名稱`，議程連結上的文字
- `網址`
- `本地路徑`。截止時間前未在網站上的 PDF，以及不是 PDF 的連結，留空

來源是 `data/` 下每個 `snapshot.json`。`python3 scripts/export_meetings_csv.py` 重寫這份 CSV。`fetch_day.py` 寫完當日快照後也會重寫它。檔案是 UTF-8，開頭有 BOM。議程頁在截止時間後才修改的會議沒有文件列。2026-11-08 沒有會議，所以沒有列。

## 狀態圖

模型只有一場會議和兩天。第一天紀要未公布。第二天開始時紀要已公布。TLC 到達 11 個狀態。圖畫 8 個狀態和 8 條箭。圖藏起結束後停住、狀態不再變的那一步。

下面的規則都成立。

- 下午 2 時 30 分之前不讀當日清單，也不存議程。
- 紀要不早於議程入庫。
- 紀要未入庫時，會議不會標成已齊。
- 議程入庫之後一直留着。
- 在公平執行下，第二天會做完。

```mermaid
stateDiagram-v2
  state "Legend" as legend {
    lg0: 等待
    lg1: 抓取
    lg2: 待補
    lg3: 完成
  }
  class lg0 blue
  class lg1 orange
  class lg2 yellow
  class lg3 teal
  s0: 等到下午2時30分
  s1: 已到2時30分，尚未讀取當日會議
  s2: 已列出當日會議
  s3: 已存議程，紀要尚未公布
  s4: 當日工作結束，會議仍待補
  s5: 已存議程，紀要已公布但未存入
  s6: 已存議程和紀要
  s7: 當日工作結束，會議已齊
  [*] --> s0
  s0 --> s1: 到了香港時間下午2時30分
  s1 --> s2: 工作讀取當日會議
  s2 --> s3: 工作存入議程和議程文件
  s3 --> s4: 工作結束並把會議留待補抓
  s4 --> s0: 下一天開始，紀要已經公布
  s2 --> s5: 工作存入議程和議程文件
  s5 --> s6: 工作存入會議紀要
  s6 --> s7: 工作結束，會議資料已齊
  class s0 blue
  class s1 blue
  class s2 orange
  class s3 orange
  class s4 yellow
  class s5 orange
  class s6 orange
  class s7 teal
```

模型沒有多場會議、表決、只限委員的文件、網路失敗，也沒有 21 日到期仍無紀要。到期仍無紀要時，計劃把 `status` 標成 `expired`。圖裡沒有這個狀態。

規格在 `docs/daily-meeting-ingest/DailyIngest.tla`，標籤在同目錄的 `view.ts`。再用狀態圖程式跑一次時，`--out` 必須是空目錄。這次檢查寫入 `/tmp/legco-daily-ingest/out3/chart.mmd`。那份原文把逗號寫成 `#65292;`。上面的圖改回逗號，箭和狀態沒有改。

## 這一版不做的事

不抓英文頁。不存議員逐一的表決。不抽取 PDF 文字。不猜第二條紀要路徑。
