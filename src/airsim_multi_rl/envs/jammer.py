from __future__ import annotations
from typing import Dict, List, Tuple, Optional
import numpy as np
from .airsim_client import AirSimClient
from ..config import UERPCConfig
import json
import urllib.request
import urllib.error
import urllib.parse

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
        # 最近一次从 UE 拉取到的 Jammer 列表（含位置与半径），用于缓存与调试
        self._ue_jammers_raw: List[dict] = []

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
        # 若启用 RPC，则优先通过 UE 的 /jammers 获取 Jammer 名单与位置（单位 cm，需要转换为 m）
        fetched_from_rpc = False
        if self.rpc.enabled:
            try:
                self._ue_jammers_raw = self._get_jammers_via_http()
                self.names = []
                for item in (self._ue_jammers_raw or []):
                    name = str(item.get("name", "")).strip()
                    loc = item.get("location", {})
                    # UE 使用 cm；后端使用 m
                    x_cm = float(loc.get("X", 0.0))
                    y_cm = float(loc.get("Y", 0.0))
                    z_cm = float(loc.get("Z", 0.0))
                    m_per_cm = 1.0 / float(max(self.rpc.cm_per_m, 1e-6))
                    pos_m = np.array([x_cm * m_per_cm, y_cm * m_per_cm, z_cm * m_per_cm], dtype=np.float32)
                    if name:
                        self.names.append(name)
                        self.positions[name] = pos_m
                        # 若返回了基准功率，缓存为初值
                        base_p = float(item.get("basePower", 0.0))
                        self.powers[name] = base_p
                # 去重并排序
                self.names = sorted(list(set(self.names)))
                fetched_from_rpc = True
            except Exception:
                fetched_from_rpc = False

        # 若未从 UE RPC 成功获取，则回退到 AirSim 场景枚举与姿态查询
        if not fetched_from_rpc:
            if not self.names:
                self.discover()
            for n in self.names:
                try:
                    pose = self.client.get_object_pose(n)
                    v = pose.position
                    self.positions[n] = np.array([v.x_val, v.y_val, v.z_val], dtype=np.float32)
                except Exception:
                    continue
            # 如果启用 RPC，尝试为每个 Jammer 拉取一次基准功率
            if self.rpc.enabled:
                for n in self.names:
                    try:
                        self.powers[n] = float(self._get_power_via_http(n))
                    except Exception:
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

    def nearest_power(self, pos_xyz: np.ndarray, step: Optional[int] = None) -> float:
        """基于位置的最近 Jammer 功率。

        行为：
        - 若 RPC 未启用或无 Jammer 数据，返回 0。
        - 若启用 RPC，并满足 `query_every_n_steps` 步频，则调用 UE `/jammer_power` 传入位置（cm）。
        - 否则，返回上次缓存的最近 Jammer 的功率值。
        """
        if not self.positions:
            return 0.0
        # 选择距离最近的 Jammer
        best_d = float("inf")
        best_name = None
        for name, jp in self.positions.items():
            d = float(np.linalg.norm(jp - pos_xyz))
            if d < best_d:
                best_d, best_name = d, name

        if best_name is None:
            return 0.0

        # 若不启用 RPC，或未满足查询步频，返回缓存
        if not self.rpc.enabled:
            return float(self.powers.get(best_name, 0.0))
        if step is not None and self.rpc.query_every_n_steps > 1:
            if (step % int(self.rpc.query_every_n_steps)) != 0:
                return float(self.powers.get(best_name, 0.0))

        # 发起位置相关查询（cm）并更新缓存
        try:
            p = float(self._get_power_via_http(best_name, pos_m=pos_xyz))
            self.powers[best_name] = p
            return p
        except Exception:
            return float(self.powers.get(best_name, 0.0))

    def _get_jammers_via_http(self) -> List[dict]:
        """GET /jammers：拉取 UE 场景中的 Jammer 概览列表。"""
        base = self.rpc.http_base.rstrip("/")
        path = self.rpc.jammers_endpoint
        url = f"{base}{path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=float(self.rpc.timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            jammers = data.get("jammers", [])
            # 兼容非标准返回
            if isinstance(jammers, list):
                return jammers
            return []

    def _get_power_via_http(self, name: str, pos_m: Optional[np.ndarray] = None) -> float:
        """查询 UE 端 Jammer 功率。

        - 若提供 pos_m（单位 m），将转换到 cm 并作为 x/y/z 参数携带。
        - 兼容完整 URL（旧字段 url）或基地址+端点（http_base + power_endpoint）。
        """
        # 构造目标 URL
        if self.rpc.url:
            base_url = self.rpc.url
        else:
            base = self.rpc.http_base.rstrip("/")
            path = self.rpc.power_endpoint
            base_url = f"{base}{path}"

        # 构造查询参数：优先使用 GET 以便调试
        params = {"name": name}
        if pos_m is not None and len(pos_m) >= 3:
            # m -> cm
            k = float(self.rpc.cm_per_m)
            x_cm = float(pos_m[0]) * k
            y_cm = float(pos_m[1]) * k
            z_cm = float(pos_m[2]) * k
            params.update({"x": x_cm, "y": y_cm, "z": z_cm})
        url_with_qs = base_url
        if params:
            qs = urllib.parse.urlencode(params)
            sep = "&" if ("?" in base_url) else "?"
            url_with_qs = f"{base_url}{sep}{qs}"

        # 发起 GET 请求
        req = urllib.request.Request(url_with_qs)
        with urllib.request.urlopen(req, timeout=float(self.rpc.timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # 兼容错误返回
            if isinstance(data, dict) and "error" in data:
                return 0.0
            return float(data.get("power", 0.0))