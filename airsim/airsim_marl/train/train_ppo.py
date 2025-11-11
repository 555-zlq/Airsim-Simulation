# airsim_marl/train/train_ppo.py
from __future__ import annotations
import numpy as np
import torch
import torch.optim as optim

from ..config import EnvConfig, PPOConfig
from ..envs.multi_drone_env import AirSimMultiDroneParallelEnv
from .rollout import MARLRolloutBuffer
from .ppo import ActorCritic, ppo_update

def main():
    env_cfg = EnvConfig()
    env = AirSimMultiDroneParallelEnv(env_cfg)

    # shared policy across agents
    obs_dim = env.observation_space(env.agents[0]).shape[0]
    act_dim = env.action_space(env.agents[0]).shape[0]

    ppo_cfg = PPOConfig()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ActorCritic(obs_dim, act_dim, hidden=128).to(device)
    optimiz = optim.Adam(model.parameters(), lr=ppo_cfg.lr)

    rng = np.random.default_rng(ppo_cfg.seed)
    total_steps = 0

    while total_steps < ppo_cfg.total_steps:
        buf = MARLRolloutBuffer(obs_dim, act_dim, ppo_cfg.rollout_horizon * len(env.agents))

        obs, infos = env.reset()
        done_flags = {a: False for a in env.agents}

        # Collect
        while buf.ptr < buf.max:
            # per-agent action
            acts = {}
            for a in env.agents:
                if done_flags[a]:
                    # dummy no-op if already done
                    acts[a] = np.zeros(act_dim, dtype=np.float32)
                    continue
                o = obs[a]
                with torch.no_grad():
                    dist = model.policy(torch.as_tensor(o, dtype=torch.float32, device=device).unsqueeze(0))
                    action = dist.sample()[0].cpu().numpy()
                    logp = dist.log_prob(torch.as_tensor(action, dtype=torch.float32, device=device)).sum(-1).cpu().item()
                    v = model.value(torch.as_tensor(o, dtype=torch.float32, device=device).unsqueeze(0)).cpu().item()
                acts[a] = action.astype(np.float32)
                # temporarily stash for buffer after env.step: store per-agent tuples
                obs[a] = (o, action, logp, v)

            next_obs, rews, terms, truncs, infos = env.step({a: (obs[a][1] if isinstance(obs[a], tuple) else acts[a]) for a in env.agents})

            # write to buffer
            for a in env.agents:
                o, act, logp, v = obs[a] if isinstance(obs[a], tuple) else (next_obs[a], acts[a], 0.0, 0.0)
                r = rews[a]
                done = terms[a] or truncs[a]
                buf.add(o, act, r, v, logp, done)
                done_flags[a] = done

            obs = next_obs
            total_steps += len(env.agents)

            if all(done_flags.values()):
                # reset to continue filling rollout
                obs, infos = env.reset()
                done_flags = {a: False for a in env.agents}

        # GAE and update
        buf.compute_returns_advantages(gamma=ppo_cfg.gamma, lam=ppo_cfg.gae_lambda, last_val=0.0)
        def data_iter():
            return buf.get(minibatch=ppo_cfg.minibatch_size)
        ppo_update(model, optimiz, data_iter, clip_ratio=ppo_cfg.clip_ratio,
                   vf_coef=ppo_cfg.vf_coef, ent_coef=ppo_cfg.ent_coef,
                   max_grad_norm=ppo_cfg.max_grad_norm, epochs=ppo_cfg.update_epochs, device=device)

        print(f"Trained on {total_steps} steps so far.")

    env.close()

if __name__ == "__main__":
    main()
