#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{env, process::{Child, Command, Stdio}, sync::Mutex, time::Duration};
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

const HOST: &str = "127.0.0.1";
const PORT: &str = "8765";
const DEFAULT_PYTHON: &str = r"C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe";

struct Backend(Mutex<Option<Child>>);

fn start_backend(app: &tauri::AppHandle) -> Result<Child, String> {
    let python = env::var("PERSONAL_LIFE_OS_PYTHON").unwrap_or_else(|_| DEFAULT_PYTHON.to_string());
    let project_root = app.path().resource_dir().map_err(|error| error.to_string())?;
    let source_root = env::var("PERSONAL_LIFE_OS_SOURCE_ROOT")
        .map(std::path::PathBuf::from)
        .unwrap_or(project_root);
    let mut command = Command::new(python);
    command.current_dir(&source_root)
        .args(["-m", "personal_life_os.web", "--host", HOST, "--port", PORT])
        .env("PYTHONPATH", source_root.join("src"))
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    command.spawn().map_err(|error| format!("无法启动本地服务：{error}"))
}

fn setup_error(message: &str) -> std::io::Error {
    std::io::Error::other(message.to_string())
}

#[tauri::command]
fn minimize_window(window: WebviewWindow) -> Result<(), String> {
    window.minimize().map_err(|error| error.to_string())
}

#[tauri::command]
fn toggle_maximize(window: WebviewWindow) -> Result<(), String> {
    if window.is_maximized().map_err(|error| error.to_string())? {
        window.unmaximize().map_err(|error| error.to_string())
    } else {
        window.maximize().map_err(|error| error.to_string())
    }
}

#[tauri::command]
fn close_window(window: WebviewWindow) -> Result<(), String> {
    window.close().map_err(|error| error.to_string())
}

fn main() {
    tauri::Builder::default()
        .manage(Backend(Mutex::new(None)))
        .setup(|app| {
            let child = start_backend(&app.handle())?;
            std::thread::sleep(Duration::from_millis(250));
            *app.state::<Backend>().0.lock().map_err(|_| setup_error("无法锁定服务状态"))? = Some(child);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
            .title("个人生活 OS").inner_size(1420.0, 920.0).min_inner_size(1080.0, 700.0)
            .resizable(true).decorations(false).transparent(true).build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![minimize_window, toggle_maximize, close_window])
        .build(tauri::generate_context!())
        .expect("error while building personal-life-os desktop")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Ok(mut backend) = app.state::<Backend>().0.lock() {
                    if let Some(mut child) = backend.take() { let _ = child.kill(); let _ = child.wait(); }
                }
            }
        });
}
