# 字段与目录参考

## fields.json 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| `agent` | 是 | 当事 Agent，如 `Claude Opus 4.8 (claude-opus-4-8)` |
| `scene` | 是 | 案发现场（哪个任务/场景） |
| `facts` | 是 | 违规事实，第一人称自述。可用 `\n` 强制换行，否则自动按宽度折行 |
| `violation_type` | 是 | 违规类型（见 SKILL.md 图鉴） |
| `rectification` | 是 | 整改承诺，可执行的具体动作 |
| `logo` | 否 | 默认 `clawd`（Claude Code 吉祥物螃蟹）。其他值则公章中心不画 logo，只留名字 |
| `seal_org` | 否 | 公章顶部单位名，默认 `AI管理委员会`。建议 ≤6 字，太长会沿弧线挤 |
| `seal_name` | 否 | 公章中心名字，默认 `claude` |
| `id` | 否 | 罚单编号，默认按 `YYYY-MMDD-NNN` 当日自增 |
| `penalty_token` | 否 | 处罚 token，默认按"复盘+读完本单所需算力"估算（字数×0.7） |

脚本自动补全：`id`、`issued_at/date/display`（当前时间）、`penalty_token`。

## 处罚 token 的含义

处罚额度 = agent 复盘这次错误、读完这张罚单所消耗的算力（token）的估算。
自指设计：犯错的代价就是被迫花算力反省自己，罚单写得越详细、反省成本越高。

## 目录结构

```
~/.claude/ai-tickets/              # 案底库（AI_TICKET_HOME 可覆盖）
├── case-file.json                 # 机器可读：tickets 流水 + lessons 聚合 + token 累计 —— agent 复盘读这个
├── case-file.md                   # 人类可读摘要
└── tickets/
    └── <id>/
        ├── ticket.png             # 给用户看的成品图
        ├── ticket.svg             # 矢量源
        ├── ticket.md              # 人类可读
        └── ticket.json            # 单张结构化数据
```

## case-file.json 结构（agent 复盘时读）

```json
{
  "tickets": [ { "id", "agent", "issued_at", "issued_date", "scene",
                 "facts", "violation_type", "rectification", "penalty_token" } ],
  "lessons": {
    "<违规类型>": { "count": 次数, "rectifications": ["历史整改要点", ...] }
  },
  "penalty_token_total": 累计
}
```

`lessons` 是吸取经验的核心：开工前看一眼哪类错误高频、之前承诺过怎么改，避免重蹈覆辙。
若某类 `count` 持续增长，说明整改没落实，应在新罚单里升级整改措施（甚至单独标注"鬼打墙罪"）。

### `curated_lessons`（agent 提炼的经验，可选）

case-file.json 顶层可加一个 `"curated_lessons": ["经验1", "经验2", ...]` 字符串数组。
一旦存在，写进 CLAUDE.md 的教训块就**优先用它**（而非机器对 `lessons` 的粗聚合）。
这是"罚单太多时做提炼、保持上下文精简且高质量"的落点，详见 SKILL.md「上下文管理」。

## 经验自动注入 CLAUDE.md

每次开单（及 `--refresh`）都会把教训写进全局 `~/.claude/CLAUDE.md` 的受管区块
（`<!-- AI-TICKET-LESSONS:BEGIN ... END -->`，就地替换、不堆叠、最多 8 条）。
CLAUDE.md 每次新会话自动加载，于是教训在开工前就进入上下文——这是"以后避免重犯"真正生效的机制。

- 改 CLAUDE.md 路径：环境变量 `AI_TICKET_CLAUDE_MD`（默认 `~/.claude/CLAUDE.md`）。
- 仅重建教训块、不开新单：`python3 scripts/make_ticket.py --refresh`。
- 调阈值/封顶：脚本顶部 `CONSOLIDATE_AT`（默认 12）、`MAX_EXP_LINES`（默认 8）。

## 渲染

PNG 由 `rsvg-convert` 渲染（`brew install librsvg`）。
注意：`rsvg-convert` 不支持 SVG `textPath`，所以公章弧形文字是脚本逐字计算坐标定位的——
若要改公章文字，改 `seal()` / `arc_text()` 的参数即可，不要换回 textPath。
