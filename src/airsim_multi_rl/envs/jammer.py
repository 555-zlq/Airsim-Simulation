from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import numpy as np
from .airsim_client import AirSimClient
from ..config import UERPCConfig
import json
import urllib.request
import urllib.error

Vec3 = Tuple[float, float, float]

class JammerLocator:
    """Jammer 发现与位置刷新模块。

    仅在 reset 阶段枚举场景对象并缓存位置，满足性能约束。
    """

    def __init__(self, client: AirSimClient, patterns: List[str], rpc: Optional[UERPCConfig] = None):
        self.client = client
        self.patterns = patterns
        self.rpc = rpc or UERPCConfig()
        self.names: List[str] = []
        self.positions: Dict[str, np.ndarray] = {}
        self.powers: Dict[str, float] = {}

    def discover(self):
        names: List[str] = []
        for p in self.patterns:
            try:
                names += self.client.list_scene_objects(p)
            except Exception:
                pass
        self.names = sorted(list(set(names)))

    def refresh_positions(self):
        self.positions.clear()
        self.powers.clear()
        if not self.names:
            self.discover()
        for n in self.names:
            try:
                pose = self.client.get_object_pose(n)
                v = pose.position
                self.positions[n] = np.array([v.x_val, v.y_val, v.z_val], dtype=np.float32)
            except Exception:
                continue
        # 如果启用 RPC，则拉取功率信息
        if self.rpc.enabled:
            for n in self.names:
                try:
                    self.powers[n] = float(self._get_power_via_http(n))
                except Exception:
                    # 若失败，置为 0（可在奖励中做降权处理）
                    self.powers[n] = 0.0

    def nearest_vec(self, pos_xyz: np.ndarray) -> Tuple[np.ndarray, float]:
        if not self.positions:
            return np.zeros(3, dtype=np.float32), float(1e6)
        best_d = float("inf")
        best_vec = np.zeros(3, dtype=np.float32)
        for jp in self.positions.values():
            vec = jp - pos_xyz
            d = float(np.linalg.norm(vec))
            if d < best_d:
                best_d = d
                best_vec = vec.astype(np.float32)
        return best_vec, best_d

    def nearest_power(self, pos_xyz: np.ndarray) -> float:
        """基于位置的最邻近 Jammer 功率，若 RPC 未开启或无数据，返回 0。"""
        if not self.positions or not self.powers:
            return 0.0
        # 简单策略：选择距离最近的 Jammer 的功率
        best_d = float("inf")
        best_name = None
        for name, jp in self.positions.items():
            d = float(np.linalg.norm(jp - pos_xyz))
            if d < best_d:
                best_d, best_name = d, name
        if best_name is None:
            return 0.0
        return float(self.powers.get(best_name, 0.0))

    def _get_power_via_http(self, name: str) -> float:
        """通过简单 HTTP RPC 从 UE 端获取 Jammer 功率。

        期望 UE 端提供 GET/POST 接口，如：
        GET {url}?name=BP_Jammer_1  或 POST {url} with JSON {"name": "BP_Jammer_1"}
        返回 JSON: {"name": "BP_Jammer_1", "power": 12.34}
        """
        url = self.rpc.url
        req = urllib.request.Request(url)
        # 兼容 GET: 添加查询参数；此处简化为 POST JSON
        payload = json.dumps({"name": name}).encode("utf-8")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, data=payload, timeout=float(self.rpc.timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return float(data.get("power", 0.0))