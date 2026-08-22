#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全交互守护智能体 - 控制面板 (极简稳定版)
只包含服务启停和日志，无额外功能
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import threading
import time
import subprocess
import os
import sys
import shutil
import socket
import ctypes

# ============================================================
# 路径兼容：源码运行用脚本目录；PyInstaller 打包后（sys.frozen）
# 用 exe 所在目录，避免 __file__ 指向临时解压目录
# ============================================================
def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_script_dir()

# 输出重定向
if sys.stdout and hasattr(sys.stdout, 'fileno'):
    try:
        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1)
        sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1)
    except:
        log_file = os.path.join(SCRIPT_DIR, "gui.log")
        sys.stdout = open(log_file, 'a', buffering=1)
        sys.stderr = sys.stdout
else:
    log_file = os.path.join(SCRIPT_DIR, "gui.log")
    sys.stdout = open(log_file, 'a', buffering=1)
    sys.stderr = sys.stdout

def debug_print(msg):
    print(f"[DEBUG] {msg}")

# 单实例
def check_single_instance():
    if sys.platform != "win32":
        return True
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\SecurityGuardAgentGUI_Mutex")
        if ctypes.windll.kernel32.GetLastError() == 183:
            ctypes.windll.user32.MessageBoxW(0, "已在运行中！", "提示", 0x40)
            return False
        global _mutex_handle
        _mutex_handle = handle
        return True
    except:
        return True

if not check_single_instance():
    sys.exit(0)

IS_WINDOWS = sys.platform == "win32"
API_BASE = "http://localhost:8080/admin/api"
ADMIN_TOKEN_FILE = os.path.join(SCRIPT_DIR, "admin_token.txt")

def get_admin_token():
    try:
        with open(ADMIN_TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
            if token:
                return token
    except Exception:
        pass
    return None

def admin_headers():
    return {"X-Admin-Token": get_admin_token() or ""}

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return False
        except OSError:
            return True

def get_available_command():
    exe_path = os.path.join(SCRIPT_DIR, "guard.exe")
    if os.path.exists(exe_path):
        return [exe_path], None
    go_path = shutil.which("go")
    if go_path:
        main_go = os.path.join(SCRIPT_DIR, "main.go")
        if os.path.exists(main_go):
            return [go_path, "run", main_go], None
        else:
            return None, f"未找到 main.go"
    return None, "未找到 Go 环境"

def kill_process_on_port(port):
    try:
        cmd = ['powershell', '-Command',
               f'Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | '
               f'ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}']
        subprocess.run(cmd, capture_output=True, timeout=10)
        time.sleep(1)
        if not is_port_in_use(port):
            return True, "释放成功"
        return False, "释放失败"
    except Exception as e:
        return False, f"异常: {e}"

class GuardConfigGUI:
    def __init__(self, root):
        global app
        app = self
        self.root = root
        self.root.title("🛡️ 守护智能体 - 极简稳定版")
        self.root.geometry("650x600")
        self.root.configure(bg='#f5f5f5')
        self.process = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._create_widgets()
        self._update_status_once()
        debug_print("GUI 初始化完成")

    def on_closing(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(1)
            if self.process.poll() is None:
                self.process.kill()
        self.root.destroy()

    def _create_widgets(self):
        # 标题
        tk.Label(self.root, text="🛡️ 安全交互守护智能体", font=("Microsoft YaHei", 16, "bold"),
                 bg='#f5f5f5').pack(pady=(20,5))
        tk.Label(self.root, text="极简稳定版 (无额外组件)", font=("Microsoft YaHei", 10),
                 bg='#f5f5f5', fg='#999').pack(pady=(0,20))

        # 控制按钮
        control_frame = tk.Frame(self.root, bg='white')
        control_frame.pack(padx=30, pady=5, fill='x')
        btn_frame = tk.Frame(control_frame, bg='white')
        btn_frame.pack(pady=10)

        self.start_btn = tk.Button(btn_frame, text="▶ 启动服务", command=self.start_service,
                                   font=("Microsoft YaHei", 11), bg='#4CAF50', fg='white', width=12)
        self.start_btn.pack(side='left', padx=5)

        self.stop_btn = tk.Button(btn_frame, text="⏹ 停止服务", command=self.stop_service,
                                  font=("Microsoft YaHei", 11), bg='#f44336', fg='white', width=12, state='disabled')
        self.stop_btn.pack(side='left', padx=5)

        self.restart_btn = tk.Button(btn_frame, text="🔄 重启", command=self.restart_service,
                                     font=("Microsoft YaHei", 11), bg='#FF9800', fg='white', width=12)
        self.restart_btn.pack(side='left', padx=5)

        self.status_label = tk.Label(control_frame, text="状态: 未启动", font=("Microsoft YaHei", 12, "bold"),
                                     bg='white', fg='red')
        self.status_label.pack(pady=5)

        # 日志区
        log_frame = tk.Frame(self.root, bg='white')
        log_frame.pack(padx=30, pady=10, fill='both', expand=True)
        tk.Label(log_frame, text="📋 服务日志", font=("Microsoft YaHei", 11, "bold"), bg='white')\
            .pack(anchor='w', padx=10, pady=5)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, font=("Consolas", 9),
                                                  bg='#1e1e1e', fg='#d4d4d4')
        self.log_text.pack(padx=10, pady=5, fill='both', expand=True)

        # 状态栏
        status_frame = tk.Frame(self.root, bg='#f5f5f5')
        status_frame.pack(fill='x', padx=30, pady=5)
        self.status_msg = tk.Label(status_frame, text="🔄 准备就绪", font=("Microsoft YaHei", 10),
                                   bg='#f5f5f5', fg='#666')
        self.status_msg.pack(side='left')
        self.redis_label = tk.Label(status_frame, text="🔴 Redis: 未知", font=("Microsoft YaHei", 10),
                                    bg='#f5f5f5', fg='#666')
        self.redis_label.pack(side='right')

        # 定时检查状态（5秒一次）
        self._schedule_status_check()

    def _schedule_status_check(self):
        self._update_status_once()
        self.root.after(5000, self._schedule_status_check)

    def _update_status_once(self):
        try:
            resp = requests.get("http://localhost:8080/health", timeout=2)
            if resp.status_code == 200:
                self.status_msg.config(text="✅ 服务运行中", fg='green')
                self._check_redis()
                self.check_service_status()
            else:
                self.status_msg.config(text="⚠️ 服务异常", fg='orange')
        except:
            self.status_msg.config(text="❌ 服务未响应", fg='red')

    def _check_redis(self):
        try:
            resp = requests.get(f"{API_BASE}/sessions", headers=admin_headers(), timeout=2)
            if resp.status_code == 200:
                self.redis_label.config(text="🟢 Redis: 已连接", fg='green')
            else:
                self.redis_label.config(text="🟡 Redis: 异常", fg='orange')
        except:
            self.redis_label.config(text="🔴 Redis: 未连接", fg='red')

    def _append_log(self, line):
        self.log_text.insert(tk.END, line + "\n")
        self.log_text.see(tk.END)
        self.log_text.update_idletasks()
        debug_print(line)

    def _clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def start_service(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("提示", "服务已在运行中")
            return

        self._clear_log()
        self._append_log("开始检查环境...")

        cmd, err = get_available_command()
        if cmd is None:
            self._append_log(f"❌ 启动失败: {err}")
            messagebox.showerror("环境错误", err)
            return
        self._append_log(f"启动命令: {' '.join(cmd)}")

        if is_port_in_use(8080):
            self._append_log("端口被占用，尝试释放...")
            success, msg = kill_process_on_port(8080)
            self._append_log(f"释放结果: {msg}")
            if not success:
                self._append_log("❌ 无法释放端口")
                messagebox.showerror("端口错误", "无法释放8080端口，请手动关闭占用进程。")
                return
        else:
            self._append_log("端口 8080 空闲")

        os.chdir(SCRIPT_DIR)
        self._append_log(f"工作目录: {SCRIPT_DIR}")
        self.status_label.config(text="状态: 启动中...", fg='orange')
        self.root.update()

        env = os.environ.copy()
        # 不再注入默认 JWT 密钥：服务端会自动生成随机密钥并持久化到 .jwt_secret
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            flags = 0x08000000 if IS_WINDOWS else 0
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                bufsize=0, universal_newlines=False, env=env,
                creationflags=flags, cwd=SCRIPT_DIR
            )
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self._append_log(f"✅ 进程已创建 (PID: {self.process.pid})")

            def reader():
                if self.process:
                    try:
                        for raw_line in iter(self.process.stdout.readline, b''):
                            if raw_line:
                                line = raw_line.decode('utf-8', errors='ignore').strip()
                                if line:
                                    self.root.after(0, self._append_log, f"[子进程] {line}")
                    except Exception as e:
                        self.root.after(0, self._append_log, f"⚠️ 日志读取异常: {e}")
            threading.Thread(target=reader, daemon=True).start()

            self._wait_for_service(retries=20)

        except Exception as e:
            self._append_log(f"❌ 启动异常: {e}")
            self.status_label.config(text="状态: 启动失败", fg='red')
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')

    def _wait_for_service(self, retries):
        if retries <= 0:
            self._append_log("❌ 服务启动超时")
            self.status_label.config(text="状态: 超时", fg='red')
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            return

        try:
            resp = requests.get("http://localhost:8080/health", timeout=1)
            if resp.status_code == 200:
                self.status_label.config(text="状态: 运行中", fg='green')
                self._append_log("✅ 健康检查通过！")
                return
        except Exception as e:
            debug_print(f"健康检查请求异常: {e}")

        self._append_log(f"⏳ 等待服务... (剩余 {retries-1})")
        self.root.after(1000, lambda: self._wait_for_service(retries - 1))

    def stop_service(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(1)
            if self.process.poll() is None:
                self.process.kill()
            self.status_label.config(text="状态: 已停止", fg='red')
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self._append_log("⏹ 服务已停止")
        else:
            messagebox.showinfo("提示", "服务未运行")

    def restart_service(self):
        self.stop_service()
        time.sleep(2)
        self.start_service()

    def check_service_status(self):
        try:
            resp = requests.get("http://localhost:8080/health", timeout=2)
            if resp.status_code == 200:
                self.status_label.config(text="状态: 运行中", fg='green')
                self.start_btn.config(state='disabled')
                self.stop_btn.config(state='normal')
                return
        except:
            pass
        self.status_label.config(text="状态: 已停止", fg='red')
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

if __name__ == "__main__":
    root = tk.Tk()
    app = GuardConfigGUI(root)
    root.mainloop()