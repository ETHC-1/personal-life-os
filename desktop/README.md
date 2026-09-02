# Windows 桌面端

这是 `personal-life-os` 的 Tauri 2 桌面客户端。桌面端拥有独立的 `desktop/ui` 界面，通过本地 API 复用 Python 业务服务，因此不会复制日历、待办和课程的领域逻辑。

## 当前能力

- 启动本机 Python Web 服务（仅监听 `127.0.0.1`）；
- 以独立 Windows 窗口打开个人生活 OS；
- 关闭窗口时自动停止本次启动的 Python 服务；
- 通过环境变量指定 Python 解释器和各类本地数据文件；
- Tauri capabilities 只保留窗口基础权限，不开放 Shell、文件系统或任意命令执行给 WebView。

## 开发运行

在项目根目录执行：

```powershell
$env:PYTHONPATH = "D:\personal-life-os\src"
$env:PERSONAL_LIFE_OS_PYTHON = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
cargo install tauri-cli --version "^2"
Set-Location desktop\src-tauri
cargo tauri dev
```

如果已安装 editable package，也可以不设置 `PYTHONPATH`。默认 Python 路径遵循项目 Windows 开发约定；生产打包时应改为随安装包提供的受控 Python 运行时或独立后端服务。

## 构建边界

当前目录提供可构建的 Tauri 工程骨架，适合作为 Windows MVP。桌面图标已放在 `src-tauri/icons/`；正式发布前仍需决定 Python 运行时的分发方式（内置运行时、独立服务或远程 API），再补充签名、自动更新、托盘和通知能力。
