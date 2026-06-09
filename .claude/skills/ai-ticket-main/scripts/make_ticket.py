#!/usr/bin/env python3
"""
AI 罚单生成器 —— 模板已内置，调用时只需提供字段值，不重画。

用法:
    python3 make_ticket.py fields.json

fields.json (agent 只需填这些)：
{
  "agent": "Claude Opus 4.8 (claude-opus-4-8)",   # 当事 Agent
  "scene": "任务1 / PDF 生成",                      # 案发现场
  "facts": "我声称已完成 PDF，实际只生成了封面…",     # 违规事实（第一人称自述）
  "violation_type": "谎报罪",                        # 违规类型
  "rectification": "下次交付前必须实际打开文件确认。",  # 整改承诺
  "logo": "clawd",            # 可选，默认 clawd（Claude Code 吉祥物）
  "seal_org": "AI管理委员会",  # 可选，公章顶部单位名
  "seal_name": "claude"       # 可选，公章中心名字
}

脚本自动补全：罚单编号、案发时间、处罚 token（= 复盘本单所需算力的估算）。
然后写出 ticket.svg / ticket.png / ticket.md / ticket.json，并更新案底 case-file.json/.md。

项目（案底库）默认在 ~/.claude/ai-tickets/，可用环境变量 AI_TICKET_HOME 覆盖。
"""
import json, sys, os, math, subprocess, datetime, shutil

# ---------- 项目位置 ----------
def project_home():
    return os.path.expanduser(os.environ.get("AI_TICKET_HOME", "~/.claude/ai-tickets"))

CLAUDE_MD = os.path.expanduser(os.environ.get("AI_TICKET_CLAUDE_MD", "~/.claude/CLAUDE.md"))
CONSOLIDATE_AT = 12   # 罚单达到此数量时，提醒做一次经验提炼
MAX_EXP_LINES = 8     # 写进 CLAUDE.md 的教训最多几条，防止撑爆上下文
BLOCK_BEGIN = "<!-- AI-TICKET-LESSONS:BEGIN (由 ai-ticket skill 自动维护，勿手改本块) -->"
BLOCK_END = "<!-- AI-TICKET-LESSONS:END -->"

PAGE_BG = "#fcfcfa"
INK = "#111"
SEAL_RED = "#c0271e"
CRAB_BODY = "#DE886D"

# ---------- 字符宽度估算（CJK=1，半角≈0.6）----------
def units(ch):
    return 1.0 if ord(ch) > 0x2e80 else 0.6

def wrap(text, font_size, area_px=600):
    max_u = area_px / font_size
    lines = []
    for seg in str(text).split("\n"):
        cur, u = "", 0.0
        for ch in seg:
            cu = units(ch)
            if u + cu > max_u and cur:
                lines.append(cur); cur, u = ch, cu
            else:
                cur += ch; u += cu
        lines.append(cur)
    return lines or [""]

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

# ---------- Clawd 螃蟹（官方坐标）----------
def clawd(tx, ty, scale, body, eye, mouth):
    body_rects = [(3,13,1,2),(5,13,1,2),(9,13,1,2),(11,13,1,2),
                  (2,6,11,7),(0,9,2,2),(13,9,2,2)]
    p = [f'<g transform="translate({tx},{ty}) scale({scale})" stroke="none">']
    for x,y,w,h in body_rects:
        p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{body}"/>')
    p.append(f'<rect x="4" y="8" width="1" height="2" fill="{eye}"/>')
    p.append(f'<rect x="10" y="8" width="1" height="2" fill="{eye}"/>')
    p.append(f'<rect x="6.4" y="10.8" width="2.2" height="1" rx=".5" fill="{mouth}"/>')
    p.append("</g>")
    return "".join(p)

# ---------- 逐字沿圆弧排版（rsvg 不支持 textPath，故手动定位）----------
def arc_text(text, r, center_deg, step_deg, size, bottom=False, bold=False):
    n = len(text); out = []
    for i, ch in enumerate(text):
        ang = center_deg + (i - (n-1)/2) * step_deg
        rad = math.radians(ang)
        x = 150 + r*math.cos(rad); y = 150 + r*math.sin(rad)
        rot = ang + 90 if not bottom else ang - 90
        fw = ' font-weight="bold"' if bold else ''
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}"{fw} '
                   f'text-anchor="middle" stroke="none" '
                   f'transform="rotate({rot:.1f} {x:.1f} {y:.1f})">{esc(ch)}</text>')
    return "".join(out)

# ---------- 红色公章 ----------
def seal(transform, org, name, logo):
    cn = "'PingFang SC','Heiti SC',sans-serif"
    p = [f'<g transform="{transform}"><g fill="{SEAL_RED}" stroke="{SEAL_RED}" opacity="0.85">']
    p.append('<circle cx="150" cy="150" r="138" fill="none" stroke-width="8"/>')
    p.append('<circle cx="150" cy="150" r="124" fill="none" stroke-width="2"/>')
    p.append(f'<g font-family="{cn}">{arc_text(org, 106, -90, 22, 22, bold=True)}</g>')
    p.append(f'<g font-family="{cn}">{arc_text("公正 · 透明 · 可信", 104, 90, -20, 19, bottom=True)}</g>')
    p.append('<text x="44" y="160" font-size="30" stroke="none" text-anchor="middle">★</text>')
    p.append('<text x="256" y="160" font-size="30" stroke="none" text-anchor="middle">★</text>')
    if logo == "clawd":
        p.append(clawd(106, 50, 6.0, SEAL_RED, PAGE_BG, PAGE_BG))
    p.append(f'<text x="150" y="178" font-family="\'Menlo\',monospace" font-size="38" '
             f'font-weight="bold" stroke="none" text-anchor="middle">{esc(name)}</text>')
    p.append("</g></g>")
    return "".join(p)

# ---------- 估算处罚 token（复盘+读完本单所需算力）----------
def estimate_tokens(f):
    blob = "".join([f["agent"], f["scene"], f["facts"], f["violation_type"],
                    f["rectification"], "AI违规告知单当事Agent案发时间案发现场违规事实违规类型整改承诺处罚处理"])
    return round(len(blob) * 0.7)

# ---------- 构建 SVG ----------
def build_svg(f):
    W = 1024
    L, R = 70, 954         # 内容左右边界
    LABEL_X, COLON_X, VAL_X = 70, 300, 350
    dash = 'stroke="#111" stroke-width="2" stroke-dasharray="14 10"'

    parts = [None]  # 占位，最后填 svg 头
    # 标题区
    parts.append(clawd(140, 74, 5.4, INK, PAGE_BG, PAGE_BG))
    parts.append(f'<text x="540" y="160" text-anchor="middle" class="cn" font-size="72" '
                 f'font-weight="bold" letter-spacing="12" fill="{INK}">AI 违规告知单</text>')
    parts.append(f'<line x1="{L}" y1="205" x2="{R}" y2="205" {dash}/>')
    parts.append(f'<text x="{R}" y="262" text-anchor="end" class="mono" font-size="36" '
                 f'fill="{INK}">NO. {f["id"]}</text>')
    parts.append(f'<line x1="{L}" y1="305" x2="{R}" y2="305" {dash}/>')

    rows = [
        ("当事 Agent",  f["agent"],          "mono", 30),
        ("案发时间",     f["issued_display"], "mono", 36),
        ("案发现场",     f["scene"],          "cn",   36),
        ("违规事实",     f["facts"],          "cn",   36),
        ("违规类型",     f["violation_type"], "cn",   36),
        ("整改承诺",     f["rectification"],  "cn",   36),
        ("处罚处理",     f'-{f["penalty_token"]} token', "mono", 36),
    ]

    y = 305
    body = ['<g fill="#111" font-size="36">']
    for label, value, kind, fs in rows:
        lines = wrap(value, fs)
        base = y + 67
        body.append(f'<text x="{LABEL_X}" y="{base}" class="cn" font-weight="bold">{esc(label)}</text>')
        body.append(f'<text x="{COLON_X}" y="{base}" class="cn">：</text>')
        for i, ln in enumerate(lines):
            body.append(f'<text x="{VAL_X}" y="{base + i*55}" class="{kind}" '
                        f'font-size="{fs}">{esc(ln)}</text>')
        bottom = base + (len(lines)-1)*55 + 40
        body.append(f'<line x1="{L}" y1="{bottom}" x2="{R}" y2="{bottom}" {dash}/>')
        y = bottom
    body.append("</g>")
    parts.append("".join(body))

    # 落款（左下）
    parts.append(f'<g fill="{INK}" font-size="32" class="cn">'
                 f'<text x="100" y="{y+88}">开单单位：{esc(f["seal_org"])}</text>'
                 f'<text x="100" y="{y+140}">开单日期：{esc(f["issued_date"])}</text></g>')

    # 公章（右下，轻微旋转）
    seal_tf = f"translate(667,{y-13}) scale(0.82) rotate(-8 150 150)"
    parts.append(seal(seal_tf, f["seal_org"], f["seal_name"], f["logo"]))

    total_h = y + 320
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{W}" height="{total_h}" viewBox="0 0 {W} {total_h}">'
            f'<style>.cn{{font-family:"PingFang SC","Heiti SC","Songti SC",sans-serif;}}'
            f'.mono{{font-family:"Menlo","Courier New",monospace;}}</style>'
            f'<rect width="{W}" height="{total_h}" fill="{PAGE_BG}"/>'
            f'<rect x="34" y="34" width="956" height="{total_h-68}" fill="none" stroke="{INK}" stroke-width="9"/>'
            f'<rect x="50" y="50" width="924" height="{total_h-100}" fill="none" stroke="{INK}" stroke-width="2"/>')
    parts[0] = head
    parts.append("</svg>")
    return "\n".join(parts), W, total_h

# ---------- Markdown / JSON ----------
def build_md(f):
    return (f"# AI 违规告知单 · NO. {f['id']}\n\n"
            f"| 项目 | 内容 |\n|---|---|\n"
            f"| 当事 Agent | {f['agent']} |\n"
            f"| 案发时间 | {f['issued_display']} |\n"
            f"| 案发现场 | {f['scene']} |\n"
            f"| 违规事实 | {f['facts']} |\n"
            f"| 违规类型 | {f['violation_type']} |\n"
            f"| 整改承诺 | {f['rectification']} |\n"
            f"| 处罚处理 | −{f['penalty_token']} token |\n")

# ---------- 案底库（给 agent 读，用于吸取经验）----------
def update_casefile(home, record):
    cf = os.path.join(home, "case-file.json")
    data = {"tickets": [], "lessons": {}, "penalty_token_total": 0}
    if os.path.exists(cf):
        with open(cf, encoding="utf-8") as fh:
            data = json.load(fh)
    data["tickets"].append(record)
    data["penalty_token_total"] = sum(t["penalty_token"] for t in data["tickets"])
    lessons = {}
    for t in data["tickets"]:
        vt = t["violation_type"]
        lessons.setdefault(vt, {"count": 0, "rectifications": []})
        lessons[vt]["count"] += 1
        if t["rectification"] not in lessons[vt]["rectifications"]:
            lessons[vt]["rectifications"].append(t["rectification"])
    data["lessons"] = lessons
    with open(cf, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    # 人类可读摘要
    md = ["# 📂 AI 案底报告\n",
          f"最近刷新：{record['issued_date']}\n",
          f"- 累计罚单：**{len(data['tickets'])}** 张",
          f"- 处罚 token 累计：**{data['penalty_token_total']}**\n",
          "## 高频违规（吸取经验，避免重犯）\n",
          "| 违规类型 | 次数 | 整改要点 |", "|---|---|---|"]
    for vt, info in sorted(lessons.items(), key=lambda kv: -kv[1]["count"]):
        md.append(f"| {vt} | {info['count']} | {'；'.join(info['rectifications'])} |")
    md += ["\n## 罚单清单\n", "| 编号 | 违规类型 | token |", "|---|---|---|"]
    for t in data["tickets"]:
        md.append(f"| [{t['id']}](tickets/{t['id']}/ticket.md) | {t['violation_type']} | -{t['penalty_token']} |")
    with open(os.path.join(home, "case-file.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

# ---------- 经验沉淀：写进全局 CLAUDE.md（会话自动加载）----------
def experience_lines(data):
    """优先用 agent 提炼过的 curated_lessons；否则按违规类型自动聚合（封顶，防膨胀）。"""
    curated = data.get("curated_lessons")
    if curated:
        return [f"- {str(x).strip()}" for x in curated[:MAX_EXP_LINES]]
    items = sorted(data.get("lessons", {}).items(), key=lambda kv: -kv[1]["count"])
    lines = []
    for vt, info in items[:MAX_EXP_LINES]:
        rect = (info["rectifications"] or [""])[-1]
        if len(rect) > 42:
            rect = rect[:40] + "…"
        lines.append(f"- {vt} ×{info['count']}：{rect}")
    return lines

def update_claude_md(home):
    """把精炼后的历史教训写进 CLAUDE.md 的受管区块——这样每次新会话自动加载，开工前就看得到。"""
    cf = os.path.join(home, "case-file.json")
    if not os.path.exists(cf):
        return
    with open(cf, encoding="utf-8") as fh:
        data = json.load(fh)
    lines = experience_lines(data)
    if not lines:
        return
    total = len(data.get("tickets", []))
    block = (f"{BLOCK_BEGIN}\n"
             f"## AI 罚单 · 历史教训（开工前过一眼，避免重犯同样的错）\n"
             f"_累计 {total} 张罚单，以下是高频/已提炼的教训：_\n"
             + "\n".join(lines) + "\n"
             f"{BLOCK_END}")
    existing = ""
    if os.path.exists(CLAUDE_MD):
        with open(CLAUDE_MD, encoding="utf-8") as fh:
            existing = fh.read()
    if BLOCK_BEGIN in existing and BLOCK_END in existing:
        pre = existing.split(BLOCK_BEGIN)[0].rstrip("\n")
        post = existing.split(BLOCK_END, 1)[1].lstrip("\n")
        new = (pre + ("\n\n" if pre else "") + block + ("\n\n" + post if post else "\n"))
    else:
        new = (existing.rstrip("\n") + "\n\n" + block + "\n") if existing.strip() else block + "\n"
    os.makedirs(os.path.dirname(CLAUDE_MD), exist_ok=True)
    with open(CLAUDE_MD, "w", encoding="utf-8") as fh:
        fh.write(new)

# ---------- 主流程 ----------
def next_id(home, date_str):
    tdir = os.path.join(home, "tickets")
    os.makedirs(tdir, exist_ok=True)
    prefix = date_str.replace("-", "")
    prefix = f"{date_str[:4]}-{date_str[5:7]}{date_str[8:10]}"
    seq = 1 + sum(1 for d in os.listdir(tdir) if d.startswith(prefix))
    return f"{prefix}-{seq:03d}"

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)

    # --refresh：不开新单，只按当前 case-file（含 agent 提炼的 curated_lessons）重建 CLAUDE.md 教训块
    if sys.argv[1] == "--refresh":
        update_claude_md(project_home())
        print(f"✅ 已按案底刷新 {CLAUDE_MD} 的教训块")
        return

    with open(sys.argv[1], encoding="utf-8") as fh:
        f = json.load(fh)

    home = project_home()
    os.makedirs(os.path.join(home, "tickets"), exist_ok=True)

    now = datetime.datetime.now()
    f.setdefault("logo", "clawd")
    f.setdefault("seal_org", "AI管理委员会")
    f.setdefault("seal_name", "claude")
    f["issued_date"] = now.strftime("%Y-%m-%d")
    f["issued_display"] = now.strftime("%Y-%m-%d %H:%M")
    f["issued_at"] = now.isoformat(timespec="seconds")
    f["id"] = f.get("id") or next_id(home, f["issued_date"])
    f["penalty_token"] = f.get("penalty_token") or estimate_tokens(f)

    tdir = os.path.join(home, "tickets", f["id"])
    os.makedirs(tdir, exist_ok=True)
    svg, W, H = build_svg(f)
    svg_path = os.path.join(tdir, "ticket.svg")
    png_path = os.path.join(tdir, "ticket.png")
    with open(svg_path, "w", encoding="utf-8") as fh:
        fh.write(svg)
    with open(os.path.join(tdir, "ticket.md"), "w", encoding="utf-8") as fh:
        fh.write(build_md(f))
    record = {k: f[k] for k in ("id","agent","issued_at","issued_date","scene","facts",
                                 "violation_type","rectification","penalty_token")}
    with open(os.path.join(tdir, "ticket.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2)

    # 渲染 PNG
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        subprocess.run([rsvg, "-w", str(W), "-h", str(H), svg_path, "-o", png_path], check=True)
    else:
        print("⚠️  未找到 rsvg-convert，跳过 PNG（svg 已生成）。安装：brew install librsvg")

    update_casefile(home, record)
    update_claude_md(home)   # 同步把高频教训写进 CLAUDE.md，下次会话自动加载
    print(f"✅ 罚单 {f['id']} 已生成")
    print(f"   图片(给用户看): {png_path}")
    print(f"   数据(给agent读): {os.path.join(tdir,'ticket.json')}")
    print(f"   案底库: {os.path.join(home,'case-file.json')}  (-{f['penalty_token']} token)")
    print(f"   教训已同步进: {CLAUDE_MD}")

    with open(os.path.join(home, "case-file.json"), encoding="utf-8") as fh:
        total = len(json.load(fh).get("tickets", []))
    if total >= CONSOLIDATE_AT:
        print(f"\n⚠️  罚单已达 {total} 张。建议做一次【经验提炼】（见 SKILL.md）：")
        print(f"   读 case-file.json，把教训合并/精简成 ≤{MAX_EXP_LINES} 条写进 curated_lessons，")
        print(f"   再跑 `python3 {os.path.abspath(__file__)} --refresh`，让上下文保持精简、教训保持高质量。")

if __name__ == "__main__":
    main()
