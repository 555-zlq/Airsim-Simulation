# airsim_marl/sim/drone_agent.py
from __future__ import annotations
from typing import Tuple
import time
import numpy as np
import airsim
from .airsim_client import AirSimClient
from ..utils import quat_to_yaw

Vec3 = Tuple[float, float, float]

class DroneAgent:
    def __init__(self, client: AirSimClient, name: str):
        self.client = client
        self.name = name
        self.last_action = np.zeros(4, dtype=np.float32)

    def place_and_takeoff(self, xyz: Vec3, ignore_collision: bool = True):
        x, y, z = xyz
        pose = airsim.Pose(airsim.Vector3r(x, y, z), airsim.to_quaternion(0, 0, 0))
        try:
            self.client.set_vehicle_pose(pose, ignore_collision, vehicle_name=self.name)
        except Exception:
            pass
        self.client.enable_api(True, vehicle_name=self.name)
        self.client.arm(True, vehicle_name=self.name)
        self.client.takeoff(vehicle_name=self.name).join()
        time.sleep(0.1)

    def move_velocity(self, vx: float, vy: float, vz: float, yaw_rate_deg: float, dt: float):
        fut = self.client.move_velocity(vx, vy, vz, yaw_rate_deg, dt, vehicle_name=self.name)
        self.last_action = np.array([vx, vy, vz, yaw_rate_deg], dtype=np.float32)
        try:
            fut.join()
        except Exception:
            pass

    def get_pose_vel_yaw(self):
        st = self.client.get_state(vehicle_name=self.name)
        pos = st.kinematics_estimated.position
        vel = st.kinematics_estimated.linear_velocity
        ori = st.kinematics_estimated.orientation
        yaw = quat_to_yaw(ori.w_val, ori.x_val, ori.y_val, ori.z_val)
        pos_np = np.array([pos.x_val, pos.y_val, pos.z_val], dtype=np.float32)
        vel_np = np.array([vel.x_val, vel.y_val, vel.z_val], dtype=np.float32)
        return pos_np, vel_np, yaw

    def collided(self) -> bool:
        col = self.client.get_collision(vehicle_name=self.name)
        return bool(col.has_collided)

    def shutdown(self):
        try:
            self.client.hover(vehicle_name=self.name).join()
            self.client.land(vehicle_name=self.name).join()
            self.client.arm(False, vehicle_name=self.name)
            self.client.enable_api(False, vehicle_name=self.name)
        except Exception:
            pass
