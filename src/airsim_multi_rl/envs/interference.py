"""
干扰层模块：在观测生成之后，对位置相关分量进行可控扰动。

遵循项目规则：
- 单一职责：仅在观测层对位置 pos(x,y,z) 进行偏移，不改变环境真实状态与动作。
- 配置驱动：从 EnvConfig.interference 读取参数，支持高斯噪声与固定偏置。
- 性能：偏移计算为 O(1)，延迟小于 5ms。
- 精度：偏移结果保留 4 位小数（可配置）。
- 鲁棒：异常输入（NaN/无效长度）时安全降级为原值。

接口设计：
- InterferenceLayer.apply(obs: np.ndarray, strength: float | None) -> np.ndarray
  输入：obs 为 17 维向量，位置在前 3 维；strength 为干扰强度（可选），由 jamming 查询层提供。
  输出：仅修改 obs[0:3] 三个分量，其他分量保持不变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import math
import numpy as np

from airsim_multi_rl.config import InterferenceConfig
from airsim_multi_rl.utils import clip


@dataclass
class InterferenceLayer:
    """干扰层实现。

    Attributes:
        cfg: 干扰配置对象。
        rng: 随机数生成器（高斯模式使用）。
    """

    cfg: InterferenceConfig
    rng: np.random.Generator

    @classmethod
    def from_config(cls, cfg: InterferenceConfig) -> "InterferenceLayer":
        seed = cfg.seed if cfg.seed is not None else np.random.SeedSequence().entropy
        rng = np.random.default_rng(seed)
        return cls(cfg=cfg, rng=rng)

    def _gaussian_offset(self, strength: Optional[float]) -> np.ndarray:
        """生成高斯噪声偏移量。

        Args:
            strength: 干扰强度（可选），若提供则作为 sigma 的放大系数（sqrt 归一）。

        Returns:
            形如 (dx, dy, dz) 的 numpy 向量。
        """
        sigma = float(self.cfg.gaussian_sigma)
        # 将强度映射到尺度：sqrt 放缩，避免过大幅度；确保非负
        if strength is not None and math.isfinite(strength):
            scale = math.sqrt(max(0.0, strength))
            sigma *= clip(scale, 0.0, 10.0)
        offset = self.rng.normal(loc=0.0, scale=sigma, size=(3,))
        return offset

    def _bias_offset(self, strength: Optional[float]) -> np.ndarray:
        """固定偏置模式：可按强度比例缩放。"""
        bx, by, bz = self.cfg.bias_vector
        vec = np.array([bx, by, bz], dtype=np.float32)
        if strength is not None and math.isfinite(strength):
            vec = vec * float(strength)
        return vec

    def _round_precision(self, vec: np.ndarray) -> np.ndarray:
        """按配置精度四舍五入。"""
        p = int(self.cfg.precision)
        # 使用 np.round 保留小数位，并确保 dtype 一致
        return np.round(vec, decimals=p, out=np.empty_like(vec))

    def apply(self, obs: np.ndarray, strength: Optional[float] = None) -> np.ndarray:
        """对观测中的位置分量施加干扰。

        Args:
            obs: 原始观测（期望长度>=3）。
            strength: 干扰强度（例如 `nearest_power` 或距离映射）。

        Returns:
            新的观测副本，仅修改前 3 个分量位置。
        """
        # 鲁棒性：空或长度不足时直接返回原值（复制，避免外部共享引用被误改）
        if obs is None or len(obs) < 3:
            return obs.copy() if isinstance(obs, np.ndarray) else np.array(obs, dtype=np.float32)

        # 仅在启用时生效
        if not self.cfg.enabled:
            return obs.copy()

        mode = (self.cfg.mode or "gaussian").lower()
        try:
            if mode == "gaussian":
                delta = self._gaussian_offset(strength)
            elif mode == "bias":
                delta = self._bias_offset(strength)
            else:
                # 未知模式：安全降级为无偏移
                delta = np.zeros(3, dtype=np.float32)

            delta = self._round_precision(delta).astype(np.float32)

            new_obs = obs.copy()
            # 仅修改位置分量
            new_obs[0:3] = new_obs[0:3] + delta
            return new_obs
        except Exception:
            # 异常降级：返回原值副本，避免训练中断
            return obs.copy()