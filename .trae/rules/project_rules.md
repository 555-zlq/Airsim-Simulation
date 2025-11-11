# PROJECT_RULES.md — 多智能体 AirSim×UE 强化学习后端（Trae 驱动）

> 目的：约束并**加速**团队在 Trae 中的协作开发，让“多架无人机穿越复杂电磁干扰（Jammer）环境”的 **多智能体强化学习（MARL）后端**具备一致的架构、风格与交付质量。  
> 适用范围：本仓库全部 Python 代码、配置、脚本与文档。Trae 可将本文件视作“项目规则”，在 Builder/Chat 两种模式下遵循。

---

## 0. 一句话需求

- 目标：在 **UE Blocks 场景 + AirSim** 中，提供 **多架无人机**（默认 `Drone1/Drone2/Drone3`）对抗 **复杂电磁干扰** 的 **PettingZoo 并行环境**，并提供训练与评测脚本。  
- UE 侧：已完成 AirSim 配置、干扰源（Jammer）放置与场景搭建。  
- Python 侧：实现**模块化、可测试、可扩展**的 RL 后端，支持**共享策略**与**多智能体训练**。

---

## 1. 目录结构（强约束）

> 若目录未创建，**Trae Builder 必须先生成完整骨架**，再落地功能代码。

```
<repo-root>/
  src/airsim_multi_rl/
    __init__.py
    config/                 # 配置（dataclass + YAML）
      __init__.py
      default.yaml
    envs/
      __init__.py
      airsim_client.py      # AirSim 适配器（连接/控制/状态，便于 mock）
      jammer.py             # Jammer 发现与位置刷新
      observation.py        # 观测拼装（集中式）
      reward.py             # 奖励组合（可插拔权重/项）
      termination.py        # 终止/越界/达成判定
      actions.py            # 动作空间定义与裁剪
      multi_drone_parallel.py  # PettingZoo ParallelEnv 粘合层
    policies/
      __init__.py
      random_policy.py
    runners/
      __init__.py
      rollout.py            # 轻量 roll-out
      train_rllib.py        # RLlib 训练入口（可选）
    scripts/
      __init__.py
      smoke_test.py         # 环境连通自检
    utils/
      __init__.py
      geometry.py
      logging.py
      seeding.py
  tests/
    test_env_shapes.py
  pyproject.toml / requirements.txt / README.md / LICENSE
  PROJECT_RULES.md          # 本规则文件
```

**禁止**在 `envs/multi_drone_parallel.py` 内直接使用 AirSim 原生 client；**必须**通过 `envs/airsim_client.py` 适配层间接调用。

---

## 2. 运行时契约（Observation / Action / Reward / Done）

### 2.1 观测（默认 17 维，统一由 `observation.py` 构建）

```
obs = concat[
  pos_xyz(3), vel_xyz(3), yaw(1),
  goal_delta(3), nearest_jammer_delta(3),
  last_action(4)
]
```

- 坐标系：AirSim NED。`yaw` 单位：**弧度**。  
- `nearest_jammer_delta`：与最近 Jammer 的向量差（无 Jammer 时置 0）。

### 2.2 动作（连续）

```
a = [vx, vy, vz, yaw_rate_deg]  # 单位：m/s, m/s, m/s, deg/s（世界系）
```

- 在 `actions.py` 内做**范围裁剪**（`v_max`、`yaw_rate_max_deg`）。

### 2.3 奖励（可插拔，`reward.py`）

- 进步奖励：`Δdist_to_goal`（靠近目标为正）。  
- 干扰惩罚：进入 `jammer_radius` 内线性扣分（或替换为真实**信道/干扰强度模型**）。  
- 成功 +100、碰撞 −50、越界 −20、步惩罚 −0.01（权重在 `RewardWeights` 中集中配置）。

### 2.4 终止/截断（`termination.py`）

- **终止**：到达目标或**碰撞**或**越界**。  
- **截断**：步数 ≥ `max_steps`。

---

## 3. UE / AirSim 假设与约束

- 已在 UE Blocks 关卡中放置 3 架无人机（名称：`Drone1/Drone2/Drone3`）。
- Jammer 命名模式：`"Jammer*" | "JammerActor*" | "BP_Jammer*"`。  
- AirSim 以 **Multirotor** 模式运行；`ip/port` 由 `config/default.yaml` 提供。  
- 动作下发使用 `moveByVelocityAsync(..., YawMode(is_rate=True))`，并**等待 join** 保证步长一致。

---

## 4. 配置管理（唯一来源）

- `src/airsim_multi_rl/config/default.yaml` 为**默认配置**；Python 端通过 `EnvConfig`（dataclass）读取与合并。  
- **严禁**硬编码 IP/Port/Bounds/半径等运行参数。  
- 允许通过 CLI / 自定义 YAML 重载默认项（合并顺序：**CLI > 用户 YAML > 默认**）。

---

## 5. 代码风格与质量门槛

- 语言：**Python 3.10–3.12**。全部**类型标注**，公共函数含 **docstring（Google 风格）**。  
- 格式化与检查（推荐本地 + CI）：
  - `ruff`（import 顺序/复杂度/常见错误）
  - `black`（代码格式化，行宽 100）
  - `mypy`（可渐进式）
  - `pytest -q`（允许通过 mock AirSim 进行形状/逻辑测试）
- 禁止**在核心循环中**混入 `print` 调试；统一使用 `utils/logging.py`。

---

## 6. 架构原则（单一职责 & 可替换）

- **适配层**：所有 AirSim I/O 只在 `airsim_client.py` 出现，便于 mock 与替换。  
- **观测/奖励/终止/动作**：各自独立模块，互不引用 AirSim 细节。  
- **环境粘合**：`multi_drone_parallel.py` 只做调度与拼装，不写业务常量。  
- **可替换**：
  - 离散动作：新增 `actions_discrete.py`，并在 env 中替换导入。
  - 高维观测：在 `observation.py` 扩展并同步更新 `space`。
  - 真实干扰：在 `jammer.py` 接入 UE 蓝图 RPC（例如 SNR/干扰功率），`reward.py`/`observation.py` 使用新量。

---

## 7. Trae 使用约定（Builder/Chat）

> 将本文件置于仓库根目录，Trae 会在**生成/修改**代码时参考以下规则。

### 7.1 Builder 模式模板（示例）

- **“生成模块骨架”**
  - 指令：`为 airsim_multi_rl 生成完整模块骨架，遵循 PROJECT_RULES.md 第1节目录结构`  
  - 验收：所有空文件与占位 `__init__.py`、默认 YAML、脚本入口齐全。

- **“实现 PettingZoo 并行环境粘合层”**
  - 指令：`实现 envs/multi_drone_parallel.py，遵循第2节契约，第6节架构原则，不直接引用 AirSim 原生 client`  
  - 验收：`reset/step/close/render` 四大接口可用，`action_space/observation_space` 正确。

- **“对接真实干扰模型”**
  - 指令：`在 jammer.py 接入 UE 蓝图 RPC：GetJammerPower(name) -> float，reward.py 以功率替代距离惩罚`  
  - 验收：可切换“距离/功率”两种模式；默认仍保持距离模式。

### 7.2 Chat 模式注意事项

- **先读配置**再写代码：所有常量从 `EnvConfig` 读取。  
- 严禁在 `multi_drone_parallel.py` 内部创建新线程或阻塞式 I/O。  
- 生成代码时**附带必要注释与类型**，优先**小函数、短模块**。

### 7.3 生成变更的通用 Checklist

- [ ] 不破坏第1节目录结构  
- [ ] 新参数写入 YAML + dataclass  
- [ ] `action/observation space` 与实现一致  
- [ ] 通过 `scripts/smoke_test.py` 自检  
- [ ] 为新增模块补充最小单测（可 mock AirSim）

---

## 8. 分支与提交

- 分支：`feature/<topic>`、`fix/<bug>`、`exp/<experiment>`、`docs/<scope>`。  
- 提交信息：`<type>(<scope>): <summary>`，type 取 `feat|fix|refactor|docs|test|chore|perf`。  
- PR 必须通过：lint、单测、自检脚本（本地或 CI）。

---

## 9. 训练与实验（最低要求）

- 统一使用 `runners/train_rllib.py` 或自研 `train/` 下的脚本；**记录**超参与随机种。  
- 建议目录：`experiments/<date>_<tag>/config.yaml`、`metrics.csv`、`notes.md`、`seed.txt`。  
- 禁止将超过 50MB 的日志/权重直接提交到仓库（使用外部存储）。

---

## 10. 性能与安全

- 控制循环中严禁频繁调用场景枚举 API（例如每步 `simListSceneObjects`），只在 reset 时刷新并缓存。  
- 所有 `Async` 控制命令在步间**等待 join**，确保 `dt` 一致。  
- 默认限制动作幅度，防止无人机飞出场景或过度机动导致模拟不稳定。

---

## 11. 常用参数（默认，可在 YAML 中修改）

- `dt=0.2s`、`max_steps=500`、`v_max=4.0m/s`、`yaw_rate_max_deg=90`  
- `goal_radius=1.5m`、`jammer_radius=6.0m`  
- `world_bounds = ((-60,60), (-60,60), (-25,-1))`  
- Jammer 名称模式：`["Jammer*", "JammerActor*", "BP_Jammer*"]`

---

## 12. 故障排查（简版）

- **动作无效**：确认 `enableApiControl/armDisarm/takeoff` 顺序正确，且 `moveByVelocityAsync().join()` 已等待。  
- **观测异常**：核对 NED 坐标系，`yaw` 是否弧度；`goal_delta` 与 `jammer_delta` 是否按 **目标/干扰 - 位置** 计算。  
- **奖励为负**：检查是否长期处于 Jammer 半径内；适当降低惩罚或扩大 `jammer_radius`。

---

## 13. 附：示例任务清单（Trae 可逐条执行）

- [ ] 在 `observation.py` 新增 **SNR** 字段并更新 `space`（占位，默认 0）。  
- [ ] 在 `reward.py` 新增 **编队保持**奖励项：与队形中心的偏差惩罚。  
- [ ] 在 `actions.py` 增加 **离散动作 spec**，导出 `ActionExecutorDiscrete`。  
- [ ] 在 `runners/rollout.py` 增加 CSV 日志导出（每步 reward_sum、dist_to_goal）。

---

**EOF**