# personal-life-os 技术栈与路线

## 1. 架构决策

根据项目新增的目标——功能强大的前端、多端互通、云服务器部署和受控的系统级能力——推荐采用混合架构：

| 层 | 推荐技术 | 主要职责 |
| --- | --- | --- |
| Web 前端 | Next.js + TypeScript | 日历、待办、课程、管理后台和完整 Web 体验 |
| 移动端 | Expo + React Native | 移动通知、快速录入和移动端查看 |
| 桌面端 | Tauri 2 + Rust | 桌面应用、托盘、系统通知和受控本地能力 |
| 云端核心 | Rust + Axum + Tokio | API、认证、权限、同步、实时连接和业务核心 |
| 专项服务 | Python 3.12 | 教务系统适配、网页解析、AI 编排和语音处理 |
| 数据层 | PostgreSQL + Redis | 持久化、同步游标、任务队列和实时事件 |

这里的“系统高级权限”只应存在于桌面端的 Rust 本地代理中。Web 页面、移动端和云端 API 不应直接拥有用户设备的管理员权限；需要提权时由独立 helper 进程执行最小化、白名单化的操作，并要求用户明确授权。

Rust 的 Axum 适合构建模块化 HTTP 服务，并可复用 Tokio、Tower 的超时、追踪、压缩和授权中间件生态。[Axum 官方文档](https://docs.rs/axum/latest/axum/) Tauri 的 capabilities 机制可以按窗口和 WebView 限制桌面前端可调用的系统能力。[Tauri capabilities 文档](https://tauri.app/security/capabilities/) Web 端采用 Next.js App Router 和 TypeScript，以获得成熟的路由、数据获取和服务端/客户端组件能力。[Next.js App Router 文档](https://nextjs.org/docs/app)

## 2. 总体策略

项目采用“模块化单体优先、适配器隔离外部系统、按需扩展”的路线：

- Rust 后端承载跨端共享的核心领域逻辑；Python 只承载教务、AI 和语音等 Python 生态优势明显的专项能力。
- AI、教务系统、通知渠道都通过明确的服务接口接入，避免业务代码绑定第三方实现。
- 初期仍按模块化单体部署；Python 专项服务通过内部 HTTP 或 gRPC 调用，不提前拆分成大量微服务。
- 所有时间使用带时区的 ISO 8601；数据库统一保存 UTC，展示时转换为用户时区。

## 3. 建议技术栈

### 云端后端

- Rust stable：云端核心服务，编译为单一可部署二进制。
- Axum + Tokio + Tower：HTTP API、异步运行时和中间件。
- Serde：请求、响应、配置和事件的序列化与反序列化。
- SQLx + sqlx-cli：类型安全的 PostgreSQL 访问和迁移。
- `tracing`：结构化日志、请求链路和敏感字段脱敏。
- OpenAPI：作为跨端契约，生成 TypeScript、Rust 和 Python 客户端模型。
- PostgreSQL：生产数据存储；开发阶段可用 SQLite 做快速测试。
- `zoneinfo`：时区处理；保留 `tzdata` 作为 Windows 和容器环境的依赖。

### Python 专项服务

- Python 3.12 + FastAPI：承载教务系统适配器、网页解析、AI 工具编排和语音处理。
- Pydantic v2：校验专项服务输入和外部页面解析结果。
- HTTPX：教务系统和模型 API 请求，统一配置超时、重试和日志脱敏。
- 专项服务不得直接写核心数据库；通过 Rust API 或内部受保护接口完成业务变更。

### 前端与客户端

- Web：Next.js + TypeScript，使用响应式界面覆盖桌面和移动浏览器。
- UI：Tailwind CSS；日历视图优先选择成熟组件，避免自研日期布局。
- 移动端：Expo + React Native，在 Web 核心流程稳定后开发。
- 桌面端：Tauri，作为后续阶段的轻量桌面壳；不在 MVP 阶段单独维护一套业务逻辑。

### 数据、任务与通知

- 首选 PostgreSQL `timestamptz` 保存事件时间，使用唯一约束和事务保证同步幂等。
- Redis：保存短期任务状态、分布式锁、发布订阅和同步通知；不作为核心事实数据源。
- 后台任务使用 Rust worker + Redis 队列；Python 专项任务由受控 worker 执行。
- 通知抽象为 `NotificationChannel`，第一阶段支持 Web 推送或邮件中的一种，随后接入 FCM/APNs。
- 小米手环同步优先依赖手机系统通知链路，不直接耦合未经确认的厂商私有 API。

### AI、认证与安全

- AI 仅调用后端定义的工具，例如 `create_event`、`update_task`、`list_schedule`。
- 工具参数先经 Pydantic 校验，再进行权限、时区、重复规则和冲突检查。
- AI 不直接访问数据库；所有写操作记录审计日志，并支持用户确认高风险变更。
- 密钥、课表账号、Cookie 和个人数据只从环境变量或本地未提交配置读取。
- 认证采用短期 access token + 可撤销 refresh token；权限按用户、设备和资源范围校验。
- 云服务器进程使用非 root 用户、最小文件权限和独立数据库账号；“服务器管理员权限”不暴露给 API。

### 工程质量

- Rust：`cargo test`、`cargo fmt --check`、`cargo clippy`。
- Python：pytest、Ruff；必要时加入 mypy 做类型检查。
- TypeScript：ESLint、`tsc --noEmit`；
- HTTPX 测试客户端：验证 API 错误处理和输入校验。
- Playwright：Web 关键流程的端到端测试。
- Docker Compose：本地启动 PostgreSQL（后续再加入 Redis）。
- GitHub Actions：执行 lint、测试和构建；每个可验证功能独立提交。

## 4. 分阶段路线

### 阶段 0：工程底座

目标：让项目具备稳定的开发和验证入口。

- 建立 Rust workspace：`server`、`worker`、`desktop-agent` 和共享协议 crate。
- 保留现有 Python 包，整理为独立的专项服务。
- 建立 OpenAPI 契约和 TypeScript/Python 客户端生成流程。
- 建立配置管理、结构化日志、统一错误响应和健康检查接口。
- 增加配置管理、结构化日志、统一错误响应和健康检查接口。
- 固化 Python 3.12、`tzdata`、测试命令和环境变量示例。

验收：新环境可以构建 Rust 服务、安装 Python 专项服务依赖、运行全量测试，并启动健康检查接口。

### 阶段 1：个人日程与待办 MVP

目标：先完成不依赖外部平台的核心价值。

- 日程、待办、提醒、标签和完成状态。
- 重复规则、时区转换、提醒时间计算和基础冲突检测。
- PostgreSQL 持久化、迁移脚本和 Rust REST API。
- Web 端实现今日视图、周视图、待办列表和基础编辑。

验收：用户可以创建、修改、完成和查询带时区的日程与待办，刷新后数据不丢失。

### 阶段 2：教务系统接入

目标：在不污染核心领域模型的前提下同步课程。

- 将现有 `CourseSource` 扩展为登录、抓取、解析和同步适配器。
- 每所学校独立实现适配器，处理登录、验证码、二次认证和页面差异。
- 对课程使用来源、外部 ID、学期和内容哈希做幂等同步。
- 同步前后进行字段校验、时区归一化和冲突检测；失败时保留可诊断日志但不记录密码。

验收：演示数据和至少一个真实学校适配器都能重复同步，重复执行不会产生重复课程。

### 阶段 3：通知与多端同步

目标：让提醒真正触达用户，并支持多端使用。

- 增加可靠的后台任务和任务状态记录。
- 接入一种移动推送渠道，再扩展到 Web Push 和邮件。
- 设计设备注册、通知去重、失败重试和用户免打扰时段。
- 增加账户、设备和同步游标；使用幂等键、版本号和事件游标明确离线修改的冲突策略。
- 使用 WebSocket 或 SSE 推送跨端变更，客户端仍以服务端数据为准。

验收：提醒按用户时区发送，重复任务不会重复通知，失败任务可重试和追踪。

### 阶段 4：AI 文本与语音助手

目标：用受控工具提升录入和查询效率。

- 先实现“查询日程、生成建议、草拟变更”，再开放写入。
- 所有写入工具执行后端校验；涉及删除、批量变更或冲突时要求用户确认。
- 保存会话与工具调用摘要，不保存不必要的敏感原文。
- 语音先采用移动端录音上传和文本转写，稳定后再评估实时语音。

验收：AI 无法绕过权限和业务校验；同一请求重复执行不会造成重复日程。

### 阶段 5：桌面端与体验优化

目标：在核心功能稳定后扩展使用场景。

- 用 Tauri 2 封装 Web 核心功能，增加系统托盘、快捷入口和受限本地代理。
- 将需要系统权限的能力拆到 Rust helper，使用 capabilities 和白名单控制，不让 WebView 直接执行任意命令。
- 用 Expo 打磨移动端通知、课程查看和快速录入。
- 根据真实使用数据优化查询、缓存、可观测性和备份恢复。

## 5. 推荐目录演进

```text
crates/
  server/              # Axum API、认证、权限和业务用例
  worker/              # Rust 后台任务和同步调度
  domain/              # 日程、待办、课程、通知领域模型
  protocol/            # OpenAPI 相关类型和事件协议
  desktop-agent/       # Tauri/Rust 本地能力代理
services/
  academic-python/     # 教务系统适配器和解析
  ai-python/           # AI 工具编排和语音处理
tests/
  rust/
  python/
  contract/
web/                   # Next.js 前端（阶段 1 引入）
mobile/                # Expo 客户端（阶段 3 引入）
desktop/               # Tauri 壳（阶段 5 引入）
```

## 6. 当前下一步

1. 建立 Rust workspace 和最小 Axum 健康检查服务。
2. 定义 OpenAPI、认证、设备和同步协议。
3. 将日程、待办、重复规则和冲突检测迁移到 Rust domain crate，并补齐测试。
4. 选择 PostgreSQL，实现第一版迁移、同步游标和权限校验。
5. 创建 Next.js Web 端，再接入 Tauri 桌面壳和受限本地代理。
6. 教务系统真实接入前，先确认学校地址、登录方式、验证码/二次认证要求和账号授权边界。

## 7. 暂不引入的技术

暂不使用微服务、Kubernetes、复杂事件总线和重量级工作流平台。这些技术只有在多用户规模、任务吞吐量或部署复杂度确实需要时再评估。
