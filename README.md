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

当 UE 在 Windows 上运行并监听 `127.0.0.1:8080` 时，WSL 侧需使用 Windows 主机的可达 IP 访问该服务。可以使用以下脚本进行端到端拉取式验证：

```bash
# 安装依赖
pip install -r requirements.txt

# 自动探测 Windows 主机 IP 并自检（默认端口 8080）
PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check --name BP_Jammer_Actor

# 或显式指定 UE HTTP 基地址
PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check \
  --base http://<WIN_HOST_IP>:8080 --name BP_Jammer_Actor --x 10 --y 0 --z 0
```

成功判定：
- `/ping` 返回 200 与 JSON（如 `{"status":"ok"}`）
- `/jammers` 返回非空列表（字段包含 `name`、`location`、`isJamming` 等）
- `/jammer_power` 至少一种调用方式（传米或传厘米）返回有效 `power` 浮点数，且时延在 10–50ms（本机）

注意：
- UE 端位置单位为 **cm**；脚本同时尝试传米与传厘米两种方式，以适配不同实现
- 若 UE 仅绑定 `127.0.0.1`，从 WSL 访问需要使用 Windows 主机的可达 IP（如 `172.x.x.1`）；必要时在 Windows 开放 8080 端口或配置端口代理到 127.0.0.1

## 单元测试

```bash
PYTHONPATH=. python -m pytest -q tests/test_env_shapes.py
```

该测试通过注入 DummyClient 验证 `reset` 与空间形状，不依赖 AirSim。

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

### 干扰惩罚模式

- `distance`：进入 `jammer_radius` 内线性扣分（默认）
- `power`：使用 UE 端返回的功率值（HTTP RPC），按线性比例扣分。支持 `/jammers` 发现与基准功率缓存、`/jammer_power` 位置相关查询（单位转换 cm↔m 与步频控制）。

启用功率模式（示例）：

```yaml
jammer_penalty_mode: "power"
ue_rpc:
  enabled: true
  http_base: "http://<WIN_HOST_IP>:8080"
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
- 暴露 REST 服务（示例 `http://127.0.0.1:8080`）：
  - `GET /ping`：健康检查
  - `GET /jammers`：列出 Jammer 概览（名称、位置cm、半径、是否开启、基准功率）
  - `GET|POST /jammer_power`：查询指定 Jammer 的功率（支持传入 `x/y/z` 为 cm 的世界坐标）
- 配置：在 `src/airsim_multi_rl/config/default.yaml` 中设置：
  ```yaml
  jammer_penalty_mode: "power"
  ue_rpc:
    enabled: true
    http_base: "http://127.0.0.1:8080"
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
