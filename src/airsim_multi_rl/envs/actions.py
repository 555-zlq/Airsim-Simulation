from __future__ import annotations
import numpy as np

class ActionExecutor:
    """连续动作执行器：裁剪并调用适配层移动。

    说明：动作格式为 [vx, vy, vz, yaw_rate_deg]，在世界系，单位 m/s, deg/s。
    """

    def __init__(self, v_max: float, yaw_rate_max_deg: float):
        self.v_max = float(v_max)
        self.yaw_rate_max_deg = float(yaw_rate_max_deg)

    def clip(self, act: np.ndarray) -> np.ndarray:
        a = act.astype(np.float32)
        a[0:3] = np.clip(a[0:3], -self.v_max, self.v_max)
        a[3] = float(np.clip(a[3], -self.yaw_rate_max_deg, self.yaw_rate_max_deg))
        return a