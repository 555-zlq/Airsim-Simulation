from __future__ import annotations
"""
轻量训练/rollout 入口：与并行环境对接，集成结构化日志。

支持：
- 每个 episode 开始/结束日志
- 每步前后日志（obs/actions/reward/info）
- 策略更新日志（学习率、loss 等）
"""

from typing import Dict, Optional
import numpy as np

from airsim_multi_rl.config import EnvConfig, load_env_config
from airsim_multi_rl.envs.multi_drone_parallel import AirSimMultiDroneParallelEnv
from airsim_multi_rl.policies.random_policy import RandomPolicy
from airsim_multi_rl.utils.logging import RLLogger
from airsim_multi_rl.utils.logging import _to_db


def run_rollout(cfg: Optional[EnvConfig] = None, episodes: int = 3, steps_per_ep: int = 50):
    cfg = cfg or load_env_config()
    # 初始化结构化日志
    logger = RLLogger.create(cfg.logging)
    env = AirSimMultiDroneParallelEnv(cfg)
    policy = RandomPolicy()

    try:
        for ep in range(1, episodes + 1):
            logger.episode_start(ep)
            obs, infos = env.reset()
            rew_sum: Dict[str, float] = {a: 0.0 for a in env.agents}
            for step in range(1, steps_per_ep + 1):
                # 记录步前观测
                logger.step_before(ep, step, obs=obs)
                # 记录干扰强度（标准化单位）：
                # - 功率模式：将最近干扰功率转为 dB
                # - 距离模式：记录最近干扰距离（米）
                kind = "power" if env.cfg.jammer_penalty_mode == "power" else "distance"
                # 从 infos 中读取每个智能体对应的干扰数据（在 step 之后也会记录）
                # 这里在步前阶段，无法获取 power；如为 power 模式，先记录上一步或 0 占位
                if kind == "power":
                    for a in env.agents:
                        # 占位强度（dB）：0 映射到极小正数避免 -inf
                        logger.interference(
                            episode=ep,
                            step=step,
                            strength=_to_db(0.0),
                            kind=kind,
                            unit="dB",
                            phase="before",
                            agent=a,
                            raw_strength=0.0,
                            raw_unit="power",
                        )
                else:
                    for a in env.agents:
                        # 距离模式在步前阶段不可直接访问 jam_vec，这里记录 0 占位
                        logger.interference(
                            episode=ep,
                            step=step,
                            strength=0.0,
                            kind=kind,
                            unit="meter",
                            phase="before",
                            agent=a,
                            raw_strength=0.0,
                            raw_unit="meter",
                        )
                actions = {a: policy.act(env.action_space(a)) for a in env.agents}
                obs, rews, terms, truncs, infos = env.step(actions)
                # 汇总回合奖励
                for a in env.agents:
                    rew_sum[a] += float(rews[a])
                # 记录步后数据
                logger.step_after(ep, step, actions=actions, reward=rews, info=infos)
                # 步后：记录真实干扰强度（结构化）
                if kind == "power":
                    for a in env.agents:
                        raw_p = float(infos[a].get("jammer_power", 0.0))
                        logger.interference(
                            episode=ep,
                            step=step,
                            strength=_to_db(raw_p),
                            kind=kind,
                            unit="dB",
                            phase="after",
                            agent=a,
                            raw_strength=raw_p,
                            raw_unit="power",
                        )
                else:
                    for a in env.agents:
                        d = float(infos[a].get("nearest_jammer_dist", 0.0))
                        logger.interference(
                            episode=ep,
                            step=step,
                            strength=d,
                            kind=kind,
                            unit="meter",
                            phase="after",
                            agent=a,
                            raw_strength=d,
                            raw_unit="meter",
                        )
                # 简单策略更新示例：记录学习率（占位）
                lr = 3e-4
                metrics = {"lr": lr, "loss": 0.0}
                logger.policy_update(ep, step, metrics)
                # 终止处理
                if all(terms[a] or truncs[a] for a in env.agents):
                    break
            # 记录 episode 结束
            logger.episode_end(ep, reward_sum=float(sum(rew_sum.values())))
    finally:
        logger.shutdown()
        env.close()