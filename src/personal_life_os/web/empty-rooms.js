const periods = ["08:00", "08:50", "09:50", "10:40", "11:20", "14:00", "14:50", "15:40", "16:30", "18:30", "19:20", "20:10", "21:00"];
const fallbackRooms = Array.from({ length: 19 }, (_, index) => `东教学楼${index + 1}教室`);
let selectedDate = new URLSearchParams(location.search).get("date");
let currentPayload = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
}

function render(payload) {
  currentPayload = payload;
  const byDate = payload.classroom_usage_by_date || {};
  const dates = Object.keys(byDate).sort();
  if (!dates.includes(selectedDate)) selectedDate = dates[0] || null;
  document.querySelector("#building").textContent = payload.building || "教学楼";
  document.querySelector("#status").textContent = payload.status === "ready" ? "数据已就绪" : "等待首次轮询";
  document.querySelector("#status-dot").className = payload.status === "ready" ? "ready" : "";
  document.querySelector("#updated-at").textContent = payload.updated_at ? `更新于 ${new Date(payload.updated_at).toLocaleString("zh-CN")}` : "暂无快照";
  document.querySelector("#dates").innerHTML = dates.map(date => `<button class="${date === selectedDate ? "active" : ""}" data-date="${date}">${escapeHtml(date)}</button>`).join("");
  document.querySelectorAll("#dates button").forEach(button => button.onclick = () => { selectedDate = button.dataset.date; history.replaceState(null, "", `?date=${selectedDate}`); render(currentPayload); });
  if (!selectedDate) { document.querySelector("#free-count").textContent = "0"; document.querySelector("#grid").innerHTML = '<div class="message">服务已启动，等待定时任务写入首份数据。</div>'; return; }
  const day = byDate[selectedDate] || {};
  const usage = new Map((day.usage || []).map(item => [item.room, new Set(item.occupied_periods || [])]));
  const rooms = day.rooms?.length ? day.rooms : fallbackRooms;
  document.querySelector("#free-count").textContent = rooms.filter(room => !(usage.get(room)?.size)).length;
  const head = periods.map((time, index) => `<th>第${index + 1}节<br><small>${time}</small></th>`).join("");
  const rows = rooms.map(room => `<tr><th>${escapeHtml(room)}</th>${periods.map((_, index) => `<td class="${usage.get(room)?.has(index + 1) ? "busy" : "free"}">${usage.get(room)?.has(index + 1) ? "有课" : "空"}</td>`).join("")}</tr>`).join("");
  document.querySelector("#grid").innerHTML = `<table><thead><tr><th>教室</th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

async function load() {
  const button = document.querySelector("#refresh"); button.disabled = true;
  try {
    const response = await fetch("/api/empty-rooms", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "读取失败");
    render(payload);
  } catch (error) {
    document.querySelector("#status-dot").className = "error";
    document.querySelector("#status").textContent = "读取失败";
    document.querySelector("#updated-at").textContent = error.message;
  } finally { button.disabled = false; }
}

document.querySelector("#refresh").onclick = load;
load();
window.setInterval(load, 300000);
