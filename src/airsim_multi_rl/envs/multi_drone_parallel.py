from __future__ import annotations
from typing import Dict, List, Optional
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from pettingzoo.utils.env import ParallelEnv

from ..config import EnvConfig
from ..utils import clip, in_bounds
from .airsim_client import AirSimClient
from .jammer import JammerLocator
from .observation import ObservationBuilder
from .reward import RewardComposer
from .termination import TerminationChecker
from .actions import ActionExecutor


class AirSimMultiDroneParallelEnv(ParallelEnv):
    """PettingZoo 并行环境粘合层。

    遵循项目规则：
    - 不直接引用 AirSim 原生 client；通过适配层访问。
    - 观测/奖励/终止/动作均为独立模块。
    """

    metadata = {"name": "airsim_multi_drone_parallel_v1"}

    def __init__(self, cfg: Optional[EnvConfig] = None, client: Optional[AirSimClient] = None):
        # 配置
        self.cfg = cfg or EnvConfig()
        self.agents: List[str] = list(self.cfg.agent_names)
        self.possible_agents = list(self.agents)

        # 适配层与世界对象
        # 允许外部注入适配层客户端，便于测试 mock
        self.client = client or AirSimClient(self.cfg.ip, self.cfg.port)
        self.jammers = JammerLocator(self.client, self.cfg.jammer_patterns, rpc=self.cfg.ue_rpc)
        self.obs_builder = ObservationBuilder()
        self.rew = RewardComposer(self.cfg.reward, self.cfg.jammer_radius, self.cfg.goal_radius, mode=self.cfg.jammer_penalty_mode)
        self.term = TerminationChecker(self.cfg.max_steps)
        self.action_exec = ActionExecutor(self.cfg.v_max, self.cfg.yaw_rate_max_deg)

        # 空间定义
        self.v_max = float(self.cfg.v_max)
        self.yaw_rate_max_deg = float(self.cfg.yaw_rate_max_deg)
        act_high = np.array([self.v_max, self.v_max, self.v_max, self.yaw_rate_max_deg], dtype=np.float32)
        self._action_spaces = {a: spaces.Box(low=-act_high, high=act_high, shape=(4,), dtype=np.float32) for a in self.agents}
        obs_high = self.obs_builder.high()
        self._observation_spaces = {a: spaces.Box(low=-obs_high, high=obs_high, shape=(17,), dtype=np.float32) for a in self.agents}

        # 运行时状态
        self._steps = 0
        self._terminated = {a: False for a in self.agents}
        self._truncated = {a: False for a in self.agents}
        self._prev_goal_dist = {a: None for a in self.agents}

    # ---- PettingZoo API ----
    def observation_space(self, agent):
        return self._observation_spaces[agent]

    def action_space(self, agent):
        return self._action_spaces[agent]

    def reset(self, seed: Optional[int] = None, options: Optional[dict] = None):
        # 仅在 reset 阶段刷新 Jammer，满足性能约束
        self.jammers.refresh_positions()

        # 无人机起飞（通过适配层封装）
        for a in self.agents:
            x, y, z = self.cfg.spawn_points[a]
            self.client.spawn_and_takeoff(x, y, z, vehicle_name=a, ignore_collision=True)

        self._steps = 0
        self._terminated = {a: False for a in self.agents}
        self._truncated = {a: False for a in self.agents}
        self._prev_goal_dist = {a: None for a in self.agents}

        obs = {a: self._get_obs(a) for a in self.agents}
        infos = {a: {} for a in self.agents}
        return obs, infos

    def step(self, actions: Dict[str, np.ndarray]):
        # 下发动作（裁剪并等待 join 保证 dt 一致）
        for a, act in actions.items():
            if self._terminated[a] or self._truncated[a]:
                continue
            # 使用动作执行器统一裁剪动作范围
            vx, vy, vz, yaw_rate = [float(x) for x in self.action_exec.clip(np.asarray(act, dtype=np.float32))]
            try:
                self.client.move_velocity(vx, vy, vz, yaw_rate, self.cfg.dt, vehicle_name=a).join()
            except Exception:
                pass

        self._steps += 1

        obs, rews, terms, truncs, infos = {}, {}, {}, {}, {}
        for a in self.agents:
            ob = self._get_obs(a)
            r, info = self._reward_and_info(a, ob)
            done, trunc = self.term.done_trunc(self._steps, info["collided"], info["out_of_bounds"], info["reached_goal"])
            obs[a], rews[a], terms[a], truncs[a], infos[a] = ob, r, done, trunc, info
            self._terminated[a], self._truncated[a] = done, trunc

        return obs, rews, terms, truncs, infos

    def render(self):
        """返回当前帧的渲染信息。

        为对齐渲染管线，提供两类输出：
        - obs：17维观测（兼容既有流程）
        - rgb：来自 AirSim 摄像头的 RGB 图像（若不可用则为 None）
        """
        frames: Dict[str, dict] = {}
        for a in self.agents:
            frames[a] = {
                "obs": self._get_obs(a),
                "rgb": self.client.get_rgb_image(vehicle_name=a, camera_name="0") if hasattr(self.client, "get_rgb_image") else None,
            }
        return frames

    def close(self):
        for a in self.agents:
            try:
                self.client.hover(vehicle_name=a).join()
                self.client.land(vehicle_name=a).join()
                self.client.arm(False, vehicle_name=a)
                self.client.enable_api(False, vehicle_name=a)
            except Exception:
                pass

    # ---- internals ----
    def _get_obs(self, a: str) -> np.ndarray:
        st = self.client.get_state(vehicle_name=a)
        pos = st.kinematics_estimated.position
        vel = st.kinematics_estimated.linear_velocity
        ori = st.kinematics_estimated.orientation
        # 计算 yaw
        from ..utils import quat_to_yaw
        yaw = quat_to_yaw(ori.w_val, ori.x_val, ori.y_val, ori.z_val)

        pos_np = np.array([pos.x_val, pos.y_val, pos.z_val], dtype=np.float32)
        vel_np = np.array([vel.x_val, vel.y_val, vel.z_val], dtype=np.float32)
        goal = np.array(self.cfg.goal_points[a], dtype=np.float32)
        jam_vec, d_jam = self.jammers.nearest_vec(pos_np)
        # last_action 由 client 不维护，这里置 0 以满足形状；真实实现可在更高层维护
        last_action = np.zeros(4, dtype=np.float32)

        ob = self.obs_builder.build(pos_np, vel_np, float(yaw), goal, jam_vec, last_action)
        # 缓存用于进步奖励
        self._prev_goal_dist[a] = float(np.linalg.norm(goal - pos_np)) if self._prev_goal_dist[a] is None else self._prev_goal_dist[a]
        return ob

    def _reward_and_info(self, a: str, ob: np.ndarray):
        pos = ob[0:3]
        goal_delta = ob[7:10]
        jam_vec = ob[10:13]
        dist_to_goal = float(np.linalg.norm(goal_delta))
        d_jam = float(np.linalg.norm(jam_vec))

        # 终止信号相关标志（通过适配层查询）
        collided = bool(self.client.get_collision(vehicle_name=a).has_collided)
        oob = not in_bounds(pos, self.cfg.world_bounds)
        reached = dist_to_goal <= self.cfg.goal_radius

        # 根据模式选择距离或功率作为第三参数（传入当前步数以实现步频控制）
        d_or_power = d_jam if self.cfg.jammer_penalty_mode != "power" else float(self.jammers.nearest_power(pos, step=self._steps))
        r, info = self.rew.compute(self._prev_goal_dist[a], dist_to_goal, d_or_power, collided, oob, reached)
        if self.cfg.jammer_penalty_mode == "power":
            info["nearest_jammer_dist"] = d_jam
        # 更新 prev_goal_dist
        self._prev_goal_dist[a] = dist_to_goal
        return float(r), info