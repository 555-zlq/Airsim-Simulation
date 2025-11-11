"""
airsim_multi_rl 包入口。

该包遵循项目规则的模块化结构：
- config: 配置（dataclass + YAML）
- envs: 环境相关模块（适配层、观测、奖励、终止、动作、并行环境）
- sim: 模拟层封装（DroneAgent 等只依赖适配层，不直接调用 AirSim 原生 client）
- utils: 通用工具（日志、几何、随机种子）
"""

__all__ = [
    "config",
    "envs",
    "policies",
    "runners",
    "scripts",
    "utils",
]