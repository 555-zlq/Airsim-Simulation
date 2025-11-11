from __future__ import annotations
from typing import Dict
import numpy as np

class ObservationBuilder:
    """集中式观测构建器。

    默认 17 维：pos(3), vel(3), yaw(1), goal_delta(3), nearest_jammer_delta(3), last_action(4)
    """

    def build(self, pos: np.ndarray, vel: np.ndarray, yaw: float, goal: np.ndarray, jam_vec: np.ndarray, last_action: np.ndarray) -> np.ndarray:
        yaw_arr = np.array([yaw], dtype=np.float32)
        goal_delta = (goal.astype(np.float32) - pos.astype(np.float32))
        return np.concatenate([pos.astype(np.float32), vel.astype(np.float32), yaw_arr, goal_delta, jam_vec.astype(np.float32), last_action.astype(np.float32)], axis=0)

    def high(self) -> np.ndarray:
        return np.full((17,), np.inf, dtype=np.float32)