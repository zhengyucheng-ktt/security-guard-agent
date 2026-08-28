# -*- coding: utf-8 -*-
"""生成《安全交互守护智能体》PDF 演示文稿"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle, PageBreak, HRFlowable)

# ---------- 字体 ----------
FONT_TITLE = "SIMHEI"   # 黑体（标题）
FONT_BODY = "DENG"      # 等线（正文）
pdfmetrics.registerFont(TTFont(FONT_TITLE, "C:/Windows/Fonts/simhei.ttf"))
pdfmetrics.registerFont(TTFont(FONT_BODY, "C:/Windows/Fonts/Deng.ttf"))

# ---------- 配色 ----------
NAVY   = HexColor("#16324F")
NAVY2  = HexColor("#1E4E79")
GOLD   = HexColor("#C9A227")
LIGHT  = HexColor("#F4F6F8")
BORDER = HexColor("#D8DEE4")
DARK   = HexColor("#2C3E50")
GREY   = HexColor("#7A8794")

# ---------- 样式 ----------
def ps(name, font=FONT_BODY, size=11, color=DARK, align=TA_CENTER, leading=None, space=0):
    return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                          alignment=align, leading=leading or size * 1.5, spaceAfter=space)

S = {
    "cover_kicker": ps("ck", FONT_BODY, 13, HexColor("#8FA9C6"), space=0),
    "cover_title":  ps("ct", FONT_TITLE, 34, white, leading=46, space=0),
    "cover_sub":    ps("cs", FONT_BODY, 15, HexColor("#C9D6E4"), space=0),
    "cover_line1":  ps("cl1", FONT_TITLE, 12, GOLD, space=0),
    "cover_foot":   ps("cf", FONT_BODY, 10, HexColor("#8FA9C6"), space=0),
    "h1":  ps("h1", FONT_TITLE, 22, NAVY, align=TA_CENTER, space=0),
    "sub": ps("sub", FONT_BODY, 10.5, GREY, align=TA_CENTER, space=0),
    "card_t": ps("ct_", FONT_TITLE, 13, NAVY2, align=TA_CENTER, space=0),
    "body_b": ps("bodyb", FONT_BODY, 11, DARK, align=TA_CENTER, space=2, leading=17),
    "small": ps("small", FONT_BODY, 9.5, GREY, align=TA_CENTER, space=0),
    "b_foot": ps("bf", FONT_BODY, 10.5, HexColor("#C9D6E4"), space=0),
}
BULLET = ParagraphStyle("bl", parent=S["body_b"], leftIndent=14, bulletIndent=2, alignment=0)

def bullet(text):
    return Paragraph(text, BULLET, bulletText="\u2022")

# ---------- 模板背景 ----------
def draw_navy(canv, doc):
    canv.saveState()
    canv.setFillColor(NAVY)
    canv.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canv.setFillColor(NAVY2)
    canv.circle(A4[0] - 20 * mm, A4[1] - 20 * mm, 38 * mm, stroke=0, fill=1)
    canv.setFillColor(HexColor("#14304E"))
    canv.circle(15 * mm, 25 * mm, 30 * mm, stroke=0, fill=1)
    canv.restoreState()

def footer(canv, doc):
    canv.saveState()
    canv.setFont(FONT_BODY, 8.5)
    canv.setFillColor(GREY)
    canv.drawCentredString(A4[0] / 2, 11 * mm,
        "安全交互守护智能体 · Security Guard Agent  ·  第 %d 页" % doc.page)
    canv.setStrokeColor(BORDER)
    canv.line(18 * mm, 15 * mm, A4[0] - 18 * mm, 15 * mm)
    canv.restoreState()

# ---------- 卡片 ----------
def card(title, lines, bg=LIGHT, border=BORDER):
    body = []
    for ln in lines:
        if ln.startswith("["):
            body.append(Paragraph("<font name='SIMHEI' color='#2E8B57'>" + ln.strip("[]") + "</font>", S["body_b"]))
        else:
            body.append(bullet(ln))
    t = Table([[Paragraph(title, S["card_t"])], body], colWidths=[178 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, border),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
    ]))
    return t

def content_page(title, subtitle, blocks, pagebreak=True):
    story = [Spacer(1, 4 * mm), Paragraph(title, S["h1"]),
             HRFlowable(width="100%", thickness=2, color=GOLD,
                        spaceBefore=2 * mm, spaceAfter=2 * mm)]
    if subtitle:
        story.append(Paragraph(subtitle, S["sub"]))
        story.append(Spacer(1, 3 * mm))
    story.extend(blocks)
    if pagebreak:
        story.append(PageBreak())
    return story

# ---------- 文档 ----------
W, H = A4
doc = BaseDocTemplate("安全交互守护智能体-演示.pdf", pagesize=A4,
                      leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=18 * mm,
                      title="安全交互守护智能体 - 演示", author="Security Guard Agent")
frame = Frame(18 * mm, 18 * mm, W - 36 * mm, H - 34 * mm, id="f")
doc.addPageTemplates([
    PageTemplate(id="front", frames=[frame], onPage=draw_navy),
    PageTemplate(id="body", frames=[frame], onPage=footer),
    PageTemplate(id="back", frames=[frame], onPage=draw_navy),
])
from reportlab.platypus import NextPageTemplate
story = []

# ===== 封面 =====
story.append(Spacer(1, 42 * mm))
story.append(Paragraph("A I   S E C U R I T Y   G A T E W A Y", S["cover_kicker"]))
story.append(Spacer(1, 10 * mm))
story.append(Paragraph("安全交互守护智能体", S["cover_title"]))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("Security Guard Agent", S["cover_sub"]))
story.append(Spacer(1, 12 * mm))
story.append(HRFlowable(width="38%", thickness=2.5, color=GOLD, spaceAfter=12 * mm))
story.append(Paragraph("给你的业务智能体，装上一道多层安全门卫", S["cover_line1"]))
story.append(Spacer(1, 58 * mm))
story.append(Paragraph("绿色免安装版 v1.1.0  ·  2026 年 8 月  ·  面向 LLM 应用的多层风控网关", S["cover_foot"]))
story.append(NextPageTemplate("body"))
story.append(PageBreak())

# ===== 目录 =====
toc_items = [
    ("01", "背景与痛点", "LLM 应用面临哪些安全风险"),
    ("02", "产品定位与防线总览", "守护智能体，而不是限制智能体"),
    ("03", "输入防线", "把住用户说的话：规则 + 混淆归一 + 多轮语境"),
    ("04", "工具防线", "管住 AI 能做的事：白名单 + 参数校验 + 令牌"),
    ("05", "输出防线", "护住出去的每一句话：脱敏 + 水印 + 差分隐私"),
    ("06", "反刷评与账号风控", "去重 + 聚合限流 + 信誉分 + 风险积分"),
    ("07", "判定引擎", "本地 / 云端 / 混合三种模式自由切换"),
    ("08", "审计与溯源", "攻击类型标签 + 防篡改哈希链 + 报表导出"),
    ("09", "业务接入", "黑箱 SDK，几行代码获得完整防护"),
    ("10", "管理界面与部署交付", "Web 后台 + 图形面板 + 绿色 ZIP / Docker"),
    ("11", "质量与验收", "67 项自动化测试 + 9 项端到端冒烟验证"),
]
rows = [[Paragraph("<font name='SIMHEI' color='#1E4E79'>%s</font>" % n, S["card_t"]),
         Paragraph("<font name='SIMHEI' color='#2C3E50'>%s</font>" % t, S["card_t"]),
         Paragraph(d, S["small"])] for n, t, d in toc_items]
toc = Table(rows, colWidths=[16 * mm, 62 * mm, 100 * mm])
toc.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
    ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
    ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ("INNERGRID", (0, 0), (-1, -1), 0.4, BORDER),
    ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ("TOPPADDING", (0, 0), (-1, -1), 8),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
story += content_page("目录", "CONTENTS · 一页看懂这个系统能做什么", [toc])

# ===== 背景与痛点 =====
story += content_page("01 · 背景与痛点", "LLM 应用落地后，安全不再是'要不要防'，而是'怎么防'", [
    card("四大核心风险", [
        "提示注入 / 越狱 —— 几句'魔法话术'就能让 AI 吐出不该说的内容",
        "数据泄露 —— 身份证、手机号、银行卡号随对话悄悄流出",
        "工具滥用 —— AI 被诱导调用删除、转账、提权等高危操作",
        "刷单刷评 —— 批量机器人灌水、薅羊毛、恶意打差评",
        "[还有多轮诱导：不直接问，铺垫几轮再套出敏感信息]",
    ]),
    Spacer(1, 4 * mm),
    Paragraph("<font name='SIMHEI' color='#C0392B'>结论：</font>防线必须同时布在<font name='SIMHEI' color='#1E4E79'>输入 — 工具 — 输出</font>全链路，任何一环失守都可能出事。", S["body_b"]),
])

# ===== 产品定位 =====
flow = [Paragraph("用户", S["card_t"]), Paragraph("→ 输入防线", S["body_b"]),
        Paragraph("→ 业务 LLM", S["card_t"]), Paragraph("→ 工具防线", S["body_b"]),
        Paragraph("→ 输出防线", S["body_b"]), Paragraph("→ 用户", S["card_t"])]
flow_t = Table([flow], colWidths=[28 * mm] * 6)
flow_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
    ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
    ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
story += content_page("02 · 产品定位与防线总览", "一句话：守护智能体，而不是限制智能体", [
    card("它是什么", [
        "位置：站在业务 LLM 与用户 / 工具之间的透明安全网关",
        "原则：默认拒绝，逐层验证通过才放行；规则可配置、误拦可调",
        "形态：单文件服务 + 图形面板 + 黑箱 SDK，非技术用户也能接入",
    ]),
    Spacer(1, 4 * mm),
    Paragraph("全链路防线", S["card_t"]),
    Spacer(1, 2 * mm),
    flow_t,
    Spacer(1, 4 * mm),
    Paragraph("每一层防线独立可开关、可配置，按你的业务风险等级灵活组合。", S["small"]),
])

# ===== 核心功能总览 =====
def mini(title, desc):
    return [Paragraph("<font name='SIMHEI' color='#1E4E79'>%s</font>" % title, S["card_t"]),
            Spacer(1, 2 * mm), Paragraph(desc, S["small"])]
grid = Table([
    [mini("输入检测", "关键词 / 正则 / 自然语言三层规则，可疑内容大模型兜底"),
     mini("提示注入防御", "混淆变体归一化 + 间接注入扫描 + 多轮会话语境分"),
     mini("工具调用防护", "高危工具拦截 + 白名单授权 + 参数深度校验 + JWT 令牌")],
    [mini("输出防护", "10 类信息动态脱敏 + 零宽字符水印 + 差分隐私噪声"),
     mini("反刷评风控", "内容去重 + 账号 / IP 聚合限流 + 信誉分 + 机器行为检测"),
     mini("审计溯源", "攻击类型标签 + 防篡改哈希链 + CSV 报表 + 只读 Token")],
], colWidths=[59 * mm] * 3)
grid.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
    ("BOX", (0, 0), (-1, -1), 0.8, BORDER),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
    ("ROUNDEDCORNERS", [8, 8, 8, 8]),
    ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
    ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]))
story += content_page("核心功能总览", "六大防线模块，覆盖 LLM 应用全生命周期", [grid,
    Spacer(1, 5 * mm),
    Paragraph("每个模块都经过自动化测试验证，可单独开关，随业务需要逐步启用。", S["small"]),
])

# ===== 输入防线 =====
story += content_page("03 · 输入防线：把住用户说的话", "四层机制协同，识别并拦截恶意输入", [
    card("三层规则引擎", [
        "关键词规则（rules.txt）：直接命中即拦截，可随时增删",
        "内置正则规则：身份证号、手机号、危险命令等自动识别",
        "自然语言规则（nlp_rules.json）：'描述意图'自动生成规则，热加载生效",
    ]),
    Spacer(1, 4 * mm),
    card("对抗混淆归一化", [
        "全角字符、多余空格、零宽字符、多层 Base64、URL 编码",
        "先归一化解码再检测 —— '忽 略 规 则'这类变体照样识别",
    ]),
    Spacer(1, 4 * mm),
    card("多轮渐进式注入防御", [
        "铺垫词累积'会话语境分' → 达标后升级审查 → 敏感请求联动拦截",
        "低风险内容自动改写（可选）：手机号等 PII 先脱敏再放行对话",
    ]),
])

# ===== 工具防线 =====
story += content_page("04 · 工具防线：管住 AI 能做的事", "四步把关，高危操作层层设卡", [
    card("调用前四步检查", [
        "第一步 白名单：不在白名单的工具直接拦截（高危工具必拦）",
        "第二步 参数清洗：内置工具按允许键过滤，防注入多余参数",
        "第三步 深度校验：SQL 注入 / 路径遍历 / 批量操作 / 敏感参数",
        "第四步 授权令牌：生成 30 秒有效的 JWT，工具端可自证授权",
    ]),
    Spacer(1, 4 * mm),
    card("工具结果回传也设防（间接注入）", [
        "网页 / 文档等工具返回内容可能携带恶意指令",
        "返回内容进模型上下文前先扫描，命中即拦截",
    ]),
])

# ===== 输出防线 =====
story += content_page("05 · 输出防线：护住出去的每一句话", "脱敏 + 水印 + 差分隐私，三道保险", [
    card("动态分级脱敏（10 类信息）", [
        "手机号、身份证、银行卡、邮箱、IP、姓名、地址、车牌、营业执照、微信号",
        "示例：13212345678 → 132****5678，按角色策略（full / partial / minimal）分级",
    ]),
    Spacer(1, 4 * mm),
    card("零宽字符水印（泄露可溯源）", [
        "每份输出嵌入肉眼不可见的唯一身份标记",
        "一旦内容外泄，提取水印即可定位到会话与用户",
    ]),
    Spacer(1, 4 * mm),
    card("差分隐私（可选）", [
        "对统计数字加入 Laplace 噪声，防止从聚合结果反推个体数据",
        "适合'本月销量多少'这类统计型输出的场景",
    ]),
])

# ===== 反刷评 =====
story += content_page("06 · 反刷评与账号风控", "让机器灌水、批量薅羊毛无处遁形", [
    card("四重反刷机制", [
        "内容去重：相同 / 相似内容在时间窗内重复提交即拦截",
        "聚合限流：账号维度 + IP 维度双重限流，突增流量自动限速",
        "信誉分：跨会话累计，行为越差分越低，低到阈值自动限流 / 终止",
        "机器行为检测：请求间隔过于均匀 → 疑似自动化脚本",
    ]),
    Spacer(1, 4 * mm),
    card("会话风险积分（自动升级处置）", [
        "30 分警告 → 60 分限流 → 80 分终止",
        "拦截行为也累计积分，持续违规会被逐级加压",
    ]),
])

# ===== 判定引擎 =====
mode_rows = [
    [Paragraph("<font name='SIMHEI' color='#FFFFFF'>模式</font>", S["small"]),
     Paragraph("<font name='SIMHEI' color='#FFFFFF'>逻辑</font>", S["small"]),
     Paragraph("<font name='SIMHEI' color='#FFFFFF'>适合场景</font>", S["small"])],
    [Paragraph("本地 local", S["body_b"]), Paragraph("只用本地 Ollama 模型，数据不出网", S["body_b"]),
     Paragraph("金融 / 医疗 / 政务等敏感行业、内网离线", S["body_b"])],
    [Paragraph("云端 cloud", S["body_b"]), Paragraph("OpenAI 兼容云端 API，判定能力最强", S["body_b"]),
     Paragraph("判定力优先、数据敏感度低的业务", S["body_b"])],
    [Paragraph("混合 hybrid", S["body_b"]), Paragraph("本地初筛 + 云端终审，双保险", S["body_b"]),
     Paragraph("兼顾隐私与判定力（推荐默认）", S["body_b"])],
]
mode_t = Table(mode_rows, colWidths=[36 * mm, 78 * mm, 64 * mm])
mode_t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), NAVY2),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT]),
    ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
    ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
]))
story += content_page("07 · 判定引擎：安全审核的'大模型法官'", "本地 / 云端 / 混合三种模式，GUI 一键切换，配置 3 秒热加载", [
    mode_t,
    Spacer(1, 4 * mm),
    card("引擎不可用时的失败策略", [
        "fallback（推荐）：自动降级到另一引擎，本地 ↔ 云端互为备份",
        "block：直接拦截 —— '审核服务不可用'，fail-closed 最安全",
        "allow：直接放行 —— fail-open，速度快但有风险",
    ]),
])

# ===== 审计溯源 =====
story += content_page("08 · 审计与溯源：全程留痕、可校验", "日志 100% 可溯源，改动任何一条都能被发现", [
    card("攻击类型自动标签", [
        "每条审计记录自动标注：提示注入 / 隐私泄露 / 违规内容 / 滥用 / 未授权工具 / 系统 / 其他",
    ]),
    Spacer(1, 4 * mm),
    card("哈希链防篡改", [
        "每条记录包含上一条的哈希，环环相扣",
        "任何人改动任意一条日志，一键'校验完整性'立即暴露",
    ]),
    Spacer(1, 4 * mm),
    card("管理能力", [
        "一键导出 CSV 报表（Excel 直接打开，中文表头）",
        "只读 Token：给'只能看、不能改'的同事用，防止误操作",
        "按天轮转归档：audit-YYYYMMDD.log，异步写入不丢审计",
    ]),
])

# ===== 业务接入 =====
code_style = ParagraphStyle("code", fontName=FONT_BODY, fontSize=9.5, textColor=HexColor("#1B3A5C"),
                            backColor=HexColor("#EDF1F5"), borderPadding=8, leading=14)
code = Paragraph(
    "from guard_sdk import Guard\n"
    "guard = Guard(api_key=\"你的密钥\")      # 一行创建\n"
    "safe_llm = guard.wrap_llm(my_llm)       # 一行包装你的大模型\n"
    "reply = safe_llm(\"用户说的话\")          # 自动完成全套防护", code_style)
story += content_page("09 · 业务接入：几行代码搞定", "不懂内部机制也能接入 —— 黑箱 SDK", [
    card("黑箱 SDK（推荐非技术用户）", [
        "输入审核 → 大模型 → 工具防护 → 输出脱敏水印，自动完成",
        "拦截时抛出 GuardBlocked，原因可直接展示给用户",
        "连 session / user 标识都不用管，SDK 自动处理",
    ]),
    Spacer(1, 4 * mm),
    code,
    Spacer(1, 4 * mm),
    Paragraph("标准 API 同样开放：user_input / tool_call / tool_result / output 四个环节可精细控制。", S["small"]),
])

# ===== 管理界面与部署 =====
story += content_page("10 · 管理界面与部署交付", "看得见、管得住、拿得走", [
    card("管理界面", [
        "Web 后台（/admin）：规则、白名单、会话、审计、水印提取",
        "图形控制面板：8 大页签 —— 服务日志 / 业务接入 / 规则管理 / 工具白名单 / 会话监控 / 审计日志 / 系统配置 / 水印提取",
        "本地 / 云端 / 混合模式一键切换，DeepSeek 等云端密钥 GUI 内填入",
    ]),
    Spacer(1, 4 * mm),
    card("部署交付", [
        "绿色免安装 ZIP：解压即用，双击「启动GUI.bat」，无需安装 Python / Go",
        "Docker 镜像约 15MB，多阶段构建，一条命令启动",
        "多实例水平扩展时用 Redis 共享会话；单实例完全不需要",
        "跨平台：Windows / Linux / macOS 二进制均已构建",
    ]),
])

# ===== 质量与验收 =====
story += content_page("11 · 质量与验收", "每一个功能都经过真实运行验证", [
    card("验证情况", [
        "67 项自动化测试全部通过（go test）",
        "端到端冒烟验证 9/9 通过：在真实打包二进制上实测全部新功能",
        "示例验证：'请帮我记录号码13212345678' → 放行并返回 132****5678",
        "示例验证：同一内容 10 分钟内重复提交 → 防刷屏拦截生效",
    ]),
    Spacer(1, 4 * mm),
    card("PRD 核心验收标准", [
        "越狱识别率 ≥ 98%　·　误拦截率 ≤ 1%",
        "多轮诱导识别率 ≥ 95%　·　高危工具拦截率 100%",
        "日志 100% 可溯源（哈希链可校验）",
    ]),
], pagebreak=False)

# ===== 封底 =====
story.append(NextPageTemplate("back"))
story.append(PageBreak())
story.append(Spacer(1, 62 * mm))
story.append(Paragraph("谢谢观看", ps("tks", FONT_TITLE, 32, white, leading=42)))
story.append(Spacer(1, 6 * mm))
story.append(HRFlowable(width="30%", thickness=2, color=GOLD, spaceAfter=10 * mm))
story.append(Paragraph("安全交互守护智能体 · Security Guard Agent · v1.1.0", S["b_foot"]))
story.append(Spacer(1, 3 * mm))
story.append(Paragraph("把 AI 的能力，关进安全的笼子里", S["b_foot"]))
story.append(Spacer(1, 42 * mm))
story.append(Paragraph("绿色免安装版 · 解压即用 · 双击「启动GUI.bat」", S["cover_foot"]))

doc.build(story)
print("PDF 生成完成")
