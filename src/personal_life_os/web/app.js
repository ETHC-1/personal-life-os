const state = { courses: [], calendarEvents: [], todos: [], selectedDate: new Date(), classroomUsageByDate: {}, roomViewDate: null, classroomBuildings: [], selectedBuildingCode: null, classroomRooms: [] };
let editingCalendarId = null;
let editingTodoId = null;
const weekdayNames = ["一", "二", "三", "四", "五", "六", "日"];
const defaultRoomPeriods = ["08:00-08:40", "08:50-09:30", "09:50-10:30", "10:40-11:20", "11:20-12:00", "14:30-15:10", "15:20-16:00", "16:10-16:50", "17:00-17:40", "18:30-19:10", "19:20-20:00", "20:10-20:50", "21:00-21:40"];
let roomPeriods = defaultRoomPeriods;
const eastTeachingRooms = Array.from({ length: 19 }, (_, index) => `东教学楼${index + 1}教室`);
const dateFormatter = new Intl.DateTimeFormat("zh-CN", { month: "long", day: "numeric", weekday: "short" });

async function invokeDesktop(command) {
  const invoke = window.__TAURI_INTERNALS__?.invoke;
  if (!invoke) return;
  try { await invoke(command); } catch (error) { console.warn("窗口控制失败", error); }
}

document.querySelectorAll("[data-window-action]").forEach(button => {
  button.addEventListener("click", () => {
    const action = button.dataset.windowAction;
    if (action === "minimize") invokeDesktop("minimize_window");
    if (action === "maximize") invokeDesktop("toggle_maximize");
    if (action === "close") invokeDesktop("close_window");
  });
});
document.querySelectorAll(".coming-soon").forEach(item => item.addEventListener("click", event => event.preventDefault()));

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));
}
function mondayOf(date) { const result = new Date(date); const day = (result.getDay() + 6) % 7; result.setDate(result.getDate() - day); result.setHours(0, 0, 0, 0); return result; }
function isoDate(date) { return date.toISOString().slice(0, 10); }
function localIsoDate(date) { const offset = date.getTimezoneOffset() * 60000; return new Date(date.getTime() - offset).toISOString().slice(0, 10); }
function localDateTimeValue(date) { const offset = date.getTimezoneOffset() * 60000; return new Date(date.getTime() - offset).toISOString().slice(0, 16); }
function localDateTimeIso(value) { const date = new Date(value); if (Number.isNaN(date.getTime())) throw new Error("请输入有效的日期时间"); const offset = -date.getTimezoneOffset(); const sign = offset >= 0 ? "+" : "-"; const hours = String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0"); const minutes = String(Math.abs(offset) % 60).padStart(2, "0"); return `${value}:00${sign}${hours}:${minutes}`; }
function sessionsFor(date) { const weekday = ((date.getDay() + 6) % 7) + 1; return state.courses.flatMap(course => course.sessions.filter(session => session.weekday === weekday).map(session => ({ course, session }))); }
function ensureWechatLoginField() {
  if (document.querySelector("#hebmu-login-url")) return;
  const panel = document.querySelector("#hebmu-panel"); const anchor = document.querySelector("#hebmu-semester").closest(".form-row");
  const label = document.createElement("label"); label.className = "field-label"; label.innerHTML = '微信授权链接（可选）<input id="hebmu-login-url" type="url" placeholder="https://jwweb.hebmu.edu.cn/app/?code=...&state=...">';
  panel.insertBefore(label, anchor);
}

function renderWeek() {
  const monday = mondayOf(state.selectedDate); const strip = document.querySelector("#week-strip"); const grid = document.querySelector("#schedule-grid");
  strip.innerHTML = ""; grid.innerHTML = "";
  for (let i = 0; i < 7; i += 1) {
    const date = new Date(monday); date.setDate(monday.getDate() + i); const active = isoDate(date) === isoDate(state.selectedDate);
    const item = document.createElement("div"); item.className = `week-day ${active ? "active" : ""}`; item.innerHTML = `${weekdayNames[i]}<strong>${date.getDate()}</strong>`; item.onclick = () => { state.selectedDate = date; renderWeek(); };
    strip.appendChild(item);
    const column = document.createElement("div"); column.className = `day-column ${isoDate(date) === isoDate(new Date()) ? "today" : ""}`;
    const sessions = sessionsFor(date).sort((a, b) => a.session.start_period - b.session.start_period);
    column.innerHTML = sessions.length ? sessions.map(({ course, session }) => `<div class="course-chip"><b>${escapeHtml(course.name)}</b><small>${session.start_time?.slice(0, 5) ?? `第${session.start_period}-${session.end_period}节`}</small><small>${escapeHtml(session.location || "待定教室")}</small></div>`).join("") : `<div class="empty-day">暂无课程</div>`;
    grid.appendChild(column);
  }
  document.querySelector("#today-label").textContent = dateFormatter.format(state.selectedDate);
  const selected = sessionsFor(state.selectedDate).sort((a, b) => a.session.start_period - b.session.start_period)[0];
  document.querySelector("#next-course-title").textContent = selected ? selected.course.name : "今天没有课程安排";
  document.querySelector("#next-course-meta").textContent = selected ? `${selected.session.start_time?.slice(0, 5) || `第${selected.session.start_period}节`} · ${selected.session.location || "待定教室"}` : "享受一段自由时间吧";
}
function renderCourses() {
  document.querySelector("#course-count").textContent = state.courses.length;
  document.querySelector("#semester-pill").textContent = state.courses[0]?.semester || "未设置学期";
  document.querySelector("#course-list").innerHTML = state.courses.length ? state.courses.map(course => `<div class="course-row"><div class="course-color"></div><div><b>${escapeHtml(course.name)}</b><small>${escapeHtml(course.teacher || "未填写教师")} · ${course.credits ?? "—"} 学分</small></div></div>`).join("") : `<div class="empty-state">还没有课程，先导入一份课表吧</div>`;
}
function renderReminders() {
  const sessions = sessionsFor(state.selectedDate).slice(0, 3); const count = document.querySelector("#reminder-count"); if (count) count.textContent = sessions.length;
  document.querySelector("#reminder-list").innerHTML = sessions.length ? sessions.map(({ course, session }) => `<div class="reminder"><div class="reminder-time">${session.start_time?.slice(0, 5) || `第${session.start_period}节`}</div><div><b>${escapeHtml(course.name)}</b><small>${escapeHtml(session.location || "待定教室")} · 提前 30 分钟提醒</small></div></div>`).join("") : `<div class="empty-state">今天暂无提醒</div>`;
}
function renderCalendar() {
  const target = document.querySelector("#calendar-list");
  if (!state.calendarEvents.length) { target.innerHTML = `<div class="empty-state">未来 7 天暂无日程，点击“添加日程”开始安排。</div>`; return; }
  target.innerHTML = state.calendarEvents.map(event => { const start = new Date(event.starts_at); const end = new Date(event.ends_at); return `<div class="calendar-event"><div class="calendar-event-date"><b>${start.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}</b><small>${start.toLocaleDateString("zh-CN", { weekday: "short" })}</small></div><div class="calendar-event-main"><b>${escapeHtml(event.title)}</b><span>${start.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })} – ${end.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}${event.location ? ` · ${escapeHtml(event.location)}` : ""}</span>${event.description ? `<small>${escapeHtml(event.description)}</small>` : ""}</div><button class="icon-button calendar-delete" data-event-id="${escapeHtml(event.id)}" title="删除日程">×</button></div>`; }).join("");
  document.querySelectorAll(".calendar-delete").forEach(button => button.onclick = () => deleteCalendarEvent(button.dataset.eventId));
}
async function loadCalendar() {
  try { const start = new Date(); start.setHours(0, 0, 0, 0); const end = new Date(start); end.setDate(end.getDate() + 7); const query = new URLSearchParams({ start: localDateTimeIso(localDateTimeValue(start)), end: localDateTimeIso(localDateTimeValue(end)) }); const response = await fetch(`/api/calendar?${query}`); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "日历读取失败"); state.calendarEvents = payload.events || []; renderCalendar(); } catch (reason) { document.querySelector("#calendar-list").innerHTML = `<div class="empty-state">无法读取日历：${escapeHtml(reason.message)}</div>`; }
}
function setCalendarStatus(message, isError = false) { const element = document.querySelector("#calendar-status"); element.textContent = message; element.hidden = false; element.className = `import-status ${isError ? "error" : ""}`; }
function openCalendarModal() { const start = new Date(); start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0); const end = new Date(start); end.setHours(end.getHours() + 1); document.querySelector("#calendar-event-title").value = ""; document.querySelector("#calendar-event-start").value = localDateTimeValue(start); document.querySelector("#calendar-event-end").value = localDateTimeValue(end); document.querySelector("#calendar-event-location").value = ""; document.querySelector("#calendar-event-description").value = ""; document.querySelector("#calendar-status").hidden = true; document.querySelector("#calendar-modal").hidden = false; document.querySelector("#calendar-event-title").focus(); }
async function createCalendarEvent() { const button = document.querySelector("#calendar-submit"); const title = document.querySelector("#calendar-event-title").value.trim(); if (!title) return setCalendarStatus("请填写日程标题", true); try { button.disabled = true; const response = await fetch("/api/calendar", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, starts_at: localDateTimeIso(document.querySelector("#calendar-event-start").value), ends_at: localDateTimeIso(document.querySelector("#calendar-event-end").value), location: document.querySelector("#calendar-event-location").value.trim() || null, description: document.querySelector("#calendar-event-description").value.trim() }) }); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "保存日程失败"); document.querySelector("#calendar-modal").hidden = true; await loadCalendar(); } catch (reason) { setCalendarStatus(reason.message, true); } finally { button.disabled = false; } }
async function deleteCalendarEvent(eventId) { if (!window.confirm("确定删除这条日程吗？")) return; const response = await fetch(`/api/calendar?id=${encodeURIComponent(eventId)}`, { method: "DELETE" }); if (response.ok) await loadCalendar(); else { const payload = await responseJson(response); setCalendarStatus(payload.error || "删除日程失败", true); } }
function renderTodos() { const target = document.querySelector("#todo-list"); if (!state.todos.length) { target.innerHTML = `<div class="empty-state">还没有待办，点击“添加待办”开始整理。</div>`; return; } const labels = { low: "低", medium: "中", high: "高" }; target.innerHTML = state.todos.map(item => `<div class="todo-item ${item.completed ? "completed" : ""}"><button class="todo-check" data-todo-id="${escapeHtml(item.id)}" aria-label="${item.completed ? "恢复" : "完成"}待办">${item.completed ? "✓" : ""}</button><div class="todo-main"><b>${escapeHtml(item.title)}</b><span><i class="priority-${item.priority}">${labels[item.priority] || "中"}</i>${item.due_at ? ` · 截止 ${new Date(item.due_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}` : ""}</span>${item.description ? `<small>${escapeHtml(item.description)}</small>` : ""}</div><button class="icon-button todo-delete" data-todo-id="${escapeHtml(item.id)}" title="删除待办">×</button></div>`).join(""); document.querySelectorAll(".todo-check").forEach(button => button.onclick = () => toggleTodo(button.dataset.todoId)); document.querySelectorAll(".todo-delete").forEach(button => button.onclick = () => deleteTodo(button.dataset.todoId)); }
async function loadTodos() { try { const response = await fetch("/api/todos"); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "待办读取失败"); state.todos = payload.todos || []; renderTodos(); } catch (reason) { document.querySelector("#todo-list").innerHTML = `<div class="empty-state">无法读取待办：${escapeHtml(reason.message)}</div>`; } }
function renderOverview(payload) { const systemTime = new Date(payload.system_time.now); document.querySelector("#today-label").textContent = systemTime.toLocaleDateString("zh-CN", { month: "long", day: "numeric", weekday: "short" }); document.querySelector("#system-clock").textContent = `当前时间 ${systemTime.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`; document.querySelector("#todo-count").textContent = payload.todo_open_count; const next = payload.calendar_events[0]; const course = sessionsFor(new Date()).sort((a, b) => a.session.start_period - b.session.start_period)[0]; if (next) { const start = new Date(next.starts_at); document.querySelector("#next-course-title").textContent = next.title; document.querySelector("#next-course-meta").textContent = `${start.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}${next.location ? ` · ${escapeHtml(next.location)}` : ""}`; } else if (course) { document.querySelector("#next-course-title").textContent = course.course.name; document.querySelector("#next-course-meta").textContent = `${course.session.start_time?.slice(0, 5) || `第${course.session.start_period}节`} · 课程安排`; } else { document.querySelector("#next-course-title").textContent = "今天暂无安排"; document.querySelector("#next-course-meta").textContent = payload.todos_due_today.length ? `还有 ${payload.todos_due_today.length} 项待办今天到期` : "享受一段自由时间吧"; } }
async function loadOverview() { try { const response = await fetch("/api/overview"); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "今日总览读取失败"); renderOverview(payload); } catch (reason) { document.querySelector("#system-clock").textContent = "时间读取失败"; console.warn(reason); } }
function openTodoModal() { document.querySelector("#todo-item-title").value = ""; document.querySelector("#todo-item-priority").value = "medium"; document.querySelector("#todo-item-due").value = ""; document.querySelector("#todo-item-description").value = ""; document.querySelector("#todo-status").hidden = true; document.querySelector("#todo-modal").hidden = false; document.querySelector("#todo-item-title").focus(); }
async function createTodo() { const button = document.querySelector("#todo-submit"); const title = document.querySelector("#todo-item-title").value.trim(); if (!title) { document.querySelector("#todo-status").textContent = "请填写待办内容"; document.querySelector("#todo-status").hidden = false; return; } try { button.disabled = true; const due = document.querySelector("#todo-item-due").value; const response = await fetch("/api/todos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, priority: document.querySelector("#todo-item-priority").value, due_at: due ? localDateTimeIso(due) : null, description: document.querySelector("#todo-item-description").value.trim() }) }); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "保存待办失败"); document.querySelector("#todo-modal").hidden = true; await loadTodos(); } catch (reason) { const status = document.querySelector("#todo-status"); status.textContent = reason.message; status.hidden = false; status.className = "import-status error"; } finally { button.disabled = false; } }
async function toggleTodo(todoId) { const item = state.todos.find(todo => todo.id === todoId); if (!item) return; const response = await fetch(`/api/todos?id=${encodeURIComponent(todoId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ completed: !item.completed }) }); if (response.ok) await loadTodos(); }
async function deleteTodo(todoId) { if (!window.confirm("确定删除这条待办吗？")) return; const response = await fetch(`/api/todos?id=${encodeURIComponent(todoId)}`, { method: "DELETE" }); if (response.ok) await loadTodos(); }
function renderClassroomTimeline() {
  const target = document.querySelector("#room-timeline");
  const activeBuilding = state.classroomBuildings.find(item => item.building_code === state.selectedBuildingCode) || state.classroomBuildings[0];
  const dates = Object.keys(state.classroomUsageByDate); if (!dates.length) { target.innerHTML = `<div class="empty-state">完成一次校园网抓取后，这里会显示教室的时间进度。</div>`; document.querySelector("#room-date-buttons").innerHTML = ""; return; }
  if (!state.roomViewDate || !state.classroomUsageByDate[state.roomViewDate]) state.roomViewDate = dates[0];
  document.querySelector("#room-date-buttons").innerHTML = dates.map((value, index) => `<button class="room-date-button ${value === state.roomViewDate ? "active" : ""}" data-date="${value}">${index === 0 ? "今天" : "明天"}<small>${value.slice(5)}</small></button>`).join("");
  document.querySelectorAll(".room-date-button").forEach(button => button.onclick = async () => { state.roomViewDate = button.dataset.date; await loadRoomPeriods(state.roomViewDate); renderClassroomTimeline(); });
  const normalizeRoom = value => String(value || "").replace(/\s+/g, "");
  const usage = new Map((state.classroomUsageByDate[state.roomViewDate].usage || []).map(item => [normalizeRoom(item.room), new Set(item.occupied_periods || [])]));
  const isEast = (activeBuilding?.building || "东教学楼").includes("东教学楼");
  const rooms = isEast ? eastTeachingRooms : (state.classroomUsageByDate[state.roomViewDate]?.rooms?.length ? state.classroomUsageByDate[state.roomViewDate].rooms : state.classroomRooms.length ? state.classroomRooms : [...usage.keys()]);
  const timelineStart = 7 * 60; const timelineEnd = 23 * 60; const timelineMinutes = timelineEnd - timelineStart;
  const toMinutes = value => { const [hour, minute] = value.split(":").map(Number); return hour * 60 + minute; };
  const ranges = roomPeriods.map(period => period.split("-").map(toMinutes));
  const position = minute => `${Math.max(0, Math.min(100, ((minute - timelineStart) / timelineMinutes) * 100))}%`;
  const afternoonStart = ranges[5]?.[0] || 14 * 60;
  const afternoonEnd = ranges[8]?.[1] || 17 * 60 + 40;
  const keyTimes = [8 * 60, 12 * 60, afternoonStart, afternoonEnd, 18 * 60 + 30, 21 * 60 + 40].filter((value, index, values) => values.indexOf(value) === index);
  const timeScale = keyTimes.map(minute => `<span style="left:${position(minute)}">${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}</span>`).join("");
  const boundaryClass = index => index === 0 ? "period-line-deep" : ([1, 3, 6, 8, 10, 12].includes(index) ? "period-line-light" : "period-line-deep");
  const periodLines = ranges.map(([start], index) => `<i class="period-line ${boundaryClass(index)}" style="left:${position(start)}"></i>`).join("") + `<i class="period-line lunch-break-line" style="left:${position(ranges[4]?.[1] || 12 * 60)}"></i>`;
  const periodLabels = ranges.map(([start, end], index) => `<span class="period-label ${index % 2 === 1 ? "period-label-alt" : ""}" style="left:${position((start + end) / 2)}">${index + 1}</span>`).join("");
  const roomRows = rooms.map((room, index) => {
    const occupied = [...(usage.get(normalizeRoom(room)) || new Set())]
      .filter(period => period >= 1 && period <= ranges.length)
      .sort((a, b) => a - b);
    const groups = occupied.reduce((result, period) => {
      const last = result[result.length - 1];
      if (last && period === last[last.length - 1] + 1 && period !== 6) last.push(period);
      else result.push([period]);
      return result;
    }, []);
    const bars = groups.map(group => {
      const [start] = ranges[group[0] - 1];
      const [, end] = ranges[group[group.length - 1] - 1];
      const label = group.length === 1
        ? roomPeriods[group[0] - 1]
        : `${roomPeriods[group[0] - 1].split("-")[0]}-${roomPeriods[group[group.length - 1] - 1].split("-")[1]}`;
      const width = Number(position(end).replace("%", "")) - Number(position(start).replace("%", ""));
      const long = end - start > 120;
      return `<b class="occupied-bar ${long ? "occupied-bar-long" : ""}" style="left:${position(start)};width:${width}%" title="${room} · ${label} · 有课" aria-label="${room}，${label}，有课"><span class="bar-label">${label}</span></b>`;
    }).join("");
    const displayRoom = isEast ? `${index + 1}教室` : room;
    return `<div class="room-timeline-row"><div class="room-name"><span>${escapeHtml(displayRoom)}</span></div><div class="room-track"><i class="availability-bar"></i>${periodLines}${bars}</div></div>`;
  });
  const floorGroups = [];
  roomRows.forEach((row, index) => {
    const floor = isEast ? (index < 4 ? 1 : Math.floor((index - 4) / 5) + 2) : "";
    let group = floorGroups[floorGroups.length - 1];
    if (!group || group.floor !== floor) { group = { floor, rows: [] }; floorGroups.push(group); }
    group.rows.push(row);
  });
  const groupedRows = floorGroups.map(group => `<div class="room-floor-group"><div class="floor-label">${group.floor ? `${group.floor}层` : ""}</div><div class="floor-rows">${group.rows.join("")}</div></div>`).join("");
  target.innerHTML = `<div class="room-timeline-grid"><div class="room-timeline-header"><div class="room-name building-heading"><span>建筑状态</span><strong>${escapeHtml(activeBuilding?.building || "东教学楼")}</strong></div><div class="time-track">${timeScale}</div></div>${groupedRows}<div class="room-period-footer"><div class="room-name">课时</div><div class="time-track">${periodLabels}</div></div></div>`;
}
async function loadCourses() {
  const error = document.querySelector("#error-banner"); error.hidden = true;
  try {
    const response = await fetch("/api/courses"); if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json(); state.courses = payload.courses || [];
    document.querySelector("#demo-banner").hidden = !payload.demo; document.querySelector("#store-path").textContent = payload.store_path;
    renderCourses(); renderWeek(); renderReminders();
  } catch (reason) { error.textContent = `无法读取课表：${reason.message}。请确认后端服务正在运行。`; error.hidden = false; }
}
async function loadClassroomUsage() {
  try {
    const response = await fetch("/api/empty-rooms", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    state.classroomBuildings = payload.buildings || [];
    if (state.classroomBuildings.length) {
      state.selectedBuildingCode = state.selectedBuildingCode || state.classroomBuildings[0].building_code;
      const selector = document.querySelector("#room-building-select");
      if (selector) { selector.innerHTML = state.classroomBuildings.map(item => `<option value="${escapeHtml(item.building_code)}">${escapeHtml(item.building)}</option>`).join(""); selector.value = state.selectedBuildingCode; selector.onchange = () => { state.selectedBuildingCode = selector.value; const selected = state.classroomBuildings.find(item => item.building_code === state.selectedBuildingCode); state.classroomUsageByDate = selected?.classroom_usage_by_date || {}; state.classroomRooms = [...new Set(Object.values(state.classroomUsageByDate).flatMap(day => [...(day.rooms || []), ...(day.usage || []).map(item => item.room)]))]; state.roomViewDate = Object.keys(state.classroomUsageByDate)[0]; loadRoomPeriods(state.roomViewDate).then(renderClassroomTimeline); }; }
      const selected = state.classroomBuildings.find(item => item.building_code === state.selectedBuildingCode) || state.classroomBuildings[0]; state.classroomUsageByDate = selected.classroom_usage_by_date || {}; state.classroomRooms = [...new Set(Object.values(state.classroomUsageByDate).flatMap(day => [...(day.rooms || []), ...(day.usage || []).map(item => item.room)]))]; state.roomViewDate = Object.keys(state.classroomUsageByDate)[0];
    } else if (Object.keys(payload.classroom_usage_by_date || {}).length) {
      state.classroomUsageByDate = payload.classroom_usage_by_date;
      state.roomViewDate = Object.keys(state.classroomUsageByDate)[0];
    }
    await loadRoomPeriods(state.roomViewDate);
    renderClassroomTimeline();
  } catch (reason) {
    console.warn("无法读取本地空教室桥接数据", reason);
  }
}
async function loadRoomPeriods(queryDate) {
  if (!queryDate) return;
  try {
    const response = await fetch(`/api/periods?date=${encodeURIComponent(queryDate)}`, { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "作息读取失败");
    roomPeriods = (payload.periods || []).map(item => `${item.start}-${item.end}`);
  } catch (reason) { roomPeriods = defaultRoomPeriods; console.warn(reason); }
}
function setImportStatus(message, isError = false) { const element = document.querySelector("#import-status"); element.textContent = message; element.hidden = false; element.className = `import-status ${isError ? "error" : ""}`; }
function setImportBusy(button, busy) { button.disabled = busy; button.textContent = busy ? "导入中，请稍候…" : button.dataset.label; }
async function responseJson(response) { const text = await response.text(); try { return JSON.parse(text); } catch { throw new Error(response.status === 404 ? "导入接口不存在，请重启 Web 服务后刷新页面" : `服务器返回了非 JSON 错误（HTTP ${response.status}）`); } }
async function importFile() {
  const file = document.querySelector("#schedule-file").files[0]; if (!file) return setImportStatus("请先选择课表文件", true);
  const button = document.querySelector("#file-import-submit"); const form = new FormData(); form.append("file", file); setImportBusy(button, true); setImportStatus("正在校验并写入课表…");
  try { const response = await fetch("/api/import/file", { method: "POST", headers: { "X-Semester": document.querySelector("#file-semester").value.trim() }, body: form }); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "导入失败"); setImportStatus(payload.message); await loadCourses(); } catch (error) { setImportStatus(error.message, true); } finally { setImportBusy(button, false); }
}
async function importHebmu() {
  const button = document.querySelector("#hebmu-import-submit"); setImportBusy(button, true); setImportStatus("正在打开校园网登录页。完成一次登录后会连续抓取课程和教室数据…");
  const today = document.querySelector("#room-query-today").value; const tomorrow = document.querySelector("#room-query-tomorrow").value;
  const payload = { semester: document.querySelector("#hebmu-semester").value.trim(), week: document.querySelector("#hebmu-week").value.trim(), start: document.querySelector("#hebmu-start").value, end: document.querySelector("#hebmu-end").value, login_url: document.querySelector("#hebmu-login-url").value.trim(), building_code: "103966187", building_name: "中山校区.东教学楼", query_dates: [today, tomorrow] };
  try { const response = await fetch("/api/import/hebmu-all", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); const result = await responseJson(response); if (!response.ok) throw new Error(result.error || "抓取失败"); state.classroomUsageByDate = result.classroom_usage_by_date || {}; state.roomViewDate = today; renderClassroomTimeline(); const totalOccupied = Object.values(state.classroomUsageByDate).reduce((sum, item) => sum + (item.usage || []).reduce((count, room) => count + (room.occupied_periods || []).length, 0), 0); const apiMessages = Object.values(result.classroom_api_status || {}).map(item => item.msg).filter(Boolean); setImportStatus(totalOccupied ? result.message : `${result.message}，接口返回：${apiMessages.join("；") || "未返回教室列表"}`); await loadCourses(); } catch (error) { setImportStatus(error.message, true); } finally { setImportBusy(button, false); }
}
function openCalendarModal(eventId = null) { editingCalendarId = eventId; const event = state.calendarEvents.find(item => item.id === eventId); const start = event ? new Date(event.starts_at) : new Date(); if (!event) start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0); const end = event ? new Date(event.ends_at) : new Date(start.getTime() + 3600000); document.querySelector("#calendar-title").textContent = event ? "编辑日程" : "新建日程"; document.querySelector("#calendar-submit").textContent = event ? "保存修改" : "保存日程"; document.querySelector("#calendar-event-title").value = event?.title || ""; document.querySelector("#calendar-event-start").value = localDateTimeValue(start); document.querySelector("#calendar-event-end").value = localDateTimeValue(end); document.querySelector("#calendar-event-location").value = event?.location || ""; document.querySelector("#calendar-event-description").value = event?.description || ""; document.querySelector("#calendar-status").hidden = true; document.querySelector("#calendar-modal").hidden = false; document.querySelector("#calendar-event-title").focus(); }
async function createCalendarEvent() { const button = document.querySelector("#calendar-submit"); const title = document.querySelector("#calendar-event-title").value.trim(); if (!title) return setCalendarStatus("请填写日程标题", true); try { button.disabled = true; const response = await fetch(editingCalendarId ? `/api/calendar?id=${encodeURIComponent(editingCalendarId)}` : "/api/calendar", { method: editingCalendarId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, starts_at: localDateTimeIso(document.querySelector("#calendar-event-start").value), ends_at: localDateTimeIso(document.querySelector("#calendar-event-end").value), location: document.querySelector("#calendar-event-location").value.trim() || null, description: document.querySelector("#calendar-event-description").value.trim() }) }); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "保存日程失败"); document.querySelector("#calendar-modal").hidden = true; await loadCalendar(); await loadOverview(); } catch (reason) { setCalendarStatus(reason.message, true); } finally { button.disabled = false; } }
function openTodoModal(todoId = null) { editingTodoId = todoId; const item = state.todos.find(todo => todo.id === todoId); document.querySelector("#todo-title").textContent = item ? "编辑待办" : "新建待办"; document.querySelector("#todo-submit").textContent = item ? "保存修改" : "保存待办"; document.querySelector("#todo-item-title").value = item?.title || ""; document.querySelector("#todo-item-priority").value = item?.priority || "medium"; document.querySelector("#todo-item-due").value = item?.due_at ? localDateTimeValue(new Date(item.due_at)) : ""; document.querySelector("#todo-item-description").value = item?.description || ""; document.querySelector("#todo-status").hidden = true; document.querySelector("#todo-modal").hidden = false; document.querySelector("#todo-item-title").focus(); }
async function createTodo() { const button = document.querySelector("#todo-submit"); const title = document.querySelector("#todo-item-title").value.trim(); if (!title) { document.querySelector("#todo-status").textContent = "请填写待办内容"; document.querySelector("#todo-status").hidden = false; return; } try { button.disabled = true; const due = document.querySelector("#todo-item-due").value; const response = await fetch(editingTodoId ? `/api/todos?id=${encodeURIComponent(editingTodoId)}` : "/api/todos", { method: editingTodoId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title, priority: document.querySelector("#todo-item-priority").value, due_at: due ? localDateTimeIso(due) : null, description: document.querySelector("#todo-item-description").value.trim() }) }); const payload = await responseJson(response); if (!response.ok) throw new Error(payload.error || "保存待办失败"); document.querySelector("#todo-modal").hidden = true; await loadTodos(); await loadOverview(); } catch (reason) { const status = document.querySelector("#todo-status"); status.textContent = reason.message; status.hidden = false; status.className = "import-status error"; } finally { button.disabled = false; } }
function decorateEditActions() { document.querySelectorAll(".calendar-delete").forEach(button => { if (!button.parentElement.querySelector(".calendar-edit")) { const edit = document.createElement("button"); edit.className = "icon-button calendar-edit"; edit.title = "编辑日程"; edit.textContent = "✎"; edit.onclick = () => openCalendarModal(button.dataset.eventId); button.before(edit); } }); document.querySelectorAll(".todo-delete").forEach(button => { if (!button.parentElement.querySelector(".todo-edit")) { const edit = document.createElement("button"); edit.className = "icon-button todo-edit"; edit.title = "编辑待办"; edit.textContent = "✎"; edit.onclick = () => openTodoModal(button.dataset.todoId); button.before(edit); } }); }
new MutationObserver(decorateEditActions).observe(document.querySelector("#calendar-list"), { childList: true }); new MutationObserver(decorateEditActions).observe(document.querySelector("#todo-list"), { childList: true });
function ensureCalendarOptions() { if (document.querySelector("#calendar-recurrence")) return; const anchor = document.querySelector("#calendar-event-location").closest(".field-label"); const row = document.createElement("div"); row.className = "form-row"; row.innerHTML = '<label class="field-label">重复<select id="calendar-recurrence"><option value="">不重复</option><option value="daily">每天</option><option value="weekly">每周</option><option value="weekdays">工作日</option></select></label><label class="field-label">重复至（重复时必填）<input id="calendar-recurrence-until" type="date"></label>'; anchor.before(row); const reminder = document.createElement("label"); reminder.className = "field-label"; reminder.innerHTML = '提醒（提前分钟，可选）<input id="calendar-reminder" type="number" min="0" max="10080" placeholder="例如 30">'; anchor.before(reminder); }
function openCalendarModal(eventId = null) { ensureCalendarOptions(); editingCalendarId = eventId; const event = state.calendarEvents.find(item => item.id === eventId); const start = event ? new Date(event.starts_at) : new Date(); if (!event) start.setMinutes(Math.ceil(start.getMinutes() / 30) * 30, 0, 0); const end = event ? new Date(event.ends_at) : new Date(start.getTime() + 3600000); document.querySelector("#calendar-title").textContent = event ? "编辑日程" : "新建日程"; document.querySelector("#calendar-submit").textContent = event ? "保存修改" : "保存日程"; document.querySelector("#calendar-event-title").value = event?.title || ""; document.querySelector("#calendar-event-start").value = localDateTimeValue(start); document.querySelector("#calendar-event-end").value = localDateTimeValue(end); document.querySelector("#calendar-event-location").value = event?.location || ""; document.querySelector("#calendar-event-description").value = event?.description || ""; document.querySelector("#calendar-recurrence").value = event?.recurrence_rule || ""; document.querySelector("#calendar-recurrence-until").value = event?.recurrence_until || ""; document.querySelector("#calendar-reminder").value = event?.reminder_minutes ?? ""; document.querySelector("#calendar-status").hidden = true; document.querySelector("#calendar-modal").hidden = false; document.querySelector("#calendar-event-title").focus(); }
async function createCalendarEvent() { const button = document.querySelector("#calendar-submit"); const title = document.querySelector("#calendar-event-title").value.trim(); const recurrence = document.querySelector("#calendar-recurrence").value; if (!title) return setCalendarStatus("请填写日程标题", true); if (recurrence && !document.querySelector("#calendar-recurrence-until").value) return setCalendarStatus("重复日程必须填写结束日期", true); try { button.disabled = true; const reminder = document.querySelector("#calendar-reminder").value; const payload = { title, starts_at: localDateTimeIso(document.querySelector("#calendar-event-start").value), ends_at: localDateTimeIso(document.querySelector("#calendar-event-end").value), location: document.querySelector("#calendar-event-location").value.trim() || null, description: document.querySelector("#calendar-event-description").value.trim(), recurrence_rule: recurrence || null, recurrence_until: recurrence ? document.querySelector("#calendar-recurrence-until").value : null, reminder_minutes: reminder === "" ? null : Number(reminder) }; const response = await fetch(editingCalendarId ? `/api/calendar?id=${encodeURIComponent(editingCalendarId)}` : "/api/calendar", { method: editingCalendarId ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }); const result = await responseJson(response); if (!response.ok) throw new Error(result.error || "保存日程失败"); document.querySelector("#calendar-modal").hidden = true; await loadCalendar(); await loadOverview(); } catch (reason) { setCalendarStatus(reason.message, true); } finally { button.disabled = false; } }
document.querySelector("#import-button").onclick = () => { ensureWechatLoginField(); const today = new Date(); const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1); document.querySelector("#hebmu-start").value = localIsoDate(today); document.querySelector("#hebmu-end").value = localIsoDate(new Date(today.getFullYear(), 11, 31)); document.querySelector("#room-query-today").value = localIsoDate(today); document.querySelector("#room-query-tomorrow").value = localIsoDate(tomorrow); document.querySelector("#import-modal").hidden = false; document.querySelector("#import-status").hidden = true; };
document.querySelector("#close-import").onclick = () => { document.querySelector("#import-modal").hidden = true; };
document.querySelector("#schedule-file").onchange = (event) => { document.querySelector("#file-label").textContent = event.target.files[0]?.name || "选择课表文件"; };
document.querySelector("#file-import-submit").dataset.label = "开始导入";
document.querySelector("#hebmu-import-submit").dataset.label = "登录一次并抓取两类信息";
document.querySelectorAll(".tab").forEach((tab) => tab.onclick = () => { document.querySelectorAll(".tab").forEach(item => item.classList.remove("active")); tab.classList.add("active"); document.querySelector("#file-panel").hidden = tab.dataset.tab !== "file"; document.querySelector("#hebmu-panel").hidden = tab.dataset.tab !== "hebmu"; document.querySelector("#import-status").hidden = true; });
document.querySelector("#file-import-submit").onclick = importFile;
document.querySelector("#hebmu-import-submit").onclick = importHebmu;
document.querySelector("#refresh-button").onclick = async () => { await loadCourses(); await loadClassroomUsage(); await loadCalendar(); await loadTodos(); await loadOverview(); };
document.querySelector("#calendar-button").onclick = openCalendarModal;
document.querySelector("#calendar-add-button").onclick = openCalendarModal;
document.querySelector("#close-calendar").onclick = () => { document.querySelector("#calendar-modal").hidden = true; };
document.querySelector("#calendar-submit").onclick = createCalendarEvent;
document.querySelector("#todo-add-button").onclick = openTodoModal;
document.querySelector("#close-todo").onclick = () => { document.querySelector("#todo-modal").hidden = true; };
document.querySelector("#todo-submit").onclick = createTodo;
document.querySelector("#today-button").onclick = () => { state.selectedDate = new Date(); renderWeek(); renderReminders(); };
renderClassroomTimeline();
loadCourses();
loadClassroomUsage();
loadCalendar();
loadTodos();
loadOverview();
window.setInterval(loadOverview, 30000);
