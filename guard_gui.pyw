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


class ToolTip:
    """简单的停留悬浮提示（hover tooltip）。"""

    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e):
        self._hide()
        self.after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 18
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify='left', bg="#ffffe0", fg="#333",
                 relief="solid", borderwidth=1, padx=8, pady=6,
                 font=("Microsoft YaHei", 9), wraplength=430).pack()
        self.tip_window = tw

    def _hide(self, _e=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class GuardConfigGUI:
    def __init__(self, root):
        global app
        app = self
        self.root = root
        self.root.title("🛡️ 守护智能体 - 增强版")
        self.root.geometry("1180x780")
        self.root.minsize(900, 620)
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
        self.llm_mode_var = tk.StringVar(value="local")
        self.llm_url_var = tk.StringVar(value="http://localhost:11434/v1/chat/completions")
        self.llm_model_var = tk.StringVar(value="qwen2.5:7b")
        self.llm_key_var = tk.StringVar(value="")
        self.cloud_url_var = tk.StringVar(value="")
        self.cloud_model_var = tk.StringVar(value="")
        self.cloud_key_var = tk.StringVar(value="")
        self.fail_policy_var = tk.StringVar(value="fail-closed")
        # 差分隐私 / 行为分析 / 话术判断
        self.dp_eps_var = tk.StringVar(value="1.0")
        self.behavior_var = tk.BooleanVar(value=False)
        self.style_judge_var = tk.BooleanVar(value=False)
        self.rewrite_var = tk.BooleanVar(value=False)

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

        # 判定引擎模式 GUI 策略切换（本地 / 云端 / 混合）
        mode_frame = tk.Frame(header, bg='#f5f5f5')
        mode_frame.pack(side='left', padx=18)
        tk.Label(mode_frame, text="判定引擎:", bg='#f5f5f5', font=("Microsoft YaHei", 9)).pack(side='left')
        self.mode_btns = {}
        for m, label, tip in (("local", "本地", "只用本地 Ollama 模型审核\n优点: 数据不出网/零成本/断网可用\n缺点: 判定力受本地模型限制"),
                              ("cloud", "云端", "只用云端 API 审核\n优点: 判定力最强/免维护\n缺点: 内容出网/按量付费"),
                              ("hybrid", "混合", "本地初筛 + 云端终审（推荐）\n优点: 隐私与能力平衡/双保险\n缺点: 可疑请求两次调用")):
            b = self._btn(mode_frame, label, lambda x=m: self._set_mode(x), bg='#E0E0E0', fg='#555', width=4)
            b.pack(side='left', padx=2)
            ToolTip(b, tip)
            self.mode_btns[m] = b
        self._update_mode_buttons()

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

    def _update_mode_buttons(self):
        """按当前模式高亮顶部切换按钮。"""
        mode = self.llm_mode_var.get()
        for m, b in self.mode_btns.items():
            if m == mode:
                b.config(bg='#4CAF50', fg='white')
            else:
                b.config(bg='#E0E0E0', fg='#555')

    def _set_mode(self, mode):
        """GUI 切换判定引擎模式（读取当前配置改 mode 后保存，热加载生效）。"""
        if not self._check_service_running():
            messagebox.showwarning("警告", "服务未运行，无法切换模式")
            return
        self.llm_mode_var.set(mode)
        self._update_mode_buttons()

        def task():
            try:
                resp = requests.get(f"{API_BASE}/config", headers=admin_headers(), timeout=3)
                if resp.status_code != 200:
                    self.root.after(0, lambda: self._check_resp(resp))
                    return
                cfg = resp.json().get('config', {})
                cfg['llm_judge_mode'] = mode
                r2 = requests.put(f"{API_BASE}/config", json=cfg, headers=admin_headers(True), timeout=3)
                if r2.status_code == 200:
                    self.root.after(0, lambda: self._append_log(f"✅ 判定引擎模式已切换为 {mode}"))
                else:
                    self.root.after(0, lambda: self._check_resp(r2))
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ 模式切换失败: {e}"))
        threading.Thread(target=task, daemon=True).start()

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
            # 安全审核 LLM（可插拔判定引擎）
            'llm_judge_mode': self.llm_mode_var.get().strip() or "local",
            'llm_judge_url': self.llm_url_var.get().strip(),
            'llm_judge_model': self.llm_model_var.get().strip(),
            'llm_judge_api_key': self.llm_key_var.get().strip(),
            'cloud_judge_url': self.cloud_url_var.get().strip(),
            'cloud_judge_model': self.cloud_model_var.get().strip(),
            'cloud_judge_api_key': self.cloud_key_var.get().strip(),
            'llm_judge_fail_policy': self.fail_policy_var.get().strip() or "fail-closed",
            'dp_epsilon': float(self.dp_eps_var.get() or 1.0),
            'enable_behavior_analysis': self.behavior_var.get(),
            'enable_llm_style_judge': self.style_judge_var.get(),
            'enable_auto_rewrite': self.rewrite_var.get(),
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
            if hasattr(self, 'integ_key_label'):
                self._update_integ_key_display()
                self._update_integ_code()
        # 安全审核 LLM 配置同步
        if cfg.get('llm_judge_mode'):
            self.llm_mode_var.set(cfg['llm_judge_mode'])
            self._update_mode_buttons()  # 同步顶部模式切换按钮高亮
        if cfg.get('llm_judge_url'):
            self.llm_url_var.set(cfg['llm_judge_url'])
        if cfg.get('llm_judge_model'):
            self.llm_model_var.set(cfg['llm_judge_model'])
        if 'llm_judge_api_key' in cfg:
            self.llm_key_var.set(cfg.get('llm_judge_api_key') or '')
        if cfg.get('cloud_judge_url'):
            self.cloud_url_var.set(cfg['cloud_judge_url'])
        if cfg.get('cloud_judge_model'):
            self.cloud_model_var.set(cfg['cloud_judge_model'])
        if 'cloud_judge_api_key' in cfg:
            self.cloud_key_var.set(cfg.get('cloud_judge_api_key') or '')
        if cfg.get('llm_judge_fail_policy'):
            # 旧值兼容映射：fallback→fail-closed（原语义"无可用引擎时拦截"）、block→fail-closed、allow→fail-open
            old = cfg['llm_judge_fail_policy']
            mapping = {"fallback": "fail-closed", "block": "fail-closed", "allow": "fail-open",
                       "fail-closed": "fail-closed", "fail-open": "fail-open"}
            self.fail_policy_var.set(mapping.get(old, "fail-closed"))
        self._update_fail_tip()
        if 'dp_epsilon' in cfg:
            self.dp_eps_var.set(str(cfg.get('dp_epsilon') or 1.0))
        if 'enable_behavior_analysis' in cfg:
            self.behavior_var.set(bool(cfg['enable_behavior_analysis']))
        if 'enable_llm_style_judge' in cfg:
            self.style_judge_var.set(bool(cfg['enable_llm_style_judge']))
        if 'enable_auto_rewrite' in cfg:
            self.rewrite_var.set(bool(cfg['enable_auto_rewrite']))
        if not silent:
            self._append_log("✅ 已同步服务端配置")

    # ============ 标签页 ============
    def _create_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        self._create_log_tab()
        self._create_integration_tab()
        self._create_rules_tab()

        self._create_whitelist_tab()
        self._create_session_tab()
        self._create_audit_tab()
        self._create_config_tab()
        self._create_watermark_tab()

    # ---- 业务接入（把 guard 嵌入业务智能体的一站式入口） ----
    def _create_integration_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="🤝 业务接入")

        # 步骤引导
        guide = ("把 guard 嵌入你的业务智能体，只需 3 步：\n"
                 "① 获取业务调用密钥（点「生成密钥」自动生成并保存）\n"
                 "② 复制右侧接入代码到你的项目\n"
                 "③ 点「测试接入」验证连通与脱敏效果")
        tk.Label(tab, text=guide, bg='#e8f5e9', fg='#2e7d32', justify='left',
                 font=("Microsoft YaHei", 9), padx=10, pady=8).pack(fill='x', padx=10, pady=(10, 6))

        # 密钥区
        key_frame = tk.Frame(tab, bg='white')
        key_frame.pack(fill='x', padx=10, pady=4)
        tk.Label(key_frame, text="业务调用密钥 (guard_api_key):", bg='white',
                 font=("Microsoft YaHei", 9)).pack(side='left')
        self.integ_key_label = tk.Label(key_frame, text="", bg='#fff3e0', fg='#e65100',
                                        font=("Consolas", 9), padx=6, pady=3)
        self.integ_key_label.pack(side='left', padx=8)
        self._btn(key_frame, "🔑 生成密钥", self._gen_guard_key, bg='#9C27B0', width=10).pack(side='left', padx=4)
        self._btn(key_frame, "📋 复制密钥", self._copy_guard_key, bg='#607D8B', width=10).pack(side='left', padx=4)

        # 接入代码
        code_frame = tk.Frame(tab, bg='white')
        code_frame.pack(fill='both', expand=True, padx=10, pady=6)
        tk.Label(code_frame, text="接入代码（复制到你的业务项目，替换 my_llm 为你的智能体函数）：",
                 bg='white', font=("Microsoft YaHei", 9)).pack(anchor='w')
        self.integ_code = scrolledtext.ScrolledText(code_frame, height=10, font=("Consolas", 10),
                                                    bg='#1e1e1e', fg='#d4d4d4', wrap='none')
        self.integ_code.pack(fill='both', expand=True, pady=4)
        self._btn(code_frame, "📋 复制代码", self._copy_integ_code, bg='#2196F3', width=10).pack(anchor='w')

        # 测试区
        test_frame = tk.Frame(tab, bg='white')
        test_frame.pack(fill='x', padx=10, pady=6)
        self._btn(test_frame, "🧪 测试接入（输入审核+输出脱敏）", self._test_integration,
                  bg='#4CAF50', width=28).pack(side='left')
        self.integ_test_result = tk.Label(test_frame, text="", bg='white', fg='#333',
                                          font=("Microsoft YaHei", 9), justify='left', anchor='w')
        self.integ_test_result.pack(side='left', padx=10)

        self._update_integ_key_display()
        self._update_integ_code()

    def _update_integ_key_display(self):
        key = self.guard_key_var.get().strip()
        if key:
            self.integ_key_label.config(text=key[:16] + "…" if len(key) > 16 else key)
        else:
            self.integ_key_label.config(text="（未设置——点「生成密钥」自动创建）")

    def _update_integ_code(self):
        key = self.guard_key_var.get().strip()
        key_line = f'guard = Guard(api_key="{key}")' if key else 'guard = Guard()  # 服务端未设密钥时无需填写'
        code = (f'from guard_sdk import Guard\n'
                f'{key_line}\n'
                f'safe_llm = guard.wrap_llm(my_llm)   # my_llm 是你的业务智能体函数\n'
                f'reply = safe_llm("用户说的话")      # 返回已脱敏+水印的安全回复\n')
        self.integ_code.delete(1.0, tk.END)
        self.integ_code.insert(tk.END, code)

    def _gen_guard_key(self):
        """生成随机业务调用密钥并保存到服务端配置。"""
        import secrets
        if not self._check_service_running():
            messagebox.showwarning("警告", "服务未运行，无法保存密钥")
            return
        new_key = "sk-" + secrets.token_hex(16)
        self.guard_key_var.set(new_key)
        self._save_config()  # 保存全部配置（含新密钥）
        self._update_integ_key_display()
        self._update_integ_code()
        self._append_log("✅ 已生成新的业务调用密钥")

    def _copy_guard_key(self):
        key = self.guard_key_var.get().strip()
        if not key:
            messagebox.showwarning("提示", "请先生成密钥")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        self._append_log("✅ 业务调用密钥已复制")

    def _copy_integ_code(self):
        code = self.integ_code.get(1.0, tk.END).strip()
        if not code:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self._append_log("✅ 接入代码已复制")

    def _test_integration(self):
        """测试接入：调 /v1/guard 验证输入审核 + 输出脱敏。"""
        def task():
            try:
                headers = {"Content-Type": "application/json"}
                key = self.guard_key_var.get().strip()
                if key:
                    headers["X-Guard-Key"] = key
                # 输入审核（正常输入应放行）
                r1 = requests.post("http://127.0.0.1:8080/v1/guard",
                                   json={"session_id": "gui-test", "user_id": "u-gui",
                                         "action_type": "user_input", "content": "今天天气怎么样"},
                                   headers=headers, timeout=5).json()
                # 输出脱敏
                r2 = requests.post("http://127.0.0.1:8080/v1/guard",
                                   json={"session_id": "gui-test", "user_id": "u-gui",
                                         "action_type": "output",
                                         "output_content": "用户手机号 13212345678"},
                                   headers=headers, timeout=5).json()
                if r1.get("decision") == "allow" and r2.get("decision") == "allow":
                    safe = r2.get("safe_output", "")
                    # 去掉水印后展示
                    clean = safe.split("\u200b")[0]
                    self.root.after(0, lambda: self.integ_test_result.config(
                        text=f"✅ 连通正常 | 脱敏示例: {clean}", fg='green'))
                else:
                    self.root.after(0, lambda: self.integ_test_result.config(
                        text=f"⚠️ 异常: 输入={r1.get('decision')} 输出={r2.get('decision')}", fg='orange'))
            except Exception as e:
                self.root.after(0, lambda: self.integ_test_result.config(
                    text=f"❌ 连接失败: {e}（请先启动服务）", fg='red'))
        threading.Thread(target=task, daemon=True).start()

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

    # ---- 规则管理（合并：关键词/正则/NLP/审核触发词） ----
    def _create_rules_tab(self):
        tab = tk.Frame(self.notebook, bg='white')
        self.notebook.add(tab, text="📋 规则管理")

        toolbar = tk.Frame(tab, bg='white')
        toolbar.pack(fill='x', padx=5, pady=5)
        tk.Label(toolbar, text="类型:", bg='white').pack(side='left', padx=5)
        self.rule_type_var = tk.StringVar(value="关键词")
        ttk.Combobox(toolbar, textvariable=self.rule_type_var, state='readonly', width=12, values=[
            "关键词", "正则", "NLP-拦截", "NLP-警告", "NLP-放行", "审核触发词"
        ]).pack(side='left', padx=5)
        tk.Label(toolbar, text="内容:", bg='white').pack(side='left', padx=5)
        self.rule_entry = tk.Entry(toolbar, width=22)
        self.rule_entry.pack(side='left', padx=5)
        self._btn(toolbar, "➕ 添加", self._add_rule, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🔄 刷新", self._load_rules_async, bg='#2196F3').pack(side='left', padx=5)

        columns = ("类型", "内容", "动作", "状态")
        self.rule_tree = ttk.Treeview(tab, columns=columns, show="headings", height=14)
        for col in columns:
            self.rule_tree.heading(col, text=col)
            self.rule_tree.column(col, width=180)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.rule_tree.yview)
        self.rule_tree.configure(yscrollcommand=scroll.set)
        self.rule_tree.pack(side='left', fill='both', expand=True, padx=5, pady=5)
        scroll.pack(side='right', fill='y')

        action_frame = tk.Frame(tab, bg='white')
        action_frame.pack(fill='x', pady=(5, 0))
        self._btn(action_frame, "✅ 启用", lambda: self._toggle_rule(True), bg='#4CAF50').pack(side='left', padx=5)
        self._btn(action_frame, "❌ 禁用", lambda: self._toggle_rule(False), bg='#FF9800').pack(side='left', padx=5)
        self._btn(action_frame, "🗑 删除选中", self._delete_rule, bg='#f44336').pack(side='left', padx=5)

        # 自测与优化单独一行（避免与右侧说明/窗口宽度互相挤占）
        test_frame = tk.Frame(tab, bg='white')
        test_frame.pack(fill='x', pady=(0, 0))
        btn_selftest = self._btn(test_frame, "⚡ 规则回归", self._run_self_test, bg='#9C27B0')
        btn_selftest.pack(side='left', padx=5)
        ToolTip(btn_selftest, "快速体检（约1秒，不调用大模型）\n"
                              "只测规则层：638 个对抗样本，关键词/正则/触发词能否拦住\n"
                              "适合：改完规则后快速确认没破坏，日常随手跑")
        btn_optimize = self._btn(test_frame, "🧪 智能调优", self._run_optimize, bg='#FF6F00')
        btn_optimize.pack(side='left', padx=5)
        ToolTip(btn_optimize, "深度调优（约5分钟，含大模型判定）\n"
                              "完整链路：638 对抗样本走真实判定路径\n"
                              "自动提取安全触发词（误伤安全阀）+ 合并自定义样本\n"
                              "适合：换模型/业务样本变化时定期跑一次")
        btn_custom = self._btn(test_frame, "📥 自定义样本", self._manage_custom_samples, bg='#00897B')
        btn_custom.pack(side='left', padx=5)
        ToolTip(btn_custom, "接入你自己的业务语料\n"
                            "攻击样本 → 并入对抗测试（智能调优时自动合并）\n"
                            "正常样本 → 并入误伤测试（防止优化误伤你的业务语句）")
        # 启动自检：确认智能调优按钮已创建（排查"看不到按钮"问题）
        print("[DEBUG] 智能调优按钮已创建 (规则管理页, _create_rules_tab)")
        tk.Label(test_frame, text="⚡规则回归=快速体检；🧪智能调优=深度优化；📥自定义样本=接入业务语料（鼠标悬停看说明）",
                 bg='white', fg='#888', font=("Microsoft YaHei", 8)).pack(side='left', padx=10)

    def _run_optimize(self):
        """智能调优本地模型：检测量级 → 三项测试 → 自动写入安全触发词（异步+轮询进度）"""
        win = tk.Toplevel(self.root)
        win.title("🧪 智能调优（本地模型自动化调优）")
        win.geometry("720x480")
        win.configure(bg='white')
        text = scrolledtext.ScrolledText(win, font=("Consolas", 9), bg='#1e1e1e', fg='#d4d4d4')
        text.pack(fill='both', expand=True, padx=8, pady=(8, 4))
        text.insert(tk.END, "正在检测本地模型量级...\n")

        # 启动优化任务
        try:
            resp = requests.post(f"{API_BASE}/security/optimize", headers=admin_headers(), timeout=10)
            if resp.status_code != 200:
                text.insert(tk.END, f"启动失败: HTTP {resp.status_code}\n")
                return
            job_id = resp.json().get("job_id")
            text.insert(tk.END, f"优化任务已启动: {job_id}\n（后台执行，约 5 分钟，含攻击+误伤+触发词测试）\n")
        except Exception as e:
            text.insert(tk.END, f"启动异常: {e}\n")
            return

        def poll():
            try:
                r = requests.get(f"{API_BASE}/security/optimize/status", params={"job_id": job_id},
                                 headers=admin_headers(), timeout=10)
                if r.status_code != 200:
                    win.after(5000, poll)
                    return
                o = r.json().get("optimize", {})
                if not o.get("done"):
                    stage = o.get("stage", "测试中")
                    atk_total = o.get("attack_total", 0) or 0
                    fp_total = o.get("fp_total", 0) or 0
                    text.delete(1.0, tk.END)
                    text.insert(tk.END, f"🔄 优化进行中...（阶段: {stage}）\n"
                                       f"攻击测试: 已完成 {o.get('attack_before', 0)}/{atk_total} 拦截\n"
                                       f"误伤基线: {o.get('fp_before', 0)}/{fp_total}\n"
                                       f"（攻击测试约需 3-5 分钟，请耐心等待）\n")
                    win.after(5000, poll)
                    return
                # 完成
                model = o.get('model', {})
                lines = [
                    f"🎉 智能调优完成（耗时 {o.get('duration_sec', 0):.0f} 秒）\n",
                    f"🧠 本地模型: {model.get('name', '?')}（{model.get('param_b', '?')} 档）\n",
                    f"🛡 攻击拦截: {o.get('attack_before', 0)} → {o.get('attack_after', 0)} / {o.get('attack_total', 0)}\n",
                    f"✅ 误伤基线: {o.get('fp_before', 0)} / {o.get('fp_total', 0)}\n",
                    f"🔑 新增触发词: {len(o.get('new_keywords') or [])} 个\n",
                ]
                for kw in o.get('new_keywords') or []:
                    lines.append(f"    + {kw}\n")
                if o.get('skipped_words'):
                    lines.append(f"⏭ 跳过（会误伤）: {len(o['skipped_words'])} 个\n")
                    for s in o['skipped_words'][:10]:
                        lines.append(f"    - {s}\n")
                if o.get('error'):
                    lines.append(f"❌ {o['error']}\n")
                text.delete(1.0, tk.END)
                text.insert(tk.END, "".join(lines))
            except Exception as e:
                win.after(5000, poll)
        poll()

    def _manage_custom_samples(self):
        """自定义样本管理：查看/添加/删除攻击样本与正常样本（优化时自动合并）。"""
        win = tk.Toplevel(self.root)
        win.title("📥 自定义样本管理")
        win.geometry("760x520")
        win.configure(bg='white')

        # 说明
        tk.Label(win, text="把你自己业务里见过的攻击语句 / 正常语句加进来，智能调优时会自动合并测试。",
                 bg='white', fg='#555', font=("Microsoft YaHei", 9)).pack(anchor='w', padx=12, pady=(10, 2))

        # 添加区
        add_frame = tk.Frame(win, bg='white')
        add_frame.pack(fill='x', padx=12, pady=4)
        tk.Label(add_frame, text="语句:", bg='white', font=("Microsoft YaHei", 9)).pack(side='left')
        entry_var = tk.StringVar()
        entry = tk.Entry(add_frame, textvariable=entry_var, width=36, font=("Microsoft YaHei", 9))
        entry.pack(side='left', padx=5)
        tk.Label(add_frame, text="分类:", bg='white', font=("Microsoft YaHei", 9)).pack(side='left')
        cat_var = tk.StringVar(value="自定义攻击")
        tk.Entry(add_frame, textvariable=cat_var, width=10, font=("Microsoft YaHei", 9)).pack(side='left', padx=5)

        add_btns = tk.Frame(win, bg='white')
        add_btns.pack(fill='x', padx=12, pady=2)
        self._btn(add_btns, "➕ 添加为攻击样本", lambda: self._add_custom_sample("attack", entry_var, cat_var, win),
                  bg='#D32F2F', width=16).pack(side='left', padx=5)
        self._btn(add_btns, "➕ 添加为正常样本", lambda: self._add_custom_sample("normal", entry_var, cat_var, win),
                  bg='#4CAF50', width=16).pack(side='left', padx=5)
        tk.Label(add_btns, text="攻击=应被拦截的恶意语句；正常=不该被拦的业务语句", bg='white', fg='#888',
                 font=("Microsoft YaHei", 8)).pack(side='left', padx=8)

        # 列表区（两个子列表）
        list_frame = tk.Frame(win, bg='white')
        list_frame.pack(fill='both', expand=True, padx=12, pady=6)

        # 攻击样本列表
        atk_lf = tk.LabelFrame(list_frame, text="攻击样本（N 个）", bg='white', font=("Microsoft YaHei", 9, "bold"))
        atk_lf.pack(side='left', fill='both', expand=True, padx=(0, 4))
        self._atk_list = scrolledtext.ScrolledText(atk_lf, font=("Consolas", 9), height=10, bg='#FFF5F5')
        self._atk_list.pack(fill='both', expand=True, padx=4, pady=4)

        # 正常样本列表
        nor_lf = tk.LabelFrame(list_frame, text="正常样本（N 个）", bg='white', font=("Microsoft YaHei", 9, "bold"))
        nor_lf.pack(side='right', fill='both', expand=True, padx=(4, 0))
        self._nor_list = scrolledtext.ScrolledText(nor_lf, font=("Consolas", 9), height=10, bg='#F5FFF5')
        self._nor_list.pack(fill='both', expand=True, padx=4, pady=4)

        # 底部操作
        bottom = tk.Frame(win, bg='white')
        bottom.pack(fill='x', padx=12, pady=6)
        self._btn(bottom, "🔄 刷新列表", lambda: self._refresh_custom_samples(), bg='#2196F3', width=12).pack(side='left', padx=5)
        self._btn(bottom, "🗑 删除选中行", self._delete_custom_sample, bg='#f44336', width=12).pack(side='left', padx=5)
        tk.Label(bottom, text="选中要删除的行后点删除；格式: 序号. 内容", bg='white', fg='#888',
                 font=("Microsoft YaHei", 8)).pack(side='left', padx=8)

        self._refresh_custom_samples()

    def _refresh_custom_samples(self):
        """刷新自定义样本列表。"""
        try:
            r = requests.get(f"{API_BASE}/samples/custom", headers=admin_headers(), timeout=5)
            if r.status_code != 200:
                return
            d = r.json().get("samples", {})
            attacks = d.get("attacks", [])
            normals = d.get("normals", [])
            self._custom_samples = {"attacks": attacks, "normals": normals}
            if hasattr(self, '_atk_list'):
                self._atk_list.delete(1.0, tk.END)
                for i, a in enumerate(attacks):
                    self._atk_list.insert(tk.END, f"{i}. [{a.get('category','')}] {a.get('content','')}\n")
                self._nor_list.delete(1.0, tk.END)
                for i, n in enumerate(normals):
                    self._nor_list.insert(tk.END, f"{i}. {n}\n")
        except Exception:
            pass

    def _add_custom_sample(self, typ, entry_var, cat_var, win):
        content = entry_var.get().strip()
        if not content:
            messagebox.showinfo("提示", "请输入语句内容")
            return
        try:
            if typ == "attack":
                r = requests.post(f"{API_BASE}/samples/custom/attack",
                                  json={"content": content, "category": cat_var.get().strip() or "自定义攻击"},
                                  headers=admin_headers(True), timeout=5)
            else:
                r = requests.post(f"{API_BASE}/samples/custom/normal",
                                  json={"content": content},
                                  headers=admin_headers(True), timeout=5)
            if r.status_code == 200 and r.json().get("status") == "ok":
                entry_var.set("")
                self._append_log(f"📥 已添加自定义样本: {content[:30]}")
                self._refresh_custom_samples()
            else:
                messagebox.showerror("错误", f"添加失败: {r.text[:100]}")
        except Exception as e:
            messagebox.showerror("错误", f"添加异常: {e}")

    def _delete_custom_sample(self):
        """删除选中行：从当前光标所在行的编号解析索引。"""
        # 简化：从攻击列表/正常列表当前光标行读取编号
        for widget, typ in ((self._atk_list, "attack"), (self._nor_list, "normal")):
            try:
                line = widget.get("insert linestart", "insert lineend").strip()
                if not line:
                    continue
                idx_str = line.split(".")[0].strip()
                idx = int(idx_str)
                r = requests.delete(f"{API_BASE}/samples/custom", json={"index": idx, "type": typ},
                                    headers=admin_headers(True), timeout=5)
                if r.status_code == 200 and r.json().get("status") == "ok":
                    self._append_log(f"🗑 已删除自定义样本 #{idx}")
                    self._refresh_custom_samples()
                    return
            except Exception:
                continue
        messagebox.showinfo("提示", "请先把光标放在要删除的行上")

    def _run_self_test(self):
        """运行对抗自测，弹窗显示穿透报告。"""
        win = tk.Toplevel(self.root)
        win.title("⚡ 规则回归（对抗自测）")
        win.geometry("680x440")
        win.configure(bg='white')
        text = scrolledtext.ScrolledText(win, font=("Consolas", 9), bg='#1e1e1e', fg='#d4d4d4')
        text.pack(fill='both', expand=True, padx=8, pady=(8, 4))
        text.insert(tk.END, "正在运行对抗自测（规则层回归）...\n")

        btn_row = tk.Frame(win, bg='white')
        btn_row.pack(fill='x', padx=8, pady=(0, 8))
        self._btn(btn_row, "🛡 采纳穿透样本为规则", self._adopt_bypass_samples, bg='#9C27B0', width=22).pack(side='left')
        tk.Label(btn_row, text="穿透样本可自动转为审核触发词或关键词拦截，堵住绕过", bg='white', fg='#888',
                 font=("Microsoft YaHei", 8)).pack(side='left', padx=8)

        def task():
            try:
                resp = requests.post(f"{API_BASE}/security/self-test", headers=admin_headers(), timeout=30)
                if resp.status_code == 200:
                    d = resp.json()
                    self._last_penetrated = d.get('penetrated', [])
                    lines = [f"🛡 对抗自测完成：{d.get('total')} 个样本，规则层拦截 {d.get('blocked_by_rules')}，"
                             f"穿透 {d.get('penetrated_count')}\n"]
                    for p in d.get('penetrated', []):
                        lines.append(f"  ❌ [{p.get('category','')}] {p.get('content','')}\n")
                    if not d.get('penetrated'):
                        lines.append("  ✅ 全部样本均被规则层识别，无穿透\n")
                    lines.append(f"\n{d.get('note','')}\n")
                    content = "".join(lines)
                    win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, content)))
                else:
                    self._last_penetrated = []
                    win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, f"自测失败: HTTP {resp.status_code}\n")))
            except Exception as e:
                self._last_penetrated = []
                win.after(0, lambda: (text.delete(1.0, tk.END), text.insert(tk.END, f"自测异常: {e}\n")))
        threading.Thread(target=task, daemon=True).start()

    def _adopt_bypass_samples(self):
        """采纳穿透样本为规则：弹选择窗口（多选样本 + 选择添加类型）。"""
        samples = getattr(self, '_last_penetrated', [])
        if not samples:
            messagebox.showinfo("提示", "暂无穿透样本可采纳\n（先运行「🛡 对抗自测」）")
            return

        win = tk.Toplevel(self.root)
        win.title("🛡 采纳穿透样本为规则")
        win.geometry("700x480")
        win.configure(bg='white')

        # 类型选择
        type_frame = tk.Frame(win, bg='white')
        type_frame.pack(fill='x', padx=10, pady=(10, 4))
        tk.Label(type_frame, text="添加为：", bg='white', font=("Microsoft YaHei", 10)).pack(side='left')
        self.adopt_type_var = tk.StringVar(value="suspicious")
        tk.Radiobutton(type_frame, text="审核触发词（命中→触发LLM深度审核，推荐）", variable=self.adopt_type_var,
                       value="suspicious", bg='white', font=("Microsoft YaHei", 9)).pack(side='left', padx=6)
        tk.Radiobutton(type_frame, text="关键词拦截（命中→直接拦截）", variable=self.adopt_type_var,
                       value="keyword", bg='white', font=("Microsoft YaHei", 9)).pack(side='left', padx=6)

        # 样本多选列表（可滚动）
        list_frame = tk.Frame(win, bg='white')
        list_frame.pack(fill='both', expand=True, padx=10, pady=4)
        tk.Label(list_frame, text="选择要采纳的穿透样本（默认全选）：", bg='white',
                 font=("Microsoft YaHei", 9)).pack(anchor='w')
        canvas = tk.Canvas(list_frame, bg='white', highlightthickness=0)
        vbar = ttk.Scrollbar(list_frame, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg='white')
        canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        vbar.pack(side='right', fill='y')
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._adopt_vars = []
        for s in samples:
            v = tk.BooleanVar(value=True)
            self._adopt_vars.append(v)
            tk.Checkbutton(inner, text=f"[{s.get('category', '')}] {s.get('content', '')}",
                           variable=v, bg='white', anchor='w', font=("Consolas", 9),
                           justify='left').pack(fill='x', padx=4, pady=1)

        btn_frame = tk.Frame(win, bg='white')
        btn_frame.pack(fill='x', padx=10, pady=8)
        self._btn(btn_frame, "✅ 添加选中为规则", lambda: self._do_adopt(samples, win), bg='#4CAF50', width=18).pack(side='left')
        self._btn(btn_frame, "取消", win.destroy, bg='#9E9E9E', width=10).pack(side='left', padx=8)

    def _do_adopt(self, samples, win):
        """按选择把穿透样本逐个添加为规则。"""
        chosen = [s for s, v in zip(samples, self._adopt_vars) if v.get()]
        if not chosen:
            messagebox.showinfo("提示", "未选择任何样本")
            return
        typ = self.adopt_type_var.get()
        ok = 0
        fail = 0
        for s in chosen:
            content = s.get('content', '')
            if not content:
                continue
            try:
                if typ == 'suspicious':
                    r = requests.post(f"{API_BASE}/suspicious-keywords", json={"keyword": content},
                                      headers=admin_headers(True), timeout=3)
                else:
                    r = requests.post(f"{API_BASE}/rules", json={
                        "type": "keyword", "pattern": content,
                        "reason": f"对抗自测采纳: {s.get('category', '')}"
                    }, headers=admin_headers(True), timeout=3)
                if r.status_code == 200:
                    ok += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
        self._append_log(f"🛡 采纳完成: 成功 {ok} 条, 失败 {fail} 条（类型: {'审核触发词' if typ == 'suspicious' else '关键词拦截'}）")
        win.destroy()
        self._load_rules_async()  # 刷新规则管理页

    def _load_rules_async(self):
        def task():
            try:
                r1 = requests.get(f"{API_BASE}/rules", headers=admin_headers(), timeout=3)
                r2 = requests.get(f"{API_BASE}/nlp-rules", headers=admin_headers(), timeout=3)
                r3 = requests.get(f"{API_BASE}/suspicious-keywords", headers=admin_headers(), timeout=3)
                data = {"rules": [], "nlp": [], "sus": []}
                if r1.status_code == 200:
                    data["rules"] = r1.json().get("rules", [])
                if r2.status_code == 200:
                    data["nlp"] = r2.json().get("rules", [])
                if r3.status_code == 200:
                    data["sus"] = r3.json().get("keywords", [])
                total = len(data["rules"]) + len(data["nlp"]) + len(data["sus"])
                self.root.after(0, lambda: (self._update_rule_tree(data),
                                            self._append_log(f"✅ 规则已刷新: 共 {total} 条")))
                if r1.status_code == 401 or r2.status_code == 401 or r3.status_code == 401:
                    self.root.after(0, lambda: self._check_resp(r1))
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ 规则加载异常: {e}"))
        threading.Thread(target=task, daemon=True).start()

    def _update_rule_tree(self, data):
        for item in self.rule_tree.get_children():
            self.rule_tree.delete(item)
        for idx, r in enumerate(data.get("rules", [])):
            t = "关键词" if r.get("type") == "keyword" else ("正则" if r.get("type") == "regex" else r.get("type", ""))
            self.rule_tree.insert("", "end", iid=f"rules-{idx}", values=(t, r.get("pattern", ""), "直接拦截", "启用"))
        for idx, r in enumerate(data.get("nlp", [])):
            action_map = {"block": "拦截", "warning": "警告", "allow": "放行"}
            st = "启用" if r.get("enabled") else "禁用"
            self.rule_tree.insert("", "end", iid=f"nlp-{idx}",
                                  values=("NLP规则", r.get("name", ""), action_map.get(r.get("action", ""), r.get("action", "")), st))
        for idx, w in enumerate(data.get("sus", [])):
            self.rule_tree.insert("", "end", iid=f"sus-{idx}", values=("审核触发词", w, "触发LLM审核", "启用"))

    def _add_rule(self):
        pattern = self.rule_entry.get().strip()
        if not pattern:
            messagebox.showwarning("提示", "请输入内容")
            return
        rule_type = self.rule_type_var.get()
        try:
            if rule_type == "关键词":
                resp = requests.post(f"{API_BASE}/rules", json={
                    "type": "keyword", "pattern": pattern, "reason": f"命中关键词: {pattern}"
                }, headers=admin_headers(True), timeout=3)
            elif rule_type == "正则":
                resp = requests.post(f"{API_BASE}/rules", json={
                    "type": "regex", "pattern": pattern, "reason": f"命中正则: {pattern}"
                }, headers=admin_headers(True), timeout=3)
            elif rule_type.startswith("NLP-"):
                action = {"NLP-拦截": "block", "NLP-警告": "warning", "NLP-放行": "allow"}[rule_type]
                resp = requests.post(f"{API_BASE}/nlp-rules", json={
                    "name": pattern, "description": pattern, "action": action
                }, headers=admin_headers(True), timeout=3)
            elif rule_type == "审核触发词":
                resp = requests.post(f"{API_BASE}/suspicious-keywords", json={"keyword": pattern},
                                     headers=admin_headers(True), timeout=3)
            else:
                return
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log(f"✅ 已添加[{rule_type}] {pattern}")
                self.rule_entry.delete(0, tk.END)
                self._load_rules_async()
            else:
                messagebox.showerror("错误", f"添加失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"添加失败: {e}")

    def _delete_rule(self):
        selected = self.rule_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条规则")
            return
        if not messagebox.askyesno("确认", "确定删除选中的规则吗？"):
            return
        iid = selected[0]
        try:
            if iid.startswith("rules-"):
                resp = requests.delete(f"{API_BASE}/rules/{iid.split('-')[1]}", headers=admin_headers(), timeout=3)
            elif iid.startswith("nlp-"):
                resp = requests.delete(f"{API_BASE}/nlp-rules/{iid.split('-')[1]}", headers=admin_headers(), timeout=3)
            elif iid.startswith("sus-"):
                resp = requests.delete(f"{API_BASE}/suspicious-keywords/{iid.split('-')[1]}", headers=admin_headers(), timeout=3)
            else:
                return
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ 规则已删除")
                self._load_rules_async()
            else:
                messagebox.showerror("错误", f"删除失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"删除失败: {e}")

    def _toggle_rule(self, enable):
        selected = self.rule_tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一条规则")
            return
        iid = selected[0]
        if not iid.startswith("nlp-"):
            messagebox.showinfo("提示", "仅 NLP 规则支持启用/禁用")
            return
        try:
            resp = requests.put(f"{API_BASE}/nlp-rules/{iid.split('-')[1]}/toggle", headers=admin_headers(), timeout=3)
            if not self._check_resp(resp):
                return
            if resp.status_code == 200:
                self._append_log("✅ NLP规则状态已切换")
                self._load_rules_async()
            else:
                messagebox.showerror("错误", f"操作失败: {resp.text}")
        except Exception as e:
            messagebox.showerror("错误", f"操作失败: {e}")


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
        self._btn(toolbar, "📤 导出报表", self._export_audit, bg='#4CAF50').pack(side='left', padx=5)
        self._btn(toolbar, "🔒 校验完整性", self._verify_audit, bg='#FF9800').pack(side='left', padx=5)
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

    def _export_audit(self):
        """导出审计日志为 CSV（Excel 直接打开）。"""
        try:
            resp = requests.get(f"{API_BASE}/logs/export", headers=admin_headers(), timeout=10)
            if resp.status_code == 200:
                path = os.path.join(SCRIPT_DIR, "audit-export.csv")
                with open(path, "wb") as f:
                    f.write(resp.content)
                self._append_log(f"✅ 报表已导出: {path}")
                if messagebox.askyesno("导出成功", f"已保存到 {path}\n是否打开？"):
                    os.startfile(path)
            elif not self._check_resp(resp):
                return
            else:
                messagebox.showerror("错误", f"导出失败: {resp.status_code}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _verify_audit(self):
        """校验审计日志哈希链完整性（防篡改）。"""
        def task():
            try:
                resp = requests.get(f"{API_BASE}/logs/verify", headers=admin_headers(), timeout=10)
                if resp.status_code == 200:
                    d = resp.json()
                    if d.get('valid'):
                        msg = f"✅ 审计日志完整（校验 {d.get('checked')} 条，无篡改）"
                    else:
                        msg = f"⚠️ 检测到 {d.get('broken')} 条被篡改！"
                    self.root.after(0, lambda: (self._append_log(msg),
                                                messagebox.showinfo('完整性校验', msg)))
                elif not self._check_resp(resp):
                    return
            except Exception as e:
                self.root.after(0, lambda: self._append_log(f"❌ 校验失败: {e}"))
        threading.Thread(target=task, daemon=True).start()

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

        # 滚动容器（配置项较多，支持滚轮滚动）
        canvas = tk.Canvas(tab, bg='white', highlightthickness=0)
        vbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        vbar.pack(side='right', fill='y')

        frame = tk.Frame(canvas, bg='white')
        canvas.create_window((0, 0), window=frame, anchor='nw')
        frame.columnconfigure(1, weight=1)


        # 内容尺寸变化时更新滚动区域
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        # 鼠标进入本页时才劫持滚轮，避免影响其他标签页
        def _bind_wheel(_e):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _unbind_wheel(_e):
            canvas.unbind_all("<MouseWheel>")
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        dp_label = tk.Label(frame, text="差分隐私:", bg='white', font=("Microsoft YaHei", 10))
        dp_label.grid(row=1, column=0, sticky='w', pady=6)
        dp_check = tk.Checkbutton(frame, variable=self.dp_var, bg='white',
                                  font=("Microsoft YaHei", 10))
        dp_check.grid(row=1, column=1, sticky='w', pady=6)
        ToolTip(dp_label, "差分隐私（Differential Privacy）\n"
                          "一种隐私保护技术：在查询/统计结果中加入受控噪声，\n"
                          "使外部无法从输出反推单个用户的数据。\n\n"
                          "本项目当前为预留能力：开启后对输出统计类数据加入噪声。\n"
                          "注意：噪声会降低统计结果精确度，一般仅对聚合统计类输出启用，\n"
                          "普通业务对话建议保持关闭。")
        ToolTip(dp_check, "差分隐私（Differential Privacy）\n"
                          "在统计结果中加入受控噪声，防止从输出反推单个用户数据。\n"
                          "当前为预留能力，普通业务建议关闭（噪声会降低结果精确度）。")

        tk.Label(frame, text="限流速率（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky='w', pady=6)
        tk.Entry(frame, textvariable=self.rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=2, column=1, sticky='w', pady=6)

        tk.Label(frame, text="默认脱敏级别:", bg='white', font=("Microsoft YaHei", 10)).grid(row=3, column=0, sticky='w', pady=6)
        ttk.Combobox(frame, textvariable=self.level_var, values=["partial", "full", "minimal"],
                     width=10, state='readonly').grid(row=3, column=1, sticky='w', pady=6)

        tk.Label(frame, text="会话超时（分钟）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=4, column=0, sticky='w', pady=6)
        tk.Entry(frame, textvariable=self.timeout_var, width=10, font=("Microsoft YaHei", 10)).grid(row=4, column=1, sticky='w', pady=6)

        # 反刷评配置
        tk.Label(frame, text="🛡️ 反刷评（评论区 AI 机器人防御）", bg='white', font=("Microsoft YaHei", 10, "bold"),
                 fg='#1976D2').grid(row=5, column=0, columnspan=2, sticky='w', pady=(10, 2))

        tk.Label(frame, text="内容去重:", bg='white', font=("Microsoft YaHei", 10)).grid(row=6, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.dup_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=6, column=1, sticky='w', pady=4)

        tk.Label(frame, text="去重窗口（分钟）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=7, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.dup_window_var, width=10, font=("Microsoft YaHei", 10)).grid(row=7, column=1, sticky='w', pady=4)

        tk.Label(frame, text="账号限流（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=8, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.user_rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=8, column=1, sticky='w', pady=4)

        tk.Label(frame, text="IP 限流（次/秒）:", bg='white', font=("Microsoft YaHei", 10)).grid(row=9, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.ip_rate_var, width=10, font=("Microsoft YaHei", 10)).grid(row=9, column=1, sticky='w', pady=4)

        tk.Label(frame, text="账号信誉分:", bg='white', font=("Microsoft YaHei", 10)).grid(row=10, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.rep_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=10, column=1, sticky='w', pady=4)

        tk.Label(frame, text="业务调用密钥:", bg='white', font=("Microsoft YaHei", 10)).grid(row=11, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.guard_key_var, width=24, show="*",
                 font=("Microsoft YaHei", 10)).grid(row=11, column=1, sticky='w', pady=4)

        # 安全审核 LLM（可插拔判定引擎）
        tk.Label(frame, text="🤖 安全审核 LLM（判定引擎）", bg='white', font=("Microsoft YaHei", 10, "bold"),
                 fg='#1976D2').grid(row=12, column=0, columnspan=2, sticky='w', pady=(10, 2))
        tk.Label(frame, text="模式:", bg='white', font=("Microsoft YaHei", 10)).grid(row=13, column=0, sticky='w', pady=4)
        self.llm_mode_combo = ttk.Combobox(frame, textvariable=self.llm_mode_var,
                                           values=["local", "cloud", "hybrid"],
                                           width=8, state='readonly')
        self.llm_mode_combo.grid(row=13, column=1, sticky='w', pady=4)
        self.llm_mode_combo.bind("<<ComboboxSelected>>", lambda e: self._update_mode_tip())
        # 模式优缺点动态说明（选择即显示）
        self.mode_tip_label = tk.Label(frame, text="", bg='#FFF8E1', fg='#5D4037', justify='left',
                                       font=("Microsoft YaHei", 9), padx=8, pady=6, wraplength=520)
        self.mode_tip_label.grid(row=14, column=0, columnspan=2, sticky='we', pady=(0, 6))
        self._update_mode_tip()
        tk.Label(frame, text="本地接口:", bg='white', font=("Microsoft YaHei", 10)).grid(row=15, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.llm_url_var, width=30, font=("Microsoft YaHei", 10)).grid(row=15, column=1, sticky='w', pady=4)
        tk.Label(frame, text="本地模型:", bg='white', font=("Microsoft YaHei", 10)).grid(row=16, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.llm_model_var, width=24, font=("Microsoft YaHei", 10)).grid(row=16, column=1, sticky='w', pady=4)
        tk.Label(frame, text="云端接口:", bg='white', font=("Microsoft YaHei", 10)).grid(row=17, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.cloud_url_var, width=30, font=("Microsoft YaHei", 10)).grid(row=17, column=1, sticky='w', pady=4)
        tk.Label(frame, text="云端模型:", bg='white', font=("Microsoft YaHei", 10)).grid(row=18, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.cloud_model_var, width=24, font=("Microsoft YaHei", 10)).grid(row=18, column=1, sticky='w', pady=4)
        tk.Label(frame, text="云端 Key:", bg='white', font=("Microsoft YaHei", 10)).grid(row=19, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.cloud_key_var, width=24, show="*",
                 font=("Microsoft YaHei", 10)).grid(row=19, column=1, sticky='w', pady=4)
        tk.Label(frame, text="判定引擎故障策略:", bg='white', font=("Microsoft YaHei", 10)).grid(row=20, column=0, sticky='w', pady=4)
        self.fail_policy_combo = ttk.Combobox(frame, textvariable=self.fail_policy_var,
                                              values=["fail-closed", "fail-open"],
                                              width=12, state='readonly')
        self.fail_policy_combo.grid(row=20, column=1, sticky='w', pady=4)
        self.fail_policy_combo.bind("<<ComboboxSelected>>", lambda e: self._update_fail_tip())
        # 故障策略动态说明（选择即显示）
        self.fail_tip_label = tk.Label(frame, text="", bg='#E3F2FD', fg='#0D47A1', justify='left',
                                       font=("Microsoft YaHei", 9), padx=8, pady=4, wraplength=520)
        self.fail_tip_label.grid(row=20, column=0, columnspan=2, sticky='we', pady=(0, 6))
        self._update_fail_tip()

        # 差分隐私 / 行为分析 / 话术判断
        # 🔑 快捷配置云端审核模型（弹窗只需填 Key）
        quick_btn = self._btn(frame, "🔑 快速配置云端审核模型（只需填 Key）", self._quick_cloud_setup,
                              bg='#9C27B0', width=28)
        quick_btn.grid(row=21, column=0, columnspan=2, sticky='w', pady=(8, 2))
        ToolTip(quick_btn, "快捷配置云端判定模型：\n"
                           "· 选择模式（hybrid=本地初筛+云端终审，推荐）\n"
                           "· 填写云端 API Key（默认已预填 DeepSeek 接口与模型）\n"
                           "· 保存即生效（热加载，无需重启）\n"
                           "需要换其他云端（通义/GLM/Kimi/OpenAI）：\n"
                           "请在上方云端接口/云端模型/云端Key 三栏填写对应值")

        tk.Label(frame, text="差分隐私ε:", bg='white', font=("Microsoft YaHei", 10)).grid(row=22, column=0, sticky='w', pady=4)
        tk.Entry(frame, textvariable=self.dp_eps_var, width=10, font=("Microsoft YaHei", 10)).grid(row=22, column=1, sticky='w', pady=4)
        tk.Label(frame, text="机器行为分析:", bg='white', font=("Microsoft YaHei", 10)).grid(row=23, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.behavior_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=23, column=1, sticky='w', pady=4)
        tk.Label(frame, text="LLM话术判断:", bg='white', font=("Microsoft YaHei", 10)).grid(row=24, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.style_judge_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=24, column=1, sticky='w', pady=4)
        tk.Label(frame, text="低风险自动改写:", bg='white', font=("Microsoft YaHei", 10)).grid(row=25, column=0, sticky='w', pady=4)
        tk.Checkbutton(frame, variable=self.rewrite_var, bg='white',
                       font=("Microsoft YaHei", 10)).grid(row=25, column=1, sticky='w', pady=4)

        tk.Label(frame, text="", bg='white').grid(row=26, column=0, pady=4)
        self._btn(frame, "💾 保存全部配置", self._save_config, bg='#4CAF50', width=16).grid(row=27, column=0, columnspan=2, sticky='w', pady=6)
        self._btn(frame, "🔄 从服务端刷新", lambda: self._sync_config_from_server(silent=False),
                  bg='#2196F3', width=16).grid(row=27, column=1, sticky='w', pady=6)

        tip = ("说明：\n"
               "· 差分隐私：开启后对输出统计数字加入 Laplace 噪声（仅建议聚合统计输出启用）\n"
               "    ε 越大噪声越小（精度高）；ε 越小隐私保护越强\n"
               "· 限流速率：每个会话每秒最多请求数\n"
               "· 脱敏级别：partial 部分脱敏 / full 完整（管理员） / minimal 最小化\n"
               "· 会话超时：风险积分缓存保留时长（分钟）\n"
               "· 内容去重：相同/高度相似评论在窗口内重复出现直接拦截（专杀刷屏）\n"
               "· 账号/IP 限流：按 user_id 与来源 IP 聚合限流，堵住分布式刷评\n"
               "· 账号信誉分：违规跨会话累计，低信誉账号直接降权\n"
               "· 机器行为分析：请求间隔过于均匀 → 判定为自动化并拦截（真人点击随机）\n"
               "· LLM话术判断：审核模型额外判断机械化刷屏话术（对明显重复才判，默认关）\n"
               "· 低风险自动改写：命中敏感词的内容自动替换为***继续对话（返回 rewritten_input）\n"
               "· 业务调用密钥：业务系统调 /v1/guard 时需携带 X-Guard-Key（留空则不鉴权）\n"
               "· 安全审核 LLM（可插拔）：local=本地模型 / cloud=云端 / hybrid=本地初筛+云端终审\n"
               "    本地用 Ollama（OpenAI 兼容端点）；云端填接口+模型+Key（如 deepseek-chat）\n"
               "    失败策略：fallback=降级到另一引擎 / allow=放行 / block=拦截（fail-closed）\n"
               "· 配置修改后服务端自动热加载，无需重启")
        tk.Label(frame, text=tip, bg='#f0f7ff', fg='#555', justify='left',
                 font=("Microsoft YaHei", 9), padx=10, pady=8).grid(row=27, column=0, columnspan=2, sticky='we', pady=10)

    def _quick_cloud_setup(self):
        """弹窗：快速配置云端判定模型（模式 + 云端 Key）。"""
        win = tk.Toplevel(self.root)
        win.title("🔑 快速配置云端审核模型")
        win.geometry("460x240")
        win.configure(bg='white')
        f = tk.Frame(win, bg='white'); f.pack(fill='both', expand=True, padx=20, pady=15)
        tk.Label(f, text="选择模式:", bg='white', font=("Microsoft YaHei", 10)).grid(row=1, column=0, sticky='w', pady=6)
        mode_var = tk.StringVar(value=self.llm_mode_var.get())
        ttk.Combobox(f, textvariable=mode_var, values=["local", "cloud", "hybrid"],
                     width=10, state='readonly').grid(row=1, column=1, sticky='w', pady=6)
        tk.Label(f, text="云端 API Key:", bg='white', font=("Microsoft YaHei", 10)).grid(row=2, column=0, sticky='w', pady=6)
        key_entry = tk.Entry(f, textvariable=self.cloud_key_var, width=32, show="*", font=("Microsoft YaHei", 10))
        key_entry.grid(row=2, column=1, sticky='w', pady=6)
        tk.Label(f, text="云端接口/模型已预填（DeepSeek），保存即生效、无需重启。", bg='white',
                 fg='#888', font=("Microsoft YaHei", 8), justify='left').grid(row=3, column=0, columnspan=2, sticky='w', pady=4)
        def do_save():
            if not mode_var.get().strip():
                messagebox.showwarning("提示", "请选择模式"); return
            if mode_var.get() != "local" and not self.cloud_key_var.get().strip():
                if not messagebox.askyesno("确认", "云端模式未填 Key 将无法调用云端，仍要保存吗？"):
                    return
            self.llm_mode_var.set(mode_var.get())
            self._save_config()
            win.destroy()
        self._btn(f, "💾 保存", do_save, bg='#4CAF50', width=12).grid(row=4, column=0, columnspan=2, sticky='w', pady=10)

    def _update_mode_tip(self):
        """按当前选择的判定引擎模式，动态显示优缺点与适用场景。"""
        tips = {
            "local": "【本地模式】用本地 Ollama 模型审核\n"
                     "✔ 优点：数据不出网（隐私/合规安全）、零 API 成本、断网可用、无 Key 泄露风险\n"
                     "✘ 缺点：判定力受本地模型与显存限制（7B 对复杂攻击有盲区）、需自己维护模型\n"
                     "▶ 适合：数据敏感（金融/医疗/政务）、离线或内网环境",
            "cloud": "【云端模式】用云端 API（OpenAI 兼容）审核\n"
                     "✔ 优点：判定能力最强、模型免维护自动升级、响应快\n"
                     "✘ 缺点：用户内容出网（隐私/合规风险，需评估）、按量付费、依赖网络与供应商可用性、Key 泄露会被盗刷\n"
                     "▶ 适合：判定力优先、数据敏感性低（客服/社区）、预算充足",
            "hybrid": "【混合模式】本地初筛 + 云端终审（双保险）\n"
                      "✔ 优点：隐私与能力平衡——本地先判，识别到风险直接拦（大多数据不出网），本地判安全才升级云端复核\n"
                      "✘ 缺点：可疑请求两次调用更慢、需同时配置两个引擎、云端不可达时依赖失败策略兜底\n"
                      "▶ 适合：兼顾隐私与判定力的场景（推荐默认）",
        }
        self.mode_tip_label.config(text=tips.get(self.llm_mode_var.get(), ""))

    def _update_fail_tip(self):
        """按当前选择的判定引擎故障策略，动态显示含义。"""
        tips = {
            "fail-closed": "【故障拦截（推荐）】判定引擎（本地/云端）不可用时 → 直接拦截，宁严勿松。\n"
                           "▶ 适合：安全优先场景——模型挂了宁可不响应，也不放行可疑内容",
            "fail-open": "【故障放行】判定引擎（本地/云端）不可用时 → 直接放行，保证业务不中断。\n"
                         "▶ 适合：可用性优先场景——宁可漏判，也不能让正常业务被模型故障卡住",
        }
        self.fail_tip_label.config(text=tips.get(self.fail_policy_var.get(), ""))

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
