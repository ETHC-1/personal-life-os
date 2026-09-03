# Ubuntu 部署

以下配置适用于 Ubuntu 24.04 LTS、2 核 4GB 服务器。假定项目部署到 `/opt/personal-life-os`，个人数据放到 `/var/lib/personal-life-os`。

## 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
sudo useradd --system --home /var/lib/personal-life-os --shell /usr/sbin/nologin personal-life-os || true
sudo mkdir -p /opt/personal-life-os /var/lib/personal-life-os
sudo chown -R personal-life-os:personal-life-os /opt/personal-life-os /var/lib/personal-life-os
```

将项目文件复制到 `/opt/personal-life-os` 后执行：

```bash
cd /opt/personal-life-os
sudo -u personal-life-os python3 -m venv .venv
sudo -u personal-life-os .venv/bin/python -m pip install --upgrade pip
sudo -u personal-life-os .venv/bin/pip install .
```

## 2. 配置凭证

只在服务器上创建，不要提交到 Git：

```bash
sudo install -o personal-life-os -g personal-life-os -m 600 /dev/null /etc/personal-life-os-empty-room.env
sudoedit /etc/personal-life-os-empty-room.env
```

内容格式如下，填写真实值时不要把文件发给别人：

```text
HEBMU_COOKIE=...
HEBMU_TOKEN=...
HEBMU_REFERER=https://jwweb.hebmu.edu.cn/app/#/work
```

## 3. 安装后台服务

```bash
sudo cp deploy/ubuntu/personal-life-os-web.service /etc/systemd/system/
sudo cp deploy/ubuntu/personal-life-os-empty-room.service /etc/systemd/system/
sudo cp deploy/ubuntu/personal-life-os-empty-room.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now personal-life-os-web.service
sudo systemctl enable --now personal-life-os-empty-room.timer
```

查看状态：

```bash
systemctl status personal-life-os-web.service
systemctl status personal-life-os-empty-room.timer
journalctl -u personal-life-os-empty-room.service -n 50 --no-pager
```

定时器每天 06:00—21:00 执行一次，每次抓取今天和明天。凭证过期时服务会失败，但不会输出 Cookie/token；更新环境文件后执行：

```bash
sudo systemctl restart personal-life-os-empty-room.timer
sudo systemctl start personal-life-os-empty-room.service
```

## 4. 网站访问

Web 服务仅监听 `127.0.0.1:8000`。独立的设备查询页是 `/empty-rooms.html`，数据接口是 `/api/empty-rooms`。查询页每 5 分钟自动刷新，也可以用 `?date=YYYY-MM-DD` 指定日期。

先安装项目内置的 Nginx 反向代理模板：

```bash
sudo cp deploy/ubuntu/nginx-personal-life-os.conf /etc/nginx/sites-available/personal-life-os
sudo ln -s /etc/nginx/sites-available/personal-life-os /etc/nginx/sites-enabled/personal-life-os
sudo nginx -t
sudo systemctl reload nginx
```

配置域名后，应使用 Certbot 或云平台入口启用 HTTPS。如果服务可从公网访问，还应在 Nginx 启用身份验证，避免教室与个人日程接口被公开暴露。模板中已预留 `auth_basic` 配置。

## 安全要求

- 不要把 `/etc/personal-life-os-empty-room.env` 复制到项目目录。
- 不要把 Cookie、token、API Key 写入日志或提交到 Git。
- 首次部署先用 `systemctl start personal-life-os-empty-room.service` 验证抓取，再开放公网访问。
- 若教务认证失效，需要重新获取临时凭证并替换服务器环境文件。
