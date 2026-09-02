# Ubuntu 云服务器部署准备

- 日期：2026-09-01
- 状态：已完成本地部署配置，待服务器执行

## 背景

用户已购买 Ubuntu 云服务器，需要让现有 Web 前端和直接空教室 API 抓取在后台运行。

## 决策

- 使用 Python 虚拟环境安装项目。
- 使用 systemd 管理 Web 服务。
- 使用 systemd timer 在每天 06:00—21:00 每小时执行空教室抓取。
- 课表、空教室快照和教务临时凭证均放在项目目录之外。
- Web 服务仅监听本机 8000 端口，公网访问交给 Nginx 和 HTTPS。

## 产物

- `deploy/ubuntu/README.md`
- `deploy/ubuntu/personal-life-os-web.service`
- `deploy/ubuntu/personal-life-os-empty-room.service`
- `deploy/ubuntu/personal-life-os-empty-room.timer`

## 后续

- 用户将项目复制到服务器并执行部署命令。
- 首次验证教务凭证和定时抓取成功后，再配置域名、HTTPS 和 OpenAI Agent 服务。
- README 已补充 LLM/Agent 的目标能力、工具边界和分阶段实施计划。
