const defaultPeriods = ["08:00-08:40", "08:50-09:30", "09:50-10:30", "10:40-11:20", "11:20-12:00", "14:30-15:10", "15:20-16:00", "16:10-16:50", "17:00-17:40", "18:30-19:10", "19:20-20:00", "20:10-20:50", "21:00-21:40"];
let periods = defaultPeriods;
const fallbackRooms = Array.from({ length: 19 }, (_, index) => `东教学楼${index + 1}教室`);
let selectedDate = new URLSearchParams(location.search).get("date");
let selectedBuildingCode = new URLSearchParams(location.search).get("building");
let currentPayload = null;

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[char]));
}

function render(payload) {
  currentPayload = payload;
  const buildings = payload.buildings || [];
  const activeBuilding = buildings.find(item => item.building_code === selectedBuildingCode) || buildings[0];
  if (activeBuilding) selectedBuildingCode = activeBuilding.building_code;
  const byDate = activeBuilding?.classroom_usage_by_date || payload.classroom_usage_by_date || {};
  const dates = Object.keys(byDate).sort();
  if (!dates.includes(selectedDate)) selectedDate = dates[0] || null;
  document.querySelector("#building").textContent = activeBuilding?.building || payload.building || "教学楼";
  const buildingSelect = document.querySelector("#building-select");
  if (buildingSelect) { buildingSelect.innerHTML = buildings.map(item => `<option value="${escapeHtml(item.building_code)}">${escapeHtml(item.building)}</option>`).join(""); buildingSelect.value = selectedBuildingCode || ""; buildingSelect.onchange = () => { selectedBuildingCode = buildingSelect.value; history.replaceState(null, "", `?building=${encodeURIComponent(selectedBuildingCode)}`); render(currentPayload); }; }
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
  const startMinutes = 7 * 60; const endMinutes = 23 * 60;
  const toMinutes = value => { const [hour, minute] = value.split(":").map(Number); return hour * 60 + minute; };
  const ranges = periods.map(period => period.split("-").map(toMinutes));
  const position = minute => `${Math.max(0, Math.min(100, ((minute - startMinutes) / (endMinutes - startMinutes)) * 100))}%`;
  const afternoonStart = ranges[5]?.[0] || 14 * 60;
  const afternoonEnd = ranges[8]?.[1] || 17 * 60 + 40;
  const keyTimes = [8 * 60, 12 * 60, afternoonStart, afternoonEnd, 18 * 60 + 30, 21 * 60 + 40].filter((value, index, values) => values.indexOf(value) === index);
  const timeScale = keyTimes.map(minute => `<span style="left:${position(minute)}">${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}</span>`).join("");
  const boundaryClass = index => index === 0 ? "period-line-deep" : ([1, 3, 6, 8, 10, 12].includes(index) ? "period-line-light" : "period-line-deep");
  const periodLines = ranges.map(([start], index) => `<i class="period-line ${boundaryClass(index)}" style="left:${position(start)}"></i>`).join("") + `<i class="period-line lunch-break-line" style="left:${position(ranges[4]?.[1] || 12 * 60)}"></i>`;
  const periodLabels = ranges.map(([start, end], index) => `<span class="period-label ${index % 2 === 1 ? "period-label-alt" : ""}" style="left:${position((start + end) / 2)}">${index + 1}</span>`).join("");
  const rows = rooms.map((room, index) => {
    const occupied = [...(usage.get(room) || new Set())].filter(period => period >= 1 && period <= ranges.length).sort((a, b) => a - b);
    const groups = occupied.reduce((result, period) => { const last = result[result.length - 1]; if (last && period === last[last.length - 1] + 1 && period !== 6) last.push(period); else result.push([period]); return result; }, []);
    const bars = groups.map(group => { const [start] = ranges[group[0] - 1]; const [, end] = ranges[group[group.length - 1] - 1]; const label = group.length === 1 ? periods[group[0] - 1] : `${periods[group[0] - 1].split("-")[0]}-${periods[group[group.length - 1] - 1].split("-")[1]}`; const width = Number(position(end).replace("%", "")) - Number(position(start).replace("%", "")); return `<b class="occupied-bar" style="left:${position(start)};width:${width}%" title="${escapeHtml(room)} · ${label} · 有课"><span>${label}</span></b>`; }).join("");
    return `<div class="room-timeline-row"><div class="room-name"><span>${index + 1}教室</span></div><div class="room-track">${periodLines}${bars}</div></div>`;
  });
  const floorGroups = [];
  rows.forEach((row, index) => {
    const floor = index < 4 ? 1 : Math.floor((index - 4) / 5) + 2;
    let group = floorGroups[floorGroups.length - 1];
    if (!group || group.floor !== floor) { group = { floor, rows: [] }; floorGroups.push(group); }
    group.rows.push(row);
  });
  const groupedRows = floorGroups.map(group => `<div class="room-floor-group"><div class="floor-label">${group.floor}层</div><div class="floor-rows">${group.rows.join("")}</div></div>`).join("");
  document.querySelector("#grid").innerHTML = `<div class="room-timeline-grid"><div class="room-timeline-header"><div class="room-name building-heading"><span>建筑状态</span><strong>东教学楼</strong></div><div class="time-track">${timeScale}</div></div>${groupedRows}<div class="room-period-footer"><div class="room-name">课时</div><div class="time-track">${periodLabels}</div></div></div>`;
}

async function load() {
  const button = document.querySelector("#refresh"); button.disabled = true;
  try {
    const response = await fetch("/api/empty-rooms", {cache: "no-store"});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "读取失败");
    render(payload);
    if (selectedDate) {
      const periodsResponse = await fetch(`/api/periods?date=${encodeURIComponent(selectedDate)}`, {cache: "no-store"});
      const periodsPayload = await periodsResponse.json();
      if (!periodsResponse.ok) throw new Error(periodsPayload.error || "作息读取失败");
      periods = (periodsPayload.periods || []).map(item => `${item.start}-${item.end}`);
      render(payload);
    }
  } catch (error) {
    document.querySelector("#status-dot").className = "error";
    document.querySelector("#status").textContent = "读取失败";
    document.querySelector("#updated-at").textContent = error.message;
  } finally { button.disabled = false; }
}

document.querySelector("#refresh").onclick = load;
load();
window.setInterval(load, 300000);
