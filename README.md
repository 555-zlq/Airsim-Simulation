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
- `power`：使用 UE 端返回的功率值（HTTP RPC），按线性比例扣分

## 与旧脚本兼容

保留 `airsim/scripts/run_smoke_test.py` 并添加路径回退逻辑，优先使用新包 `airsim_multi_rl`；如导入失败则回退到旧包结构。

## 注意事项

- 请在 `config/default.yaml` 或自定义 YAML 中设置 IP/Port/Bounds/半径等参数，不要硬编码。
- 在 UE 中确保 3 架无人机命名为 `Drone1/Drone2/Drone3`，且 `SimMode` 为 Multirotor。
- 如需接入真实干扰模型，可在 `envs/jammer.py` 接入 UE 蓝图 RPC，并在 `reward.py`/`observation.py` 使用新量。

## UE 端实现指南（Jammer 功率 RPC）

- 蓝图或 C++ 提供一个可查询指定 Jammer 名称功率的接口 `GetJammerPower(name) -> float`
- 通过 HTTP 暴露一个端点（示例 `http://127.0.0.1:8080/jammer_power`）：
  - 请求：POST JSON `{ "name": "BP_Jammer_1" }` 或 GET `?name=BP_Jammer_1`
  - 返回：JSON `{ "name": "BP_Jammer_1", "power": 12.34 }`
  - 可使用 UE 的 HTTP 模块或嵌入式 Web 服务（插件）实现简易 Handler
- 配置：在 `src/airsim_multi_rl/config/default.yaml` 中设置：
  ```yaml
  jammer_penalty_mode: "power"
  ue_rpc:
    enabled: true
    url: "http://127.0.0.1:8080/jammer_power"
    timeout: 0.5
  ```
- 环境行为：
  - `jammer.py` 在 reset 阶段发现 Jammer 并刷新其位置；若启用 RPC，会为每个 Jammer 调用一次功率查询并缓存。
  - `multi_drone_parallel.py` 在计算奖励时，按模式选择距离或功率作为惩罚输入，并在 `info` 中同时填充 `nearest_jammer_dist` 以便分析。

实现细节建议（UE 端）：
- 蓝图：为每个 Jammer Actor 维护当前输出功率（可根据距离、遮挡、随机变化、电子战模型等更新），在 HTTP Handler 中查询并返回。
- 性能：避免每步调用场景枚举；仅在重置时刷新 Jammer 列表与位置（本项目已遵循）。
- 稳定性：确保 HTTP 端点返回快速且有超时；在 Python 端已设置 `timeout` 防止阻塞。

已知限制：离线 DummyClient 不进行真实物理与姿态仿真，仅用于形状与基本逻辑验证。
