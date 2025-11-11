from __future__ import annotations
import math
from typing import Dict, Tuple

class DummyFuture:
    def join(self):
        return None

class DummyClient:
    """无 AirSim 的模拟适配层，支持基本接口以离线运行与单测。

    - 维护简单的位置/速度状态
    - 不进行真实物理模拟，仅按速度积分
    """

    def __init__(self, agent_names: Tuple[str, ...] | list[str] = ("Drone1", "Drone2", "Drone3")):
        self.pos: Dict[str, Tuple[float, float, float]] = {a: (0.0, 0.0, -3.0) for a in agent_names}
        self.vel: Dict[str, Tuple[float, float, float]] = {a: (0.0, 0.0, 0.0) for a in agent_names}
        self._collided: Dict[str, bool] = {a: False for a in agent_names}

    # 兼容 AirSimClient 接口
    def list_scene_objects(self, pattern: str):
        # 返回空，测试时可按需扩展
        return []

    def get_object_pose(self, name: str):
        class _Vec:
            def __init__(self, x, y, z):
                self.x_val, self.y_val, self.z_val = x, y, z
        class _Pose:
            def __init__(self):
                self.position = _Vec(0.0, 0.0, 0.0)
        return _Pose()

    def set_vehicle_pose_xyz(self, x: float, y: float, z: float, ignore_collision: bool, vehicle_name: str):
        self.pos[vehicle_name] = (float(x), float(y), float(z))

    def enable_api(self, enabled: bool, vehicle_name: str):
        return None

    def arm(self, armed: bool, vehicle_name: str):
        return None

    def takeoff(self, vehicle_name: str):
        return DummyFuture()

    def hover(self, vehicle_name: str):
        return DummyFuture()

    def land(self, vehicle_name: str):
        return DummyFuture()

    def spawn_and_takeoff(self, x: float, y: float, z: float, vehicle_name: str, ignore_collision: bool = True):
        self.set_vehicle_pose_xyz(x, y, z, ignore_collision, vehicle_name)
        return None

    def move_velocity(self, vx: float, vy: float, vz: float, yaw_rate_deg: float, duration: float, vehicle_name: str):
        # 简单速度积分更新位置，不考虑姿态与 yaw
        px, py, pz = self.pos[vehicle_name]
        nx = px + float(vx) * float(duration)
        ny = py + float(vy) * float(duration)
        nz = pz + float(vz) * float(duration)
        self.pos[vehicle_name] = (nx, ny, nz)
        self.vel[vehicle_name] = (float(vx), float(vy), float(vz))
        return DummyFuture()

    def get_state(self, vehicle_name: str):
        class _Vec:
            def __init__(self, x, y, z):
                self.x_val, self.y_val, self.z_val = x, y, z
        class _Ori:
            def __init__(self):
                self.w_val, self.x_val, self.y_val, self.z_val = 1.0, 0.0, 0.0, 0.0
        class _Kin:
            def __init__(self, p, v):
                self.position = _Vec(*p)
                self.linear_velocity = _Vec(*v)
                self.orientation = _Ori()
        class _State:
            def __init__(self, p, v):
                self.kinematics_estimated = _Kin(p, v)
        return _State(self.pos[vehicle_name], self.vel[vehicle_name])

    def get_collision(self, vehicle_name: str):
        class _Col:
            def __init__(self, c):
                self.has_collided = c
        return _Col(self._collided[vehicle_name])