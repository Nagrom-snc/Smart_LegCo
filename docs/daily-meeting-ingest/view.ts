export const title = "每日下午2時30分的立法會抓取";

export const colors = {
  等待: "blue",
  待補: "yellow",
  完成: "teal",
  到期: "pink",
  錯過: "orange",
};

export const state = (v) => {
  if (v.day === 1 && v.clock === "before") return "第一天，未到下午2時30分";
  if (v.day === 1 && v.clock === "due" && v.snap1 === false) return "第一天已到2時30分，尚未抓取";
  if (v.day === 1 && v.snap1 === true) return "第一天已抓，會議待補";
  if (v.day === 2 && v.clock === "before" && v.snap1 === true) return "第二天早上，昨天已入庫";
  if (v.day === 2 && v.clock === "before" && v.snap1 === false) return "第二天早上，昨天尚未抓取";
  if (v.day === 2 && v.clock === "due" && v.snap2 === false && v.snap1 === true)
    return "第二天已到2時30分，待跟進昨天的會議";
  if (v.day === 2 && v.clock === "due" && v.snap1 === false && v.snap2 === false)
    return "已過補抓窗口，第一天沒有快照";
  if (v.status === "complete") return "會議已齊，紀要已存";
  if (v.status === "expired") return "跟進窗口已過，會議標成到期";
  if (v.snap2 === true && v.snap1 === false) return "第二天已抓，第一天的會議不在庫";
  return "其他";
};

export const group = (v) => {
  const name = state(v);
  if (
    name === "第一天，未到下午2時30分" ||
    name === "第一天已到2時30分，尚未抓取" ||
    name === "第二天早上，昨天尚未抓取" ||
    name === "已過補抓窗口，第一天沒有快照"
  )
    return "等待";
  if (
    name === "第一天已抓，會議待補" ||
    name === "第二天早上，昨天已入庫" ||
    name === "第二天已到2時30分，待跟進昨天的會議"
  )
    return "待補";
  if (name === "會議已齊，紀要已存") return "完成";
  if (name === "跟進窗口已過，會議標成到期") return "到期";
  if (name === "第二天已抓，第一天的會議不在庫") return "錯過";
  return "等待";
};

export const step = (action, from, to) => {
  if (action === "Tick" && from.day === 1) return "到了第一天下午2時30分";
  if (action === "Tick" && from.snap1 === true) return "到了第二天下午2時30分";
  if (action === "Tick" && from.snap1 === false) return "到了第二天下午2時30分，不再補昨天";
  if (action === "RunDay1") return "抓取第一天：存議程，會議留待補，重寫CSV";
  if (action === "RollToMorningUnrun") return "當日沒跑，進入第二天早上";
  if (action === "ToNextMorning") return "進入第二天早上";
  if (action === "CatchUp") return "打開程式，補抓昨天：存議程，重寫CSV";
  if (action === "FollowUpComplete") return "跟進昨天：存入紀要，會議完成，重寫CSV";
  if (action === "FollowUpExpired") return "跟進昨天：窗口已過且沒有紀要，標成到期，重寫CSV";
  if (action === "RunDay2Only") return "只抓第二天，第一天的會議沒有入庫";
  if (action === "Done") return null;
  return action;
};
