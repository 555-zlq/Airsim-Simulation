from __future__ import annotations
import numpy as np
from airsim_multi_rl.config import EnvConfig
from airsim_multi_rl.envs.multi_drone_parallel import AirSimMultiDroneParallelEnv
from airsim_multi_rl.envs.airsim_client import AirSimClient

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

    def get_rgb_image(self, vehicle_name: str, camera_name: str = "0"):
        # 返回一个固定的 8x8 RGB 帧，便于验证渲染结构
        return np.zeros((8, 8, 3), dtype=np.uint8)


def test_spaces_and_reset():
    cfg = EnvConfig()
    # 启用干扰层（高斯），确保不影响空间与形状
    cfg.interference.enabled = True
    cfg.interference.mode = "gaussian"
    cfg.interference.gaussian_sigma = 0.01
    env = AirSimMultiDroneParallelEnv(cfg, client=DummyClient())
    # 检查空间形状
    for a in env.agents:
        assert env.action_space(a).shape == (4,)
        assert env.observation_space(a).shape == (17,)
    obs, infos = env.reset()
    assert set(obs.keys()) == set(env.agents)
    for a, ob in obs.items():
        assert ob.shape == (17,)
        # 干扰层只影响位置分量：检查 pos_raw 备份存在，且类型正确
        assert "pos_raw" in infos[a]
        assert "timestamp" in infos[a]
        assert isinstance(infos[a]["pos_raw"], list) and len(infos[a]["pos_raw"]) == 3
    env.close()


def test_render_contains_rgb_and_obs():
    cfg = EnvConfig()
    env = AirSimMultiDroneParallelEnv(cfg, client=DummyClient())
    env.reset()
    frames = env.render()
    for a in env.agents:
        assert isinstance(frames[a], dict)
        assert "obs" in frames[a]
        assert "rgb" in frames[a]
        # rgb 为 numpy 数组或 None，这里要求数组形状为 (H,W,3)
        rgb = frames[a]["rgb"]
        assert rgb is None or (rgb.ndim == 3 and rgb.shape[2] >= 3)
    env.close()


def test_power_mode_info_keys():
    cfg = EnvConfig()
    cfg.jammer_penalty_mode = "power"
    # 禁用 HTTP，确保在无 UE 情况下也能运行；功率应为 0
    cfg.ue_rpc.enabled = False
    # 启用干扰层偏置，验证不破坏 info 键
    cfg.interference.enabled = True
    cfg.interference.mode = "bias"
    cfg.interference.bias_vector = (0.001, -0.001, 0.0)
    env = AirSimMultiDroneParallelEnv(cfg, client=DummyClient())
    env.reset()
    actions = {a: np.zeros((4,), dtype=np.float32) for a in env.agents}
    obs, rews, terms, truncs, infos = env.step(actions)
    for a in env.agents:
        assert "dist_to_goal" in infos[a]
        assert "jammer_power" in infos[a]
        assert isinstance(infos[a]["jammer_power"], float)
        # 干扰层集成后应包含时间戳与原始位置备份
        assert "timestamp" in infos[a]
        assert "pos_raw" in infos[a]
    env.close()