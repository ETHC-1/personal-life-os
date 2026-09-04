const defaultPeriods = [["08:00","08:40"],["08:50","09:30"],["09:50","10:30"],["10:40","11:20"],["11:20","12:00"],["14:30","15:10"],["15:20","16:00"],["16:10","16:50"],["17:00","17:40"],["18:30","19:10"],["19:20","20:00"],["20:10","20:50"],["21:00","21:40"]];
let periods = defaultPeriods;
const fallbackRooms = Array.from({length: 19}, (_, i) => `东教学楼${i + 1}教室`);
const params = new URLSearchParams(location.search);
let selectedDate = params.get("date");
let selectedBuildingCode = params.get("building");
let selectedPeriod = Number(params.get("period")) || null;
let currentPayload = null;

const localDate = date => { const value = date || new Date(); return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,"0")}-${String(value.getDate()).padStart(2,"0")}`; };
const minutes = value => { const [hour, minute] = value.split(":").map(Number); return hour * 60 + minute; };
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
const updateUrl = () => { const next = new URLSearchParams(); if (selectedBuildingCode) next.set("building", selectedBuildingCode); if (selectedDate) next.set("date", selectedDate); if (selectedPeriod) next.set("period", selectedPeriod); history.replaceState(null,"",`${location.pathname}?${next}`); };
function periodForNow() { const now = new Date().getHours()*60 + new Date().getMinutes(); const current = periods.findIndex(([start,end]) => now >= minutes(start) && now <= minutes(end)); if (current >= 0) return current + 1; const next = periods.findIndex(([start]) => now < minutes(start)); return next >= 0 ? next + 1 : 1; }
function labelDate(value) { const today = localDate(); const tomorrow = localDate(new Date(Date.now()+86400000)); return value === today ? "今天" : value === tomorrow ? "明天" : value.slice(5).replace("-","月") + "日"; }
function setMessage(text) { document.querySelector("#room-list").innerHTML = `<div class="message">${escapeHtml(text)}</div>`; }

function render(payload) {
  currentPayload = payload;
  const buildings = [...(payload.buildings || [])].sort((a,b) => (a.building || "").includes("东教学楼") ? -1 : (b.building || "").includes("东教学楼") ? 1 : 0);
  const active = buildings.find(item => item.building_code === selectedBuildingCode) || buildings[0];
  if (active) selectedBuildingCode = active.building_code;
  const byDate = active?.classroom_usage_by_date || payload.classroom_usage_by_date || {};
  const dates = Object.keys(byDate).sort();
  if (!dates.includes(selectedDate)) selectedDate = dates.includes(localDate()) ? localDate() : dates[0] || null;
  if (!selectedPeriod || selectedPeriod < 1 || selectedPeriod > periods.length) selectedPeriod = selectedDate === localDate() ? periodForNow() : 1;
  const buildingName = active?.building || payload.building || "教学楼";
  document.querySelector("#building").textContent = `${buildingName} · ${selectedDate ? labelDate(selectedDate) : "等待数据"}`;
  document.querySelector("#status").textContent = payload.status === "ready" ? "数据已就绪" : "等待首次查询";
  document.querySelector("#status-dot").className = payload.status === "ready" ? "ready" : "";
  document.querySelector("#updated-at").textContent = payload.updated_at ? `更新于 ${new Date(payload.updated_at).toLocaleString("zh-CN")}` : "暂无快照";
  const select = document.querySelector("#building-select"); select.innerHTML = buildings.map(item => `<option value="${escapeHtml(item.building_code)}">${escapeHtml(item.building)}</option>`).join(""); select.value = selectedBuildingCode || ""; select.onchange = () => { selectedBuildingCode = select.value; updateUrl(); render(currentPayload); };
  document.querySelector("#dates").innerHTML = dates.map(date => `<button class="${date === selectedDate ? "active" : ""}" data-date="${date}">${labelDate(date)}</button>`).join("");
  document.querySelectorAll("#dates button").forEach(button => button.onclick = () => { selectedDate = button.dataset.date; selectedPeriod = selectedDate === localDate() ? periodForNow() : 1; updateUrl(); render(currentPayload); loadPeriods(); });
  document.querySelector("#period-buttons").innerHTML = periods.map(([start],i) => `<button class="${i+1 === selectedPeriod ? "active" : ""}" data-period="${i+1}"><b>${i+1}</b><small>${start}</small></button>`).join("");
  document.querySelectorAll("#period-buttons button").forEach(button => button.onclick = () => { selectedPeriod = Number(button.dataset.period); updateUrl(); render(currentPayload); });
  const day = byDate[selectedDate] || {}; const usage = new Map((day.usage || []).map(item => [item.room, new Set(item.occupied_periods || [])]));
  const isEast = buildingName.includes("东教学楼"); const rooms = isEast ? fallbackRooms : [...new Set((day.rooms || []).concat((day.usage || []).map(item => item.room)))];
  const freeRooms = rooms.filter(room => !usage.get(room)?.has(selectedPeriod)); const range = periods[selectedPeriod-1] || ["",""];
  document.querySelector("#free-count").textContent = freeRooms.length; document.querySelector("#period-label").textContent = `${selectedDate ? labelDate(selectedDate) : "等待数据"} · 第${selectedPeriod}节 ${range[0]}—${range[1]}`; document.querySelector("#query-hint").textContent = selectedDate === localDate() ? "已自动定位最近课时" : "选择课时查看可用教室";
  document.querySelector("#result-note").textContent = payload.updated_at ? `共 ${rooms.length} 间 · ${new Date(payload.updated_at).toLocaleTimeString("zh-CN",{hour:"2-digit",minute:"2-digit"})} 更新` : "";
  document.querySelector("#room-list").innerHTML = !selectedDate ? '<div class="message">服务已启动，等待首份空教室数据</div>' : freeRooms.length ? freeRooms.map(room => `<span>${escapeHtml(isEast ? room.replace("东教学楼","") : room)}</span>`).join("") : '<div class="message">这一节暂未找到可用教室</div>';
  renderTimeline(rooms, usage, buildingName); updateUrl();
}
function renderTimeline(rooms, usage, buildingName) {
  const labels = periods.map(([start],i) => `<span>${i+1}<small>${start}</small></span>`).join("");
  const rows = rooms.map(room => { const occupied = usage.get(room) || new Set(); const cells = periods.map((_,i) => `<i class="${occupied.has(i+1) ? "busy" : "free"}"></i>`).join(""); return `<div class="timeline-row"><strong>${escapeHtml(buildingName.includes("东教学楼") ? room.replace("东教学楼","") : room)}</strong><div>${cells}</div></div>`; }).join("");
  document.querySelector("#grid").innerHTML = `<div class="timeline-head"><strong>${escapeHtml(buildingName)}</strong><div>${labels}</div></div>${rows}`;
}
async function loadPeriods() { if (!selectedDate) return; try { const response = await fetch(`/api/periods?date=${encodeURIComponent(selectedDate)}`,{cache:"no-store"}); const result = await response.json(); if (response.ok && result.periods?.length) { periods = result.periods.map(item => [item.start,item.end]); render(currentPayload); } } catch (error) { console.warn("作息读取失败",error); } }
async function load() { const button = document.querySelector("#refresh"); button.disabled = true; try { const response = await fetch("/api/empty-rooms",{cache:"no-store"}); const payload = await response.json(); if (!response.ok) throw new Error(payload.error || "读取失败"); render(payload); await loadPeriods(); } catch (error) { document.querySelector("#status-dot").className = "error"; document.querySelector("#status").textContent = "读取失败"; document.querySelector("#updated-at").textContent = error.message; setMessage("暂时无法读取数据，请稍后重试"); } finally { button.disabled = false; } }
document.querySelector("#refresh").onclick = load; load(); window.setInterval(load,300000);
