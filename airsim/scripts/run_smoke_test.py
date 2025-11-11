# scripts/run_smoke_test.py
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

# --- 路径处理：优先使用新 src 布局下的 airsim_multi_rl 包 ---
# 计算仓库根目录，并将 src 加入 Python 搜索路径，避免工作目录不一致导致的导入失败
repo_root = Path(__file__).resolve().parents[2]
src_dir = repo_root / "src"
if src_dir.exists():
    sys.path.insert(0, str(src_dir))

# 回退：同时保留旧结构（airsim/airsim_marl）的导入能力，兼容历史脚本
try:
    from airsim_multi_rl.envs.multi_drone_parallel import AirSimMultiDroneParallelEnv
    from airsim_multi_rl.config import load_env_config
    USE_NEW = True
except ModuleNotFoundError:
    # 将 airsim 目录加入搜索路径，尝试旧包
    airsim_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(airsim_dir))
    from airsim_marl.envs.multi_drone_env import AirSimMultiDroneParallelEnv  # type: ignore
    from airsim_marl.config import EnvConfig  # type: ignore
    USE_NEW = False

def main():
    # 创建环境配置（新布局使用 YAML 合并，旧布局使用默认 dataclass）
    if USE_NEW:
        cfg = load_env_config(user_yaml_path=None)
    else:
        cfg = EnvConfig()
    env = AirSimMultiDroneParallelEnv(cfg)
    obs, infos = env.reset()
    print("agents:", env.agents)

    for t in range(30):
        actions = {}
        for a in env.agents:
            # small forward velocity on x
            actions[a] = np.array([0.5, 0.0, 0.0, 0.0], dtype=np.float32)
        obs, rew, term, trunc, info = env.step(actions)
        print(f"t={t:02d}  reward_sum={sum(rew.values()):.3f}")
        if all(term.values()) or all(trunc.values()):
            break
    env.close()

if __name__ == "__main__":
    main()
