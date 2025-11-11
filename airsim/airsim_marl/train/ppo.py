# airsim_marl/train/ppo.py
from __future__ import annotations
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal

class ActorCritic(nn.Module):
    def __init__(self, obs_dim: int, act_dim: int, hidden=128):
        super().__init__()
        self.pi = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, act_dim)
        )
        self.v  = nn.Sequential(
            nn.Linear(obs_dim, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden), nn.Tanh(),
            nn.Linear(hidden, 1)
        )
        self.log_std = nn.Parameter(torch.zeros(act_dim))

    def forward(self, x):
        raise NotImplementedError

    def value(self, x):
        return self.v(x).squeeze(-1)

    def policy(self, x):
        mean = self.pi(x)
        std = torch.exp(self.log_std)
        return Normal(mean, std)

def ppo_update(model: ActorCritic, optimizer, data_iter, clip_ratio=0.2, vf_coef=0.5, ent_coef=0.0, max_grad_norm=0.5, epochs=8, device="cpu"):
    for _ in range(epochs):
        for obs, acts, rets, advs, old_logps in data_iter():
            obs = torch.as_tensor(obs, dtype=torch.float32, device=device)
            acts = torch.as_tensor(acts, dtype=torch.float32, device=device)
            rets = torch.as_tensor(rets, dtype=torch.float32, device=device)
            advs = torch.as_tensor(advs, dtype=torch.float32, device=device)
            old_logps = torch.as_tensor(old_logps, dtype=torch.float32, device=device)

            dist = model.policy(obs)
            logps = dist.log_prob(acts).sum(-1)
            ratio = torch.exp(logps - old_logps)
            advs_norm = (advs - advs.mean()) / (advs.std() + 1e-8)
            clip_adv = torch.clamp(ratio, 1.0 - clip_ratio, 1.0 + clip_ratio) * advs_norm
            pg_loss = -(torch.min(ratio * advs_norm, clip_adv)).mean()

            v = model.value(obs)
            v_loss = F.mse_loss(v, rets)

            ent = dist.entropy().sum(-1).mean()

            loss = pg_loss + vf_coef * v_loss - ent_coef * ent

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
