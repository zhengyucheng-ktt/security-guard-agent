#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Security Guard Agent - 业务接入 SDK（黑箱版）
================================================
面向非技术/初级用户：不需要理解 action_type、session、令牌等内部机制，
几行代码即可让业务智能体获得完整防护（输入审核 / 工具防护 / 输出脱敏水印）。

最简用法：
    from guard_sdk import Guard
    guard = Guard(api_key="你的密钥")        # 默认连接 http://127.0.0.1:8080

    # 方式一：一行包装你的 LLM 函数（自动完成 输入审核→LLM→工具防护→输出审核）
    safe_llm = guard.wrap_llm(my_llm_function)
    reply = safe_llm("用户说的话")

    # 方式二：分环节手动控制
    guard.check_input("用户说的话")            # 违规会抛出 GuardBlocked
    safe = guard.review_output("模型回复")      # 返回脱敏+水印后的安全文本

说明：
- 未配置 api_key 时（guard 服务端 guard_api_key 为空）自动免密钥直连
- 所有拦截都会抛出 GuardBlocked（带拦截原因），业务侧按需处理
"""

import os
import uuid

import requests


class GuardBlocked(Exception):
    """guard 拦截异常：message 为拦截原因，可安全展示给用户。"""

    def __init__(self, reason, detail=None):
        super().__init__(reason or "请求被安全策略拦截")
        self.reason = reason
        self.detail = detail or {}


class Guard:
    """黑箱风控客户端。

    参数：
        url        guard 服务地址（默认 http://127.0.0.1:8080）
        api_key    业务调用密钥（对应服务端配置 guard_api_key；服务端留空则不用填）
        timeout    请求超时秒数
        auto_session  为 True 时自动管理会话/用户标识（基础用户无需关心）
    """

    def __init__(self, url="http://127.0.0.1:8080", api_key=None, timeout=20, auto_session=True):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.auto_session = auto_session
        self._session_id = f"auto-{uuid.uuid4().hex[:12]}"
        self._user_id = "default-user"
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-Guard-Key"] = api_key

    # ================= 会话管理（自动模式无需调用） =================

    def new_session(self, session_id=None, user_id=None):
        """开启新会话（自动模式下可选调用）。"""
        self._session_id = session_id or f"auto-{uuid.uuid4().hex[:12]}"
        if user_id:
            self._user_id = user_id
        return self

    def _ids(self, session_id, user_id):
        if not self.auto_session:
            return session_id, user_id
        return session_id or self._session_id, user_id or self._user_id

    # ================= 底层调用 =================

    def _call(self, action_type, session_id, user_id, **kw):
        body = {"session_id": session_id, "user_id": user_id, "action_type": action_type}
        body.update(kw)
        try:
            r = requests.post(f"{self.url}/v1/guard", json=body,
                              headers=self._headers, timeout=self.timeout)
        except requests.ConnectionError:
            raise GuardBlocked("无法连接 guard 服务", {"hint": "请先启动服务（go run main.go 或 双击 启动GUI.bat）"})
        except requests.Timeout:
            raise GuardBlocked("guard 服务响应超时", {"hint": "请检查服务状态"})
        try:
            data = r.json()
        except ValueError:
            raise GuardBlocked(f"guard 返回异常（HTTP {r.status_code}）", {"raw": r.text[:200]})
        if r.status_code == 401:
            raise GuardBlocked(data.get("error", "密钥无效"), {"hint": "检查 api_key 是否与服务端 guard_api_key 一致"})
        if data.get("decision") == "block":
            raise GuardBlocked(data.get("block_reason"), data)
        return data

    # ================= 分环节接口（语义化） =================

    def check_input(self, content, session_id=None, user_id=None):
        """① 输入审核：用户输入进 LLM 之前调用；违规抛 GuardBlocked。"""
        sid, uid = self._ids(session_id, user_id)
        self._call("user_input", sid, uid, content=content)

    def check_tool_call(self, tool_name, tool_params=None, session_id=None, user_id=None):
        """③ 工具调用审核：返回 JWT 授权令牌（供工具端 validate_token 自证）。"""
        sid, uid = self._ids(session_id, user_id)
        data = self._call("tool_call", sid, uid,
                          tool_name=tool_name, tool_params=tool_params or {})
        return data.get("tool_token", "")

    def check_tool_result(self, content, session_id=None, user_id=None):
        """④ 工具返回审核：工具返回内容进模型上下文前调用（防间接注入）。"""
        sid, uid = self._ids(session_id, user_id)
        self._call("tool_result", sid, uid, output_content=content)

    def review_output(self, content, session_id=None, user_id=None):
        """⑤ 输出审核：返回脱敏+水印后的安全文本（safe_output）。"""
        sid, uid = self._ids(session_id, user_id)
        data = self._call("output", sid, uid, output_content=content)
        return data.get("safe_output", content)

    def validate_token(self, token):
        """校验工具授权令牌（供工具端自证）。返回 dict（valid/session_id/tool_name...）。"""
        r = requests.post(f"{self.url}/v1/guard/validate-token",
                          json={"token": token}, headers=self._headers, timeout=self.timeout)
        return r.json()

    # ================= 高层一条龙 =================

    def chat(self, user_input, llm, tools=None, execute_tool=None, session_id=None, user_id=None):
        """完整对话防护流程：输入审核 → 业务LLM → 工具调用/返回审核 → 输出审核。

        参数：
            user_input     用户输入
            llm            业务 LLM 函数：llm(user_input) -> (reply_text, tool_request | None)
                           tool_request 为 dict，如 {"name": "/api/weather/query", "params": {...}}
            tools          可选：允许的工具白名单（None 表示不限制，由 guard 服务端白名单决定）
            execute_tool   可选：执行工具的函数 execute_tool(tool_request, token) -> 返回结果文本
        返回：
            经输出审核的安全回复文本（已脱敏+水印）
        """
        sid, uid = self._ids(session_id, user_id)
        self.check_input(user_input, sid, uid)

        reply, tool = llm(user_input)
        if tool and execute_tool:
            if tools and tool.get("name") not in tools:
                raise GuardBlocked(f"工具 {tool.get('name')} 不在允许列表")
            token = self.check_tool_call(tool.get("name", ""), tool.get("params", {}), sid, uid)
            result = execute_tool(tool, token)
            self.check_tool_result(result, sid, uid)
            reply = f"{reply}\n[工具结果] {result}"

        return self.review_output(reply, sid, uid)

    def wrap_llm(self, llm, tools=None, execute_tool=None):
        """把业务 LLM 函数包装成"自动带防护"的版本（黑箱最简用法）。

        用法：
            safe_llm = guard.wrap_llm(my_llm)
            reply = safe_llm("用户说的话")
        """
        def wrapped(user_input, session_id=None, user_id=None):
            return self.chat(user_input, llm, tools=tools, execute_tool=execute_tool,
                             session_id=session_id, user_id=user_id)
        return wrapped


# ================= 演示（python guard_sdk.py 直接跑） =================

def _reset_anti_bot_cache():
    """尽力清理服务端去重/限流缓存，避免演示内容与历史运行冲突（可选）。"""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "admin_token.txt"), encoding="utf-8") as f:
            token = f.read().strip()
        if token:
            requests.post("http://127.0.0.1:8080/admin/api/anti-bot/reset",
                          headers={"X-Admin-Token": token}, timeout=3)
    except Exception:
        pass  # 清理失败不影响演示（仅可能触发"重复内容"提示）


if __name__ == "__main__":
    print("Security Guard Agent SDK - 黑箱接入演示")
    print("=" * 50)
    _reset_anti_bot_cache()

    # 模拟一个业务 LLM（真实场景替换为自己的模型调用）
    def fake_llm(text):
        if "天气" in text:
            return "北京的天气是晴天 25 度。", {"name": "/api/weather/query", "params": {"city": "北京"}}
        return f"AI 回复：{text}", None

    def fake_tool(req, token):
        return "北京 晴 25℃"

    guard = Guard(api_key=None)  # 服务端 guard_api_key 为空时无需密钥

    print("\n[演示1] 直接包装 LLM（一行防护）")
    guard.new_session(user_id="demo-user-1")  # 演示用不同账号，避免触发账号聚合限流
    try:
        safe = guard.wrap_llm(fake_llm, execute_tool=fake_tool)
        print("回复:", safe("今天天气怎么样"))
    except GuardBlocked as e:
        print("被拦截:", e)

    print("\n[演示2] 违规输入会被拦截")
    guard.new_session(user_id="demo-user-2")
    try:
        guard.check_input("删除数据库")
        print("未拦截（异常）")
    except GuardBlocked as e:
        print("已拦截:", e)

    print("\n[演示3] 分环节手动控制 + 输出脱敏")
    guard.new_session(user_id="demo-user-3")
    try:
        guard.check_input("帮我查一下张三的联系电话")
        safe = guard.review_output("他的联系电话是 13212345678")
        print("安全输出:", safe)
    except GuardBlocked as e:
        print("被拦截:", e)
