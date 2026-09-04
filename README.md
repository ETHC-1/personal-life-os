# personal-life-os
一个可以帮你打理日常生活的个人生活操作系统，用于管理日程、待办、课程、提醒以及 AI 助手交互。

## 项目愿景

打造一个跨 Web、移动端和桌面端的个人行程管家，支持：

- 日历与日程规划
- 待办事项和提醒
- 自动同步学习官网课表
- AI 文本与语音助手
- 移动端通知，并通过手机通知同步到小米手环
- 多端数据同步

## 当前状态

项目处于个人日程与待办 MVP 阶段，已完成日历、待办和今日总览的第一版闭环。详细进度见 [项目工作进度](docs/work-progress.md)。

## 开发原则

- API Key 和账号凭证只通过环境变量配置
- 不提交个人隐私数据、课表账号或 `.env` 文件
- 涉及日程修改的 AI 操作必须经过后端校验
- 每完成一个可验证功能就创建一次 Git 提交

## 技术路线

技术栈选择与分阶段实施计划见 [技术栈与路线](docs/technical-roadmap.md)。

## 课程导入

课程功能将不同来源统一写入最终课表文件。默认建议把个人数据存放在项目外，例如：

```python
from personal_life_os.courses import FinalScheduleStore, HebmuBrowserImporter, import_schedule_file

store = FinalScheduleStore(r"D:\\personal-life-os-data\\final_schedule.json")

# 手动导入 JSON / HTML / CSV：
store.replace(import_schedule_file("my_schedule.json", semester="202601"))

# 河北医科大学：打开可见浏览器，由用户手动完成校园网登录：
# courses = HebmuBrowserImporter().fetch_courses(
#     semester="202601", start=date(2026, 9, 1), end=date(2027, 1, 31)
# )
# store.replace(courses)
```

浏览器抓取需要可选依赖 `playwright`，不会接收或保存账号、密码、验证码和 Cookie。最终课表文件属于个人数据，应放在项目目录外；项目内的本地存档文件也已加入 `.gitignore`。

命令行使用：

```text
# 导入手动准备的 JSON / HTML
course-import file my_schedule.json --semester 202601

# 打开可见浏览器；用户手动完成校园网登录后自动抓取
course-import hebmu --semester 202601 --start 2026-09-01 --end 2027-01-31
```

可通过 `PERSONAL_LIFE_OS_SCHEDULE_PATH` 指定最终课表文件路径。未指定时，默认写入当前用户目录下的 `.personal-life-os/final_schedule.json`，不写入项目仓库。

## 基础 Web 前端

项目现在包含一个零依赖的基础 Web 前端，用于预览今日概览、周课表、课程库和提醒。没有本地课表文件时会自动使用演示数据：

```text
python -m personal_life_os.web
```

然后打开 <http://127.0.0.1:8000>。也可以使用安装后的命令：

```text
personal-life-os-web --port 8000
```

前端通过 `/api/courses` 读取 `PERSONAL_LIFE_OS_SCHEDULE_PATH` 指向的 JSON 文件；导入课表后刷新页面即可查看真实课程。

页面右上角的“导入课表”支持上传 JSON/HTML/HTM 文件。选择“校园网登录”后点击“打开校园网并抓取”，服务会启动可见浏览器，用户手动完成校园网登录，完成后自动抓取并保存课表。浏览器导入需要安装可选依赖：

### 日历与系统时间后端

日历事件保存在 `PERSONAL_LIFE_OS_CALENDAR_PATH` 指定的 JSON 文件中，未指定时使用当前用户目录下的 `.personal-life-os/calendar.json`。事件时间必须是带时区的 ISO 8601 格式：

```text
GET  /api/time?timezone=Asia/Shanghai
GET  /api/calendar?start=2026-09-01T00:00:00+08:00&end=2026-09-02T00:00:00+08:00
POST /api/calendar
     {"title":"项目评审","starts_at":"2026-09-01T09:00:00+08:00","ends_at":"2026-09-01T10:00:00+08:00"}
DELETE /api/calendar?id=<事件 id>
PUT  /api/calendar?id=<事件 id>
GET  /api/reminders
```

新增事件会检查时间冲突；`personal-life-os-web --calendar-store <路径>` 可直接指定日历文件。
日程还支持每天、每周和工作日重复，以及按提前分钟数计算提醒；提醒结果可通过 `GET /api/reminders` 查询。

待办事项保存在 `PERSONAL_LIFE_OS_TODO_PATH` 指定的 JSON 文件中，默认使用当前用户目录下的 `.personal-life-os/todos.json`。首页“我的待办”支持新增、编辑、设置低/中/高优先级、填写截止时间、完成/恢复和删除。

首页今日总览通过 `GET /api/overview` 聚合系统时间、今日日程和今日到期待办，时间默认按 `Asia/Shanghai` 计算，也可传入 `timezone` 参数。

```text
python -m pip install -e ".[browser]"
python -m playwright install chromium
```

空教室接口目前先以独立命令验证抓取链路，不修改课表文件：

```text
course-import empty-room --building-code "[楼栋代码]" --building-name "[校区].[楼栋名称]" --date 2026-09-01
```

该命令输出指定楼栋和日期在接口响应中出现过使用记录的教室；完整“空教室”结果还需要补齐教室总清单并进行占用差集计算，之后再合并到 Web 前端。

如果微信沙箱只能在微信内登录，可在本地使用 Fiddler 采集桥，不把微信 Cookie/token 发到云端。先启动本地桥：

```text
course-import empty-room-bridge --output "D:\\personal-life-os-data\\empty-rooms.json"
```

打开 `http://127.0.0.1:8765/` 可查看桥接程序是否运行、最近一次是否收到数据及非敏感解析诊断；桥接兼容 UTF-8/GB18030 编码；`/ingest` 仅接受 Fiddler 的 POST，不能直接用浏览器打开测试。

Web 前端会在启动和点击右上角刷新时读取桥接快照。若桥接输出到 `D:\personal-life-os-data\empty-rooms.json`，请用同一路径启动 Web：

```powershell
$env:PYTHONPATH = "D:\personal-life-os\src"
& "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" -m personal_life_os.web --empty-room-store "D:\personal-life-os-data\empty-rooms.json"
```

也可以设置 `PERSONAL_LIFE_OS_EMPTY_ROOM_PATH`，这样不必每次传命令行参数。桥接器收到新响应后，刷新 `http://127.0.0.1:8000/` 即可看到对应日期的东教学楼 1—19 教室时间视图。

然后将 `tools/fiddler_classroom_bridge.js` 中的辅助函数和 `OnBeforeResponse` 逻辑合并到 Fiddler 的 `Rules > Customize Rules`。Fiddler 发往本机前只保留教室、日期和占用课时；`--remote-url` 可选，只有脱敏结果会被转发到云端。

## LLM 助手与 Agent 规划

项目计划接入 OpenAI API，让用户可以使用自然语言管理课表、日记、提醒和空教室信息。推荐采用“LLM 理解意图，后端工具执行操作”的边界：模型不直接拥有任意文件读写权限，只能调用后端定义并校验过的工具。

### 适合由普通脚本完成的功能

- 读取、保存和备份课表 JSON；
- 修改课程时间、地点和周次，并检查时间冲突；
- 创建和读取日记；
- 查询今日/明日课表和空教室；
- 生成提醒、每日定时任务和固定格式统计。

### 适合由 LLM/Agent 完成的功能

- 将“下周三的生理学改到东教学楼 10 教室”解析成结构化修改请求；
- 根据上下文判断用户是在新增、修改还是查询；
- 调用多个后端工具完成每日总结和第二天准备；
- 对模糊日期、课程和危险操作向用户请求确认。

建议的受控工具包括 `list_schedule`、`update_course`、`create_diary`、`get_empty_rooms` 和 `create_reminder`。所有写操作都必须经过参数校验、时间冲突检查、原子写入和审计记录；删除、覆盖或批量修改必须先确认。

推荐实施顺序：先接入只读查询，再接入日记写入，然后加入需要确认的课表修改，最后增加每日总结、通知和多步骤 Agent。OpenAI API Key 只能保存在后端环境变量中，不能写入前端代码、课表文件或 Git。

## Ubuntu 云服务器部署

Ubuntu 部署文件位于 [`deploy/ubuntu/`](deploy/ubuntu/)，包含 Web 服务和空教室定时抓取的 systemd 配置。推荐使用 Ubuntu 24.04 LTS、2 核 4GB、40GB 以上 SSD，并将个人数据存放在 `/var/lib/personal-life-os`，将教务临时凭证存放在服务器权限受限的环境文件中。

详细步骤见 [Ubuntu 部署说明](deploy/ubuntu/README.md)。当前直接空教室抓取不需要微信浏览器或 Fiddler；如果教务会话过期，需要重新获取临时 Cookie/token，不应把它们写入仓库或日志。

服务器启动后，可在 `/empty-rooms.html` 使用适合手机和平板的独立空教室页面，或让其他设备直接读取 `/api/empty-rooms` JSON 接口。公网部署必须在 Nginx 或云网关启用 HTTPS 和身份验证。

`GET /api/periods?date=YYYY-MM-DD` 返回当天 13 个课时的实际时间。每年 5 月 1 日至 7 月 5 日，第 6—9 节从 14:00 开始；其余日期第 6—9 节从 14:30 开始，第 10 节固定 18:30。

网页端“校园网登录”面板现在可以填写楼栋信息，点击“登录一次并抓取两类信息”，在一次手动登录后同时读取课程和教室使用数据。命令行也可使用：

```text
course-import hebmu-all --semester 202601 --start 2026-09-01 --end 2027-01-31 --building-code "[楼栋代码]" --building-name "[校区].[楼栋名称]" --date 2026-09-01
```

### 独立空教室云端轮询

可先用直接 API 探针验证会话是否能脱离微信页面工作。探针只读取环境变量中的临时凭证，只输出 HTTP 状态和响应结构，不输出 Cookie、token 或原始课程数据：

```powershell
$env:PYTHONPATH = "D:\\personal-life-os\\src"
$env:HEBMU_COOKIE = "从当前已授权请求复制的 Cookie；仅保存在当前 PowerShell 会话"
$env:HEBMU_TOKEN = "从 classroom 请求头复制的 token 值；仅保存在当前 PowerShell 会话"
$env:HEBMU_REFERER = "从 classroom 请求头复制的 Referer 值；仅保存在当前 PowerShell 会话"
& "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" -m personal_life_os.courses.cli empty-room-direct-probe --date 2026-09-01
```

如果 `classroom_endpoint.http_status` 为 200 且 `msg` 不是“请先登录”，说明可以继续开发无浏览器轮询；如果仍提示登录，说明该 API 依赖微信 WebView 会话，应继续使用持久化浏览器或 Fiddler 桥。测试结束后执行 `Remove-Item Env:HEBMU_COOKIE, Env:HEBMU_TOKEN, Env:HEBMU_REFERER -ErrorAction SilentlyContinue`。

验证成功后，可以直接抓取今天和明天并写入脱敏快照：

```powershell
& "C:\\Users\\Administrator\\AppData\\Local\\Programs\\Python\\Python312\\python.exe" -m personal_life_os.courses.cli empty-room-direct --output "D:\\personal-life-os-data\\empty-rooms-direct.json" --days-ahead 1
```

该命令不打开浏览器、不启动 Fiddler，只使用当前 PowerShell 会话中的临时凭证。

课表抓取仍使用上面的 `hebmu`/`hebmu-all` 流程；云端空教室抓取使用独立 worker，不会修改课表文件。首次在有图形界面的云服务器会话中手动完成微信授权，后续复用持久化浏览器 Profile：

```text
course-import empty-room-poll --user-data-dir "D:\\personal-life-os-data\\wechat-profile" --output "D:\\personal-life-os-data\\empty-rooms.json" --once
course-import empty-room-poll --user-data-dir "D:\\personal-life-os-data\\wechat-profile" --output "D:\\personal-life-os-data\\empty-rooms.json" --headless
```

默认每天 07:00 和 14:00 各执行一次，并查询今天和明天。也可以通过环境变量 `HEBMU_WECHAT_LOGIN_URL` 临时提供微信授权回调链接；授权链接、Cookie 和 token 不应写入仓库或日志。云服务器必须能够运行持久化 Chromium；若学校强制微信 WebView，普通云端 Chromium 仍可能无法完成首次授权，此时应使用带远程桌面的浏览器环境或在本地授权后同步结果。
