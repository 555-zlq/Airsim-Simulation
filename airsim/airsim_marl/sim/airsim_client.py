# airsim_marl/sim/airsim_client.py
from __future__ import annotations
from typing import List
import airsim

class AirSimClient:
    """Thin wrapper over AirSim's Python client with explicit methods used by the env."""

    def __init__(self, ip: str, port: int):
        self.client = airsim.MultirotorClient(ip=ip, port=port)
        self.client.confirmConnection()

    # ---- Scene / jammer related ----
    def list_scene_objects(self, pattern: str) -> List[str]:
        return self.client.simListSceneObjects(pattern)

    def get_object_pose(self, name: str) -> airsim.Pose:
        return self.client.simGetObjectPose(name)

    # ---- Vehicle control ----
    def set_vehicle_pose(self, pose: airsim.Pose, ignore_collision: bool, vehicle_name: str):
        return self.client.simSetVehiclePose(pose, ignore_collision, vehicle_name=vehicle_name)

    def enable_api(self, enabled: bool, vehicle_name: str):
        return self.client.enableApiControl(enabled, vehicle_name=vehicle_name)

    def arm(self, armed: bool, vehicle_name: str):
        return self.client.armDisarm(armed, vehicle_name=vehicle_name)

    def takeoff(self, vehicle_name: str):
        return self.client.takeoffAsync(vehicle_name=vehicle_name)

    def hover(self, vehicle_name: str):
        return self.client.hoverAsync(vehicle_name=vehicle_name)

    def land(self, vehicle_name: str):
        return self.client.landAsync(vehicle_name=vehicle_name)

    def move_velocity(self, vx: float, vy: float, vz: float, yaw_rate_deg: float, duration: float, vehicle_name: str):
        return self.client.moveByVelocityAsync(
            vx=vx, vy=vy, vz=vz, duration=duration,
            drivetrain=airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate_deg),
            vehicle_name=vehicle_name
        )

    # ---- State / collision ----
    def get_state(self, vehicle_name: str) -> airsim.MultirotorState:
        return self.client.getMultirotorState(vehicle_name=vehicle_name)

    def get_collision(self, vehicle_name: str) -> airsim.CollisionInfo:
        return self.client.simGetCollisionInfo(vehicle_name=vehicle_name)
