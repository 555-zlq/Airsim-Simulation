# airsim_marl/train/rollout.py
from __future__ import annotations
import numpy as np
from typing import Dict, List

class MARLRolloutBuffer:
    """Simple on-policy buffer that concatenates steps from all agents into one big batch.
    Assumes shared observation/action spaces across agents."""
    def __init__(self, obs_dim: int, act_dim: int, horizon: int):
        self.obs = np.zeros((horizon, obs_dim), dtype=np.float32)
        self.acts = np.zeros((horizon, act_dim), dtype=np.float32)
        self.rets = np.zeros((horizon,), dtype=np.float32)
        self.rews = np.zeros((horizon,), dtype=np.float32)
        self.vals = np.zeros((horizon,), dtype=np.float32)
        self.logps = np.zeros((horizon,), dtype=np.float32)
        self.advs = np.zeros((horizon,), dtype=np.float32)
        self.dones = np.zeros((horizon,), dtype=np.float32)
        self.ptr = 0
        self.max = horizon

    def add(self, o, a, r, v, logp, done):
        if self.ptr >= self.max: return False
        self.obs[self.ptr] = o
        self.acts[self.ptr] = a
        self.rews[self.ptr] = r
        self.vals[self.ptr] = v
        self.logps[self.ptr] = logp
        self.dones[self.ptr] = float(done)
        self.ptr += 1
        return True

    def compute_returns_advantages(self, gamma=0.99, lam=0.95, last_val=0.0):
        # GAE-Lambda with episode boundaries indicated by done flags
        adv = 0.0
        for t in reversed(range(self.ptr)):
            next_nonterminal = 1.0 - self.dones[t]
            delta = self.rews[t] + gamma * next_nonterminal * (self.vals[t+1] if t+1 < self.ptr else last_val) - self.vals[t]
            adv = delta + gamma * lam * next_nonterminal * adv
            self.advs[t] = adv
            self.rets[t] = self.advs[t] + self.vals[t]

    def get(self, minibatch=1024):
        idxs = np.random.permutation(self.ptr)
        for start in range(0, self.ptr, minibatch):
            mb = idxs[start:start+minibatch]
            yield (self.obs[mb], self.acts[mb], self.rets[mb], self.advs[mb], self.logps[mb])
