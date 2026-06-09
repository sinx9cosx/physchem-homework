# 可逆过程模块：三个核心问题的修复方案

## 问题总览

| # | 严重程度 | 问题 |
|:---:|:---:|---|
| 1 | 🔴 严重 | 等温可逆 ΔS_sys 由速度重标定的 `dq/T` 累加得到，非真正可逆热温商 |
| 2 | 🟡 中等 | 可逆过程同时跑微观碰撞 + 宏观热修正，两套动力学存在尺度冲突 |
| 3 | 🟡 中等 | 等温不可逆 ΔS_sys 直接赋值 `dSsysIrr = dSsysRev`，未验证终态一致 |

---

## 问题 1：等温可逆 ΔS_sys 的来源不可靠

### 问题本质

当前代码：

```javascript
// 等温模式下速度重标定
const scale = Math.sqrt(targetK / kBefore);
for (const p of rev_particles) { p.vx *= scale; p.vy *= scale; }
dq_step = kAfter - kBefore;

// 熵变直接用 dq/T 累加
dS_sys_step = dq_step / T_bath;
rev_cum_dS_sys += dS_sys_step;
```

速度重标定是**确定性全局缩放**，不是热力学意义上的可逆热传递。虽然数值上 `Σ dq/T ≈ Nk·ln(V_f/V_i)`（因为 `dq ≈ -dw` 的能量守恒），但这是巧合而非物理必然。

### 修复方案

**改为直接从状态函数公式计算 ΔS_sys**。熵是状态函数，对理想气体可精确写为闭式表达式，无需依赖 `dq/T` 的数值累加。

#### 修正后的 `stepReversible()` 熵计算部分

```javascript
// ===== 等温模式 =====
if (heatModeSelect.value === 'isothermal') {
  // 速度重标定（仅用于维持温度，不再用于计算熵）
  const targetK = N * rev_initialT0;
  if (kBefore > 1e-12) {
    const scale = Math.sqrt(targetK / kBefore);
    for (const p of rev_particles) {
      p.vx *= scale;
      p.vy *= scale;
    }
    const kAfter = revKineticEnergy();
    dq_step = kAfter - kBefore;
    rev_heatExchange += dq_step;
  }

  // ★ 熵变：直接由状态函数公式计算（等温，二维理想气体）
  const V = revVolume();
  rev_cum_dS_sys = N * Math.log(V / rev_initialV0);     // 系统熵变
  rev_cum_dS_surr = -rev_heatExchange / rev_initialT0;   // 环境熵变
  rev_cum_dS_univ = rev_cum_dS_sys + rev_cum_dS_surr;    // 总熵变
}

// ===== 绝热模式 =====
else {
  dq_step = 0;
  // ★ 可逆绝热：ΔS_sys ≡ 0，ΔS_univ ≡ 0（直接从定义出发）
  rev_cum_dS_sys  = 0;
  rev_cum_dS_surr = 0;
  rev_cum_dS_univ = 0;
}
```

#### 关键改进

| 改进点 | 原代码 | 修复后 |
|--------|--------|--------|
| `dS_sys` 计算 | `Σ dq_step / T`（依赖控制器行为） | `N·ln(V/V₀)`（严格状态函数，二维等温） |
| `dS_surr` 计算 | 同上 | `-q_total / T_bath`（宏观热效应） |
| 可逆绝热 | 累加 `dq=0` 每一步 | 直接硬置 0，概念更清晰 |

#### 为什么状态函数公式是正确的（二维理想气体）

等温过程（`T = T₀` 恒定）：

$$dU = 0 \quad\Rightarrow\quad \delta q_{\text{rev}} = -\delta w_{\text{rev}} = P\,dV = \frac{NkT}{V}dV$$

$$dS_{\text{sys}} = \frac{\delta q_{\text{rev}}}{T} = \frac{Nk}{V}dV \quad\Rightarrow\quad \Delta S_{\text{sys}} = Nk\ln\frac{V_f}{V_i}$$

这是从状态函数导出的**精确表达式**，与热量是如何具体传递的（随机碰撞还是重标定）无关。

---

## 问题 2：两套动力学并存导致物理含义模糊

### 问题本质

当前可逆过程同时运行：

1. **微观碰撞动力学**：分子与移动活塞弹性碰撞 → 动能传递给活塞（膨胀时分子变慢）
2. **宏观热修正**：速度重标定 → 动能瞬间补回（等温时）

两步在同一时间步内先后发生：
```
Step N:
  ① 活塞位移 dV → 分子撞活塞 → 分子动能↓
  ② 速度重标定     → 分子动能↑↑（补回①的损失 + 等温所需）
```

这导致：
- 每个时间步内，能量经历了"先损失再补回"的人工循环
- `dS_sys` 的每一步累加值取决于该步中重标定补了多少，而非连续可逆热传递
- 微观碰撞和宏观修正的**时间顺序**影响了中间态的熵积累

### 修复方案（推荐方案 A）

**可逆过程不跑分子动力学，纯用宏观解析公式。**

对教学而言，"准静态可逆过程"本身就是理想化的极限——每一步都是平衡态。既然如此，直接解析计算 `P(V)` 和 `w` 比用有限粒子做分子动力学**更准确、更清晰**。

#### 修改后的 `stepReversible()`：纯宏观模式

```javascript
function stepReversible() {
  if (rev_currentStep >= rev_totalSteps) {
    rev_running = false;
    if (irrev_pathRecorded && !workFillAnimating) {
      workFillAnimating = true;
      workFillProgress = 0;
    }
    return;
  }

  const dV_per_step = (rev_targetVolume - rev_initialV0) / rev_totalSteps;

  // 活塞位置：纯几何更新（无分子动力学）
  rev_xP += dV_per_step / H;
  rev_currentStep++;
  if (rev_xP < minX) rev_xP = minX;
  if (rev_xP > maxX) rev_xP = maxX;

  const V  = rev_xP * H;
  const isIso = (heatModeSelect.value === 'isothermal');
  const gamma = 2;  // 二维理想气体 γ = 1 + 2/2 = 2

  // ----- 压力：解析公式 -----
  let P_gas;
  if (isIso) {
    P_gas = N * rev_initialT0 / V;  // 等温：P = NkT₀/V
  } else {
    // 绝热：PV^γ = const
    P_gas = rev_initialP0 * Math.pow(rev_initialV0 / V, gamma);
  }

  // ----- 功：解析积分 -----
  const dw = -P_gas * dV_per_step;
  rev_workMicro += dw;

  // ----- 内能（仅绝热模式有变化） -----
  let dU = 0;
  if (!isIso) {
    const V0 = rev_initialV0;
    dU = (rev_initialP0 * V0 / (gamma - 1))
       * (Math.pow(V0 / V, gamma - 1) - 1);
  }

  // ----- 热量 -----
  let dq_step = 0;
  if (isIso) {
    dq_step = -dw;  // 等温：dU=0 → δq = -δw
    rev_heatExchange += dq_step;
  }

  // ----- 熵变：状态函数公式（不依赖 dq/T 累加）-----
  if (isIso) {
    rev_cum_dS_sys  = N * Math.log(V / rev_initialV0);
    rev_cum_dS_surr = -rev_heatExchange / rev_initialT0;
    rev_cum_dS_univ = rev_cum_dS_sys + rev_cum_dS_surr;
  } else {
    rev_cum_dS_sys  = 0;
    rev_cum_dS_surr = 0;
    rev_cum_dS_univ = 0;
  }

  // ----- 记录 trace -----
  rev_trace.vol.push(V);
  rev_trace.pGas.push(P_gas);
  rev_trace.wRev.push(rev_workMicro);
  rev_trace.qRev.push(rev_heatExchange);
  rev_trace.dU.push(dU);
  rev_trace.dS_sys.push(rev_cum_dS_sys);
  rev_trace.dS_surr.push(rev_cum_dS_surr);
  rev_trace.dS_univ.push(rev_cum_dS_univ);

  rev_time += baseDt * Number(speedSlider.value);

  if (rev_currentStep >= rev_totalSteps) {
    rev_running = false;
    if (irrev_pathRecorded && !workFillAnimating) {
      workFillAnimating = true;
      workFillProgress = 0;
    }
  }
}
```

#### 对应删除的内容

不再需要：
- `rev_particles[]` 及所有粒子初始化/碰撞/壁面反弹代码
- `revKineticEnergy()`、`revTemperature()`、`revResolveCollisions()` 等辅助函数
- `revPreEquilibrateFixedVolume()`、`revMeasureReferencePressure()`
- 可逆过程的速度重标定代码（`heatModeSelect === 'isothermal'` 分支）

`initReversible()` 简化为：

```javascript
function initReversible() {
  rev_xP = xMax * Number(posSlider.value);
  rev_initialV0 = rev_xP * H;
  rev_initialT0 = Number(tempSlider.value);
  rev_initialP0 = N * rev_initialT0 / rev_initialV0;

  const targetRatio = Number(revTargetRatioSlider.value);
  rev_targetVolume = rev_initialV0 * targetRatio;
  const targetXP = rev_targetVolume / H;
  if (targetXP < minX) rev_targetVolume = minX * H;
  if (targetXP > maxX) rev_targetVolume = maxX * H;

  rev_totalSteps = Number(revStepsSlider.value);
  rev_currentStep = 0;
  rev_workMicro = 0;
  rev_heatExchange = 0;
  rev_cum_dS_sys = 0;
  rev_cum_dS_surr = 0;
  rev_cum_dS_univ = 0;
  rev_time = 0;
  rev_active = true;

  rev_trace = { vol:[], pGas:[], wRev:[], qRev:[], dU:[], 
                dS_sys:[], dS_surr:[], dS_univ:[] };

  // 初始种子点
  const P0 = rev_initialP0;
  for (let i = 0; i < 3; i++) {
    rev_trace.vol.push(rev_initialV0);
    rev_trace.pGas.push(P0);
    rev_trace.wRev.push(0);
    rev_trace.qRev.push(0);
    rev_trace.dU.push(0);
    rev_trace.dS_sys.push(0);
    rev_trace.dS_surr.push(0);
    rev_trace.dS_univ.push(0);
  }
}
```

#### 方案 A 的优势

| 维度 | 原实现 | 方案 A |
|------|--------|--------|
| 物理一致性 | 两套机制混用 | 纯解析，物理干净 |
| 可逆验证 | `ΔS_univ ≈ 0` 靠巧合 | `ΔS_univ ≡ 0`**严格成立** |
| 代码量 | ~200 行粒子动力学 | ~50 行解析公式 |
| 性能 | 每步 O(N²) 碰撞检测 | O(1) |
| 波动的教学含义 | 模糊（有限粒子涨落 vs 非平衡） | 可逆线天然光滑，对比更清晰 |

#### 若要保留分子可视化（方案 B）

如果仍希望粒子在可逆过程中可见（视觉连续性），可以在 `drawSimulation()` 中复用不可逆模块的粒子数组做**静态渲染**，或仅保留粒子的自由飞行（不做碰撞/不做热修正），而 `P_gas` 和 `w` 仍用解析公式。

---

## 问题 3：等温不可逆 ΔS_sys 直接抄袭可逆值

### 问题本质

`drawComparisonTable()` 中的代码：

```javascript
if (isIso) {
  dSsysIrr = dSsysRev;  // ← 假设终态相同，但不验证
}
```

前提是「不可逆终态体积 = 可逆终态体积」，但用户可能设置了不同的 `P_ext` 导致终态体积不同，也可能在不可逆尚未稳定时提前记录。熵是状态函数可以用解析公式算，但**必须用不可逆路径的实际终态**。

### 修复方案

用不可逆路径录制的**实际数据**独立计算 ΔS_sys：

```javascript
function drawComparisonTable() {
  // ... 前置检查 ...

  const isIso = (heatModeSelect.value === 'isothermal');

  // ===== 不可逆 ΔS_sys：从不可逆路径实际终态独立计算 =====
  const V_irrev_i = irrev_path.vol[0];                        // 初始体积
  const V_irrev_f = irrev_path.vol[irrev_path.vol.length - 1]; // 终态体积
  const dU_irrev_f = irrev_path.dU[irrev_path.dU.length - 1];  // 终态 ΔU

  let dSsysIrr;
  if (isIso) {
    // 等温：ΔS = Nk·ln(V_f/V_i)
    // 注意：即使不可逆路径中间非平衡，只要初末态温度相同，此式严格成立
    dSsysIrr = N * Math.log(Math.max(V_irrev_f, 1e-8) / Math.max(V_irrev_i, 1e-8));
  } else {
    // 绝热：ΔS = N·ln(T_f/T_i) + N·ln(V_f/V_i)（二维理想气体）
    const T_i = initialTemp0;
    const T_f_irrev = Math.max(T_i + dU_irrev_f / N, 1e-8);
    dSsysIrr = N * Math.log(T_f_irrev / T_i)
             + N * Math.log(Math.max(V_irrev_f, 1e-8) / Math.max(V_irrev_i, 1e-8));
  }

  const qIrrFinal = irrev_path.q[irrev_path.q.length - 1] || 0;
  const dSsurrIrr = -qIrrFinal / Math.max(initialTemp0, 1e-8);
  const dSunivIrr = dSsysIrr + dSsurrIrr;

  // ===== 可逆 ΔS_sys：同样用状态函数公式 =====
  const V_rev_f = rev_trace.vol[rev_trace.vol.length - 1];
  let dSsysRev;
  if (isIso) {
    dSsysRev = N * Math.log(Math.max(V_rev_f, 1e-8) / Math.max(rev_initialV0, 1e-8));
  } else {
    dSsysRev = rev_cum_dS_sys;  // 绝热可逆 ΔS_sys = 0
  }

  // ... 后续表格渲染不变 ...
}
```

#### 统一公式速查（二维理想气体，`k_B = 1`）

| 条件 | ΔS_sys 公式 |
|------|------------|
| 等温 | `ΔS = N·ln(V_f / V_i)` |
| 绝热可逆 | `ΔS = 0` |
| 绝热不可逆 | `ΔS = N·ln(T_f / T_i) + N·ln(V_f / V_i)` |
| 一般（两个自由度） | `ΔS = N·ln(T_f / T_i) + N·ln(V_f / V_i)` |

---

## 三个修复的整合验证清单

修复完成后，应验证以下断言：

| # | 验证断言 | 预期结果 |
|:---:|---|:---:|
| 1 | 等温可逆 `ΔS_univ` | **严格 = 0**（零容差） |
| 2 | 绝热可逆 `ΔS_sys` | **严格 = 0** |
| 3 | 等温不可逆 `ΔS_univ` | **> 0**（只要 `P_ext ≠ P_initial`） |
| 4 | 绝热不可逆 `ΔS_sys` | **> 0**（即使 `q = 0`） |
| 5 | 等温可逆/不可逆 `ΔS_sys` 相等 | 仅当**终态体积相同**；不等时各自公式独立成立 |
| 6 | 可逆膨胀 `|w_rev|` | 严格 `= NkT₀·ln(V_f/V_i)`（等温），不与碰撞功耦合 |

---

## 总结

三个问题的根因都是同一个：**试图用有限粒子的分子动力学来模拟理想的准静态可逆过程**，导致熵的计算不得不依赖数值控制器的行为，而非物理定律。

修复策略的核心思路：

> **可逆过程 = 理想极限 → 用解析公式，不用分子动力学。**
>
> **熵 = 状态函数 → 用 (T, V) 终态直接算，不累加 dq/T。**

这样修复后，PV 图上的可逆曲线是完美光滑的等温/绝热线，ΔS_univ 的零/正对比不再依赖数值巧合，教学含义一目了然。
