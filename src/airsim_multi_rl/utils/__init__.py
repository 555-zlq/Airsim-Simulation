from __future__ import annotations
import math
import numpy as np

def quat_to_yaw(w: float, x: float, y: float, z: float) -> float:
    """将四元数转换为偏航角（弧度）。

    AirSim 的 Quaternionr 顺序为 (w, x, y, z)。
    """
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)

def clip(x: float, lo: float, hi: float) -> float:
    """裁剪标量值到指定范围。"""
    return float(max(lo, min(hi, x)))

def np_norm(v: np.ndarray) -> float:
    """计算向量的 L2 范数。"""
    return float(np.linalg.norm(v))

def in_bounds(pos_xyz: np.ndarray, bounds) -> bool:
    """判断位置是否在世界边界内。"""
    (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds
    x, y, z = map(float, pos_xyz[:3])
    return (xmin <= x <= xmax) and (ymin <= y <= ymax) and (zmin <= z <= zmax)

__all__ = ["quat_to_yaw", "clip", "np_norm", "in_bounds"]