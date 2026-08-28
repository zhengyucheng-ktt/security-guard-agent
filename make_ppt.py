# -*- coding: utf-8 -*-
"""生成《安全交互守护智能体》演示 PPT（16:9，深蓝安全主题）v2：卡片文字填满 + 真实测试数据"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn

NAVY   = RGBColor(0x16, 0x32, 0x4F)
NAVY2  = RGBColor(0x1E, 0x4E, 0x79)
GOLD   = RGBColor(0xC9, 0xA2, 0x27)
LIGHT  = RGBColor(0xF4, 0xF6, 0xF8)
BORDER = RGBColor(0xD8, 0xDE, 0xE4)
DARK   = RGBColor(0x2C, 0x3E, 0x50)
GREY   = RGBColor(0x7A, 0x87, 0x94)
WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
RED    = RGBColor(0xC0, 0x39, 0x2B)
GREEN  = RGBColor(0x2E, 0x8B, 0x57)
FONT = "微软雅黑"

def set_font(run, size=18, color=DARK, bold=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = FONT
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        ea = rPr.makeelement(qn('a:ea'), {})
        rPr.append(ea)
    ea.set('typeface', FONT)

def add_text(slide, x, y, w, h, text, size=18, color=DARK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.15):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = ln
        set_font(r, size, color, bold)
    return tb

def add_rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.fill.solid()
    sp.fill.fore_color.rgb = fill
    if line:
        sp.line.color.rgb = line
        sp.line.width = Pt(1)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    return sp

def title_bar(slide, title, subtitle=None):
    add_rect(slide, 0, 0, 13.333, 1.15, NAVY)
    add_rect(slide, 0, 1.15, 13.333, 0.06, GOLD)
    add_text(slide, 0.6, 0.16, 12, 0.9, title, 30, WHITE, True, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE)
    if subtitle:
        add_text(slide, 0.6, 1.32, 12, 0.5, subtitle, 14, GREY)

def card(slide, x, y, w, h, title, lines, title_color=NAVY2):
    add_rect(slide, x, y, w, h, LIGHT, BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
    add_text(slide, x + 0.22, y + 0.12, w - 0.44, 0.45, title, 16, title_color, True)
    body = "\n".join(("• " + ln) for ln in lines)
    # 行距 1.25、字号 12.5，尽量填满卡片
    add_text(slide, x + 0.22, y + 0.6, w - 0.44, h - 0.8, body, 12.5, DARK, spacing=1.25)

def section(slide, no, title, subtitle, cards):
    title_bar(slide, "%s  %s" % (no, title), subtitle)
    n = len(cards)
    if n == 1:
        card(slide, 1.0, 1.85, 11.3, 4.7, cards[0][0], cards[0][1])
    elif n == 2:
        card(slide, 1.0, 1.85, 5.55, 4.7, cards[0][0], cards[0][1])
        card(slide, 6.78, 1.85, 5.55, 4.7, cards[1][0], cards[1][1])
    elif n == 3:
        card(slide, 1.0, 1.85, 11.3, 1.55, cards[0][0], cards[0][1])
        card(slide, 1.0, 3.55, 5.55, 3.0, cards[1][0], cards[1][1])
        card(slide, 6.78, 3.55, 5.55, 3.0, cards[2][0], cards[2][1])
    else:
        card(slide, 1.0, 1.85, 5.55, 2.25, cards[0][0], cards[0][1])
        card(slide, 6.78, 1.85, 5.55, 2.25, cards[1][0], cards[1][1])
        card(slide, 1.0, 4.3, 5.55, 2.25, cards[2][0], cards[2][1])
        card(slide, 6.78, 4.3, 5.55, 2.25, cards[3][0], cards[3][1])

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]

# ===== 1 封面 =====
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, 13.333, 7.5, NAVY)
add_rect(s, 11.6, -1.5, 4, 4, NAVY2, shape=MSO_SHAPE.OVAL)
add_rect(s, -1.5, 5.8, 4, 4, RGBColor(0x14, 0x30, 0x4E), shape=MSO_SHAPE.OVAL)
add_text(s, 1.0, 1.3, 11.3, 0.6, "A I   S E C U R I T Y   G A T E W A Y", 16, RGBColor(0x8F, 0xA9, 0xC6), align=PP_ALIGN.CENTER)
add_text(s, 1.0, 2.2, 11.3, 1.3, "安全交互守护智能体", 48, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 3.5, 11.3, 0.7, "Security Guard Agent", 22, RGBColor(0xC9, 0xD6, 0xE4), align=PP_ALIGN.CENTER)
add_rect(s, 5.2, 4.4, 2.9, 0.04, GOLD)
add_text(s, 1.0, 4.7, 11.3, 0.6, "给你的业务智能体，装上一道多层安全门卫", 20, GOLD, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 6.3, 11.3, 0.5, "绿色免安装版 v1.1.0  ·  2026 年 8 月  ·  面向 LLM 应用的多层风控网关", 14, RGBColor(0x8F, 0xA9, 0xC6), align=PP_ALIGN.CENTER)

# ===== 2 目录 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "目录", "CONTENTS")
toc = [
    ("01", "背景与痛点", "LLM 应用面临哪些安全风险"),
    ("02", "产品定位与全链路防线", "守护智能体，而不是限制智能体"),
    ("03", "六大核心防线", "输入 / 工具 / 输出 / 反刷评 / 判定 / 思维链"),
    ("04", "审计与溯源", "全程留痕，哈希链防篡改"),
    ("05", "业务接入", "黑箱 SDK，几行代码搞定"),
    ("06", "性能与安全自测", "约 1ms 开销、84% 拦截、误判均为隐私设计"),
    ("07", "部署与交付", "绿色 ZIP / Docker / 多实例"),
]
for i, (no, t, d) in enumerate(toc):
    y = 1.55 + i * 0.78
    add_text(s, 1.3, y, 1.2, 0.6, no, 22, GOLD, True)
    add_text(s, 2.7, y + 0.02, 4.2, 0.6, t, 17, NAVY2, True)
    add_text(s, 7.2, y + 0.05, 5.2, 0.5, d, 13, GREY)

# ===== 3 背景与痛点 =====
s = prs.slides.add_slide(BLANK)
section(s, "01", "背景与痛点", "LLM 应用落地后，安全不再是'要不要防'，而是'怎么防'", [
    ("四大核心风险 + 一个深层挑战", [
        "提示注入 / 越狱 —— 几句'魔法话术'让 AI 吐出不该说的内容",
        "数据泄露 —— 身份证、手机号、银行卡随对话悄悄流出",
        "工具滥用 —— AI 被诱导调用删除、转账、提权等高危操作",
        "刷单刷评 —— 批量机器人灌水、薅羊毛、恶意打差评",
        "多轮诱导 —— 不直接问，铺垫几轮再套出敏感信息",
        "编码混淆 —— 全角/Base64/HTML 实体变体绕过关键词检测",
        "结论：防线必须同时布在输入—工具—输出全链路",
    ]),
])

# ===== 4 产品定位 =====
s = prs.slides.add_slide(BLANK)
section(s, "02", "产品定位与全链路防线", "守护智能体，而不是限制智能体", [
    ("它是什么", [
        "位置：站在业务 LLM 与用户 / 工具之间的透明安全网关",
        "原则：默认拒绝，逐层验证通过才放行；规则可配置、误拦可调",
        "形态：单文件服务 + 图形面板 + 黑箱 SDK，非技术用户也能接入",
        "设计：每层防线独立可开关、可配置，按风险等级灵活组合",
        "目标：安全与体验兼得——拦截恶意，不打扰正常用户",
    ]),
    ("全链路防线", [
        "用户 → 输入防线 → 业务 LLM → 工具防线 → 输出防线 → 用户",
        "输入防线：规则引擎 + 混淆归一 + 多轮语境分 + 大模型兜底",
        "工具防线：白名单 + 参数校验 + 30 秒 JWT 令牌",
        "输出防线：脱敏 + 零宽水印 + 差分隐私",
        "思维链监控管住'AI 脑子里的话'，三层形成闭环",
        "审计全程留痕：每个判定都可溯源、可校验、可导出",
    ]),
])

# ===== 5 核心功能总览 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "03 · 六大核心防线", "覆盖 LLM 应用全生命周期")
grid = [
    ("输入检测", "关键词/正则/自然语言三层规则，可疑内容大模型兜底"),
    ("提示注入防御", "编码混淆归一化、间接注入扫描、多轮会话语境分"),
    ("工具调用防护", "高危拦截、白名单授权、参数深度校验、JWT 令牌"),
    ("输出防护", "10 类信息脱敏、零宽水印、差分隐私噪声"),
    ("反刷评风控", "内容去重、账号/IP 聚合限流、信誉分、机器行为"),
    ("审计溯源", "攻击类型标签、防篡改哈希链、CSV 报表、只读 Token"),
]
for i, (t, d) in enumerate(grid):
    x = 1.0 + (i % 3) * 3.85
    y = 1.65 + (i // 3) * 2.75
    add_rect(s, x, y, 3.6, 2.5, LIGHT, BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
    add_text(s, x + 0.2, y + 0.2, 3.2, 0.6, t, 19, NAVY2, True, PP_ALIGN.CENTER)
    add_text(s, x + 0.25, y + 0.95, 3.1, 1.4, d, 12.5, DARK, False, PP_ALIGN.CENTER, spacing=1.2)

# ===== 6 输入防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "输入防线：把住用户说的话", "四层机制协同，识别并拦截恶意输入", [
    ("三层规则引擎", [
        "关键词规则（rules.txt）：命中即拦截，可随时增删",
        "正则规则：身份证、手机号（带词边界防误判）等自动识别",
        "自然语言规则（nlp_rules.json）：描述意图自动生成规则",
        "全部支持 3 秒热加载，改完即生效",
    ]),
    ("对抗混淆归一化", [
        "全角字符、多余空格、零宽字符先归一化",
        "URL 编码、Base64（含前缀/双层）、HTML 实体、Unicode 转义解码",
        "'忽 略 规 则'、B64、&#x89c4;、\\u89c4 变体照样识别",
        "先解码再检测，编码绕不过规则层",
    ]),
    ("多轮渐进式注入防御", [
        "铺垫词累积'会话语境分' → 达标升级审查 → 敏感联动拦截",
        "实测：5 轮诱导前 4 轮无害放行，第 5 轮敏感请求被拦",
        "低风险内容自动改写：手机号等 PII 先脱敏再放行",
        "不误拦正常对话，只拦真正越界的那一步",
    ]),
])

# ===== 7 工具防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "工具防线：管住 AI 能做的事", "四步把关，高危操作层层设卡", [
    ("调用前四步检查", [
        "① 白名单：不在白名单的工具直接拦截，高危工具必拦",
        "② 参数清洗：内置工具按允许键过滤，未声明键消毒剔除",
        "③ 深度校验：SQL 注入 / 路径遍历 / XSS / 批量 / 敏感参数",
        "④ 授权令牌：生成 30 秒有效 JWT，工具端可自证授权",
        "数组批量参数 ≥5 项视为批量操作，≤4 项正常放行",
    ]),
    ("工具结果回传也设防", [
        "网页 / 文档等工具返回内容可能携带恶意指令",
        "返回内容进模型上下文前先扫描（间接注入防御）",
        "命中即拦截并记录审计，防止'带毒内容'污染模型",
        "思维链（thinking）同步检测 AI 自主产生的危险思路",
    ]),
])

# ===== 8 输出防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "输出防线：护住出去的每一句话", "脱敏 + 水印 + 差分隐私，三道保险", [
    ("动态分级脱敏（10 类信息）", [
        "手机号、身份证、银行卡、邮箱、IP、姓名、地址",
        "车牌、营业执照、微信号共 10 类自动识别脱敏",
        "示例：13212345678 → 132****5678",
        "按角色策略分级：full / partial / minimal",
    ]),
    ("零宽字符水印", [
        "每份输出嵌入肉眼不可见的唯一身份标记",
        "一旦内容外泄，提取水印即可定位会话与用户",
        "防截图外传、防数据二次分发溯源",
    ]),
    ("差分隐私", [
        "对统计数字加入 Laplace 噪声",
        "防止从聚合结果反推个体数据",
        "适合'本月销量'等统计型输出场景",
    ]),
])

# ===== 9 反刷评 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "反刷评与账号风控", "让机器灌水、批量薅羊毛无处遁形", [
    ("四重反刷机制", [
        "内容去重：相同 / 相似内容在时间窗内重复提交即拦截",
        "聚合限流：账号维度 + IP 维度双重限流，突增自动限速",
        "信誉分：跨会话累计，行为越差分越低，低到阈值自动处置",
        "机器行为检测：请求间隔过于均匀 → 疑似自动化脚本",
        "实测：同一内容 10 分钟内重复提交被拦截",
    ]),
    ("会话风险积分（自动升级）", [
        "30 分警告 → 60 分限流 → 80 分终止",
        "拦截行为也累计积分，持续违规逐级加压",
        "管理端可一键解封 / 手动封禁",
        "内存模式积分持久化，重启不丢",
    ]),
])

# ===== 10 判定引擎 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "03 · 判定引擎", "安全审核的'大模型法官'，三种模式 GUI 一键切换")
rows = [
    ("本地 local", "只用本地 Ollama 模型，数据不出网", "金融/医疗/政务、内网离线"),
    ("云端 cloud", "OpenAI 兼容 API，判定能力最强", "判定力优先、数据敏感度低"),
    ("混合 hybrid", "本地初筛 + 云端终审，双保险", "兼顾隐私与判定力（推荐）"),
]
add_rect(s, 1.0, 1.65, 11.3, 0.6, NAVY2)
add_text(s, 1.2, 1.7, 3.4, 0.5, "模式", 14, WHITE, True)
add_text(s, 4.8, 1.7, 4.4, 0.5, "逻辑", 14, WHITE, True)
add_text(s, 9.4, 1.7, 2.8, 0.5, "适合场景", 14, WHITE, True)
for i, (a, b, c) in enumerate(rows):
    y = 2.35 + i * 0.85
    bg = LIGHT if i % 2 == 0 else WHITE
    add_rect(s, 1.0, y, 11.3, 0.75, bg, BORDER)
    add_text(s, 1.2, y + 0.12, 3.4, 0.5, a, 14, NAVY2, True)
    add_text(s, 4.8, y + 0.12, 4.4, 0.5, b, 13, DARK)
    add_text(s, 9.4, y + 0.12, 2.8, 0.5, c, 13, DARK)
card(s, 1.0, 5.15, 11.3, 1.7, "引擎不可用时的失败策略", [
    "fallback（推荐）：自动降级到另一引擎，本地 ↔ 云端互为备份",
    "block：直接拦截（fail-closed，最安全）· allow：直接放行（fail-open，有风险）",
    "判定缓存 30 秒：相同内容重复审查零开销；配置 3 秒热加载",
])

# ===== 11 思维链监控 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "思维链监控", "AI 动手之前，先拦住它的危险念头", [
    ("为什么需要", [
        "危险不只会来自用户诱导——AI 自己也可能'想歪'",
        "计划提权、导出数据、转走资金等危险意图可能自主产生",
        "等 AI 真正动手再拦往往太晚，要在'动手前'拦截",
    ]),
    ("怎么用", [
        "业务智能体把思考过程传入（action_type = thinking）",
        "注入特征扫描 + 大模型判定，命中即拦截并记录审计",
        "实测：'转走资金''删除所有用户'等思考被拦截",
    ]),
    ("闭环配合", [
        "输入防线管'进来的话'，输出防线管'出去的话'",
        "思维链防线管'AI 脑子里的话'，三层形成完整闭环",
        "拦截发生在风险产生的那一刻，而非结果发生之后",
    ]),
])

# ===== 12 审计溯源 =====
s = prs.slides.add_slide(BLANK)
section(s, "04", "审计与溯源：全程留痕、可校验", "日志 100% 可溯源，改动任何一条都能被发现", [
    ("攻击类型自动标签", [
        "每条审计记录自动标注攻击类型",
        "提示注入 / 隐私泄露 / 违规内容 / 滥用 / 未授权工具 / 系统 / 其他",
        "按天轮转归档：audit-YYYYMMDD.log",
        "异步写入不丢审计，队列满降级同步",
    ]),
    ("哈希链防篡改", [
        "每条记录包含上一条的哈希，环环相扣",
        "一键'校验完整性'，任何改动立即暴露",
        "旧格式记录兼容校验，升级不断链",
    ]),
    ("管理能力", [
        "CSV 报表一键导出，Excel 直接打开",
        "只读 Token 给'只能看不能改'的同事",
        "耗时字段全程记录（latency_ms / llm_ms）",
    ]),
])

# ===== 13 业务接入 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "05 · 业务接入", "不懂内部机制也能接入 —— 黑箱 SDK")
card(s, 1.0, 1.65, 5.5, 2.3, "黑箱 SDK（推荐非技术用户）", [
    "输入审核 → 大模型 → 工具防护 → 输出脱敏，自动完成",
    "拦截时抛出 GuardBlocked，原因可直接展示给用户",
    "连 session / user 标识都不用管，SDK 自动处理",
])
add_rect(s, 6.9, 1.65, 5.4, 2.3, RGBColor(0xED, 0xF1, 0xF5), BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 7.15, 1.8, 4.9, 2.0, "from guard_sdk import Guard\nguard = Guard(api_key=\"\")\nsafe_llm = guard.wrap_llm(my_llm)\nreply = safe_llm(\"用户说的话\")", 13, NAVY2, True)
card(s, 1.0, 4.25, 11.3, 2.5, "标准 API 同样开放（精细控制）", [
    "四环节：user_input / tool_call / tool_result / output，外加思维链 thinking",
    "每个环节返回 decision / block_reason / risk_level / current_score / latency_ms",
    "工具端可调用 /v1/guard/validate-token 自证授权，防越权调用",
    "SDK 与 API 双通道，业务侧按需选择，全程可观测可追溯",
])

# ===== 14 性能量化 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "06 · 性能量化", "网关自身开销约 1ms，损耗透明可查")
perf = [
    ("普通输入放行", "0.9 ms", "1.2 ms"),
    ("工具调用放行/拦截", "1.0 ms", "1.5 ms"),
    ("输出脱敏+水印", "1.2 ms", "1.9 ms"),
    ("大模型判定（可选）", "~0.9 s", "仅可疑内容触发"),
]
add_rect(s, 1.0, 1.65, 11.3, 0.6, NAVY2)
add_text(s, 1.2, 1.7, 4.5, 0.5, "场景", 14, WHITE, True)
add_text(s, 6.0, 1.7, 2.5, 0.5, "P50", 14, WHITE, True)
add_text(s, 8.8, 1.7, 3.0, 0.5, "P95", 14, WHITE, True)
for i, (a, b, c) in enumerate(perf):
    y = 2.35 + i * 0.75
    bg = LIGHT if i % 2 == 0 else WHITE
    add_rect(s, 1.0, y, 11.3, 0.65, bg, BORDER)
    add_text(s, 1.2, y + 0.1, 4.5, 0.5, a, 14, NAVY2, True)
    add_text(s, 6.0, y + 0.1, 2.5, 0.5, b, 14, DARK)
    add_text(s, 8.8, y + 0.1, 3.0, 0.5, c, 13, DARK)
card(s, 1.0, 5.35, 11.3, 1.7, "结论", [
    "网关自身开销 P50 约 1ms，平均与中位一致（keep-alive 长连接实测）",
    "20 并发实测吞吐约 1280 请求/秒；每请求耗时写入响应与审计日志",
    "若每次新建 TCP 连接会叠加约 20ms 握手开销，业务侧用连接池即可消除",
])

# ===== 15 安全自测 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "06 · 安全自测", "红队演练 + 误判测试，双向验证（61 攻击样本 / 90 正常样本）")
add_rect(s, 1.0, 1.65, 5.55, 2.5, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 1.0, 1.75, 5.55, 0.6, "攻击拦截率", 17, GOLD, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 2.3, 5.55, 1.0, "84%", 44, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 3.35, 5.55, 0.6, "拦截 51 / 61 种攻击手法", 13, RGBColor(0xC9, 0xD6, 0xE4), False, PP_ALIGN.CENTER)
add_text(s, 1.0, 3.75, 5.55, 0.4, "越狱 14/15 · 工具 12/12 · 思维链 5/5 · 混淆 16/19", 11, RGBColor(0xC9, 0xD6, 0xE4), False, PP_ALIGN.CENTER)
add_rect(s, 6.78, 1.65, 5.55, 2.5, GREEN, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 6.78, 1.75, 5.55, 0.6, "误拦截率（90 正常样本）", 17, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 6.78, 2.3, 5.55, 1.0, "7 / 90", 40, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 6.78, 3.35, 5.55, 0.6, "全部为隐私设计拦截", 13, WHITE, False, PP_ALIGN.CENTER)
add_text(s, 6.78, 3.75, 5.55, 0.4, "纯误判 0：日常对话/订单号/改绑手机号全放行", 11, WHITE, False, PP_ALIGN.CENTER)
card(s, 1.0, 4.4, 11.3, 2.55, "演练成果与边界说明", [
    "修复 8 个真实漏洞：Base64（含双层）/HTML实体/Unicode 转义解码、银行卡/邮箱误判、工具参数注入、XSS、批量数组、思维链危险意图",
    "剩余穿透：hex 编码、反写、拼音、谐音等罕见变体，以及多轮铺垫单条（设计正确）",
    "多轮诱导 5 轮实测：前 4 轮无害铺垫放行，第 5 轮敏感请求联动拦截",
    "隐私拦截为设计行为（输入侧防泄露），开启'自动改写'后手机号等脱敏放行，对话不中断",
])

# ===== 16 部署交付 =====
s = prs.slides.add_slide(BLANK)
section(s, "07", "部署与交付", "看得见、管得住、拿得走", [
    ("绿色免安装 ZIP", [
        "解压即用，双击「启动GUI.bat」即可启动",
        "无需安装 Python / Go，Windows 直接运行",
        "配置 / 规则 / 白名单全部开箱自带",
    ]),
    ("Docker / 多实例", [
        "Docker 镜像约 15MB，多阶段构建",
        "一条命令启动：docker run -p 8080:8080",
        "多实例用 Redis 共享会话，单实例零依赖",
    ]),
    ("管理界面", [
        "Web 后台 /admin + 图形面板 8 大页签",
        "本地 / 云端 / 混合模式一键切换",
        "配置 3 秒热加载，改完即生效",
    ]),
])

# ===== 17 封底 =====
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, 13.333, 7.5, NAVY)
add_text(s, 1.0, 2.6, 11.3, 1.2, "谢谢观看", 44, WHITE, True, PP_ALIGN.CENTER)
add_rect(s, 5.6, 4.0, 2.1, 0.04, GOLD)
add_text(s, 1.0, 4.3, 11.3, 0.7, "安全交互守护智能体 · Security Guard Agent · v1.1.0", 18, RGBColor(0xC9, 0xD6, 0xE4), align=PP_ALIGN.CENTER)
add_text(s, 1.0, 5.2, 11.3, 0.6, "把 AI 的能力，关进安全的笼子里", 16, GOLD, align=PP_ALIGN.CENTER)
add_text(s, 1.0, 6.4, 11.3, 0.5, "绿色免安装版 · 解压即用 · 双击「启动GUI.bat」", 13, RGBColor(0x8F, 0xA9, 0xC6), align=PP_ALIGN.CENTER)

prs.save("安全交互守护智能体-演示.pptx")
print("PPT 生成完成: %d 页" % len(prs.slides._sldIdLst))
