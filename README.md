# AirSim×UE 多智能体强化学习后端（并行 PettingZoo 环境）

本项目提供在 **UE Blocks 场景 + AirSim** 中的 **多架无人机（Drone1/Drone2/Drone3）** 对抗 **Jammer 干扰** 的并行环境实现，遵循 `PROJECT_RULES.md` 的架构与约束：

- 目录结构：核心代码位于 `src/airsim_multi_rl/`（配置/适配层/观测/奖励/终止/动作/并行环境）。
- 运行时契约：观测 17 维、动作连续 4 维、奖励可插拔、终止与截断分离。
- 适配层：所有 AirSim I/O 仅在 `envs/airsim_client.py`，便于 mock 与替换。

## 安装依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 运行测试所需
pip install pytest pyyaml
```

## 快速自检（Smoke Test）

支持两种模式：

- 在线模式（需要运行中的 AirSim/UE Blocks）：
  ```bash
  PYTHONPATH=src python -m airsim_multi_rl.scripts.smoke_test
  ```
- 离线模式（无 AirSim，仅验证环境逻辑与输出）：
  ```bash
  SMOKE_OFFLINE=1 PYTHONPATH=src python -m airsim_multi_rl.scripts.smoke_test
  ```

输出中将显示 `agents` 名称与每步奖励和，满足基本连通与形状自检。

### UE HTTP 拉取式自检（WSL → Windows）

当 UE 在 Windows 上运行并监听 `127.0.0.1:18080` 时，WSL 侧需使用 Windows 主机的可达 IP 访问该服务。可以使用以下脚本进行端到端拉取式验证：

```bash
# 安装依赖
pip install -r requirements.txt

# 自动探测 Windows 主机 IP 并自检（默认端口 18080）
PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check --name BP_JammerActor

# 或显式指定 UE HTTP 基地址（端口统一为 18080）
PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check \
  --base http://<WIN_HOST_IP>:18080 --name BP_JammerActor --x 10 --y 0 --z 0

# 多 Jammer 名称一次性验证（建议与你的 UE 名称一致）
PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check \
  --base http://<WIN_HOST_IP>:18080 --names BP_JammerActor,BP_JammerActor2,BP_JammerActor3 --x 10 --y 0 --z 0
```

成功判定：
- `/ping` 返回 200 与 JSON（如 `{"status":"ok"}`）
- `/jammers` 返回非空列表（字段包含 `name`、`location`、`isJamming` 等）
- `/jammer_power` 至少一种调用方式（传米或传厘米）返回有效 `power` 浮点数，且时延在 10–50ms（本机）

注意：
- UE 端位置单位为 **cm**；脚本同时尝试传米与传厘米两种方式，以适配不同实现
- 若 UE 仅绑定 `127.0.0.1`，从 WSL 访问需要使用 Windows 主机的可达 IP（如 `172.x.x.1`）；必要时在 Windows 开放 18080 端口或配置端口代理到 127.0.0.1

## 单元测试

```bash
PYTHONPATH=. python -m pytest -q tests/test_env_shapes.py
```

该测试通过注入 DummyClient 验证 `reset` 与空间形状，不依赖 AirSim。

## 训练日志（结构化 JSON）

为满足强化学习训练过程的日志需求，新增 `utils/logging.py` 与 `runners/rollout.py`：

- 日志内容：
  - episode 开始/结束（含累计奖励）
  - step 前后（观测、动作、奖励、环境 info）
  - 策略更新（学习率、loss 等指标）
  - 干扰强度（每步，含标准化单位与类型）
- 输出格式：
  - JSON（包含 `ts`、`level`、`name`、`msg`，以及结构化字段如 `episode`、`step`、`metrics`）
  - 控制台实时输出 + 文件轮转（默认 5MB，保留 3 个备份）
- 性能：
  - 使用 `QueueHandler/QueueListener` 异步写入，降低对训练速度的影响

启用与配置（`config/default.yaml`）：

```yaml
logging:
  enabled: true
  level: "INFO"           # DEBUG/INFO/WARNING/ERROR
  console: true
  file: true
  file_path: "logs/train.log"
  max_bytes: 5242880
  backup_count: 3
  queue: true
  include_metrics_highlight: true
```

使用示例：

```python
from airsim_multi_rl.config import load_env_config
from airsim_multi_rl.runners.rollout import run_rollout

cfg = load_env_config()
run_rollout(cfg, episodes=5, steps_per_ep=100)
```

远程日志：可在 `RLLogger.create` 外部包装自定义 Handler（如 HTTP/Fluentd），或通过队列监听器附加处理器实现。

### 干扰强度日志（Interference Logging）

为满足“每步干扰强度记录”的分析与溯源需求，日志系统新增结构化干扰日志接口：

- 接口：`RLLogger.interference(episode, step, strength, kind, unit, **kwargs)`
  - `episode`：回合编号（可选）
  - `step`：步编号
  - `strength`：干扰强度（标准化单位）
  - `kind`：干扰类型（`power` 或 `distance`）
  - `unit`：度量单位（如 `dB` 或 `meter`）
  - `kwargs`：额外结构化字段，如 `agent`、`raw_strength`、`raw_unit`

- 消息前缀：`msg` 字段固定为 `"[INTERFERENCE]"`，便于筛选与下游处理。

- 记录位置：
  - 步前（`step_before` 之后）：记录占位强度（power 记录 `0 dB`；distance 记录 `0 meter`），用于统一对齐时间轴。
  - 步后（`step_after` 之后）：记录真实干扰强度：
    - `power` 模式：从 `infos[agent]['jammer_power']` 读取功率并转换为 dB（`_to_db`）。
    - `distance` 模式：从 `infos[agent]['nearest_jammer_dist']` 读取最近距离（米）。

- 性能与异步：沿用结构化日志的异步队列写入，不改变训练主循环的同步逻辑。

示例（来自 `runners/rollout.py`）：

```python
from airsim_multi_rl.utils.logging import RLLogger, _to_db

logger = RLLogger.create(cfg.logging)
kind = "power" if env.cfg.jammer_penalty_mode == "power" else "distance"
# 步前占位
for a in env.agents:
    logger.interference(episode=ep, step=step, strength=_to_db(0.0) if kind=="power" else 0.0,
                        kind=kind, unit="dB" if kind=="power" else "meter",
                        agent=a, raw_strength=0.0, raw_unit="power" if kind=="power" else "meter")
# 环境一步
obs, rews, terms, truncs, infos = env.step(actions)
# 步后真实值
for a in env.agents:
    if kind == "power":
        raw_p = float(infos[a].get("jammer_power", 0.0))
        logger.interference(episode=ep, step=step, strength=_to_db(raw_p), kind="power", unit="dB",
                            agent=a, raw_strength=raw_p, raw_unit="power")
    else:
        d = float(infos[a].get("nearest_jammer_dist", 0.0))
        logger.interference(episode=ep, step=step, strength=d, kind="distance", unit="meter",
                            agent=a, raw_strength=d, raw_unit="meter")
```

日志样例（JSON 行）：

```json
{"ts":"2025-01-01T12:00:00","level":"INFO","name":"rl.train","msg":"[INTERFERENCE]","episode":1,"step":7,"strength":-0.0,"kind":"power","unit":"dB","agent":"Drone1","raw_strength":0.5,"raw_unit":"power"}
```

筛选命令：

```bash
grep "\[INTERFERENCE\]" logs/train.log | head -n 5
```

注意：如启用 `jammer_penalty_mode: power` 且开启 UE RPC，功率来自 `/jammer_power` 查询，并按 `cm_per_m` 做单位换算；距离模式则基于最近 Jammer 的向量范数。

## 目录结构（关键）

```
src/airsim_multi_rl/
  ├─ config/
  │   ├─ __init__.py         # EnvConfig/RewardWeights + YAML 合并加载
  │   └─ default.yaml        # 默认运行参数
  ├─ envs/
  │   ├─ __init__.py
  │   ├─ airsim_client.py    # AirSim 适配层（连接/控制/状态）
  │   ├─ dummy_client.py     # 离线模拟客户端（测试用）
  │   ├─ jammer.py           # Jammer 发现与位置缓存
  │   ├─ observation.py      # 17维观测构建
  │   ├─ reward.py           # 奖励组合器
  │   ├─ termination.py      # 终止/截断判定
  │   └─ multi_drone_parallel.py  # PettingZoo 并行环境粘合层
  ├─ scripts/
  │   └─ smoke_test.py       # 自检脚本，支持离线/在线模式
  └─ utils/
      └─ __init__.py
```

## 运行时契约摘要

- 观测：`pos(3), vel(3), yaw(1), goal_delta(3), nearest_jammer_delta(3), last_action(4)` → 17维。
- 动作：`[vx, vy, vz, yaw_rate_deg]`，在 `actions.py` 中裁剪范围。
- 奖励：进步奖励、干扰惩罚、成功/碰撞/越界/步惩罚（权重可配）。
- 终止/截断：到达目标/碰撞/越界为终止；步数达上限为截断。

### 干扰层（Interference Layer）

为支持“状态干扰”实验，环境新增 `envs/interference.py` 干扰层：
- 仅对观测中的位置分量 `obs[0:3]` 施加偏移，不改变环境真实状态。
- 支持两种模式：
  - `gaussian`：按 `gaussian_sigma` 生成高斯噪声；可用干扰强度作为尺度。
  - `bias`：固定偏置向量，可按强度比例缩放。
- 精度与鲁棒：偏移结果保留 `precision` 位小数；异常输入降级为原值。
- 集成位置：在 `multi_drone_parallel.py` 的 `reset/step` 返回观测前应用。奖励与终止均使用未扰动的原始观测计算。

启用示例（`config/default.yaml`）：

```yaml
interference:
  enabled: true
  mode: "gaussian"      # 或 "bias"
  gaussian_sigma: 0.02   # 米
  bias_vector: [0.0, 0.0, 0.0]
  precision: 4
  seed: null
```

或在代码中：

```python
from airsim_multi_rl.config import EnvConfig
cfg = EnvConfig()
cfg.interference.enabled = True
cfg.interference.mode = "gaussian"
```

强度来源：
- 当 `jammer_penalty_mode=power` 时，使用最近 Jammer 的 `nearest_power(pos)`。
- 否则使用最近 Jammer 的距离 `||nearest_jammer_delta||`。

观测与信息：
- 返回观测仅位置分量被扰动；其他维度不变。
- `infos[agent]` 增加 `pos_raw`（原始位置备份）与 `timestamp`（秒），便于对比实验。

### 干扰惩罚模式

- `distance`：进入 `jammer_radius` 内线性扣分（默认）
- `power`：使用 UE 端返回的功率值（HTTP RPC），按线性比例扣分。支持 `/jammers` 发现与基准功率缓存、`/jammer_power` 位置相关查询（单位转换 cm↔m 与步频控制）。

启用功率模式（示例）：

```yaml
jammer_penalty_mode: "power"
ue_rpc:
  enabled: true
  http_base: "http://<WIN_HOST_IP>:18080"
  jammers_endpoint: "/jammers"
  power_endpoint: "/jammer_power"
  timeout: 0.5
  cm_per_m: 100.0
  query_every_n_steps: 3
```

建议将 `<WIN_HOST_IP>` 设置为 WSL 内可达的 Windows 主机 IP（可通过 `ip route | awk '/default/ {print $3}'` 获取）。

## 与旧脚本兼容

保留 `airsim/scripts/run_smoke_test.py` 并添加路径回退逻辑，优先使用新包 `airsim_multi_rl`；如导入失败则回退到旧包结构。

## 注意事项

- 请在 `config/default.yaml` 或自定义 YAML 中设置 IP/Port/Bounds/半径等参数，不要硬编码。
- 在 UE 中确保 3 架无人机命名为 `Drone1/Drone2/Drone3`，且 `SimMode` 为 Multirotor。
- 如需接入真实干扰模型，可在 `envs/jammer.py` 接入 UE 蓝图 RPC，并在 `reward.py`/`observation.py` 使用新量。

## UE 端实现指南（Jammer 功率 RPC）

- 蓝图或 C++ 提供查询接口：`GetJammerPower(name) -> float` 与 `GetJammerPowerAtLocation(FVector)`（位置相关功率）。
- 暴露 REST 服务（示例 `http://127.0.0.1:18080`）：
  - `GET /ping`：健康检查
  - `GET /jammers`：列出 Jammer 概览（名称、位置cm、半径、是否开启、基准功率）
  - `GET|POST /jammer_power`：查询指定 Jammer 的功率（支持传入 `x/y/z` 为 cm 的世界坐标）
- 配置：在 `src/airsim_multi_rl/config/default.yaml` 中设置：
  ```yaml
  jammer_penalty_mode: "power"
  ue_rpc:
    enabled: true
    http_base: "http://127.0.0.1:18080"
    jammers_endpoint: "/jammers"
    power_endpoint: "/jammer_power"
    timeout: 0.5
    cm_per_m: 100.0
    query_every_n_steps: 1
  ```
- 环境行为：
  - `jammer.py`：reset 阶段通过 `/jammers` 缓存 Jammer 名称与位置（cm→m），并缓存基准功率；step 阶段按照 `query_every_n_steps` 频率对最近 Jammer 调用 `/jammer_power`（位置参数以 cm 传入），并回填缓存。
  - `multi_drone_parallel.py`：奖励计算时按模式选择距离或功率（传入当前步数以控制查询频率），并在 `info` 填充 `nearest_jammer_dist` 与 `jammer_power`（power 模式）。

实现细节建议（UE 端）：
- 蓝图：为每个 Jammer Actor 维护当前输出功率（随距离/遮挡/噪声更新），在 HTTP Handler 中查询并返回。
- 性能：避免每步枚举；仅在 reset 阶段刷新列表；复杂模型可在 Tick 缓存，再供查询。
- 稳定性：HTTP 端点尽量快速，后端设置短超时；必要时做简单重试。

## 渲染管线对齐
- `env.render()` 现返回 `{agent: {"obs": ..., "rgb": ...}}`，其中 `rgb` 来自 AirSim 摄像头（不可用时为 None）。
- 可按需扩展摄像头名称与返回格式（例如 dict 包含宽高、时间戳）。

已知限制：离线 DummyClient 不进行真实物理与姿态仿真，仅用于形状与基本逻辑验证。
