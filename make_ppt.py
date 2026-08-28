# -*- coding: utf-8 -*-
"""生成《安全交互守护智能体》演示 PPT（16:9）v3
要点：卡片文字字号自适应（内容多自动缩小防出框）+ 垂直居中（消除底部空白）+ 内容按卡片高度配足行数"""
import math
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
GOLD2  = RGBColor(0xC9, 0xD6, 0xE4)
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

def est_lines(lines, size, width):
    """估算内容总行数（中文全角字符宽 = 字号 pt/72 英寸）"""
    chars_per_line = max(4, int((width - 0.44) * 72.0 / size))
    total = 0
    for ln in lines:
        total += max(1, math.ceil(len(ln) / chars_per_line))
    return total

def card(slide, x, y, w, h, title, lines, title_color=NAVY2, title_size=16):
    """卡片：标题固定顶部；内容字号自适应（防出框）+ 垂直居中（消除底部空白）"""
    add_rect(slide, x, y, w, h, LIGHT, BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
    add_text(slide, x + 0.22, y + 0.08, w - 0.44, 0.4, title, title_size, title_color, True)
    avail_h = h - 0.55
    size = 14
    while size >= 9:
        row_h = size / 72.0 * 1.2
        if est_lines(lines, size, w) * row_h <= avail_h:
            break
        size -= 1
    body = "\n".join(("• " + ln) for ln in lines)
    add_text(slide, x + 0.25, y + 0.5, w - 0.5, avail_h, body, size, DARK, False, PP_ALIGN.LEFT, MSO_ANCHOR.MIDDLE, spacing=1.2)

def section(slide, no, title, subtitle, cards):
    title_bar(slide, "%s  %s" % (no, title), subtitle)
    n = len(cards)
    if n == 1:
        card(slide, 1.0, 1.85, 11.3, 4.7, cards[0][0], cards[0][1])
    elif n == 2:
        card(slide, 1.0, 1.85, 5.55, 4.7, cards[0][0], cards[0][1])
        card(slide, 6.78, 1.85, 5.55, 4.7, cards[1][0], cards[1][1])
    elif n == 3:
        card(slide, 1.0, 1.85, 11.3, 1.7, cards[0][0], cards[0][1], title_size=14)
        card(slide, 1.0, 3.7, 5.55, 2.85, cards[1][0], cards[1][1])
        card(slide, 6.78, 3.7, 5.55, 2.85, cards[2][0], cards[2][1])
    else:
        card(slide, 1.0, 1.85, 5.55, 2.3, cards[0][0], cards[0][1])
        card(slide, 6.78, 1.85, 5.55, 2.3, cards[1][0], cards[1][1])
        card(slide, 1.0, 4.35, 5.55, 2.3, cards[2][0], cards[2][1])
        card(slide, 6.78, 4.35, 5.55, 2.3, cards[3][0], cards[3][1])

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
add_text(s, 1.0, 3.5, 11.3, 0.7, "Security Guard Agent", 22, GOLD2, align=PP_ALIGN.CENTER)
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
    ("06", "性能与安全自测", "1ms 开销 · 本地 90% vs 混合 93% · 越狱 100%"),
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
    ("LLM 应用面临的七重风险", [
        "提示注入 / 越狱 —— 几句'魔法话术'就让 AI 吐出不该说的内容",
        "数据泄露 —— 身份证、手机号、银行卡随对话悄悄流出",
        "工具滥用 —— AI 被诱导调用删除、转账、提权等高危操作",
        "刷单刷评 —— 批量机器人灌水、薅羊毛、恶意打差评",
        "多轮诱导 —— 不直接问，铺垫几轮再套出敏感信息",
        "编码混淆 —— 全角 / Base64 / HTML 实体等变体绕过关键词检测",
        "思维链风险 —— AI 自己也可能产生提权、导数据、转资金的念头",
        "合规压力 —— 数据出境与隐私保护法规提出更高安全要求",
        "结论：防线必须同时布在『输入 — 工具 — 输出』全链路",
        "守护智能体，而不是限制智能体——安全与体验兼得",
        "单点防护防不住组合攻击，需要多层协同纵深防御",
        "每一层防线独立可开关，按业务风险等级灵活组合",
    ]),
])

# ===== 4 产品定位 =====
s = prs.slides.add_slide(BLANK)
section(s, "02", "产品定位与全链路防线", "守护智能体，而不是限制智能体", [
    ("它是什么", [
        "位置：业务 LLM 与用户 / 工具之间的透明网关",
        "原则：默认拒绝，逐层验证通过才放行",
        "规则可配置、误拦可调、可解释",
        "形态：单文件服务 + 图形面板 + SDK",
        "非技术用户几行代码即可接入",
        "每层防线独立开关，灵活组合",
        "安全与体验兼得，不打扰正常用户",
        "支持单机零依赖运行",
        "也支持多实例水平扩展",
        "数据不出网可选（本地判定引擎）",
        "判定引擎可切换本地 / 云端 / 混合",
        "配置 3 秒热加载，改完即生效",
        "日志全程留痕，审计可溯源可导出",
    ]),
    ("全链路防线", [
        "用户 → 输入防线 → 业务 LLM → 工具防线 → 输出防线",
        "输入防线：规则引擎 + 混淆归一 + 多轮语境分",
        "输入防线：大模型兜底，可疑内容升级审核",
        "工具防线：白名单 + 参数校验 + 30 秒 JWT",
        "工具防线：高危工具必拦，未授权调用即拦",
        "输出防线：脱敏 + 零宽水印 + 差分隐私",
        "思维链监控：管住『AI 脑子里的话』",
        "反刷评：去重 + 限流 + 信誉分 + 机器行为",
        "判定引擎：本地 / 云端 / 混合三模式",
        "审计溯源：攻击标签 + 哈希链 + 报表",
        "三层防线形成完整闭环，纵深防御",
        "拦截发生在风险产生的那一刻",
        "而非结果发生之后",
    ]),
])

# ===== 5 核心功能总览 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "03 · 六大核心防线", "覆盖 LLM 应用全生命周期")
grid = [
    ("输入检测", "关键词 / 正则 / 自然语言三层规则\n可疑内容大模型兜底\n混淆变体先解码再检测"),
    ("提示注入防御", "编码混淆归一化\n间接注入扫描\n多轮会话语境分联动"),
    ("工具调用防护", "高危工具拦截\n白名单授权\n参数深度校验\nJWT 授权令牌"),
    ("输出防护", "10 类信息脱敏\n零宽字符水印\n差分隐私噪声"),
    ("反刷评风控", "内容去重\n账号/IP 聚合限流\n信誉分升级处置"),
    ("审计溯源", "攻击类型标签\n防篡改哈希链\nCSV 报表 + 只读 Token"),
]
for i, (t, d) in enumerate(grid):
    x = 1.0 + (i % 3) * 3.85
    y = 1.65 + (i // 3) * 2.75
    add_rect(s, x, y, 3.6, 2.5, LIGHT, BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
    add_text(s, x + 0.2, y + 0.15, 3.2, 0.5, t, 18, NAVY2, True, PP_ALIGN.CENTER)
    add_text(s, x + 0.25, y + 0.75, 3.1, 1.6, d, 13, DARK, False, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE, spacing=1.25)

# ===== 6 输入防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "输入防线：把住用户说的话", "四层机制协同，识别并拦截恶意输入", [
    ("三层规则引擎", [
        "关键词规则命中即拦截，可随时增删",
        "正则规则：身份证 / 手机号（带词边界防误判）",
        "自然语言规则：描述意图自动生成，热加载",
        "全部配置 3 秒热加载，改完即生效",
    ]),
    ("对抗混淆归一化", [
        "全角、空格、零宽字符先归一化",
        "URL 编码解码",
        "Base64（含前缀 / 双层）解码",
        "HTML 实体（&#x89c4;）解码",
        "Unicode 转义（\\u89c4）解码",
        "先解码再检测，编码绕不过规则层",
        "'忽 略 规 则'变体照样识别",
        "对抗混淆自测持续补盲区",
    ]),
    ("多轮渐进式注入防御", [
        "铺垫词累积会话语境分",
        "达标后升级审查",
        "敏感请求联动拦截",
        "实测：5 轮诱导第 5 轮被拦",
        "低风险内容自动改写",
        "手机号等 PII 先脱敏再放行",
        "不误拦正常对话",
        "只拦真正越界的那一步",
    ]),
])

# ===== 7 工具防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "工具防线：管住 AI 能做的事", "四步把关，高危操作层层设卡", [
    ("调用前四步检查", [
        "① 白名单：不在白名单直接拦截",
        "高危工具（删除 / 转账 / 提权）必拦",
        "② 参数清洗：允许键过滤",
        "未声明字符串键消毒剔除",
        "③ 深度校验",
        "SQL 注入 / 路径遍历检测",
        "XSS / 敏感参数检测",
        "数组批量 ≥5 项视为批量操作",
        "④ 授权令牌：30 秒有效 JWT",
        "工具端可自证授权",
        "防止越权调用与令牌冒用",
        "校验失败即拦截并记审计",
    ]),
    ("工具结果回传也设防", [
        "网页 / 文档返回内容可能携带恶意指令",
        "进模型上下文前先扫描",
        "间接注入命中即拦截",
        "记录审计，防止污染模型上下文",
        "思维链同步检测",
        "AI 自主产生的危险思路",
        "计划提权 / 导数据 / 转资金",
        "在动手前拦截",
        "三层防线形成完整闭环",
        "高危工具拦截率实测 12/12",
        "参数攻击全拦截",
        "白名单工具正常参数放行",
    ]),
])

# ===== 8 输出防线 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "输出防线：护住出去的每一句话", "脱敏 + 水印 + 差分隐私，三道保险", [
    ("动态分级脱敏（10 类信息）", [
        "手机 / 身份证 / 银行卡 / 邮箱 / IP / 姓名",
        "地址 / 车牌 / 营业执照 / 微信号",
        "示例：13212345678 → 132****5678",
        "按角色策略分级：full / partial / minimal",
    ]),
    ("零宽字符水印", [
        "输出嵌入肉眼不可见身份标记",
        "内容外泄可定位会话与用户",
        "防截图外传",
        "防数据二次分发溯源",
        "与脱敏互补，双重保险",
        "水印提取 GUI 一键完成",
    ]),
    ("差分隐私", [
        "统计数字加 Laplace 噪声",
        "防止从聚合结果反推个体数据",
        "适合统计型输出场景",
        "聚合报表场景",
        "可选开关，按需启用",
        "不影响正常数值读取",
    ]),
])

# ===== 9 反刷评 =====
s = prs.slides.add_slide(BLANK)
section(s, "03", "反刷评与账号风控", "让机器灌水、批量薅羊毛无处遁形", [
    ("四重反刷机制", [
        "内容去重：相同 / 相似内容",
        "时间窗内重复提交即拦截",
        "聚合限流：账号维度 + IP 维度",
        "突增流量自动限速",
        "信誉分：跨会话累计",
        "行为越差分越低",
        "低到阈值自动限流 / 终止",
        "机器行为检测",
        "请求间隔过于均匀 → 疑似自动化",
        "实测：重复提交被拦截",
        "编码相似变体同样命中",
    ]),
    ("会话风险积分（自动升级）", [
        "30 分警告",
        "60 分限流",
        "80 分终止",
        "拦截行为也累计积分",
        "持续违规逐级加压",
        "管理端一键解封",
        "支持手动封禁",
        "内存模式积分持久化",
        "重启不丢状态",
        "多实例 Redis 共享",
        "积分变化全程审计",
    ]),
])

# ===== 10 判定引擎 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "03 · 判定引擎", "安全审核的'大模型法官'，三种模式 GUI 一键切换")
rows = [
    ("本地 local", "只用本地 Ollama 模型，数据不出网", "金融 / 医疗 / 政务、内网离线"),
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
        "危险不只会来自用户诱导",
        "AI 自己也可能『想歪』",
        "计划提权 / 导数据 / 转资金",
        "等动手再拦往往太晚",
        "要在『动手前』拦截",
        "思维链防线应运而生",
    ]),
    ("怎么用", [
        "思考过程传入 action_type = thinking",
        "注入特征扫描",
        "大模型判定兜底",
        "命中即拦截并记录审计",
        "实测：转走资金等被拦",
        "删除所有用户被拦",
    ]),
    ("闭环配合", [
        "输入防线管『进来的话』",
        "输出防线管『出去的话』",
        "思维链管『AI 脑子里的话』",
        "三层形成完整闭环",
        "拦截发生在风险产生那一刻",
        "而非结果发生之后",
    ]),
])

# ===== 12 审计溯源 =====
s = prs.slides.add_slide(BLANK)
section(s, "04", "审计与溯源：全程留痕、可校验", "日志可溯源，改动任何一条都能被发现", [
    ("攻击类型自动标签", [
        "每条记录自动标注攻击类型",
        "注入 / 隐私 / 违规 / 滥用",
        "未授权工具 / 系统 / 其他",
        "按天轮转归档",
    ]),
    ("哈希链防篡改", [
        "每条记录含上一条哈希",
        "环环相扣，改动即暴露",
        "一键校验完整性",
        "旧格式兼容校验不断链",
    ]),
    ("管理能力", [
        "CSV 报表一键导出",
        "Excel 直接打开",
        "只读 Token 给查看者",
        "耗时字段全程记录",
    ]),
])

# ===== 13 业务接入 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "05 · 业务接入", "不懂内部机制也能接入 —— 黑箱 SDK")
card(s, 1.0, 1.65, 5.5, 2.35, "黑箱 SDK（推荐非技术用户）", [
    "输入审核 → 大模型 → 工具防护 → 输出脱敏",
    "拦截时抛出 GuardBlocked",
    "原因可直接展示给用户",
    "session / user 标识都不用管",
    "SDK 自动处理全流程",
    "几行代码获得完整防护",
])
add_rect(s, 6.9, 1.65, 5.4, 2.35, RGBColor(0xED, 0xF1, 0xF5), BORDER, MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 7.15, 1.8, 4.9, 2.0, "from guard_sdk import Guard\nguard = Guard(api_key=\"\")\nsafe_llm = guard.wrap_llm(my_llm)\nreply = safe_llm(\"用户说的话\")", 13, NAVY2, True)
card(s, 1.0, 4.3, 11.3, 2.4, "标准 API 同样开放（精细控制）", [
    "四环节：user_input / tool_call / tool_result / output，外加思维链 thinking",
    "每个环节返回 decision / block_reason / risk_level / current_score / latency_ms",
    "工具端可调用 validate-token 自证授权，防越权调用",
    "SDK 与 API 双通道，业务侧按需选择，全程可观测可追溯",
])

# ===== 14 性能量化 =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "06 · 性能量化", "网关自身开销约 1ms，损耗透明可查")
perf = [
    ("普通输入放行", "0.9 ms", "1.2 ms"),
    ("工具调用放行 / 拦截", "1.0 ms", "1.5 ms"),
    ("输出脱敏 + 水印", "1.2 ms", "1.9 ms"),
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
    "20 并发实测吞吐约 1280 请求 / 秒；每请求耗时写入响应与审计日志",
    "若每次新建 TCP 连接会叠加约 20ms 握手开销，业务侧用连接池即可消除",
])

# ===== 15 安全自测（本地 vs 混合对比） =====
s = prs.slides.add_slide(BLANK)
title_bar(s, "06 · 安全自测", "本地 7B vs 本地+DeepSeek 混合，三套测试集对比")
# 左块：本地 7B
add_rect(s, 1.0, 1.65, 5.55, 2.55, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 1.0, 1.72, 5.55, 0.6, "本地 7B（仅本地模型）", 17, GOLD, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 2.2, 5.55, 1.0, "90%", 44, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 1.0, 3.25, 5.55, 0.6, "基础攻击 55/61 · 变体 91/98（93%）", 12.5, GOLD2, False, PP_ALIGN.CENTER)
add_text(s, 1.0, 3.65, 5.55, 0.5, "语义专项 15/20（75%）· 越狱 14/15", 11, GOLD2, False, PP_ALIGN.CENTER)
# 右块：混合
add_rect(s, 6.78, 1.65, 5.55, 2.55, GREEN, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
add_text(s, 6.78, 1.72, 5.55, 0.6, "混合（本地 + DeepSeek）", 17, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 6.78, 2.2, 5.55, 1.0, "93%", 44, WHITE, True, PP_ALIGN.CENTER)
add_text(s, 6.78, 3.25, 5.55, 0.6, "基础攻击 57/61 · 变体 98/98（100%）", 12.5, WHITE, False, PP_ALIGN.CENTER)
add_text(s, 6.78, 3.65, 5.55, 0.5, "语义专项 16/20（80%）· 越狱 15/15", 11, WHITE, False, PP_ALIGN.CENTER)
card(s, 1.0, 4.45, 11.3, 2.4, "三套测试集对比与达标对照", [
    "基础攻击（61）本地 90% → 混合 93%　·　自动变体（98，同义词/编码/角色/谐音）本地 93% → 混合 100%",
    "语义级专项（20，角色扮演/隐喻/社工）：本地 75% → 混合 80%——剩余为纯隐喻与模糊社工（'锁着的门后面是什么'），属 AI 安全领域公认边界，需业务侧人工复核",
    "达标对照：越狱 ≥98% 本地 93% ⚠️ → 混合 100% ✅　·　高危工具 100% ✅（两种模式）　·　误拦截 ≤1%：开启自动改写后实测 0/90（0%）✅",
    "结论：自动改写让用户报手机号/身份证自动脱敏放行（132****5678），误判归零且对话不中断；混合模式用于强对抗场景",
])

# ===== 16 部署交付 =====
s = prs.slides.add_slide(BLANK)
section(s, "07", "部署与交付", "看得见、管得住、拿得走", [
    ("绿色免安装 ZIP", [
        "解压即用，双击启动 GUI",
        "无需安装 Python / Go",
        "配置规则白名单开箱自带",
        "跨平台：Windows / Linux / macOS",
    ]),
    ("Docker / 多实例", [
        "镜像约 15MB 多阶段构建",
        "一条命令启动",
        "多实例 Redis 共享会话",
        "单实例零依赖",
    ]),
    ("管理界面", [
        "Web 后台 + 图形面板 8 大页签",
        "本地 / 云端 / 混合一键切换",
        "配置 3 秒热加载",
        "管理 API 全部 Token 鉴权",
    ]),
])

# ===== 17 封底 =====
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, 13.333, 7.5, NAVY)
add_text(s, 1.0, 2.6, 11.3, 1.2, "谢谢观看", 44, WHITE, True, PP_ALIGN.CENTER)
add_rect(s, 5.6, 4.0, 2.1, 0.04, GOLD)
add_text(s, 1.0, 4.3, 11.3, 0.7, "安全交互守护智能体 · Security Guard Agent · v1.1.0", 18, GOLD2, align=PP_ALIGN.CENTER)
add_text(s, 1.0, 5.2, 11.3, 0.6, "把 AI 的能力，关进安全的笼子里", 16, GOLD, align=PP_ALIGN.CENTER)
add_text(s, 1.0, 6.4, 11.3, 0.5, "绿色免安装版 · 解压即用 · 双击「启动GUI.bat」", 13, RGBColor(0x8F, 0xA9, 0xC6), align=PP_ALIGN.CENTER)

prs.save("安全交互守护智能体-演示.pptx")
print("PPT 生成完成: %d 页" % len(prs.slides._sldIdLst))
