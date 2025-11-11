# airsim_marl/sim/world.py
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
import airsim
from .airsim_client import AirSimClient
from ..utils import np_norm

Vec3 = Tuple[float, float, float]

class World:
    def __init__(self, client: AirSimClient, jammer_patterns: List[str], bounds):
        self.client = client
        self.jammer_patterns = jammer_patterns
        self.bounds = bounds
        self.jammer_names: List[str] = []
        self.jammer_positions: Dict[str, np.ndarray] = {}

    def discover_jammers(self):
        names: List[str] = []
        for p in self.jammer_patterns:
            try:
                names += self.client.list_scene_objects(p)
            except Exception:
                pass
        self.jammer_names = sorted(list(set(names)))

    def refresh_jammers(self):
        self.jammer_positions.clear()
        if not self.jammer_names:
            self.discover_jammers()
        for n in self.jammer_names:
            try:
                pose: airsim.Pose = self.client.get_object_pose(n)
                jp = pose.position
                self.jammer_positions[n] = np.array([jp.x_val, jp.y_val, jp.z_val], dtype=np.float32)
            except Exception:
                continue

    def nearest_jammer_vec(self, pos_xyz: np.ndarray):
        if not self.jammer_positions:
            return np.zeros(3, dtype=np.float32), float(1e6)
        best_vec = None
        best_d = float("inf")
        for jp in self.jammer_positions.values():
            vec = jp - pos_xyz
            d = np_norm(vec)
            if d < best_d:
                best_d = d
                best_vec = vec
        return best_vec.astype(np.float32), float(best_d)
