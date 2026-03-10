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

    # --- 通信与干扰参数 ---
    # 频段与功率
    comm_freq_hz: Dict[str, float] = field(default_factory=lambda: {
        "Drone1": 2.4e9,
        "Drone2": 2.4e9,
        "Drone3": 2.4e9,
    })
    comm_tx_dbm_per_drone: Dict[str, float] = field(default_factory=lambda: {
        "Drone1": 20.0,
        "Drone2": 20.0,
        "Drone3": 20.0,
    })
    comm_rx_gain_db: float = 0.0
    comm_noise_floor_dbm: float = -95.0
    comm_beacon_period_s: float = 0.2
    comm_freq_min_hz: float = 2.3e9
    comm_freq_max_hz: float = 2.5e9

    # 跳频
    hop_enabled: bool = False
    hop_period_s: float = 1.0
    hop_sequence: Dict[str, List[float]] = field(default_factory=lambda: {
        "Drone1": [2.4e9, 2.41e9],
        "Drone2": [2.4e9, 2.41e9],
        "Drone3": [2.4e9, 2.41e9],
    })

    # 干扰器参数（伺服天线 + 窄带）
    jammer_eirp_dbm: float = 40.0
    jammer_gain_max_dbi: float = 10.0
    jammer_gain_side_dbi: float = -5.0
    jammer_main_lobe_width_deg: float = 30.0
    jammer_narrow_bw_hz: float = 1.0e6
    jammer_servo_slew_deg_per_s: float = 180.0
    jammer_detection_snr_db: float = 5.0
    jammer_detection_latency_ms: float = 50.0
    jammer_reacquisition_ms: float = 100.0
    jammer_target_sinr_db: float = 5.0
    jammer_penalty_w: float = 1.0

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
