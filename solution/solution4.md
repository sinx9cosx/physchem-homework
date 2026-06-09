网页代码问题说明及修改建议

# 1. 可逆过程 trace 数组无限增长

**位置**：`recordRevTrace()` 函数

主模拟有 `shift()` 限制数组长度为 `traceLen`（260），但可逆模拟的 `recordRevTrace()` **只 push 不移除**：

```javascript
function recordRevTrace() {
    revSim.trace.vol.push(revSim.currentVolume);
    revSim.trace.pGas.push(revSim.currentP);
    // ... 没有 shift()！
}
```

若用户设置 3000 步，每条数组会增长到 3000+ 元素。在 `drawRevTrace()` 中：
```javascript
const x = padL + (i / Math.max(arr.length - 1, 1)) * pw;
```
会导致曲线被持续压缩，后续数据点几乎不可分辨。

# 2. `updateRevStats()` 不在动画循环中，数据显示不实时

**位置**：`animate()` 函数

`animate()` 中**只更新画布**，不更新统计面板：

```javascript
if (rev_running) {
    stepReversible();      // 或 stepRevIsochoric()
    drawRevSimulation();   // ← 只画图
}
if (rev_active) {
    drawRevTrace();
    drawRevEnergy();
}
// 缺少 updateRevStats()
```
修改：要实时更新统计面板

# 3.死 CSS 代码

`.theory` 和 `.theory-grid` 等样式定义了但 HTML 中从未使用（所有理论卡用的是 `.lecture`）：

```css
.theory { ... }        /* 未使用 */
.theory h2 { ... }     /* 未使用 */
.theory-grid { ... }   /* 未使用 */
```

修改：建议清理

# 4. 加速膨胀时粒子的非物理行为

**位置**：`stepOne()` 末尾的粒子限位逻辑

```javascript
for (const p of particles) {
    if (p.x > xP - r) {
        p.x = xP - r;
        p.vx = Math.min(p.vx, vP - Math.abs(p.vx) * 0.2);
    }
}
```

这段代码在活塞碰撞处理**之后**再次将越界粒子强行拉回，并对其 vx 做经验性削减。其物理含义含糊——如果活塞已经正确处理了碰撞（前面的 `if (p.x > xP - r)` 分支），为什么还需要这个"二次矫正"？

在强膨胀 (`Pext/P₀ = 0.35`) 时，活塞快速右移，部分粒子可能"穿透"活塞（尤其是 dt 较大时）。这段代码是一个 ad-hoc 补丁，不是物理碰撞。

修改：使用子步（sub-stepping）替代经验修正

# 5. 渐近稳定判据缺失

理论卡第 9 节说：
> 判断"过程结束"时，应等到体系接近新的稳定状态

但代码中没有自动检测过程结束的机制——模拟会一直运行。学生需要自己判断何时停止。虽然这是"教学演示"的合理选择，但可以加入一个简单的指标（如活塞速度 < 阈值 + 压力均衡度 < 阈值）并以视觉方式提示。



# 6. 滑块拖动后自动重置的行为差异

- `posSlider.onchange` → 调用 `initialize()`（拖动后立即重置）
- `ratioSlider.oninput` → 仅 `updateLabels()`（不重置，需手动点重置）

修改：统一行为——要么都在 `onchange` 时重置并给出 toast 提示，要么都只在"重置"按钮时生效。