# airsim_marl/utils.py
from __future__ import annotations
import math
import numpy as np

def quat_to_yaw(w: float, x: float, y: float, z: float) -> float:
    # AirSim Quaternionr is (w, x, y, z). Return yaw (radians).
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)

def clip(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))

def np_norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))

def in_bounds(pos_xyz: np.ndarray, bounds) -> bool:
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds
    x, y, z = map(float, pos_xyz[:3])
    return (xmin <= x <= xmax) and (ymin <= y <= ymax) and (zmin <= z <= zmax)
