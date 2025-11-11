from __future__ import annotations
import os
import numpy as np
from airsim_multi_rl.config import load_env_config
from airsim_multi_rl.envs.multi_drone_parallel import AirSimMultiDroneParallelEnv
from airsim_multi_rl.envs.dummy_client import DummyClient

def main():
    # 读取默认配置（可通过环境变量 SMOKE_YAML 指定用户 YAML）
    user_yaml = os.environ.get("SMOKE_YAML")
    cfg = load_env_config(user_yaml_path=user_yaml)

    # 如果设置环境变量 SMOKE_OFFLINE=1，则使用 DummyClient 离线模拟
    offline = os.environ.get("SMOKE_OFFLINE") == "1"
    client = DummyClient(cfg.agent_names) if offline else None
    env = AirSimMultiDroneParallelEnv(cfg, client=client)
    obs, infos = env.reset()
    print("agents:", env.agents)

    for t in range(30):
        actions = {}
        for a in env.agents:
            actions[a] = np.array([0.5, 0.0, 0.0, 0.0], dtype=np.float32)
        obs, rew, term, trunc, info = env.step(actions)
        print(f"t={t:02d}  reward_sum={sum(rew.values()):.3f}")
        if all(term.values()) or all(trunc.values()):
            break
    env.close()

if __name__ == "__main__":
    main()