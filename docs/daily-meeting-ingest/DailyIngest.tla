---- MODULE DailyIngest ----
EXTENDS Integers

VARIABLES
  clock,
  day,
  phase,
  agenda,
  minutesReady,
  minutes,
  openLeft

vars == <<clock, day, phase, agenda, minutesReady, minutes, openLeft>>

Init ==
  /\ clock = "before"
  /\ day = 1
  /\ phase = "waiting"
  /\ agenda = FALSE
  /\ minutesReady = FALSE
  /\ minutes = FALSE
  /\ openLeft = TRUE

ClockHits ==
  /\ clock = "before"
  /\ phase = "waiting"
  /\ clock' = "due"
  /\ UNCHANGED <<day, phase, agenda, minutesReady, minutes, openLeft>>

ListMeetings ==
  /\ clock = "due"
  /\ phase = "waiting"
  /\ phase' = "listed"
  /\ UNCHANGED <<clock, day, agenda, minutesReady, minutes, openLeft>>

SaveAgenda ==
  /\ phase = "listed"
  /\ agenda' = TRUE
  /\ phase' = "saved"
  /\ UNCHANGED <<clock, day, minutesReady, minutes, openLeft>>

SaveMinutes ==
  /\ phase = "saved"
  /\ minutesReady
  /\ ~minutes
  /\ minutes' = TRUE
  /\ UNCHANGED <<clock, day, phase, agenda, minutesReady, openLeft>>

FinishRun ==
  /\ phase = "saved"
  /\ \/ minutes
     \/ ~minutesReady
  /\ phase' = "finished"
  /\ openLeft' = ~minutes
  /\ UNCHANGED <<clock, day, agenda, minutesReady, minutes>>

NextDay ==
  /\ phase = "finished"
  /\ day < 2
  /\ day' = day + 1
  /\ clock' = "before"
  /\ phase' = "waiting"
  /\ minutesReady' = TRUE
  /\ UNCHANGED <<agenda, minutes, openLeft>>

Done ==
  /\ phase = "finished"
  /\ day = 2
  /\ UNCHANGED vars

Next ==
  ClockHits \/ ListMeetings \/ SaveAgenda \/ SaveMinutes \/ FinishRun \/ NextDay \/ Done

Spec == Init /\ [][Next]_vars /\ WF_vars(Next)

TypeOK ==
  /\ clock \in {"before", "due"}
  /\ day \in 1..2
  /\ phase \in {"waiting", "listed", "saved", "finished"}
  /\ agenda \in BOOLEAN
  /\ minutesReady \in BOOLEAN
  /\ minutes \in BOOLEAN
  /\ openLeft \in BOOLEAN

NoFetchBeforeDue ==
  phase \in {"listed", "saved"} => clock = "due"

MinutesAfterAgenda ==
  minutes => agenda

NotClosedWhileMissing ==
  openLeft = FALSE => minutes

AgendaStays ==
  [][agenda => agenda']_vars

EventuallyComplete ==
  <>(phase = "finished" /\ day = 2 /\ minutes /\ openLeft = FALSE)

====
