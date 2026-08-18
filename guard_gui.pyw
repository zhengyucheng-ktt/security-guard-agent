import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
import threading
import time

# ============================================================
# 配置
# ============================================================

API_BASE = "http://localhost:8080/admin/api"

# ============================================================
# 主窗口
# ============================================================

class GuardConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🛡️ 守护智能体 - 配置面板")
        self.root.geometry("500x480")
        self.root.resizable(False, False)
        self.root.configure(bg='#f5f5f5')

        self.create_widgets()
        self.load_config()

    def create_widgets(self):
        # 标题
        title = tk.Label(self.root, text="🛡️ 安全交互守护智能体", font=("Microsoft YaHei", 16, "bold"), bg='#f5f5f5', fg='#333')
        title.pack(pady=(20, 5))

        subtitle = tk.Label(self.root, text="配置面板", font=("Microsoft YaHei", 10), bg='#f5f5f5', fg='#999')
        subtitle.pack(pady=(0, 20))

        # 配置卡片
        card = tk.Frame(self.root, bg='white', relief='flat', highlightthickness=1, highlightcolor='#ddd')
        card.pack(padx=30, pady=5, fill='both')

        # ---- 差分隐私开关 ----
        row1 = tk.Frame(card, bg='white')
        row1.pack(fill='x', padx=20, pady=12)

        tk.Label(row1, text="🔢 差分隐私降噪", font=("Microsoft YaHei", 11, "bold"), bg='white').pack(side='left')
        tk.Label(row1, text="对统计数字添加噪声，保护隐私", font=("Microsoft YaHei", 9), bg='white', fg='#999').pack(side='left', padx=(10,0))

        self.dp_var = tk.BooleanVar()
        dp_switch = tk.Checkbutton(row1, variable=self.dp_var, command=self.on_dp_change, bg='white')
        dp_switch.pack(side='right')

        # ---- 限流阈值 ----
        row2 = tk.Frame(card, bg='white')
        row2.pack(fill='x', padx=20, pady=12)

        tk.Label(row2, text="🚦 限流阈值", font=("Microsoft YaHei", 11, "bold"), bg='white').pack(side='left')
        tk.Label(row2, text="次/秒", font=("Microsoft YaHei", 9), bg='white', fg='#999').pack(side='right')

        self.rate_var = tk.StringVar(value="10")
        rate_entry = tk.Entry(row2, textvariable=self.rate_var, width=8, font=("Microsoft YaHei", 10), justify='center')
        rate_entry.pack(side='right', padx=(0, 5))

        # ---- 默认脱敏级别 ----
        row3 = tk.Frame(card, bg='white')
        row3.pack(fill='x', padx=20, pady=12)

        tk.Label(row3, text="🔒 默认脱敏级别", font=("Microsoft YaHei", 11, "bold"), bg='white').pack(side='left')
        tk.Label(row3, text="新用户默认策略", font=("Microsoft YaHei", 9), bg='white', fg='#999').pack(side='left', padx=(10,0))

        self.level_var = tk.StringVar(value="partial")
        level_combo = ttk.Combobox(row3, textvariable=self.level_var, values=["full", "partial", "minimal"], width=10, state="readonly")
        level_combo.pack(side='right')

        # ---- 会话超时 ----
        row4 = tk.Frame(card, bg='white')
        row4.pack(fill='x', padx=20, pady=12)

        tk.Label(row4, text="⏱️ 会话超时", font=("Microsoft YaHei", 11, "bold"), bg='white').pack(side='left')
        tk.Label(row4, text="分钟", font=("Microsoft YaHei", 9), bg='white', fg='#999').pack(side='right')

        self.timeout_var = tk.StringVar(value="30")
        timeout_entry = tk.Entry(row4, textvariable=self.timeout_var, width=8, font=("Microsoft YaHei", 10), justify='center')
        timeout_entry.pack(side='right', padx=(0, 5))

        # ---- 保存按钮 ----
        save_btn = tk.Button(self.root, text="💾 保存配置", command=self.save_config, font=("Microsoft YaHei", 11), bg='#4CAF50', fg='white', width=20, height=1, relief='flat')
        save_btn.pack(pady=20)

        # ---- 状态信息 ----
        status_frame = tk.Frame(self.root, bg='#f5f5f5')
        status_frame.pack(fill='x', padx=30, pady=(0, 10))

        self.status_label = tk.Label(status_frame, text="🔄 加载配置中...", font=("Microsoft YaHei", 10), bg='#f5f5f5', fg='#666')
        self.status_label.pack(side='left')

        self.redis_label = tk.Label(status_frame, text="🔴 Redis: 未知", font=("Microsoft YaHei", 10), bg='#f5f5f5', fg='#666')
        self.redis_label.pack(side='right')

        # 自动刷新状态
        self.start_status_monitor()

    # ============================================================
    # 功能函数
    # ============================================================

    def load_config(self):
        try:
            resp = requests.get(f"{API_BASE}/config", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                config = data.get('config', {})
                self.dp_var.set(config.get('enable_differential_privacy', False))
                self.rate_var.set(str(config.get('rate_limit', 10)))
                self.level_var.set(config.get('default_level', 'partial'))
                self.timeout_var.set(str(config.get('session_timeout', 30)))
                self.update_status("✅ 配置已加载", 'green')
                self.check_redis()
            else:
                self.update_status("⚠️ 服务未响应", 'orange')
        except requests.exceptions.ConnectionError:
            self.update_status("❌ 无法连接服务 (请确保服务已启动)", 'red')
        except Exception as e:
            self.update_status(f"❌ 加载失败: {e}", 'red')

    def save_config(self):
        config = {
            'enable_differential_privacy': self.dp_var.get(),
            'rate_limit': int(self.rate_var.get() or 10),
            'default_level': self.level_var.get(),
            'session_timeout': int(self.timeout_var.get() or 30)
        }

        try:
            resp = requests.put(f"{API_BASE}/config", json=config, timeout=3)
            if resp.status_code == 200:
                messagebox.showinfo("成功", "✅ 配置已保存并生效")
                self.update_status("✅ 配置已保存", 'green')
            else:
                messagebox.showerror("错误", f"保存失败: {resp.text}")
        except requests.exceptions.ConnectionError:
            messagebox.showerror("错误", "❌ 无法连接服务")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {e}")

    def on_dp_change(self):
        # 开关变化时自动保存
        self.save_config()

    def update_status(self, msg, color='#666'):
        self.status_label.config(text=msg, fg=color)

    def check_redis(self):
        try:
            resp = requests.get(f"{API_BASE}/sessions", timeout=2)
            if resp.status_code == 200:
                self.redis_label.config(text="🟢 Redis: 已连接", fg='green')
            else:
                self.redis_label.config(text="🟡 Redis: 异常", fg='orange')
        except:
            self.redis_label.config(text="🔴 Redis: 未连接", fg='red')

    def start_status_monitor(self):
        def monitor():
            while True:
                try:
                    resp = requests.get(f"{API_BASE}/config", timeout=2)
                    if resp.status_code == 200:
                        self.root.after(0, lambda: self.update_status("✅ 服务运行中", 'green'))
                        self.root.after(0, self.check_redis)
                    else:
                        self.root.after(0, lambda: self.update_status("⚠️ 服务异常", 'orange'))
                except:
                    self.root.after(0, lambda: self.update_status("❌ 服务未响应", 'red'))
                time.sleep(10)

        threading.Thread(target=monitor, daemon=True).start()


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = GuardConfigGUI(root)
    root.mainloop()