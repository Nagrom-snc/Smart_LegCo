export const title = "每日下午2時30分的立法會抓取";

export const colors = {
  等待: "blue",
  抓取: "orange",
  待補: "yellow",
  完成: "teal",
};

export const state = (v) => {
  if (v.phase === "waiting" && v.clock === "before") return "等到下午2時30分";
  if (v.phase === "waiting" && v.clock === "due") return "已到2時30分，尚未讀取當日會議";
  if (v.phase === "listed") return "已列出當日會議";
  if (v.phase === "saved" && v.minutesReady === false) return "已存議程，紀要尚未公布";
  if (v.phase === "saved" && v.minutesReady === true && v.minutes === false)
    return "已存議程，紀要已公布但未存入";
  if (v.phase === "saved" && v.minutes === true) return "已存議程和紀要";
  if (v.phase === "finished" && v.openLeft === true) return "當日工作結束，會議仍待補";
  if (v.phase === "finished" && v.openLeft === false) return "當日工作結束，會議已齊";
  return "其他";
};

export const group = (v) => {
  const name = state(v);
  if (name === "等到下午2時30分" || name === "已到2時30分，尚未讀取當日會議") return "等待";
  if (name === "當日工作結束，會議仍待補") return "待補";
  if (name === "當日工作結束，會議已齊") return "完成";
  return "抓取";
};

export const step = (action, _from, to) => {
  if (action === "ClockHits") return "到了香港時間下午2時30分";
  if (action === "ListMeetings") return "工作讀取當日會議";
  if (action === "SaveAgenda") return "工作存入議程和議程文件";
  if (action === "SaveMinutes") return "工作存入會議紀要";
  if (action === "FinishRun" && to.openLeft === true) return "工作結束並把會議留待補抓";
  if (action === "FinishRun" && to.openLeft === false) return "工作結束，會議資料已齊";
  if (action === "NextDay") return "下一天開始，紀要已經公布";
  if (action === "Done") return null;
  return action;
};
