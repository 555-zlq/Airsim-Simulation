from __future__ import annotations
from typing import Tuple

class TerminationChecker:
    """终止/截断判定模块。"""

    def __init__(self, max_steps: int):
        self.max_steps = int(max_steps)

    def done_trunc(self, steps: int, collided: bool, oob: bool, reached: bool) -> Tuple[bool, bool]:
        done = bool(collided or oob or reached)
        trunc = bool(steps >= self.max_steps)
        return done, trunc