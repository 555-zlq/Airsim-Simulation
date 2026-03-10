# airsim_marl/envs/multi_drone_env.py
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import time
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pettingzoo.utils.env import ParallelEnv

from ..config import EnvConfig
from ..utils import clip, in_bounds
from ..sim.airsim_client import AirSimClient
from ..sim.drone_agent import DroneAgent
from ..sim.world import World
from .jammer import CommJammerModel

class AirSimMultiDroneParallelEnv(ParallelEnv):
    metadata = {"name": "airsim_multi_drone_parallel_v1"}

    def __init__(self, cfg: Optional[EnvConfig] = None):
        self.cfg = cfg or EnvConfig()
        self.agents: List[str] = list(self.cfg.agent_names)
        self.possible_agents = list(self.agents)

        # sim & world
        self.client = AirSimClient(self.cfg.ip, self.cfg.port)
        self.world = World(self.client, self.cfg.jammer_patterns, self.cfg.world_bounds)
        self.world.refresh_jammers()
        self.jammer_model = CommJammerModel(self.world, self.cfg)

        # drones
        self.drones: Dict[str, DroneAgent] = {a: DroneAgent(self.client, a) for a in self.agents}

        # spaces
        self.v_max = float(self.cfg.v_max)
        self.yaw_rate_max_deg = float(self.cfg.yaw_rate_max_deg)
        act_high = np.array([self.v_max, self.v_max, self.v_max, self.yaw_rate_max_deg], dtype=np.float32)
        self._action_spaces = {a: spaces.Box(low=-act_high, high=act_high, shape=(4,), dtype=np.float32) for a in self.agents}
        obs_high = np.full((17,), np.inf, dtype=np.float32)
        self._observation_spaces = {a: spaces.Box(low=-obs_high, high=obs_high, shape=(17,), dtype=np.float32) for a in self.agents}

        # runtime
        self._steps = 0
        self._terminated = {a: False for a in self.agents}
        self._truncated = {a: False for a in self.agents}
        self._prev_goal_dist = {a: None for a in self.agents}

    # ---- PettingZoo API ----
    def observation_space(self, agent): return self._observation_spaces[agent]
    def action_space(self, agent): return self._action_spaces[agent]

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        # reset world & drones
        self.world.refresh_jammers()
        for a in self.agents:
            self.drones[a].place_and_takeoff(self.cfg.spawn_points[a], ignore_collision=True)

        time.sleep(0.2)

        self._steps = 0
        self._terminated = {a: False for a in self.agents}
        self._truncated = {a: False for a in self.agents}
        self._prev_goal_dist = {a: None for a in self.agents}

        obs = {a: self._get_obs(a) for a in self.agents}
        infos = {a: {} for a in self.agents}
        return obs, infos

    def step(self, actions: Dict[str, np.ndarray]):
        # issue actions
        for a, act in actions.items():
            if self._terminated[a] or self._truncated[a]:
                continue
            vx, vy, vz, yaw_rate = [float(x) for x in act]
            vx = clip(vx, -self.v_max, self.v_max)
            vy = clip(vy, -self.v_max, self.v_max)
            vz = clip(vz, -self.v_max, self.v_max)
            yaw_rate = clip(yaw_rate, -self.yaw_rate_max_deg, self.yaw_rate_max_deg)
            self.drones[a].move_velocity(vx, vy, vz, yaw_rate, self.cfg.dt)

        self._steps += 1

        obs, rews, terms, truncs, infos = {}, {}, {}, {}, {}
        for a in self.agents:
            ob = self._get_obs(a)
            r, info = self._reward_and_info(a, ob)
            done, trunc = self._done_trunc(a, ob, info)
            obs[a], rews[a], terms[a], truncs[a], infos[a] = ob, r, done, trunc, info
            self._terminated[a], self._truncated[a] = done, trunc

        return obs, rews, terms, truncs, infos

    def render(self):  # rely on AirSim window; return state for debugging
        return {a: self._get_obs(a) for a in self.agents}

    def close(self):
        for a in self.agents:
            self.drones[a].shutdown()

    # ---- internals ----
    def _get_obs(self, a: str) -> np.ndarray:
        pos, vel, yaw = self.drones[a].get_pose_vel_yaw()
        goal = np.array(self.cfg.goal_points[a], dtype=np.float32)
        goal_delta = goal - pos

        jam_vec, _ = self.world.nearest_jammer_vec(pos)
        last_action = self.drones[a].last_action.astype(np.float32)
        # 计算通信频点（支持跳频）
        freq = float(self.cfg.comm_freq_hz.get(a, 2.4e9))
        if self.cfg.hop_enabled:
            seq = self.cfg.hop_sequence.get(a, [freq])
            if len(seq) > 0:
                idx = (self._steps // max(int(self.cfg.hop_period_s / max(self.cfg.dt, 1e-6)), 1)) % len(seq)
                freq = float(seq[idx])
        # 更新 jammer 指向（使用最近干扰器追踪该无人机）
        self.jammer_model.update_pointing(target_name=a, target_pos=pos, dt_s=self.cfg.dt, detected_freq_hz=freq)
        # 计算 SINR 并 jammed 标志
        sinr_db = self.jammer_model.sinr_db(target_pos=pos, target_tx_dbm=float(self.cfg.comm_tx_dbm_per_drone.get(a, 20.0)), freq_hz=freq)
        is_jammed = 1.0 if sinr_db < self.cfg.jammer_target_sinr_db else 0.0

        return np.concatenate([
            pos, vel, np.array([yaw], dtype=np.float32),
            goal_delta, jam_vec, last_action
        ], axis=0)

    def _reward_and_info(self, a: str, ob: np.ndarray):
        pos = ob[0:3]; goal_delta = ob[7:10]; jam_vec = ob[10:13]
        dist_to_goal = float(np.linalg.norm(goal_delta))

        prev = self._prev_goal_dist[a]
        progress = 0.0 if prev is None else (prev - dist_to_goal)
        self._prev_goal_dist[a] = dist_to_goal

        r = 1.0 * progress  # progress reward
        # 通信干扰惩罚（基于 SINR）
        freq = float(self.cfg.comm_freq_hz.get(a, 2.4e9))
        if self.cfg.hop_enabled:
            seq = self.cfg.hop_sequence.get(a, [freq])
            if len(seq) > 0:
                idx = (self._steps // max(int(self.cfg.hop_period_s / max(self.cfg.dt, 1e-6)), 1)) % len(seq)
                freq = float(seq[idx])
        sinr_db = self.jammer_model.sinr_db(target_pos=pos, target_tx_dbm=float(self.cfg.comm_tx_dbm_per_drone.get(a, 20.0)), freq_hz=freq)
        per = self.jammer_model.per_from_sinr(sinr_db)
        r -= self.cfg.jammer_penalty_w * per
        r -= 0.01  # step penalty

        collided = self.drones[a].collided()
        oob = not in_bounds(pos, self.cfg.world_bounds)
        reached = dist_to_goal <= self.cfg.goal_radius
        if reached: r += 100.0
        if collided: r -= 50.0
        if oob: r -= 20.0

        info = {
            "collided": collided,
            "out_of_bounds": oob,
            "reached_goal": reached,
            "dist_to_goal": dist_to_goal,
            "sinr_db": sinr_db,
            "per": per,
        }
        return float(r), info

    def _done_trunc(self, a: str, ob: np.ndarray, info: dict):
        done = info["collided"] or info["out_of_bounds"] or info["reached_goal"]
        trunc = (self._steps >= self.cfg.max_steps)
        return bool(done), bool(trunc)
