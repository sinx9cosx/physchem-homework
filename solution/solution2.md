# 可逆过程分子模拟改进方案


## 一、模拟算法：准静态活塞控制

### 与不可逆模拟的对比

| | 不可逆（上半部分） | 可逆（下半部分） |
|---|---|---|
| 活塞驱动 | 力平衡：`F = (P_piston - P_ext)×H - damp×v` | 位置控制：`x_p += Δx_step`（预设位移） |
| P_ext | 用户设定恒定值 | 不设 P_ext，活塞由外部机构定位 |
| 每帧操作 | 1 次 MD 步（含碰撞 + 活塞运动） | N_relax 次 MD 步（碰撞 + 恒温），再移动活塞 |
| 功 | `w_ext = -P_ext·ΔV`（宏观公式）+ `w_coll`（碰撞累计） | `w_rev = ΣΔK_collision`（纯碰撞累计，即 w_coll） |
| 热 | 全局速度重标定 | 弛豫期间逐步重标定，累计为 q |

### 伪代码

```javascript
function stepReversibleMD() {
  if (rev_step >= rev_totalSteps) return; // 完成

  // —— 阶段 1：移动活塞一个微小步长 ——
  const dx = (xP_target - xP_initial) / rev_totalSteps;
  xP += dx * rev_direction;           // +1 膨胀, -1 压缩
  rev_currentVolume = xP * H;

  // —— 阶段 2：固定活塞，弛豫 nRelax 步 ——
  // 粒子正常碰撞、与固定活塞碰撞（活塞速度=0）
  // 碰撞功计入 rev_workMicro
  // 若等温模式：每步或每若干步做速度重标定，累计热量
  for (let k = 0; k < nRelaxPerStep; k++) {
    moveParticles(dt);
    resolveParticleCollisions();
    resolveWallCollisions();    // 活塞 vP=0，纯反射
    if (isIso) applyThermostat(); // 逐步恒温
    rev_workMicro += ΣΔK_collision;  // 碰撞动能变化（此时为 0，因为活塞不动）
  }

  // —— 阶段 3：记录状态 ——
  // 用此时的体积和弛豫后的温度计算 P = NkT/V
  rev_currentP = N * temperature() / rev_currentVolume;
  recordRevTrace();

  rev_step++;
}
```


### 更精确的算法

```javascript
function stepReversibleMD() {
  if (rev_step >= rev_totalSteps) return;

  // 微移活塞（这一帧活塞有速度 vP = dx/dt）
  const dx = (xP_target - xP_initial) / rev_totalSteps;
  vP = dx / dt;  // 赋予一个极小的虚拟速度用于碰撞计算
  xP += dx;

  // 一步 MD（含移动活塞的碰撞）
  moveParticlesAndCollide();  // 碰撞功在此累计
  
  vP = 0;  // 立即归零
  
  // 弛豫 nRelax 步（活塞静止）
  for (let k = 0; k < nRelax; k++) {
    moveParticlesAndCollideFixedPiston();
    if (isIso) gentleThermostat();  // 缓慢恒温
  }

  rev_currentP = N * temperature() / rev_currentVolume;
  recordRevTrace();
  rev_step++;
}
```


## 二、关键参数设置

```javascript
// 可逆模拟参数（添加到控制面板）
rev_totalSteps:     800 ~ 3000   // 总步数（滑条）
nRelaxPerStep:      3 ~ 15       // 每步弛豫次数（滑条，默认 5）
// 总 MD 步数 = rev_totalSteps × (1 + nRelaxPerStep)
// 800 步 × 6 = 4800 帧，在 60fps 约 80 秒
```

### 建议的预设按钮

```html
<button id="revNearEqBtn">近可逆（3000步，弛豫10）</button>
<button id="revFastBtn">快速准静态（500步，弛豫2）</button>
<button id="revUltraSlowBtn">极慢（3000步，弛豫20）</button>
```

## 三、需要修改的代码关键点

### 3.1 复用上半部分的碰撞引擎

可逆模拟的画布和数据完全独立，但复用同一套粒子碰撞函数。需要创建一个 `ReversibleSim` 类或对象：

```javascript
const revSim = {
  particles: [],    // 独立的粒子数组
  xP: 0, vP: 0,
  N: 180,           // 可与不可逆不同
  workMicro: 0,
  heatExchange: 0,
  // ...
};
```

### 3.2 可逆模拟的活塞碰撞（关键修改）

```javascript
// 可逆活塞碰撞：活塞在移动瞬间有微小的 vP
// 碰撞公式与不可逆完全相同，但 vP 是预设的而非力驱动的
if (p.x > xP - r) {
  p.x = xP - r;
  const u = p.vx - vP;     // vP 来自预设位移
  if (u > 0) {
    const eBefore = 0.5 * m * (p.vx*p.vx + p.vy*p.vy);
    p.vx = vP - u;
    const eAfter = 0.5 * m * (p.vx*p.vx + p.vy*p.vy);
    revSim.workMicro += (eAfter - eBefore);
  }
}
```

### 3.3 恒温器改进

不可逆部分使用全局速度重标定（一步到位），可逆部分建议使用**更温和的重标定**，在弛豫期间分多次逐步拉回：

```javascript
function gentleThermostat(targetT, rate = 0.3) {
  const T = kineticEnergy() / N;
  const lambda = 1 + rate * (Math.sqrt(targetT / Math.max(T, 1e-8)) - 1);
  for (const p of particles) { p.vx *= lambda; p.vy *= lambda; }
  const dK = kineticEnergy() - K_before;
  heatExchange += dK;
}
```

`rate` 越小越温和，推荐 0.1~0.3。

---

## 四、对比表改进

将当前纯解析对比替换为**两条模拟轨迹的实测值对比**：

```javascript
function buildComparisonTable() {
  // 不可逆终态：从上半部分模拟中直接读取
  const wIrr = workMicro;          // 或 workExternal()
  const qIrr = heatExchange;
  const dUIrr = deltaU();
  
  // 可逆终态：从下半部分模拟中直接读取
  const wRev = revSim.workMicro;
  const qRev = revSim.heatExchange;
  const dURev = revSim.deltaU();
  
  // 熵：从状态函数公式计算（两个过程分别用各自的终态 T, V）
  const dSsysIrr = N*Math.log(Tf_irr/Ti) + N*Math.log(Vf_irr/Vi);
  const dSsysRev = N*Math.log(Tf_rev/Ti) + N*Math.log(Vf_rev/Vi);
  // ...
}
```

对比表新增一行：

| 量 | 不可逆 | 可逆 |
|----|--------|------|
| 模拟帧数 | xxx | xxx |
| 活塞碰撞功 w_coll | xxx | xxx |
| 累计热量 q | xxx | xxx |
| ΔU | xxx | xxx |
| 终态温度 T_f | xxx | xxx |
| 终态体积 V_f | xxx | xxx |
| ΔS_sys（状态函数） | xxx | xxx |
| ΔS_univ | xxx | xxx |

---

## 五、新增教学内容

在可逆理论讲义中增加一节：

```html
<details>
  <summary>5. 弛豫步数与可逆性的关系（新增）</summary>
  <div class="lecture-body">
    <p>在本模拟中，"弛豫步数"控制活塞每移动一步后，粒子有多少时间来重新达到局部平衡。
    弛豫步数越多 → 过程越慢 → 越接近可逆极限。</p>
    <p>学生实验建议：</p>
    <ul>
      <li>保持目标体积和总步数不变，只改变弛豫步数（如 2/5/15）</li>
      <li>观察 w_rev 是否趋近解析值 -NkT₀ln(V_f/V₀)</li>
      <li>观察 ΔS_univ 是否趋近 0</li>
      <li>弛豫步数=0 时，过程趋近不可逆极限</li>
    </ul>
  </div>
</details>
```
