from __future__ import annotations
import numpy as np
from src.airsim_multi_rl.config import EnvConfig
from src.airsim_multi_rl.envs.multi_drone_parallel import AirSimMultiDroneParallelEnv
from src.airsim_multi_rl.envs.airsim_client import AirSimClient

class DummyClient(AirSimClient):
    """最小 Dummy 适配层，用于在无 AirSim 的情况下运行形状测试。"""

    def __init__(self):
        class _C:
            pass
        self.client = _C()  # 仅占位，不做真实连接

    # 以下方法返回固定值以满足环境调用
    def spawn_and_takeoff(self, x: float, y: float, z: float, vehicle_name: str, ignore_collision: bool = True):
        return None
    def move_velocity(self, vx: float, vy: float, vz: float, yaw_rate_deg: float, duration: float, vehicle_name: str):
        class _F:
            def join(self_inner):
                return None
        return _F()
    def get_state(self, vehicle_name: str):
        class _Vec:
            def __init__(self, x, y, z):
                self.x_val, self.y_val, self.z_val = x, y, z
        class _Ori:
            def __init__(self):
                self.w_val, self.x_val, self.y_val, self.z_val = 1.0, 0.0, 0.0, 0.0
        class _Kin:
            def __init__(self):
                self.position = _Vec(0.0, 0.0, -3.0)
                self.linear_velocity = _Vec(0.0, 0.0, 0.0)
                self.orientation = _Ori()
        class _State:
            def __init__(self):
                self.kinematics_estimated = _Kin()
        return _State()
    def get_collision(self, vehicle_name: str):
        class _Col:
            def __init__(self):
                self.has_collided = False
        return _Col()


def test_spaces_and_reset():
    cfg = EnvConfig()
    env = AirSimMultiDroneParallelEnv(cfg, client=DummyClient())
    # 检查空间形状
    for a in env.agents:
        assert env.action_space(a).shape == (4,)
        assert env.observation_space(a).shape == (17,)
    obs, infos = env.reset()
    assert set(obs.keys()) == set(env.agents)
    for a, ob in obs.items():
        assert ob.shape == (17,)
    env.close()