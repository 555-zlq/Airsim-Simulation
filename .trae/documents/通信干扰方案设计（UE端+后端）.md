# 方案总览

* 目标：在 UE Blocks + AirSim 中模拟“伺服天线 + 窄带放大器”对多机通信的实时干扰，覆盖信标/DMRS/跳频侦测、精准指向与干扰注入，并与现有 MARL 环境无缝集成。

* 思路：UE 负责可视化与少量姿态/动画；干扰的物理计算、网络仿真与对环境的影响由 Python 后端完成；双方通过现有 AirSim RPC/Blueprint 暴露的最小接口交互，避免深度改 AirSim 插件。

## UE 端设计

* Jammer 蓝图：`BP_Jammer`（命名遵循项目规则），包含

  * 组件：`SceneRoot`、`StaticMesh_Antenna`、`Arrow_MainLobe`、`TextRender`（显示功率/SINR/锁定状态）

  * 变量：`eirp_dbm`、`main_lobe_width_deg`、`servo_slew_deg_per_s`、`narrow_bw_hz`、`active_freq_hz`、`is_locked`

  * 事件：`Tick` 内更新伺服指向（Yaw/Pitch），将当前指向与活动频点通过 RPC/蓝图可读接口暴露

* 伺服控制

  * 指向目标：后端每步提供目标无人机的世界坐标与频点；蓝图按 `servo_slew_deg_per_s` 限制转速，显示指向动画

  * 丢锁与重捕：当频点突变或角度变化超出阈值时，进入 `reacquire` 状态，显示扫描动画

* 交互接口（最小集）

  * 从后端→UE：`SetJammerAim(name, yaw_deg, pitch_deg)`、`SetJammerActiveFreq(name, freq_hz)`（可用 AirSim `simSetObjectPose` + 自定义 BP 变量映射；或蓝图读 RPC 变量）

  * 从 UE→后端：可选 `GetJammerPose(name)`（后端也可仅在 reset 缓存 UE 位置，按项目规则避免每步枚举）

## 后端设计

* 位置/频点获取

  * 无人机频点：在环境中引入“信标”模拟（每机周期性广播 `beacon{freq}`），或直接由策略/配置层定义每机当前通信频点

  * 侦测模型：Jammer 对扫描带宽 `scan_bw_hz` 扫描，按 `detection_snr_db` 门限检测频点，存在 `detection_latency_ms` 和估计误差

* 伺服与指向

  * 后端计算期望指向角（世界系），施加 `servo_slew_deg_per_s` 限制与指向误差；将角度回传 UE 以驱动蓝图动画

* 干扰计算

  * 路径损耗：简化 Friis/对数距离损耗 `L(d) = L0 + 10*n*log10(d/d0)`

  * 天线增益：主瓣余弦模型 `G(θ) = Gmax * cos^p(θ)`，副瓣常量 `G_side`

  * 频域选择性：窄带宽 `narrow_bw_hz` 下，仅影响 `|f - active_freq| ≤ BW/2` 的链路

  * 干扰功率：`Pj_rx_dbm = EIRP_dbm + G(θ) - L(d)`

  * 信号功率：`Ps_rx_dbm = Tx_dbm + G_rx - L(d_sig)`（可简化为常值 + 距离项）

  * SINR：`SINR = Ps / (N0*B + ΣPj)`；映射到 PER `per = 1 - exp(-k * SINR)` 或逻辑函数

* 通信仿真

  * 为多机间的协调/信息共享引入消息层（不影响 AirSim 控制 RPC）：消息包含时间戳、发送机、频点、载荷

  * 依据 SINR/频域命中决定：丢包（drop）、延迟（随机排队/重传）与比特错误（可选）

* 跳频支持

  * 每机定义跳频序列（PRBS/列表），`Δt_hop` 周期切换；Jammer 根据侦测与追踪策略产生 `is_locked`/`lost_lock`，并有 `reacquisition_delay_ms`

## 数据流与接口

* 环境 step 流程

  * 读取无人机状态（`getMultirotorState`）与当前频点

  * 更新 Jammer 指向与锁定状态

  * 计算对每机的 `Pj_rx`、`SINR` 与消息层的 PER/延迟

  * 生成观测：为各机附加 `nearest_jammer_delta`、`SINR`、`is_jammed`（项目规则 2.1 扩展）

  * 执行动作下发与 `join`（遵循项目规则 12）

* 与 UE 的交互频率

  * 在 `reset` 时枚举 Jammer/Drone 对象并缓存；每步仅下发 Jammer 指向与活动频点以可视化，避免频繁查询

## 配置项（新增到 YAML + EnvConfig）

* `comm.tx_dbm_per_drone`、`comm.rx_gain_db`、`comm.noise_floor_dbm`

* `comm.freq_min_hz`、`comm.freq_max_hz`、`comm.beacon_period_s`

* `hop.enabled`、`hop.sequence`、`hop.period_s`

* `jammer.eirp_dbm`、`jammer.main_lobe_width_deg`、`jammer.gain_max_dbi`、`jammer.gain_side_dbi`

* `jammer.narrow_bw_hz`、`jammer.servo_slew_deg_per_s`、`jammer.detection_snr_db`、`jammer.detection_latency_ms`、`jammer.reacquisition_ms`

* `jammer.name_patterns: ["Jammer*", "JammerActor*", "BP_Jammer*"]`（沿用项目规则 11）

## 环境集成

* `envs/jammer.py`：实现上述物理/侦测/指向/功率计算，提供 `get_power(vehicle_name, freq)` 与状态查询

* `envs/observation.py`：在默认 17 维观测中新增 `SINR` 与 `is_jammed` 占位（默认 0/False），同步更新 `space`

* `reward.py`：干扰惩罚从“距离”切换为“功率/信道质量”，例如 `penalty = w_jam * f(SINR)`（保留距离模式作为备选）

* `multi_drone_parallel.py`：粘合消息层（发送/接收）与 Jammer 影响，确保不直接使用 AirSim 原生 client

## 可视化与调试

* UE 端显示：Jammer 上方 `TextRender` 显示 `freq(MHz) / lock / Pj(dBm)`

* Python 端：在 `utils/logging.py` 中记录每步 `SINR/丢包率/重捕耗时`；提供 `scripts/smoke_test.py` 的连通性与数值边界自检

## 验证方案

* 单机静止场景：固定频点与 Jammer 指向，验证 `SINR` 与 PER 单调关系

* 跳频测试：设定两档频点交替，检查 `reacquisition_ms` 与锁定状态的转换

* 多机协同：验证在 Jammer 作用下，跨机消息成功率符合预期并影响策略行为

* 性能：确认 50Hz RPC 限制不被阻塞（参考 AirSim 文档），每步计算在 `dt=0.2s` 内完成

## 迭代路线

* 迭代 1：实现距离/方向驱动的简化干扰（主瓣 + 路损 + 窄带）与消息层（丢包/延迟）

* 迭代 2：加入跳频与侦测延迟/误差模型，完善锁定/重捕逻辑

* 迭代 3：替换距离惩罚为基于 `SINR` 的奖励/终止项，并扩展观测空间；完善 UE 可视化与调试脚本

