# Jammer HTTP Service 使用指南（UE 4.27.2 × Trae 后端）

> 本指南面向 **Trae** 上的后端开发者与训练脚本，说明如何通过我们实现的 **内置 HttpServer 轻量 REST 服务** 与 **JammerActor** 交互，获取干扰功率等数据以驱动多智能体强化学习（AirSim×UE Blocks 场景）。

------

## 目录

- [整体架构](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#整体架构)
- [UE 端组件](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#ue-端组件)
  - [JammerActor](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#jammeractor)
  - [JammerHttpService](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#jammerhttpservice)
- [构建与运行](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#构建与运行)
- [API 参考](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#api-参考)
  - [`GET /ping`](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#get-ping)
  - [`GET /jammers`](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#get-jammers)
  - [`GET|POST /jammer_power`](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#getpost-jammer_power)
- [数据契约（JSON）](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#数据契约json)
- [单位与坐标](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#单位与坐标)
- [Trae 后端对接建议](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#trae-后端对接建议)
  - [Python 最小客户端](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#python-最小客户端)
  - [采样策略与缓存](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#采样策略与缓存)
  - [在强化学习环境中的接入示例](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#在强化学习环境中的接入示例)
- [错误处理与重试](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#错误处理与重试)
- [安全与部署注意事项](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#安全与部署注意事项)
- [常见问题排查](https://leopard-x.memofun.net/c/690aba15-900c-832d-8d46-dd8d17cb72de#常见问题排查)

------

## 整体架构

- **JammerActor（C++）**：在关卡中代表干扰源，提供 `GetJammerPower()` 与 `GetJammerPowerAtLocation(FVector)` 这类查询函数（你可替换成更符合电磁模型的实现）。
- **JammerHttpService（C++ Actor）**：使用 UE **HttpServer** 模块在本机开启 REST 服务，暴露 `/ping`、`/jammers`、`/jammer_power` 三类接口。
- **Trae 后端**：通过 HTTP 请求上述接口，按需拉取 Jammer 状态/功率；在训练循环中将功率用于观测或奖励。

------

## UE 端组件

### JammerActor

提供以下蓝图可调用函数（已实现）：

- `float GetJammerPower() const`
   返回当前 Jammer 的**基准功率**（若未开启干扰则返回 0）。
- `float GetJammerPowerAtLocation(const FVector& WorldLocation) const`
   基于**世界坐标点**计算的**位置相关功率**（示例为 `1/r²` 衰减），可替换为你的物理/遮挡/噪声模型。
- 其他辅助：
  - `bool IsJamming() const`：是否开启干扰。
  - `float GetRadiusCm() const`：干扰半径（以 `USphereComponent` 的半径为准）。

### JammerHttpService

- 作为 UE Actor 拖入关卡即可**启动 REST 服务**。
- 配置项：
  - `Port`（默认 `18080`）：HTTP 监听端口。
- 返回均为 **JSON**，并设置 CORS 响应头以便浏览器/本机调试。

------

## 构建与运行

1. **模块依赖**（`*.Build.cs`）已配置：

```
HTTP, HttpServer, Json, JsonUtilities
```

1. **编译**
    删除 `Binaries/` 与 `Intermediate/`，重新生成 VS 工程，从 UE 编辑器编译。
2. **关卡布置**
    把一个或多个 `BP_Jammer_*`（或 C++ JammerActor）放入关卡；再把 `JammerHttpService` 拖入关卡（如需改端口，在细节面板设置）。
3. **运行/自测**

```bash
curl "http://127.0.0.1:18080/ping"
curl "http://127.0.0.1:18080/jammers"
curl "http://127.0.0.1:18080/jammer_power?name=BP_Jammer_1&x=1000&y=0&z=0"
```

------

## API 参考

### `GET /ping`

**用途**：健康检查。
 **响应示例**

```json
{ "status": "ok" }
```

------

### `GET /jammers`

**用途**：列出场景中的 Jammer 概览（名称、路径、位置、半径、是否开启、基准功率）。
 **响应示例**

```json
{
  "jammers": [
    {
      "name": "BP_Jammer_1",
      "path": "/Game/Maps/YourMap.YourMap:PersistentLevel.BP_Jammer_1",
      "isJamming": true,
      "basePower": 1.0,
      "radiusCm": 5000.0,
      "location": { "X": 100.0, "Y": 0.0, "Z": 0.0 }
    }
  ]
}
```

------

### `GET|POST /jammer_power`

**用途**：查询指定 Jammer 的功率。
 **两种调用方式**：

- **GET**：`/jammer_power?name=BP_Jammer_1&x=1000&y=0&z=0`
   `name` 必填；`x/y/z` 可选，不传则返回**基准功率**（不考虑距离）。
- **POST JSON**：

```json
{ "name": "BP_Jammer_1", "x": 1000.0, "y": 0.0, "z": 0.0 }
```

**响应示例**

```json
{
  "name": "BP_Jammer_1",
  "power": 0.0004,
  "queryLocation": { "X": 1000.0, "Y": 0.0, "Z": 0.0 }
}
```

> 说明：当前实现统一返回 HTTP 200 + JSON；如找不到 Jammer 返回：

```json
{ "error": "jammer not found", "name": "<你传入的 name>" }
```

------

## 数据契约（JSON）

| 字段            | 类型          | 说明                                        |
| --------------- | ------------- | ------------------------------------------- |
| `name`          | string        | Jammer 名称（关卡唯一名，如 `BP_Jammer_1`） |
| `path`          | string        | UE 对象路径（可用于诊断）                   |
| `isJamming`     | bool          | 是否开启干扰                                |
| `basePower`     | number        | 基准功率（未考虑距离；单位由你的模型决定）  |
| `radiusCm`      | number        | 干扰半径（**厘米**）                        |
| `location`      | object{X,Y,Z} | Jammer 世界坐标（**厘米**）                 |
| `power`         | number        | 查询得到的功率（可能考虑距离）              |
| `queryLocation` | object{X,Y,Z} | 查询位置（可选，传入时回显）                |
| `error`         | string        | 错误信息（仅错误时存在）                    |

------

## 单位与坐标

- **UE 单位**：`cm`。接口中 `location`、`queryLocation` 的 `X/Y/Z` 为**厘米**。
- **AirSim/NED**：你的训练环境通常使用米（m），请在后端进行单位转换。
- **示例模型**：`GetJammerPowerAtLocation` 使用 `1/r²` 衰减（r 为米）。可在 C++ 替换为更真实的传播/遮挡模型，也可在后端做二次处理。

------

## Trae 后端对接建议

### Python 最小客户端

```python
import os, requests

JAMMER_BASE = os.environ.get("JAMMER_BASE", "http://127.0.0.1:8080")
TIMEOUT = float(os.environ.get("JAMMER_TIMEOUT", "0.3"))

def jammer_ping():
    r = requests.get(f"{JAMMER_BASE}/ping", timeout=TIMEOUT); r.raise_for_status()
    return r.json()

def list_jammers():
    r = requests.get(f"{JAMMER_BASE}/jammers", timeout=TIMEOUT); r.raise_for_status()
    return r.json().get("jammers", [])

def get_power(name: str, xyz=None):
    if xyz is None:
        r = requests.get(f"{JAMMER_BASE}/jammer_power", params={"name": name}, timeout=TIMEOUT)
    else:
        x, y, z = xyz
        r = requests.get(f"{JAMMER_BASE}/jammer_power", params={"name": name, "x": x, "y": y, "z": z}, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return float(data["power"])
```

> **建议**：为所有请求添加**短超时**（0.3–0.5s）与**最多 1 次重试**，避免后端阻塞训练循环。

### 采样策略与缓存

- **发现阶段**：在每次 `env.reset()` 时调用 `/jammers`，缓存 Jammer 名单与静态信息（路径、半径）。
- **循环阶段**：
  - 若功率仅与距离相关：可以只在**观测构建**时用位置直接计算（在 UE 或后端），**减少 HTTP 请求**。
  - 若功率有随时间变化/遮挡：每步（或每 N 步）对**最近 Jammer**调用 `/jammer_power`。
- **并发**：多无人机时，一次 step **合并调用**（线程池或异步）可显著降低总耗时。

### 在强化学习环境中的接入示例

以你现有的 17 维观测为例，可以把 `nearest_jammer_power` 加入观测或奖励：

- **观测**：在构建 `obs` 时附加 `power`（形成 18 维，或单独开 dict obs）。

- **奖励**：替换“进入半径内线性扣分”为基于功率的惩罚，例如：

  ```
  r -= alpha * clamp(power, 0, P_max)
  ```

- **伪码**：

```python
# 在 step 里，已知 drone_pos_world_cm
power = get_power("BP_Jammer_1", xyz=(drone_pos_world_cm[0], drone_pos_world_cm[1], drone_pos_world_cm[2]))
# 观测扩展
obs = np.concatenate([obs17, [power]], axis=0)
# 奖励（示例）
reward -= 0.1 * min(power, 10.0)
```

------

## 错误处理与重试

- **网络/超时**：捕获 `requests.Timeout/ConnectionError`，做 1 次快速重试；若仍失败，使用**无功率惩罚**或使用**上一次值**以保持训练连续性。
- **Jammer 不存在**：接口会返回 `{"error":"jammer not found"}`；后端应 fallback 到 0 功率或忽略该 Jammer。
- **端口占用**：切换 `JammerHttpService.Port`，或确认上次 PIE 已停止。

------

## 安全与部署注意事项

- **默认仅本机使用**（`127.0.0.1:18080`）；如需跨机访问，请在系统防火墙放行端口，并考虑加入简单鉴权（令牌）或限制来源 IP。

- **CORS**：已添加 `Access-Control-Allow-Origin: *` 便于调试；生产环境可限定域名或移除。

- **写操作**：当前路由均为只读。如需从后端**切换干扰开关/功率**，请新增 `POST /jammer_set` 路由，并在 handler 中用

  ```cpp
  AsyncTask(ENamedThreads::GameThread, [](){ /* 修改 Actor 属性 */ });
  ```

  保证在游戏线程内写入。

------

## 常见问题排查

- **`/ping` 失败**：确认关卡中已放置 `JammerHttpService` 且端口未被占用；查看 Output Log 是否打印 `Listening on port ...`。
- **`/jammers` 为空**：确认关卡里存在 `JammerActor` 实例（名称如 `BP_Jammer_1`），且 BeginPlay 已执行。
- **功率总为 0**：检查 `bIsJamming` 是否为 `true`；或你传入的 `x/y/z` 是否与场景尺度一致（UE 使用 **cm**）。
- **请求卡住**：后端务必设置短超时；UE 端 handler 不要做重计算，如需复杂模型请考虑缓存或在 Tick 中更新状态后供查询。

