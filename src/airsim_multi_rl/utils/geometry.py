from __future__ import annotations
import math
from typing import Tuple

def euclidean_distance(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    """计算三维欧氏距离。

    Args:
        a: 点A坐标 (x, y, z)
        b: 点B坐标 (x, y, z)

    Returns:
        两点之间的欧氏距离。
    """
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    dz = float(a[2]) - float(b[2])
    return math.sqrt(dx * dx + dy * dy + dz * dz)

def normalize_yaw_rad(yaw: float) -> float:
    """将弧度制 yaw 归一化到 [-pi, pi] 区间。

    Args:
        yaw: 输入弧度。

    Returns:
        归一化后的弧度值。
    """
    y = float(yaw)
    while y > math.pi:
        y -= 2.0 * math.pi
    while y < -math.pi:
        y += 2.0 * math.pi
    return y