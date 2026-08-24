#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全交互守护智能体 - 控制面板（增强版 · 流畅优化）
性能优化：所有轮询类网络请求全部在后台线程执行，主线程仅做 UI 更新；
          审计日志只加载末尾 500 行；请求防重入；去除日志强制刷新。
功能：服务启停、NLP规则、关键词/正则规则、工具白名单、会话监控（自动刷新/解封）、
      审计日志（自动刷新/清空）、系统配置（完整4项）、水印提取、管理Token显示与复制
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
# 路径兼容（打包关键）：
# 源码运行 -> 脚本所在目录；PyInstaller 打包后（sys.frozen）
# 必须用 exe 所在目录，否则 __file__ 指向临时解压目录，
# 会导致找不到 guard.exe / admin_token.txt / 配置文件
# ============================================================
def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

SCRIPT_DIR = get_script_dir()

# ============================================================
# 输出重定向（强制 UTF-8，避免 GBK 编码异常）
# ============================================================
def setup_output():
    try:
        if sys.stdout and hasattr(sys.stdout, 'fileno'):
            sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', buffering=1, encoding='utf-8')
        else:
            log_file = os.path.join(SCRIPT_DIR, "gui.log")
            sys.stdout = open(log_file, 'a', buffering=1, encoding='utf-8')
    except Exception:
        log_file = os.path.join(SCRIPT_DIR, "gui.log")
        sys.stdout = open(log_file, 'a', buffering=1, encoding='utf-8')

    try:
        if sys.stderr and hasattr(sys.stderr, 'fileno'):
            sys.stderr = os.fdopen(sys.stderr.fileno(), 'w', buffering=1, encoding='utf-8')
        else:
            sys.stderr = sys.stdout
    except Exception:
        sys.stderr = sys.stdout

setup_output()

def debug_print(msg):
    try:
        print(f"[DEBUG] {msg}")
    except UnicodeEncodeError:
        pass

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
AUDIT_TAIL = 500  # 审计日志只加载末尾 N 行

def get_admin_token():
    """读取管理后台 Token（由服务端启动时生成）。"""
    try:
        with open(ADMIN_TOKEN_FILE, "r", encoding="utf-8") as f:
            token = f.read().strip()
            if token:
                return token
    except Exception:
        pass
    return None

def admin_headers(json_body=False):
    headers = {"X-Admin-Token": get_admin_token() or ""}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers

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
        self.root.title("🛡️ 守护智能体 - 增强版")
        self.root.geometry("980x760")
        self.root.minsize(820, 620)
        self.root.configure(bg='#f5f5f5')
        self.process = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 配置变量
        self.dp_var = tk.BooleanVar(value=False)
        self.rate_var = tk.StringVar(value="10")
        self.level_var = tk.StringVar(value="partial")
        self.timeout_var = tk.StringVar(value="30")
        # 反刷评配置变量
        self.dup_var = tk.BooleanVar(value=True)
        self.dup_window_var = tk.StringVar(value="10")
        self.user_rate_var = tk.StringVar(value="5")
        self.ip_rate_var = tk.StringVar(value="30")
        self.rep_var = tk.BooleanVar(value=True)
        # 业务侧调用密钥（/v1/guard 鉴权；留空则不限）
        self.guard_key_var = tk.StringVar(value="")
        # 安全审核 LLM 配置
        self.llm_url_var = tk.StringVar(value="http://localhost:11434/v1/chat/completions")
        self.llm_model_var = tk.StringVar(value="qwen2.5:7b")
        self.llm_key_var = tk.StringVar(value="")

        # 自动刷新 / 自动滚动开关
        self.session_auto = tk.BooleanVar(value=True)
        self.audit_auto = tk.BooleanVar(value=True)
        self.log_autoscroll = tk.BooleanVar(value=True)

        # 防重入标志 / 服务状态记忆
        self._sessions_loading = False
        self._audit_loading = False
        self._was_up = False

        self._create_header()
        self._create_notebook()
        self._create_status_bar()

        self._update_token_display()
        self._sync_config_from_server(silent=True)  # 后台执行，不阻塞
        self._schedule_status_check()
        debug_print("GUI 初始化完成")

    # ============ 通用 ============
    def _btn(self, parent, text, command, bg='#2196F3', fg='white', width=None):
        return tk.Button(parent, text=text, command=command, font=("Microsoft YaHei", 9),
                         bg=bg, fg=fg, width=width, relief='flat', cursor='hand2',
                         activebackground=bg, activeforeground='white', bd=0)

    def _check_resp(self, resp):
        """401 时给出友好提示，返回 False。"""
        if resp.status_code == 401:
            messagebox.showwarning("鉴权失败",
                                   "管理 Token 无效或缺失。\n"
                                   f"请确认 {ADMIN_TOKEN_FILE} 存在，\n"
                                   "或重启服务（会重新生成 Token）。")
            return False
        return True

    def _copy_token(self):
        token = get_admin_token()
        if not token:
            messagebox.showwarning("提示", f"未找到 {ADMIN_TOKEN_FILE}，请先启动服务")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(token)
        self._append_log("✅ 管理 Token 已复制到剪贴板")

    def _update_token_display(self):
        token = get_admin_token()
        if token:
            short = token[:10] + "…" if len(token) > 12 else token
            self.token_label.config(text=f"🔑 Token: {short}", fg='green')
        else:
            self.token_label.config(text="🔑 Token: 未找到（启动服务后生成）", fg='orange')

    def on_closing(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(1)
            if self.process.poll() is None:
                self.process.kill()
        self.root.destroy()

    # ============ 头部 ============
    def _create_header(self):
        header = tk.Frame(self.root, bg='#f5f5f5')
        header.pack(fill='x', padx=10, pady=(10, 5))

        tk.Label(header, text="🛡️ 安全交互守护智能体", font=("Microsoft YaHei", 16, "bold"),
                 bg='#f5f5f5', fg='#333').pack(side='left')

        cfg = tk.Frame(header, bg='#f5f5f5')
        cfg.pack(side='left', padx=20)
        tk.Label(cfg, text="🔢 差分隐私:", bg='#f5f5f5', font=("Microsoft YaHei", 9)).pack(side='left')
        cb = tk.Checkbutton(cfg, variable=self.dp_var, command=self._on_dp_change, bg='#f5f5f5')
        cb.pack(side='left', padx=5)
        tk.Label(cfg, text="🚦 限流:", bg='#f5f5f5', font=("Microsoft YaHei", 9)).pack(side='left')
        self.rate_entry = tk.Entry(cfg, textvariable=self.rate_var, width=4, font=("Microsoft YaHei", 9))
        self.rate_entry.pack(side='left', padx=5)
        tk.Label(cfg, text="次/秒", bg='#f5f5f5', font=("Microsoft YaHei", 9)).pack(side='left')
        self._btn(cfg, "💾 保存", self._save_config, bg='#4CAF50', width=6).pack(side='left', padx=5)

        btn = tk.Frame(header, bg='#f5f5f5')
        btn.pack(side='right')
        self.start_btn = self._btn(btn, "▶ 启动", self.start_service, bg='#4CAF50', width=7)
        self.start_btn.pack(side='left', padx=2)
        self.stop_btn = self._btn(btn, "⏹ 停止", self.stop_service, bg='#f44336', width=7)
        self.stop_btn.config(state='disabled')
        self.stop_btn.pack(side='left', padx=2)
        self.restart_btn = self._btn(btn, "🔄 重启", self.restart_service, bg='#FF9800', width=7)
        self.restart_btn.pack(side='left', padx=2)
        self.status_label = tk.Label(btn, text="状态: 未启动", font=("Microsoft YaHei", 10, "bold"),
                                     bg='#f5f5f5', fg='red')
        self.status_label.pack(side='left', padx=10)

    def _on_dp_change(self):
        self._save_config()

    def _save_config(self):
        if not self._check_service_running():
            messagebox.showwarning("警告", "服务未运行，无法保存配置")
            return
        try:
            rate = int(self.rate_var.get())
            if rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "限流请输入正整数（次/秒）")
            return
        try:
            timeout = int(self.timeout_var.get())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "会话超时请输入正整数（分钟）")
            return
        try:
            dup_window = int(self.dup_window_var.get())
            user_rate = int(self.user_rate_var.get())
            ip_rate = int(self.ip_rate_var.get())
            if dup_window <= 0 or user_rate <= 0 or ip_rate <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "去重窗口/账号限流/IP限流请输入正整数")
            return
        level = self.level_var.get()
        if level not in ("partial", "full", "minimal"):
            messagebox.showwarning("提示", "脱敏级别仅支持 partial / full / minimal")
            return
        config = {
            'enable_differential_privacy': self.dp_var.get(),
            'rate_limit': rate,
            'default_level': level,
            'session_timeout': timeout,
            # 反刷评配置
            'enable_duplicate_detection': self.dup_var.get(),
            'duplicate_window_minutes': dup_window,
            'user_rate_limit': user_rate,
            'ip_rate_limit': ip_rate,
            'enable_reputation_score': self.rep_var.get(),
            'guard_api_key': self.guard_key_var.get().strip(),
            # 安全审核 LLM
            'llm_judge_url': self.llm_url_var.get().strip(),
            'llm_judge_model': self.llm_model_var.get().strip(),
            'llm_judge_api_key': self.llm_key_var.get().strip(),
        }
        try:
            resp = requests.put(f"{API_BASE}/config", json=config, headers=admin_headers(True), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                messagebox.showinfo("成功", "✅ 配置已保存")
                self.status_msg.config(text="✅ 配置已保存", fg='green')
            else:
                messagebox.showerror("错误", f"保存失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def _sync_config_from_server(self, silent=False):
        """后台拉取服务端配置并同步到界面控件（不阻塞主线程）。"""
        def task():
            if not self._check_service_running():
                return
            try:
                resp = requests.get(f"{API_BASE}/config", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    cfg = resp.json().get('config', {})
                    self.root.after(0, lambda: self._apply_config(cfg, silent))
            except Exception as e:
                debug_print(f"配置同步失败: {e}")
        threading.Thread(target=task, daemon=True).start()

    def _apply_config(self, cfg, silent=False):
        if 'enable_differential_privacy' in cfg:
            self.dp_var.set(bool(cfg['enable_differential_privacy']))
        if 'rate_limit' in cfg and cfg['rate_limit']:
            self.rate_var.set(str(cfg['rate_limit']))
        if 'default_level' in cfg and cfg['default_level']:
            self.level_var.set(cfg['default_level'])
        if 'session_timeout' in cfg and cfg['session_timeout']:
            self.timeout_var.set(str(cfg['session_timeout']))
        # 反刷评配置同步
        if 'enable_duplicate_detection' in cfg:
            self.dup_var.set(bool(cfg['enable_duplicate_detection']))
        if cfg.get('duplicate_window_minutes'):
            self.dup_window_var.set(str(cfg['duplicate_window_minutes']))
        if cfg.get('user_rate_limit'):
            self.user_rate_var.set(str(cfg['user_rate_limit']))
        if cfg.get('ip_rate_limit'):
            self.ip_rate_var.set(str(cfg['ip_rate_limit']))
        if 'enable_reputation_score' in cfg:
            self.rep_var.set(bool(cfg['enable_reputation_score']))
        if 'guard_api_key' in cfg:
            self.guard_key_var.set(cfg.get('guard_api_key') or '')
        # 安全审核 LLM 配置同步
        if cfg.get('llm_judge_url'):
            self.llm_url_var.set(cfg['llm_judge_url'])
        if cfg.get('llm_judge_model'):
            self.llm_model_var.set(cfg['llm_judge_model'])
        if 'llm_judge_api_key' in cfg:
            self.llm_key_var.set(cfg.get('llm_judge_api_key') or '')
        if not silent:
            self._append_log("✅ 已同步服务端配置")

    # ============ 标签页 ============
    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        self._create_log_tab()
        self._create_nlp_tab()
        self._create_keyword_tab()
        self._create_whitelist_tab()
        self._create_session_tab()
        self._create_audit_tab()
        self._create_config_tab()
        self._create_watermark_tab()

    # ---- 服务日志 ----
    def _create_log_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="📋 服务日志")
        self.log_text = scrolledtext.ScrolledText(tab, font=("Consolas", 9), bg='#1e1e1e', fg='#d4d4d4')
        self.log_text.pack(fill='both', expand=True, padx=5, pady=5)
        btn_frame = tk.Frame(tab, bg='white')
        btn_frame.pack(fill='x', pady=5)
        self._btn(btn_frame, "清空日志", self._clear_log, bg='#ff9800', width=10).pack(side='right', padx=10)
        tk.Checkbutton(btn_frame, text="自动滚动", variable=self.log_autoscroll, bg='white',
                       font=("Microsoft YaHei", 9)).pack(side='right', padx=10)

    def _append_log(self, line):
        self.log_text.insert(tk.END, line + "\n")
        if self.log_autoscroll.get():
            self.log_text.see(tk.END)
        debug_print(line)

    def _clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self._append_log("📋 日志已清空")

    # ---- NLP 规则 ----
    def _create_nlp_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="🧠 NLP规则")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        tk.Label(toolbar, text="名称:", bg='white').pack(side='left', padx=5)
        self.nlp_name_entry = tk.Entry(toolbar, width=12)
        self.nlp_name_entry.pack(side='left', padx=5)
        tk.Label(toolbar, text="描述:", bg='white').pack(side='left', padx=5)
        self.nlp_desc_entry = tk.Entry(toolbar, width=20)
        self.nlp_desc_entry.pack(side='left', padx=5)
        tk.Label(toolbar, text="动作:", bg='white').pack(side='left', padx=5)
        self.nlp_action_var = tk.StringVar(value="block")
        ttk.Combobox(toolbar, textvariable=self.nlp_action_var, values=["block", "warning", "allow"],
                     width=8, state='readonly').pack(side='left', padx=5)
        self._btn(toolbar, "➕ 添加", self._add_nlp_rule, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🔄 刷新", self._load_nlp_rules_async, bg='#2196F3').pack(side='left', padx=5)

        columns = ("ID", "名称", "描述", "动作", "状态", "创建时间")
        self.nlp_tree = ttk.Treeview(tab, columns=columns, show="headings", height=10)
        for col in columns:
            self.nlp_tree.heading(col, text=col)
            self.nlp_tree.column(col, width=100)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.nlp_tree.yview)
        self.nlp_tree.configure(yscrollcommand=scroll.set)
        self.nlp_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scroll.pack(side='right', fill='y')

        action_frame = tk.Frame(tab, bg='white')
        action_frame.pack(fill='x', pady=5)
        self._btn(action_frame, "启用", lambda: self._toggle_nlp_rule(True), bg='#4CAF50').pack(side='left', padx=5)
        self._btn(action_frame, "禁用", lambda: self._toggle_nlp_rule(False), bg='#FF9800').pack(side='left', padx=5)
        self._btn(action_frame, "删除", self._delete_nlp_rule, bg='#f44336').pack(side='left', padx=5)

    def _load_nlp_rules_async(self):
        def task():
            try:
                resp = requests.get(f"{API_BASE}/nlp-rules", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    rules = resp.json().get('rules', [])
                    self.root.after(0, lambda: self._update_nlp_tree(rules))
                    self.root.after(0, lambda: self._append_log(f"✅ NLP规则已刷新: {len(rules)} 条"))
                elif not self._check_resp(resp):
                    return
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ NLP规则加载异常: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _update_nlp_tree(self, rules):
        for item in self.nlp_tree.get_children():
            self.nlp_tree.delete(item)
        for r in rules:
            status = "✅ 启用" if r.get('enabled') else "❌ 禁用"
            self.nlp_tree.insert("", "end", values=(
                r.get('id', ''), r.get('name', ''), r.get('description', ''),
                r.get('action', ''), status, r.get('created_at', '')
            ))

    def _add_nlp_rule(self):
        name = self.nlp_name_entry.get().strip()
        desc = self.nlp_desc_entry.get().strip()
        action = self.nlp_action_var.get()
        if not name or not desc:
            messagebox.showwarning("提示", "请输入名称和描述")
            return
        try:
            resp = requests.post(f"{API_BASE}/nlp-rules", json={
                "name": name, "description": desc, "action": action
            }, headers=admin_headers(True), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"✅ NLP规则已添加: {name}")
                self.nlp_name_entry.delete(0, tk.END)
                self.nlp_desc_entry.delete(0, tk.END)
                self._load_nlp_rules_async()
            else:
                messagebox.showerror("错误", f"添加失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"添加失败: {e}")

    def _toggle_nlp_rule(self, enable):
        selected = self.nlp_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条规则")
            return
        index = self.nlp_tree.index(selected[0])
        try:
            resp = requests.put(f"{API_BASE}/nlp-rules/{index}/toggle", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ NLP规则状态已切换")
                self._load_nlp_rules_async()
            else:
                messagebox.showerror("错误", f"操作失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {e}")

    def _delete_nlp_rule(self):
        selected = self.nlp_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条规则")
            return
        if not messagebox.askyesno("确认", "确定删除选中的规则吗？"):
            return
        index = self.nlp_tree.index(selected[0])
        try:
            resp = requests.delete(f"{API_BASE}/nlp-rules/{index}", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ NLP规则已删除")
                self._load_nlp_rules_async()
            else:
                messagebox.showerror("错误", f"删除失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    # ---- 关键词/正则规则 ----
    def _create_keyword_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="🔑 关键词规则")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        tk.Label(toolbar, text="类型:", bg='white').pack(side='left', padx=5)
        self.kw_type_var = tk.StringVar(value="关键词")
        ttk.Combobox(toolbar, textvariable=self.kw_type_var, values=["关键词", "正则"],
                     width=6, state='readonly').pack(side='left', padx=5)
        tk.Label(toolbar, text="内容:", bg='white').pack(side='left', padx=5)
        self.kw_entry = tk.Entry(toolbar, width=15)
        self.kw_entry.pack(side='left', padx=5)
        tk.Label(toolbar, text="原因:", bg='white').pack(side='left', padx=5)
        self.kw_reason_entry = tk.Entry(toolbar, width=18)
        self.kw_reason_entry.pack(side='left', padx=5)
        self._btn(toolbar, "➕ 添加", self._add_keyword_rule, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🔄 刷新", self._load_keyword_rules_async, bg='#2196F3').pack(side='left', padx=5)

        columns = ("类型", "内容", "原因")
        self.kw_tree = ttk.Treeview(tab, columns=columns, show="headings", height=10)
        for col in columns:
            self.kw_tree.heading(col, text=col)
            self.kw_tree.column(col, width=180)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.kw_tree.yview)
        self.kw_tree.configure(yscrollcommand=scroll.set)
        self.kw_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scroll.pack(side='right', fill='y')

        action_frame = tk.Frame(tab, bg='white')
        action_frame.pack(fill='x', pady=5)
        self._btn(action_frame, "删除选中", self._delete_keyword_rule, bg='#f44336').pack(side='left', padx=5)

    def _load_keyword_rules_async(self):
        def task():
            try:
                resp = requests.get(f"{API_BASE}/rules", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    rules = resp.json().get('rules', [])
                    self.root.after(0, lambda: self._update_kw_tree(rules))
                    self.root.after(0, lambda: self._append_log(f"✅ 规则已刷新: {len(rules)} 条"))
                elif not self._check_resp(resp):
                    return
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ 规则加载异常: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _update_kw_tree(self, rules):
        for item in self.kw_tree.get_children():
            self.kw_tree.delete(item)
        for r in rules:
            type_label = "关键词" if r.get('type') == 'keyword' else ("正则" if r.get('type') == 'regex' else r.get('type', ''))
            self.kw_tree.insert("", "end", values=(type_label, r.get('pattern', ''), r.get('reason', '')))

    def _add_keyword_rule(self):
        pattern = self.kw_entry.get().strip()
        reason = self.kw_reason_entry.get().strip()
        if not pattern:
            messagebox.showwarning("提示", "请输入内容")
            return
        type_map = {"关键词": "keyword", "正则": "regex"}
        rule_type = type_map.get(self.kw_type_var.get(), "keyword")
        try:
            resp = requests.post(f"{API_BASE}/rules", json={
                "type": rule_type, "pattern": pattern, "reason": reason or f"命中关键词: {pattern}"
            }, headers=admin_headers(True), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"✅ 规则已添加: [{self.kw_type_var.get()}] {pattern}")
                self.kw_entry.delete(0, tk.END)
                self.kw_reason_entry.delete(0, tk.END)
                self._load_keyword_rules_async()
            else:
                messagebox.showerror("错误", f"添加失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"添加失败: {e}")

    def _delete_keyword_rule(self):
        selected = self.kw_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条规则")
            return
        if not messagebox.askyesno("确认", "确定删除选中的规则吗？"):
            return
        index = self.kw_tree.index(selected[0])
        try:
            resp = requests.delete(f"{API_BASE}/rules/{index}", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ 规则已删除")
                self._load_keyword_rules_async()
            else:
                messagebox.showerror("错误", f"删除失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    # ---- 工具白名单 ----
    def _create_whitelist_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="📜 工具白名单")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        tk.Label(toolbar, text="工具路径:", bg='white').pack(side='left', padx=5)
        self.wl_entry = tk.Entry(toolbar, width=35)
        self.wl_entry.pack(side='left', padx=5)
        self._btn(toolbar, "➕ 添加", self._add_whitelist, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🔄 刷新", self._load_whitelist_async, bg='#2196F3').pack(side='left', padx=5)

        self.wl_listbox = tk.Listbox(tab, font=("Consolas", 10), height=12)
        self.wl_listbox.pack(fill='both', expand=True, padx=5, pady=5)

        action_frame = tk.Frame(tab, bg='white')
        action_frame.pack(fill='x', pady=5)
        self._btn(action_frame, "删除选中", self._delete_whitelist, bg='#f44336').pack(side='left', padx=5)

    def _load_whitelist_async(self):
        def task():
            try:
                resp = requests.get(f"{API_BASE}/whitelist", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    tools = resp.json().get('whitelist', [])
                    self.root.after(0, lambda: self._update_wl_listbox(tools))
                    self.root.after(0, lambda: self._append_log(f"✅ 白名单已刷新: {len(tools)} 条"))
                elif not self._check_resp(resp):
                    return
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ 白名单加载异常: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _update_wl_listbox(self, tools):
        self.wl_listbox.delete(0, tk.END)
        for t in tools:
            self.wl_listbox.insert(tk.END, t)

    def _add_whitelist(self):
        tool = self.wl_entry.get().strip()
        if not tool:
            messagebox.showwarning("提示", "请输入工具路径")
            return
        try:
            resp = requests.post(f"{API_BASE}/whitelist", json={"tool": tool}, headers=admin_headers(True), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"✅ 白名单已添加: {tool}")
                self.wl_entry.delete(0, tk.END)
                self._load_whitelist_async()
            else:
                messagebox.showerror("错误", f"添加失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"添加失败: {e}")

    def _delete_whitelist(self):
        selection = self.wl_listbox.curselection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条记录")
            return
        if not messagebox.askyesno("确认", "确定删除选中的记录吗？"):
            return
        index = selection[0]
        try:
            resp = requests.delete(f"{API_BASE}/whitelist/{index}", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ 白名单已删除")
                self._load_whitelist_async()
            else:
                messagebox.showerror("错误", f"删除失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    # ---- 会话监控 ----
    def _create_session_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="👥 会话监控")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        self._btn(toolbar, "🔄 刷新", lambda: self._load_sessions_async(auto=self.session_auto.get()),
                  bg='#2196F3').pack(side='left', padx=5)
        tk.Checkbutton(toolbar, text="自动刷新(5秒)", variable=self.session_auto, bg='white',
                       font=("Microsoft YaHei", 9)).pack(side='left', padx=5)
        self._btn(toolbar, "🔓 解封选中会话", self._reset_session, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🚫 封禁选中会话", self._ban_session, bg='#f44336').pack(side='left', padx=5)
        self._btn(toolbar, "📋 风险明细", self._show_session_detail, bg='#2196F3').pack(side='left', padx=5)

        columns = ("会话ID", "风险积分", "状态")
        self.session_tree = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        for col in columns:
            self.session_tree.heading(col, text=col)
            self.session_tree.column(col, width=180)
        self.session_tree.pack(fill='both', expand=True, padx=5, pady=5)

    def _load_sessions_async(self, auto=False):
        """加载会话列表；auto=True 时形成 5 秒循环（带防重入）。"""
        if self._sessions_loading:
            if auto and self.session_auto.get():
                self.root.after(5000, lambda: self._load_sessions_async(auto=True))
            return
        self._sessions_loading = True

        def task():
            try:
                resp = requests.get(f"{API_BASE}/sessions", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    sessions = resp.json().get('sessions', [])
                    self.root.after(0, lambda: self._update_session_tree(sessions))
                elif resp.status_code == 401 and not auto:
                    self.root.after(0, lambda: self._check_resp(resp))
            except Exception as e:
                if not auto:
                    self.root.after(0, lambda: self._append_log(f"❌ 会话加载异常: {e}"))
            finally:
                self._sessions_loading = False
                if auto and self.session_auto.get():
                    self.root.after(5000, lambda: self._load_sessions_async(auto=True))
        threading.Thread(target=task, daemon=True).start()

    def _update_session_tree(self, sessions):
        for item in self.session_tree.get_children():
            self.session_tree.delete(item)
        for s in sessions:
            status = s.get('status', '正常')
            if status == '已终止':
                status = '🔴 已终止'
            elif status == '已限流':
                status = '🟡 已限流'
            elif status == '警告':
                status = '🟠 警告'
            else:
                status = '🟢 正常'
            self.session_tree.insert("", "end", values=(s.get('id', ''), s.get('score', 0), status))

    def _reset_session(self):
        selected = self.session_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要解封的会话")
            return
        session_id = self.session_tree.item(selected[0], 'values')[0]
        if not messagebox.askyesno("确认", f"确定解封会话 {session_id} 吗？\n（将重置其风险积分与限流状态）"):
            return
        try:
            resp = requests.put(f"{API_BASE}/sessions/{session_id}/reset", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"✅ 会话已解封: {session_id}")
                self._load_sessions_async(auto=self.session_auto.get())
            else:
                messagebox.showerror("错误", f"解封失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"解封失败: {e}")

    def _ban_session(self):
        selected = self.session_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择要封禁的会话")
            return
        session_id = self.session_tree.item(selected[0], 'values')[0]
        if not messagebox.askyesno("确认", f"确定封禁会话 {session_id} 吗？\n（其风险积分将设为 100，立即终止）"):
            return
        try:
            resp = requests.put(f"{API_BASE}/sessions/{session_id}/ban", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"🚫 会话已封禁: {session_id}")
                self._load_sessions_async(auto=self.session_auto.get())
            else:
                messagebox.showerror("错误", f"封禁失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"封禁失败: {e}")

    def _show_session_detail(self):
        selected = self.session_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个会话")
            return
        session_id = self.session_tree.item(selected[0], 'values')[0]

        win = tk.Toplevel(self.root)
        win.title(f"📋 会话风险明细 - {session_id}")
        win.geometry("760x480")
        win.configure(bg='white')
        text = scrolledtext.ScrolledText(win, font=("Consolas", 9), bg='#1e1e1e', fg='#d4d4d4')
        text.pack(fill='both', expand=True, padx=8, pady=8)
        text.insert(tk.END, "加载中...\n")

        def task():
            try:
                resp = requests.get(f"{API_BASE}/sessions/{session_id}/audit", headers=admin_headers(), timeout=5)
                if resp.status_code == 200:
                    records = resp.json().get('records', [])
                    lines = [f"会话 {session_id} 的历史记录（共 {len(records)} 条）：\n"]
                    for r in records:
                        if 'raw' in r:
                            lines.append(r['raw'])
                        else:
                            lines.append(
                                f"[{r.get('time','')}] {r.get('action_type','')} → {r.get('decision','')} "
                                f"risk={r.get('risk_level','')} score={r.get('score','')} reason={r.get('reason','')}\n"
                                f"    content: {r.get('content','')}\n"
                            )
                    content = "\n".join(lines) if len(lines) > 1 else "暂无该会话的审计记录\n"
                    win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, content)))
                else:
                    win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, f"加载失败: {resp.status_code}\n")))
            except Exception as e:
                win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, f"加载异常: {e}\n")))
        threading.Thread(target=task, daemon=True).start()

    # ---- 审计日志 ----
    def _create_audit_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="📝 审计日志")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        self._btn(toolbar, "🔄 刷新", lambda: self._load_audit_logs_async(auto=self.audit_auto.get()),
                  bg='#2196F3').pack(side='left', padx=5)
        self._btn(toolbar, "🧹 清空文件", self._clear_audit_file, bg='#f44336').pack(side='left', padx=5)
        self._btn(toolbar, "📂 打开日志目录", self._open_log_dir, bg='#607D8B').pack(side='left', padx=5)
        tk.Checkbutton(toolbar, text="自动刷新(5秒)", variable=self.audit_auto, bg='white',
                       font=("Microsoft YaHei", 9)).pack(side='left', padx=5)
        self.audit_count_label = tk.Label(toolbar, text="显示: - 行", bg='white', fg='#666',
                                          font=("Microsoft YaHei", 9))
        self.audit_count_label.pack(side='right', padx=10)

        self.audit_text = scrolledtext.ScrolledText(tab, font=("Consolas", 8), bg='#1e1e1e', fg='#d4d4d4', height=15)
        self.audit_text.pack(fill='both', expand=True, padx=5, pady=5)
        tk.Label(tab, text=f"仅显示最近 {AUDIT_TAIL} 行（审计日志按天轮转：audit.log 为当日，历史见 audit-YYYYMMDD.log）",
                 bg='white', fg='#999', font=("Microsoft YaHei", 8)).pack(anchor='w', padx=5)

    def _open_log_dir(self):
        try:
            if IS_WINDOWS:
                os.startfile(SCRIPT_DIR)  # noqa: B606 仅在 Windows 使用
            else:
                subprocess.Popen(["xdg-open", SCRIPT_DIR])
        except Exception as e:
            messagebox.showerror("错误", f"打开目录失败: {e}")

    def _load_audit_logs_async(self, auto=False):
        """加载审计日志末尾；auto=True 时形成 5 秒循环（带防重入）。"""
        if self._audit_loading:
            if auto and self.audit_auto.get():
                self.root.after(5000, lambda: self._load_audit_logs_async(auto=True))
            return
        self._audit_loading = True

        def task():
            try:
                resp = requests.get(f"{API_BASE}/logs?tail={AUDIT_TAIL}", headers=admin_headers(), timeout=3)
                if resp.status_code == 200:
                    text = resp.text
                    self.root.after(0, lambda: self._update_audit_text(text))
                elif resp.status_code == 401 and not auto:
                    self.root.after(0, lambda: self._check_resp(resp))
            except Exception as e:
                if not auto:
                    self.root.after(0, lambda: self._append_log(f"❌ 审计日志加载异常: {e}"))
            finally:
                self._audit_loading = False
                if auto and self.audit_auto.get():
                    self.root.after(5000, lambda: self._load_audit_logs_async(auto=True))
        threading.Thread(target=task, daemon=True).start()

    def _update_audit_text(self, text):
        self.audit_text.delete(1.0, tk.END)
        self.audit_text.insert(tk.END, text)
        line_count = text.count('\n')
        self.audit_count_label.config(text=f"显示: {line_count} 行")

    def _clear_audit_file(self):
        if not messagebox.askyesno("确认", "确定清空 audit.log 文件内容吗？"):
            return
        try:
            with open(os.path.join(SCRIPT_DIR, "audit.log"), "w", encoding="utf-8") as f:
                f.write("")
            self._append_log("✅ audit.log 已清空")
            self._load_audit_logs_async(auto=self.audit_auto.get())
        except Exception as e:
            messagebox.showerror("错误", f"清空失败: {e}")

    # ---- 系统配置 ----
    def _create_config_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="⚙️ 系统配置")

        frame = tk.Frame(tab, bg='white')
        frame.pack(fill='x', padx=20, pady=15)
        frame.columnconfigure(1, weight=1)

        tk.Label(frame, text="差分隐私:", bg='white', font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky='w', pady=6)
        tk.Checkbutton(frame, variable=self.dp_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=0, column=1, sticky='w', pady=6)

        tk.Label(frame, text="限流速率（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky='w', pady=6)
        tk.Entry(frame, textvariable=self.rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=1, column=1, sticky='w', pady=6)

        tk.Label(frame, text="默认脱敏级别:", bg='white', font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky='w', pady=6)
        ttk.Combobox(frame, textvariable=self.level_var, values=["partial", "full", "minimal"],
                     width=10, state='readonly').grid(row=2, column=1, sticky='w', pady=6)

        tk.Label(frame, text="会话超时（分钟）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=3, column=0, sticky='w', pady=6)
        tk.Entry(frame, textvariable=self.timeout_var, width=10, font=("Microsoft YaHei", 10)).grid(row=3, column=1, sticky='w', pady=6)

        # 反刷评配置
        tk.Label(frame, text="🛡️ 反刷评（评论区 AI 机器人防御）", bg='white', font=("Microsoft YaHei", 10, "bold"),
                 fg='#1976D2').grid(row=4, column=0, columnspan=2, sticky='w', pady=(10, 2))

        tk.Label(frame, text="内容去重:", bg='white', font=("Microsoft YaHei", 10)).grid(row=5, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.dup_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=5, column=1, sticky='w', pady=4)

        tk.Label(frame, text="去重窗口（分钟）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=6, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.dup_window_var, width=10, font=("Microsoft YaHei", 10)).grid(row=6, column=1, sticky='w', pady=4)

        tk.Label(frame, text="账号限流（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=7, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.user_rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=7, column=1, sticky='w', pady=4)

        tk.Label(frame, text="IP 限流（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=8, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.ip_rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=8, column=1, sticky='w', pady=4)

        tk.Label(frame, text="账号信誉分:", bg='white', font=("Microsoft YaHei", 10)).grid(row=9, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.rep_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=9, column=1, sticky='w', pady=4)

        tk.Label(frame, text="业务调用密钥:", bg='white', font=("Microsoft YaHei", 10)).grid(row=10, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.guard_key_var, width=24, show="*",
                 font=("Microsoft YaHei", 10)).grid(row=10, column=1, sticky='w', pady=4)

        # 安全审核 LLM
        tk.Label(frame, text="🤖 安全审核 LLM（判定模型）", bg='white', font=("Microsoft YaHei", 10, "bold"),
                 fg='#1976D2').grid(row=11, column=0, columnspan=2, sticky='w', pady=(10, 2))
        tk.Label(frame, text="接口地址:", bg='white', font=("Microsoft YaHei", 10)).grid(row=12, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.llm_url_var, width=30, font=("Microsoft YaHei", 10)).grid(row=12, column=1, sticky='w', pady=4)
        tk.Label(frame, text="模型名:", bg='white', font=("Microsoft YaHei", 10)).grid(row=13, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.llm_model_var, width=24, font=("Microsoft YaHei", 10)).grid(row=13, column=1, sticky='w', pady=4)
        tk.Label(frame, text="API Key:", bg='white', font=("Microsoft YaHei", 10)).grid(row=14, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.llm_key_var, width=24, show="*",
                 font=("Microsoft YaHei", 10)).grid(row=14, column=1, sticky='w', pady=4)

        tk.Label(frame, text="", bg='white').grid(row=15, column=0, pady=4)
        self._btn(frame, "💾 保存全部配置", self._save_config, bg='#4CAF50', width=16).grid(row=16, column=0, columnspan=2, sticky='w', pady=6)
        self._btn(frame, "🔄 从服务端刷新", lambda: self._sync_config_from_server(silent=False),
                  bg='#2196F3', width=16).grid(row=16, column=1, sticky='w', pady=6)

        tip = ("说明：\n"
               "· 差分隐私：开启后对输出统计类数据加入噪声（预留扩展）\n"
               "· 限流速率：每个会话每秒最多请求数\n"
               "· 脱敏级别：partial 部分脱敏 / full 完整（管理员） / minimal 最小化\n"
               "· 会话超时：风险积分缓存保留时长（分钟）\n"
               "· 内容去重：相同/高度相似评论在窗口内重复出现直接拦截（专杀刷屏）\n"
               "· 账号/IP 限流：按 user_id 与来源 IP 聚合限流，堵住分布式刷评\n"
               "· 账号信誉分：违规跨会话累计，低信誉账号直接降权\n"
               "· 业务调用密钥：业务系统调 /v1/guard 时需携带 X-Guard-Key（留空则不鉴权）\n"
               "· 安全审核 LLM：判定模型（OpenAI 兼容接口）。本地换大模型改模型名；\n"
               "    接云端填 API 端点+Key（如 deepseek-chat）。留空自动用默认 Ollama\n"
               "· 配置修改后服务端自动热加载，无需重启")
        tk.Label(frame, text=tip, bg='#f0f7ff', fg='#555', justify='left',
                 font=("Microsoft YaHei", 9), padx=10, pady=8).grid(row=17, column=0, columnspan=2, sticky='we', pady=10)

    # ---- 水印提取 ----
    def _create_watermark_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="💧 水印提取")

        input_frame = tk.Frame(tab, bg='white')
        input_frame.pack(fill='x', padx=10, pady=5)
        tk.Label(input_frame, text="粘贴带水印的内容:", bg='white').pack(anchor='w')
        self.wm_input = scrolledtext.ScrolledText(input_frame, height=5, font=("Consolas", 10))
        self.wm_input.pack(fill='x', pady=5)

        btn_frame = tk.Frame(tab, bg='white')
        btn_frame.pack(fill='x', padx=10, pady=5)
        self._btn(btn_frame, "🔍 提取水印", self._extract_watermark, bg='#4CAF50', width=14).pack(side='left', padx=5)

        output_frame = tk.Frame(tab, bg='white')
        output_frame.pack(fill='both', expand=True, padx=10, pady=5)
        tk.Label(output_frame, text="提取结果:", bg='white').pack(anchor='w')
        self.wm_result = scrolledtext.ScrolledText(output_frame, height=6, font=("Consolas", 10))
        self.wm_result.pack(fill='both', expand=True, pady=5)

    def _extract_watermark(self):
        content = self.wm_input.get(1.0, tk.END).strip()
        if not content:
            messagebox.showinfo("提示", "请先粘贴内容")
            return
        try:
            resp = requests.post(f"{API_BASE}/extract-watermark", json={"content": content},
                                 headers=admin_headers(True), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                data = resp.json()
                self.wm_result.delete(1.0, tk.END)
                result = f"水印: {data.get('watermark', '未检测到')}\n"
                result += f"会话ID: {data.get('session_id', '')}\n"
                result += f"用户ID: {data.get('user_id', '')}\n"
                result += f"时间戳: {data.get('timestamp', '')}\n"
                result += f"消息: {data.get('message', '')}"
                self.wm_result.insert(tk.END, result)
                self._append_log("✅ 水印提取完成")
            else:
                messagebox.showerror("错误", f"提取失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"提取失败: {e}")

    # ============ 状态栏 ============
    def _create_status_bar(self):
        status_frame = tk.Frame(self.root, bg='#f5f5f5')
        status_frame.pack(fill='x', padx=10, pady=(0, 5))
        self.status_msg = tk.Label(status_frame, text="🔄 准备就绪", font=("Microsoft YaHei", 9),
                                   bg='#f5f5f5', fg='#666')
        self.status_msg.pack(side='left')

        self.token_label = tk.Label(status_frame, text="🔑 Token: -", font=("Microsoft YaHei", 9),
                                    bg='#f5f5f5', fg='#666')
        self.token_label.pack(side='left', padx=15)
        self._btn(status_frame, "复制", self._copy_token, bg='#607D8B', width=4).pack(side='left')

        self.redis_label = tk.Label(status_frame, text="🔴 Redis: 未知", font=("Microsoft YaHei", 9),
                                    bg='#f5f5f5', fg='#666')
        self.redis_label.pack(side='right')

    # ============ 服务管理 ============
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
        # 不注入默认 JWT 密钥：服务端自动生成随机密钥并持久化到 .jwt_secret
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

            # 后台等待服务就绪，不阻塞主线程
            self._wait_for_service(retries=20)

        except Exception as e:
            self._append_log(f"❌ 启动异常: {e}")
            self.status_label.config(text="状态: 启动失败", fg='red')
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')

    def _wait_for_service(self, retries):
        """后台线程轮询健康检查，就绪后回调主线程。"""
        def task():
            for _ in range(retries):
                try:
                    resp = requests.get("http://localhost:8080/health", timeout=1)
                    if resp.status_code == 200:
                        self.root.after(0, self._on_service_ready)
                        return
                except Exception:
                    pass
                time.sleep(1)
            self.root.after(0, self._on_service_timeout)
        threading.Thread(target=task, daemon=True).start()

    def _on_service_ready(self):
        self.status_label.config(text="状态: 运行中", fg='green')
        self._append_log("✅ 健康检查通过！")
        self._update_token_display()
        self._sync_config_from_server(silent=True)
        self._load_sessions_async(auto=self.session_auto.get())
        self._load_audit_logs_async(auto=self.audit_auto.get())

    def _on_service_timeout(self):
        self._append_log("❌ 服务启动超时")
        self.status_label.config(text="状态: 超时", fg='red')
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')

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

    def _check_service_running(self):
        try:
            requests.get("http://localhost:8080/health", timeout=1)
            return True
        except:
            return False

    def _schedule_status_check(self):
        self._update_status_once()
        self.root.after(5000, self._schedule_status_check)

    def _update_status_once(self):
        """健康检查放后台线程，主线程不阻塞。"""
        def task():
            up = False
            try:
                r = requests.get("http://localhost:8080/health", timeout=1)
                up = (r.status_code == 200)
            except Exception:
                up = False
            self.root.after(0, lambda: self._on_status_result(up))
        threading.Thread(target=task, daemon=True).start()

    def _on_status_result(self, up):
        if up:
            self.status_msg.config(text="✅ 服务运行中", fg='green')
            self.status_label.config(text="状态: 运行中", fg='green')
            self.start_btn.config(state='disabled')
            self.stop_btn.config(state='normal')
            self._update_token_display()
            if not self._was_up:
                # 服务刚就绪：同步配置、启动会话/审计自动刷新
                self._sync_config_from_server(silent=True)
                self._load_sessions_async(auto=self.session_auto.get())
                self._load_audit_logs_async(auto=self.audit_auto.get())
            self._was_up = True
            self._check_redis()
        else:
            self._was_up = False
            self.status_msg.config(text="❌ 服务未响应", fg='red')
            self.status_label.config(text="状态: 已停止", fg='red')
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.redis_label.config(text="🔴 Redis: 未连接", fg='red')
            self._update_token_display()

    def _check_redis(self):
        """Redis 状态检查放后台线程。"""
        def task():
            status = "down"
            try:
                resp = requests.get(f"{API_BASE}/sessions", headers=admin_headers(), timeout=2)
                if resp.status_code == 200:
                    status = "ok"
                elif resp.status_code == 401:
                    status = "auth"
                else:
                    status = "error"
            except Exception:
                status = "down"
            self.root.after(0, lambda: self._on_redis_result(status))
        threading.Thread(target=task, daemon=True).start()

    def _on_redis_result(self, status):
        if status == "ok":
            self.redis_label.config(text="🟢 Redis: 已连接", fg='green')
        elif status == "auth":
            self.redis_label.config(text="🟡 Redis: Token异常", fg='orange')
        elif status == "error":
            self.redis_label.config(text="🟡 Redis: 异常", fg='orange')
        else:
            self.redis_label.config(text="🔴 Redis: 未连接", fg='red')


if __name__ == "__main__":
    root = tk.Tk()
    app = GuardConfigGUI(root)
    root.mainloop()
