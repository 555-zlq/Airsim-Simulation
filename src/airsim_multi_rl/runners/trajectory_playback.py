from __future__ import annotations
import os
import csv
import math
from typing import Dict, List, Optional, Tuple
import numpy as np

from airsim_multi_rl.config import EnvConfig, load_env_config
from airsim_multi_rl.envs.airsim_client import AirSimClient
from airsim_multi_rl.envs.jammer import JammerLocator
from airsim_multi_rl.envs.reward import RewardComposer
from airsim_multi_rl.envs.termination import TerminationChecker
from airsim_multi_rl.utils import quat_to_yaw, in_bounds
from airsim_multi_rl.utils.logging import RLLogger, _to_db


def _vec3(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> np.ndarray:
    return np.array([float(b[0]) - float(a[0]), float(b[1]) - float(a[1]), float(b[2]) - float(a[2])], dtype=np.float32)


def _norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def _clip(v: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, v)))


def _yaw_to_target(curr_yaw: float, dx: float, dy: float, yaw_rate_max_deg: float, dt: float) -> float:
    target_yaw = math.atan2(dy, dx)
    diff = target_yaw - curr_yaw
    while diff > math.pi:
        diff -= 2 * math.pi
    while diff < -math.pi:
        diff += 2 * math.pi
    rate_deg = math.degrees(diff) / dt
    return _clip(rate_deg, -yaw_rate_max_deg, yaw_rate_max_deg)


def run_trajectory(cfg: Optional[EnvConfig] = None, client: Optional[AirSimClient] = None, episodes: int = 1, steps_per_ep: int = 500) -> Dict[str, float]:
    cfg = cfg or load_env_config()
    logger = RLLogger.create(cfg.logging)
    cli_offline = os.environ.get("TRAJECTORY_OFFLINE") == "1"
    if client is None:
        client = AirSimClient(cfg.ip, cfg.port) if not cli_offline else None
    if client is None and cli_offline:
        from airsim_multi_rl.envs.dummy_client import DummyClient as _Dummy
        client = _Dummy(tuple(cfg.agent_names))
    jammer = JammerLocator(client, cfg.jammer_patterns, rpc=cfg.ue_rpc)
    reward = RewardComposer(cfg.reward, cfg.jammer_radius, cfg.goal_radius, mode=cfg.jammer_penalty_mode)
    term = TerminationChecker(cfg.max_steps)

    traj = getattr(cfg, "trajectory", None)
    speed = float(traj.get("speed", cfg.v_max)) if isinstance(traj, dict) else float(cfg.v_max)
    yaw_align = bool(traj.get("yaw_align", True)) if isinstance(traj, dict) else True
    dt = float(traj.get("dt") or cfg.dt) if isinstance(traj, dict) else float(cfg.dt)
    csv_enabled = bool(traj.get("csv_enabled", True)) if isinstance(traj, dict) else True
    csv_path = str(traj.get("csv_path", "logs/trajectory_demo.csv")) if isinstance(traj, dict) else "logs/trajectory_demo.csv"
    waypoints: Dict[str, List[List[float]]] = traj.get("waypoints", {}) if isinstance(traj, dict) else {}

    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    csv_file = open(csv_path, "w", newline="", encoding="utf-8") if csv_enabled else None
    csv_writer = csv.writer(csv_file) if csv_file else None
    if csv_writer:
        csv_writer.writerow(["episode", "step", "agent", "x", "y", "z", "dist_to_goal", "jammer_power", "reward", "collided", "oob", "reached_goal", "timestamp"])

    summary: Dict[str, float] = {}
    try:
        for ep in range(1, episodes + 1):
            logger.episode_start(ep)
            jammer.refresh_positions()
            idx: Dict[str, int] = {}
            prev_goal_dist: Dict[str, Optional[float]] = {}
            rew_sum: Dict[str, float] = {}
            for a in cfg.agent_names:
                pts = waypoints.get(a, [])
                start = tuple(pts[0]) if pts else tuple(cfg.spawn_points[a])
                client.spawn_and_takeoff(start[0], start[1], start[2], vehicle_name=a, ignore_collision=True)
                idx[a] = 0
                prev_goal_dist[a] = None
                rew_sum[a] = 0.0
            for step in range(1, steps_per_ep + 1):
                logger.step_before(ep, step, obs={})
                for a in cfg.agent_names:
                    pts = waypoints.get(a, [])
                    goal_pt = tuple(pts[-1]) if pts else tuple(cfg.goal_points[a])
                    st = client.get_state(vehicle_name=a)
                    p = st.kinematics_estimated.position
                    v = st.kinematics_estimated.linear_velocity
                    o = st.kinematics_estimated.orientation
                    curr = (p.x_val, p.y_val, p.z_val)
                    i = idx[a]
                    target = tuple(pts[i]) if (pts and i < len(pts)) else goal_pt
                    vec = _vec3(curr, target)
                    d = _norm(vec)
                    if d <= cfg.goal_radius:
                        idx[a] = min(i + 1, len(pts) - 1) if pts else i
                        target = tuple(pts[idx[a]]) if pts else goal_pt
                        vec = _vec3(curr, target)
                        d = _norm(vec)
                    if d > 1e-6:
                        dir_vec = vec / d
                    else:
                        dir_vec = np.zeros(3, dtype=np.float32)
                    vx, vy, vz = (dir_vec * speed).tolist()
                    yaw = quat_to_yaw(o.w_val, o.x_val, o.y_val, o.z_val)
                    yaw_rate = _yaw_to_target(yaw, vec[0], vec[1], cfg.yaw_rate_max_deg, dt) if yaw_align else 0.0
                    client.move_velocity(vx, vy, vz, yaw_rate, dt, vehicle_name=a).join()
                rews: Dict[str, float] = {}
                for a in cfg.agent_names:
                    pts = waypoints.get(a, [])
                    goal_pt = tuple(pts[-1]) if pts else tuple(cfg.goal_points[a])
                    st = client.get_state(vehicle_name=a)
                    p = st.kinematics_estimated.position
                    curr = (p.x_val, p.y_val, p.z_val)
                    gd = _norm(_vec3(curr, goal_pt))
                    collided = bool(client.get_collision(vehicle_name=a).has_collided)
                    oob = not in_bounds(np.array(curr, dtype=np.float32), cfg.world_bounds)
                    reached = gd <= cfg.goal_radius
                    power = float(jammer.nearest_power(np.array(curr, dtype=np.float32), step=step)) if cfg.jammer_penalty_mode == "power" else 0.0
                    r, info = reward.compute(prev_goal_dist[a], gd, power if cfg.jammer_penalty_mode == "power" else gd, collided, oob, reached)
                    prev_goal_dist[a] = gd
                    rews[a] = float(r)
                    rew_sum[a] += float(r)
                    logger.interference(episode=ep, step=step, strength=_to_db(power), kind="power" if cfg.jammer_penalty_mode == "power" else "distance", unit="dB" if cfg.jammer_penalty_mode == "power" else "meter", agent=a, raw_strength=power if cfg.jammer_penalty_mode == "power" else gd, raw_unit="power" if cfg.jammer_penalty_mode == "power" else "meter")
                    if csv_writer:
                        csv_writer.writerow([ep, step, a, curr[0], curr[1], curr[2], gd, power, float(r), int(collided), int(oob), int(reached), float(ep * 1.0)])
                logger.step_after(ep, step, actions={}, reward=rews, info={})
                done, trunc = False, False
                if all(_norm(_vec3((client.get_state(a).kinematics_estimated.position.x_val, client.get_state(a).kinematics_estimated.position.y_val, client.get_state(a).kinematics_estimated.position.z_val), tuple(waypoints.get(a, [])[-1] if waypoints.get(a, []) else cfg.goal_points[a])) ) <= cfg.goal_radius for a in cfg.agent_names):
                    done = True
                if step >= steps_per_ep or step >= cfg.max_steps:
                    trunc = True
                if done or trunc:
                    break
            logger.episode_end(ep, reward_sum=float(sum(rew_sum.values())))
            for a in cfg.agent_names:
                summary[f"{a}.reward_sum"] = rew_sum[a]
    finally:
        if csv_file:
            csv_file.close()
        logger.shutdown()
        for a in cfg.agent_names:
            try:
                client.hover(vehicle_name=a).join()
                client.land(vehicle_name=a).join()
            except Exception:
                pass
    return summary


def main():
    run_trajectory()


if __name__ == "__main__":
    main()
