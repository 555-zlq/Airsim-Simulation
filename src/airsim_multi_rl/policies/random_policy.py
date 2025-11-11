from __future__ import annotations
import numpy as np

class RandomPolicy:
    """随机策略占位：按动作空间采样动作。

    用于快速验证 env 接口，非训练用途。
    """

    def act(self, space) -> np.ndarray:
        return space.sample()