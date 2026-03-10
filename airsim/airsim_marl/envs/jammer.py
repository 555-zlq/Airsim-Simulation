from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import math
import time
import numpy as np

from ..sim.world import World
from ..utils import np_norm


@dataclass
class JammerState:
    name: str
    pos: np.ndarray
    yaw_deg: float = 0.0
    pitch_deg: float = 0.0
    active_freq_hz: Optional[float] = None
    is_locked: bool = False
    last_update_s: float = 0.0


class CommJammerModel:
    def __init__(self, world: World, cfg):
        self.world = world
        self.cfg = cfg
        self.jammers: Dict[str, JammerState] = {}
        self._init_from_world()

    def _init_from_world(self):
        self.world.refresh_jammers()
        now = time.time()
        for name, pos in self.world.jammer_positions.items():
            self.jammers[name] = JammerState(name=name, pos=pos, last_update_s=now)

    def _desired_angles(self, jam: JammerState, target_pos: np.ndarray) -> Tuple[float, float]:
        vec = target_pos - jam.pos
        # 计算世界系下的 yaw/pitch 指向角
        yaw = math.degrees(math.atan2(vec[1], vec[0]))
        dist_xy = math.hypot(vec[0], vec[1])
        pitch = math.degrees(math.atan2(-vec[2], dist_xy))
        return yaw, pitch

    def _slew(self, cur: float, des: float, rate_deg_s: float, dt_s: float) -> float:
        delta = (des - cur + 180.0) % 360.0 - 180.0
        max_step = rate_deg_s * dt_s
        if abs(delta) <= max_step:
            return des
        return (cur + math.copysign(max_step, delta)) % 360.0

    def update_pointing(self, target_name: str, target_pos: np.ndarray, dt_s: float, detected_freq_hz: Optional[float]):
        # 为单目标更新所有 jammer 指向（简单模式：所有 jammer 追踪同一目标）
        for jam in self.jammers.values():
            des_yaw, des_pitch = self._desired_angles(jam, target_pos)
            jam.yaw_deg = self._slew(jam.yaw_deg, des_yaw, self.cfg.jammer_servo_slew_deg_per_s, dt_s)
            jam.pitch_deg = self._slew(jam.pitch_deg, des_pitch, self.cfg.jammer_servo_slew_deg_per_s, dt_s)
            jam.active_freq_hz = detected_freq_hz
            yaw_err = abs(((des_yaw - jam.yaw_deg + 180.0) % 360.0) - 180.0)
            pitch_err = abs(((des_pitch - jam.pitch_deg + 180.0) % 360.0) - 180.0)
            jam.is_locked = (detected_freq_hz is not None) and (yaw_err <= self.cfg.jammer_main_lobe_width_deg/2) and (pitch_err <= self.cfg.jammer_main_lobe_width_deg/2)

    def update_pointing_for_targets(self, assignments: Dict[str, Tuple[np.ndarray, Optional[float]]], dt_s: float):
        # assignments: jammer_name -> (target_pos, detected_freq_hz)
        for name, (target_pos, detected_freq_hz) in assignments.items():
            jam = self.jammers.get(name)
            if jam is None:
                continue
            des_yaw, des_pitch = self._desired_angles(jam, target_pos)
            jam.yaw_deg = self._slew(jam.yaw_deg, des_yaw, self.cfg.jammer_servo_slew_deg_per_s, dt_s)
            jam.pitch_deg = self._slew(jam.pitch_deg, des_pitch, self.cfg.jammer_servo_slew_deg_per_s, dt_s)
            jam.active_freq_hz = detected_freq_hz
            yaw_err = abs(((des_yaw - jam.yaw_deg + 180.0) % 360.0) - 180.0)
            pitch_err = abs(((des_pitch - jam.pitch_deg + 180.0) % 360.0) - 180.0)
            jam.is_locked = (detected_freq_hz is not None) and (yaw_err <= self.cfg.jammer_main_lobe_width_deg/2) and (pitch_err <= self.cfg.jammer_main_lobe_width_deg/2)

    def _antenna_gain_dbi(self, jam: JammerState, target_pos: np.ndarray) -> float:
        vec = target_pos - jam.pos
        # 计算与主瓣方向的夹角
        yaw_des, pitch_des = self._desired_angles(jam, target_pos)
        yaw_err = abs(((yaw_des - jam.yaw_deg + 180.0) % 360.0) - 180.0)
        pitch_err = abs(((pitch_des - jam.pitch_deg + 180.0) % 360.0) - 180.0)
        ang = max(yaw_err, pitch_err)
        if ang <= self.cfg.jammer_main_lobe_width_deg/2:
            # 主瓣近似余弦模型
            p = 4.0
            return float(self.cfg.jammer_gain_max_dbi * (math.cos(math.radians(ang)) ** p))
        else:
            return float(self.cfg.jammer_gain_side_dbi)

    def _path_loss_db(self, d_m: float) -> float:
        # 对数距离损耗模型，n≈2.0（自由空间），d0=1m，L0=0
        n = 2.0
        d0 = 1.0
        if d_m <= d0:
            return 0.0
        return 10.0 * n * math.log10(d_m / d0)

    def jammer_rx_power_dbm(self, target_pos: np.ndarray, freq_hz: float) -> float:
        if not self.jammers:
            return -200.0
        total_linear = 0.0
        for jam in self.jammers.values():
            d = np_norm(target_pos - jam.pos)
            if jam.active_freq_hz is None:
                continue
            # 频域选择性
            if abs(jam.active_freq_hz - freq_hz) > self.cfg.jammer_narrow_bw_hz / 2:
                continue
            gain = self._antenna_gain_dbi(jam, target_pos)
            pl = self._path_loss_db(max(d, 0.1))
            pj_dbm = float(self.cfg.jammer_eirp_dbm + gain - pl)
            total_linear += 10 ** (pj_dbm / 10.0)
        if total_linear <= 0.0:
            return -200.0
        return 10.0 * math.log10(total_linear)

    def sinr_db(self, target_pos: np.ndarray, target_tx_dbm: float, freq_hz: float) -> float:
        # 信号功率（简化：接收端固定增益 + 路损）
        # 这里使用最近无人机-接收端距离为同一位置，若需要真实链路请提供对端位置
        ps_dbm = target_tx_dbm + self.cfg.comm_rx_gain_db - self._path_loss_db(1.0)
        pj_dbm = self.jammer_rx_power_dbm(target_pos, freq_hz)
        noise_dbm = self.cfg.comm_noise_floor_dbm
        # 合并干扰 + 噪声
        i_linear = 10 ** (pj_dbm / 10.0) + 10 ** (noise_dbm / 10.0)
        s_linear = 10 ** (ps_dbm / 10.0)
        if i_linear <= 0:
            return 100.0
        return 10.0 * math.log10(s_linear / i_linear)

    def per_from_sinr(self, sinr_db: float) -> float:
        # 逻辑函数近似：SINR 高则 PER 低
        k = 0.8
        x0 = self.cfg.jammer_target_sinr_db
        return 1.0 / (1.0 + math.exp(k * (sinr_db - x0)))
