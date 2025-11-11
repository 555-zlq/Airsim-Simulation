from __future__ import annotations
import dataclasses
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import os
import yaml

Vec3 = Tuple[float, float, float]
Bounds = Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]


@dataclass
class RewardWeights:
    """奖励权重配置。

    说明：可插拔的奖励组合，便于在 YAML 或 CLI 中调整。
    """

    progress: float = 1.0
    jammer_penalty: float = 0.5
    step_penalty: float = 0.01
    success_bonus: float = 100.0
    collision_penalty: float = 50.0
    oob_penalty: float = 20.0


@dataclass
class EnvConfig:
    """环境配置（从 YAML + CLI 合并），遵循项目规则默认值。

    合并顺序：CLI > 用户 YAML > 默认。
    """

    ip: str = "172.17.0.1"
    port: int = 41451
    agent_names: List[str] = field(default_factory=lambda: ["Drone1", "Drone2", "Drone3"])
    dt: float = 0.2
    max_steps: int = 500
    v_max: float = 4.0
    yaw_rate_max_deg: float = 90.0
    goal_radius: float = 1.5
    jammer_radius: float = 6.0
    world_bounds: Bounds = ((-60.0, 60.0), (-60.0, 60.0), (-25.0, -1.0))
    jammer_patterns: List[str] = field(default_factory=lambda: ["Jammer*", "JammerActor*", "BP_Jammer*"])
    # 干扰惩罚模式：distance 或 power（默认 distance）
    jammer_penalty_mode: str = "distance"
    # UE 蓝图 RPC 配置（用于查询干扰功率）
    ue_rpc: "UERPCConfig" = field(default_factory=lambda: UERPCConfig())

    spawn_points: Dict[str, Vec3] = field(
        default_factory=lambda: {
            "Drone1": (-10.0, 0.0, -3.0),
            "Drone2": (0.0, -10.0, -3.0),
            "Drone3": (10.0, 0.0, -3.0),
        }
    )
    goal_points: Dict[str, Vec3] = field(
        default_factory=lambda: {
            "Drone1": (20.0, 20.0, -5.0),
            "Drone2": (-20.0, 20.0, -5.0),
            "Drone3": (0.0, -20.0, -5.0),
        }
    )

    reward: RewardWeights = field(default_factory=RewardWeights)


@dataclass
class UERPCConfig:
    """UE 蓝图 RPC 配置。

    当 enabled=True 时，jammer.py 将通过 HTTP 查询 UE 端暴露的 `GetJammerPower(name)` 功能。
    """

    enabled: bool = False
    url: str = "http://127.0.0.1:8080/jammer_power"
    timeout: float = 0.5


def _deep_update(dst: dict, src: dict) -> dict:
    """递归合并字典：src 覆盖 dst（浅层与嵌套）。"""
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            _deep_update(dst[k], v)
        else:
            dst[k] = v
    return dst


def load_env_config(user_yaml_path: Optional[str] = None, cli_overrides: Optional[dict] = None) -> EnvConfig:
    """加载并合并环境配置。

    Args:
        user_yaml_path: 用户自定义 YAML 路径。
        cli_overrides: 命令行传入的覆盖项（字典）。

    Returns:
        EnvConfig: 合并后的配置对象。
    """

    # 1) 默认 YAML
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, os.pardir))
    default_yaml = os.path.join(repo_root, "src", "airsim_multi_rl", "config", "default.yaml")
    cfg_dict: dict = {}
    if os.path.isfile(default_yaml):
        with open(default_yaml, "r", encoding="utf-8") as f:
            cfg_dict = yaml.safe_load(f) or {}

    # 2) 用户 YAML
    if user_yaml_path and os.path.isfile(user_yaml_path):
        with open(user_yaml_path, "r", encoding="utf-8") as f:
            user_dict = yaml.safe_load(f) or {}
        cfg_dict = _deep_update(cfg_dict, user_dict)

    # 3) CLI 覆盖
    if cli_overrides:
        cfg_dict = _deep_update(cfg_dict, cli_overrides)

    # 将字典映射到 dataclass（支持嵌套 RewardWeights）
    def as_reward(d: dict) -> RewardWeights:
        return RewardWeights(**d) if d else RewardWeights()
    def as_rpc(d: dict) -> UERPCConfig:
        return UERPCConfig(**d) if d else UERPCConfig()

    if "reward" in cfg_dict and isinstance(cfg_dict["reward"], dict):
        cfg_dict["reward"] = as_reward(cfg_dict["reward"])
    if "ue_rpc" in cfg_dict and isinstance(cfg_dict["ue_rpc"], dict):
        cfg_dict["ue_rpc"] = as_rpc(cfg_dict["ue_rpc"])

    # 使用 dataclasses.replace 兼容未知字段
    base = EnvConfig()
    known_fields = {f.name for f in dataclasses.fields(base)}
    filtered = {k: v for k, v in cfg_dict.items() if k in known_fields}
    return dataclasses.replace(base, **filtered)


__all__ = ["EnvConfig", "RewardWeights", "UERPCConfig", "load_env_config"]