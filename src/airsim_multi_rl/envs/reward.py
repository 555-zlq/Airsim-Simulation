from __future__ import annotations
from typing import Tuple
import numpy as np
from ..config import RewardWeights

class RewardComposer:
    """奖励组合器：可插拔的奖励项与权重。

    支持两种干扰惩罚模式：
    - distance：进入半径内线性扣分
    - power：按UE提供的功率做线性或比例扣分
    """

    def __init__(self, weights: RewardWeights, jammer_radius: float, goal_radius: float, mode: str = "distance"):
        self.w = weights
        self.jammer_radius = float(jammer_radius)
        self.goal_radius = float(goal_radius)
        self.mode = str(mode)

    def compute_distance(self, prev_goal_dist: float | None, dist_to_goal: float, d_jam: float, collided: bool, oob: bool, reached: bool) -> Tuple[float, dict]:
        progress = 0.0 if prev_goal_dist is None else (prev_goal_dist - dist_to_goal)
        r = self.w.progress * progress
        if d_jam < self.jammer_radius:
            r -= self.w.jammer_penalty * (self.jammer_radius - d_jam)
        r -= self.w.step_penalty
        if reached:
            r += self.w.success_bonus
        if collided:
            r -= self.w.collision_penalty
        if oob:
            r -= self.w.oob_penalty
        info = {
            "dist_to_goal": float(dist_to_goal),
            "nearest_jammer_dist": float(d_jam),
            "reached_goal": bool(reached),
            "collided": bool(collided),
            "out_of_bounds": bool(oob),
        }
        return float(r), info

    def compute_power(self, prev_goal_dist: float | None, dist_to_goal: float, power: float, collided: bool, oob: bool, reached: bool) -> Tuple[float, dict]:
        progress = 0.0 if prev_goal_dist is None else (prev_goal_dist - dist_to_goal)
        r = self.w.progress * progress
        # 简单线性扣分：功率越大惩罚越多，可按需替换为更真实的信道模型
        r -= self.w.jammer_penalty * float(power)
        r -= self.w.step_penalty
        if reached:
            r += self.w.success_bonus
        if collided:
            r -= self.w.collision_penalty
        if oob:
            r -= self.w.oob_penalty
        info = {
            "dist_to_goal": float(dist_to_goal),
            "jammer_power": float(power),
            "reached_goal": bool(reached),
            "collided": bool(collided),
            "out_of_bounds": bool(oob),
        }
        return float(r), info

    def compute(self, prev_goal_dist: float | None, dist_to_goal: float, d_or_power: float, collided: bool, oob: bool, reached: bool) -> Tuple[float, dict]:
        if self.mode == "power":
            return self.compute_power(prev_goal_dist, dist_to_goal, d_or_power, collided, oob, reached)
        else:
            return self.compute_distance(prev_goal_dist, dist_to_goal, d_or_power, collided, oob, reached)