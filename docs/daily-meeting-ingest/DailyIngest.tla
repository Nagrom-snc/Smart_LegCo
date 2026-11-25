---- MODULE DailyIngest ----
EXTENDS Integers

\* One meeting, on day 1. Day 2 is both the next calendar day and the end of
\* that meeting's follow-up window. The real job uses 21 days; the chart uses
\* the next day so the picture stays small.

VARIABLES
  day,
  clock,
  snap1,
  snap2,
  agenda,
  minutes,
  status,
  csv

vars == <<day, clock, snap1, snap2, agenda, minutes, status, csv>>

Init ==
  /\ day = 1
  /\ clock = "before"
  /\ snap1 = FALSE
  /\ snap2 = FALSE
  /\ agenda = FALSE
  /\ minutes = FALSE
  /\ status = "none"
  /\ csv = FALSE

\* 14:30 arrives. This step reads nothing.
Tick ==
  /\ clock = "before"
  /\ clock' = "due"
  /\ UNCHANGED <<day, snap1, snap2, agenda, minutes, status, csv>>

\* The 14:30 run for day 1. Minutes are not on the site yet.
RunDay1 ==
  /\ day = 1
  /\ clock = "due"
  /\ ~snap1
  /\ snap1' = TRUE
  /\ agenda' = TRUE
  /\ status' = "open"
  /\ csv' = TRUE
  /\ UNCHANGED <<day, clock, snap2, minutes>>

\* The machine was off at 14:30. The next morning, yesterday is still missing.
RollToMorningUnrun ==
  /\ day = 1
  /\ clock = "due"
  /\ ~snap1
  /\ day' = 2
  /\ clock' = "before"
  /\ UNCHANGED <<snap1, snap2, agenda, minutes, status, csv>>

\* Day 1 was stored. Morning of day 2, before today's cutoff.
ToNextMorning ==
  /\ day = 1
  /\ clock = "due"
  /\ snap1
  /\ day' = 2
  /\ clock' = "before"
  /\ UNCHANGED <<snap1, snap2, agenda, minutes, status, csv>>

\* Opening the program before today's 14:30 catches up yesterday.
CatchUp ==
  /\ day = 2
  /\ clock = "before"
  /\ ~snap1
  /\ snap1' = TRUE
  /\ agenda' = TRUE
  /\ status' = "open"
  /\ csv' = TRUE
  /\ UNCHANGED <<day, clock, snap2, minutes>>

\* Day 2 at 14:30. Yesterday's meeting is open, and minutes are now on the site.
FollowUpComplete ==
  /\ day = 2
  /\ clock = "due"
  /\ ~snap2
  /\ snap1
  /\ status = "open"
  /\ minutes' = TRUE
  /\ status' = "complete"
  /\ snap2' = TRUE
  /\ csv' = TRUE
  /\ UNCHANGED <<day, clock, snap1, agenda>>

\* Day 2 at 14:30. The window has ended and minutes are still absent.
FollowUpExpired ==
  /\ day = 2
  /\ clock = "due"
  /\ ~snap2
  /\ snap1
  /\ status = "open"
  /\ ~minutes
  /\ status' = "expired"
  /\ snap2' = TRUE
  /\ csv' = TRUE
  /\ UNCHANGED <<day, clock, snap1, agenda, minutes>>

\* Day 2 at 14:30, and yesterday was never stored. The one-day lookback has closed.
RunDay2Only ==
  /\ day = 2
  /\ clock = "due"
  /\ ~snap2
  /\ ~snap1
  /\ status = "none"
  /\ snap2' = TRUE
  /\ csv' = TRUE
  /\ UNCHANGED <<day, clock, snap1, agenda, minutes, status>>

Done ==
  /\ snap2
  /\ UNCHANGED vars

Next ==
  \/ Tick
  \/ RunDay1
  \/ RollToMorningUnrun
  \/ ToNextMorning
  \/ CatchUp
  \/ FollowUpComplete
  \/ FollowUpExpired
  \/ RunDay2Only
  \/ Done

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

TypeOK ==
  /\ day \in 1..2
  /\ clock \in {"before", "due"}
  /\ snap1 \in BOOLEAN
  /\ snap2 \in BOOLEAN
  /\ agenda \in BOOLEAN
  /\ minutes \in BOOLEAN
  /\ status \in {"none", "open", "complete", "expired"}
  /\ csv \in BOOLEAN

\* Today's snapshot is not written before today's 14:30.
\* Yesterday may be written before today's 14:30: that is the catch-up.
NoReadTodayEarly ==
  /\ (day = 1 /\ clock = "before") => ~snap1
  /\ snap2 => (day = 2 /\ clock = "due")
  /\ agenda <=> snap1

\* A run that stores a snapshot rewrites the CSV in the same step.
\* A skip stores neither.
CsvTracksWrites ==
  csv <=> (snap1 \/ snap2)

MinutesAfterAgenda ==
  minutes => agenda

CompleteMeansMinutes ==
  (status = "complete") <=> minutes

ExpiredMeansNoMinutes ==
  status = "expired" => (~minutes /\ snap1 /\ snap2 /\ day = 2 /\ clock = "due")

OpenMeansWaiting ==
  status = "open" => (agenda /\ ~minutes /\ snap1 /\ ~snap2)

AgendaStays ==
  [][agenda => agenda']_vars

TerminalStays ==
  [][(status \in {"complete", "expired"} => status' = status)]_vars

EventuallyWritesADay ==
  <>(snap2)

====
