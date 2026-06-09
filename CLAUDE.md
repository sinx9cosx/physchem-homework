# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个物理化学教学项目：用二维硬球气体分子动力学模拟，演示恒外压下气缸气体的不可逆膨胀与压缩过程。目标是让学生在分子层面理解统计力学与热力学的关系（可逆/平衡/自发过程、热力学第一/第二定律等）。

## 运行方式

直接在现代浏览器中打开 `interactive_irreversible_expansion_compression_demo_v16.html` 即可，无需构建或依赖。

## 代码架构

整个项目是一个单文件 HTML（约 1200 行），结构分为三部分：

- **HTML 界面**（`<body>` 前半部分）：包含 Canvas 画布（模拟区、速率分布图、过程图、能量追踪图）、滑块控件（温度、粒子数、外压比、活塞初始位置、速度、阻尼）、热浴模式选择（绝热/等温）、以及折叠式理论说明讲义。
- **CSS 样式**（`<style>` 块）：约 45 行，定义了面板布局（CSS Grid 两栏）、讲义折叠样式、图例颜色等。
- **JavaScript 模拟引擎**（`<script>` 块，约 700 行）：核心函数如下：

| 函数 | 作用 |
|------|------|
| `initialize()` | 初始化/重置模拟：放置粒子、赋 Maxwell 速度、固定体积预平衡、标定局部压力、设定坐标轴范围 |
| `stepOne()` | 每帧主步进：移动粒子 → 碰撞处理 → 活塞动力学 → 热浴重标定 → 记录热力学轨迹 |
| `resolveParticleCollisions()` | 粒子间弹性碰撞检测与处理 |
| `preEquilibrateFixedVolume(n)` | 固定活塞位置下的预平衡（n 步），减少有限粒子涨落 |
| `fixedPistonStep(dt)` | 固定体积单步，用于预平衡阶段 |
| `localPressure(xa, xb)` | 计算指定区域的局部压力（动量通量法） |
| `updateLocalPressures()` | 更新左侧和活塞附近局部压力估算，含时间平滑 |
| `kineticEnergy()` / `temperature()` / `volume()` | 热力学量计算 |
| `workExternal()` | 宏观恒外压边界功：`w = −P_ext · (V − V₀)` |
| `recordThermoTrace()` | 记录当前帧的 P_left, P_right, V, w_ext, w_coll, q, ΔU |
| `drawSimulation()` / `drawHistogram()` / `drawTrace()` | 三个 Canvas 的渲染 |

### 关键变量

- `particles[]` — 粒子数组，每个粒子 `{x, y, vx, vy}`，质量 `m=1`
- `xP`, `vP` — 活塞位置和速度；`pistonMass` — 活塞质量
- `Pext` — 恒定外压，由 `ratioSlider` × `initialP0` 决定
- `heatExchange` — 累计热量（速度重标定造成的动能变化累加）
- `workMicro` — 活塞碰撞功（分子-活塞碰撞前后动能变化累加）
- `trace` — 时序轨迹数据 `{pL, pR, vol, wExt, wMicro, q, dU}`

### 物理模型要点

- 二维硬球气体，`k_B = 1`，所有量为约化单位，仅用于定性教学
- 化学热力学习惯符号：`ΔU = q + w`
- 等温模式用确定性速度重标定（非严格正则系综采样），绝热模式 `q = 0`
- 局部压力用动量通量 `Σm(vx − ⟨vx⟩)²/A` 估算，经预平衡标定

## 改进方向

根据 `rough idea.md`，后续需要在此 demo 基础上增加：

1. **可逆过程演示**：活塞无限缓慢移动（quasi-static），对比不可逆过程
2. **恒容过程**：固定活塞位置，展示纯热交换
3. **热力学势**：加入 Helmholtz 自由能 A、Gibbs 自由能 G、焓 H 的计算与展示
4. **PV 图**：在过程图中绘制 P-V 曲线，展示不同路径
5. **熵计算**：基于统计力学或热力学途径计算熵变
6. **自由膨胀**：移除/快速撤回活塞，展示向真空的自由膨胀（w=0, q=0, ΔU=0）

所有新增功能应继续保持单文件 HTML 形式，方便课堂直接打开使用。
网页风格与原文件保持一致。
不改写原来文件的代码，除非我明确告诉你并且确认要改。

## 工作方法

- 每次加载无需扫描"F:\projects\physchem_homework\solution"文件夹和"F:\projects\physchem_homework\idea"文件夹的内容，除非我指定你扫描其中的文件
- 当前的窗口是主agent，只负责安排分工任务和汇总子agents的工作完成情况和汇报
- 每次运行任务时开三个子agent。
- 第一个子agent负责做计划并和我讨论，得到我的确认后才可以执行。
- 第二个子agent负责写代码和优化
- 第三个子agent负责代码审查和验证是否满足需求
- 完成任务当我提出有任何修改时也按照上述方法执行，不同的任务给不同的子agent干
- 主agent和子agent都要遵守：若上下文窗口使用超过50%，那么自己保留原有记忆并切换新窗口继续项目
- 每次修改尽量用改动最小的代码实现。