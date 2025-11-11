# airsim_marl/config.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

Vec3 = Tuple[float, float, float]
Bounds = Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]

@dataclass
class EnvConfig:
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

    spawn_points: Dict[str, Vec3] = field(default_factory=lambda: {
        "Drone1": (-10.0, 0.0, -3.0),
        "Drone2": (0.0, -10.0, -3.0),
        "Drone3": (10.0, 0.0, -3.0),
    })
    goal_points: Dict[str, Vec3] = field(default_factory=lambda: {
        "Drone1": (20.0, 20.0, -5.0),
        "Drone2": (-20.0, 20.0, -5.0),
        "Drone3": (0.0, -20.0, -5.0),
    })

    jammer_patterns: List[str] = field(default_factory=lambda: ["Jammer*", "JammerActor*", "BP_Jammer*"])

@dataclass
class PPOConfig:
    seed: int = 42
    total_steps: int = 30_000
    rollout_horizon: int = 256
    minibatch_size: int = 1024
    update_epochs: int = 8
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_ratio: float = 0.2
    lr: float = 3e-4
    vf_coef: float = 0.5
    ent_coef: float = 0.0
    max_grad_norm: float = 0.5
