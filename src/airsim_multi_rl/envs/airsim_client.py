from __future__ import annotations
from typing import List, TYPE_CHECKING
import importlib

if TYPE_CHECKING:
    import airsim  # 仅用于类型检查，不在运行时强制依赖

class AirSimClient:
    """AirSim 适配层：封装连接/控制/状态方法，便于 mock。

    注意：环境中严禁直接使用 airsim 原生 client，只能通过本适配层调用。
    """

    def __init__(self, ip: str, port: int):
        # 惰性导入 AirSim，避免在无 AirSim 的测试环境下模块导入失败
        ai = importlib.import_module("airsim")
        self._airsim = ai
        # 创建底层 AirSim MultirotorClient 并确认连接
        self.client = ai.MultirotorClient(ip=ip, port=port)
        self.client.confirmConnection()

    # ---- 场景/干扰源 ----
    def list_scene_objects(self, pattern: str) -> List[str]:
        return self.client.simListSceneObjects(pattern)

    def get_object_pose(self, name: str):
        return self.client.simGetObjectPose(name)

    # ---- 载具控制 ----
    def set_vehicle_pose(self, pose, ignore_collision: bool, vehicle_name: str):
        return self.client.simSetVehiclePose(pose, ignore_collision, vehicle_name=vehicle_name)

    def set_vehicle_pose_xyz(self, x: float, y: float, z: float, ignore_collision: bool, vehicle_name: str):
        """根据世界坐标设置载具姿态（偏航置零）。

        在适配层内部构造 Pose，避免上层直接依赖 airsim 库类型。
        """
        pose = self._airsim.Pose(self._airsim.Vector3r(float(x), float(y), float(z)), self._airsim.to_quaternion(0.0, 0.0, 0.0))
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

    def spawn_and_takeoff(self, x: float, y: float, z: float, vehicle_name: str, ignore_collision: bool = True):
        """在指定位置刷新并起飞，封装 API 顺序与 join。

        注意：所有 Async 命令在本函数内等待 join，确保步长一致。
        """
        try:
            self.set_vehicle_pose_xyz(x, y, z, ignore_collision, vehicle_name)
        except Exception:
            pass
        self.enable_api(True, vehicle_name=vehicle_name)
        self.arm(True, vehicle_name=vehicle_name)
        fut = self.takeoff(vehicle_name=vehicle_name)
        try:
            fut.join()
        except Exception:
            pass

    def move_velocity(self, vx: float, vy: float, vz: float, yaw_rate_deg: float, duration: float, vehicle_name: str):
        return self.client.moveByVelocityAsync(
            vx=vx, vy=vy, vz=vz, duration=duration,
            drivetrain=self._airsim.DrivetrainType.MaxDegreeOfFreedom,
            yaw_mode=self._airsim.YawMode(is_rate=True, yaw_or_rate=yaw_rate_deg),
            vehicle_name=vehicle_name,
        )

    # ---- 状态/碰撞 ----
    def get_state(self, vehicle_name: str):
        return self.client.getMultirotorState(vehicle_name=vehicle_name)

    def get_collision(self, vehicle_name: str):
        return self.client.simGetCollisionInfo(vehicle_name=vehicle_name)