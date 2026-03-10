from __future__ import annotations
"""
结构化训练日志工具：JSON 日志 + 控制台 + 文件轮转 + 队列。

设计要点：
- 性能：使用 QueueHandler/QueueListener 异步写入文件与控制台，降低对训练主循环的影响。
- 结构化：统一输出 JSON，包含时间戳、级别、模块、消息与自定义字段（step、episode、metrics）。
- 轮转：支持 RotatingFileHandler，默认 5MB、保留 3 个备份。
- 开关：通过 LoggingConfig 控制启用、级别、输出渠道。
"""

import json
import logging
import logging.handlers
import os
import queue
import sys
import math
from dataclasses import dataclass
from typing import Any, Dict, Optional
import numpy as np

from airsim_multi_rl.config import LoggingConfig


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        # 合并额外字段
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            payload.update(_to_jsonable(record.extra))
        return json.dumps(_to_jsonable(payload), ensure_ascii=False, separators=(",", ":"))


def _to_jsonable(obj: Any) -> Any:
    """递归转换为 JSON 可序列化的对象。

    - numpy.ndarray -> list
    - numpy 标量 -> Python 标量
    - dict/list/tuple/set -> 递归转换
    - 其他不可序列化对象 -> str(obj)
    - 非有限浮点（NaN/inf）-> 字符串表示，避免 JSON 失败
    """
    if obj is None:
        return None
    if isinstance(obj, (str, bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else str(obj)
    if isinstance(obj, np.ndarray):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return val if math.isfinite(val) else str(val)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    # 带 tolist 的对象优先使用
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        try:
            return obj.tolist()
        except Exception:
            return str(obj)
    # fallback：字符串化避免抛错
    try:
        return str(obj)
    except Exception:
        return "<unserializable>"


def _to_db(value: float, ref: float = 1.0, eps: float = 1e-12) -> float:
    """将功率值转换为 dB（相对参考值）。

    说明：
    - 避免 log(0) 导致的负无穷，加入 eps。
    - 默认参考值为 1.0；若使用 dBm 等单位需在上层做单位换算。
    """
    try:
        v = float(value)
        r = float(ref) if ref != 0.0 else 1.0
        base = (v / r) + float(eps)
        return float(10.0 * math.log10(base))
    except Exception:
        return float(0.0)


@dataclass
class RLLogger:
    cfg: LoggingConfig
    logger: logging.Logger
    q: Optional[queue.Queue]
    listener: Optional[logging.handlers.QueueListener]

    @classmethod
    def create(cls, cfg: LoggingConfig) -> "RLLogger":
        logger = logging.getLogger("rl.train")
        logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
        logger.propagate = False

        fmt = JsonFormatter()
        handlers = []

        # 控制台输出
        if cfg.console:
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
            sh.setFormatter(fmt)
            handlers.append(sh)

        # 文件轮转
        if cfg.file:
            os.makedirs(os.path.dirname(cfg.file_path), exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(
                cfg.file_path, maxBytes=int(cfg.max_bytes), backupCount=int(cfg.backup_count), encoding="utf-8"
            )
            fh.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))
            fh.setFormatter(fmt)
            handlers.append(fh)

        q: Optional[queue.Queue] = None
        listener: Optional[logging.handlers.QueueListener] = None
        if cfg.queue:
            q = queue.Queue(-1)
            # 将所有处理器交由监听器驱动
            listener = logging.handlers.QueueListener(q, *handlers, respect_handler_level=True)
            listener.start()
            qh = logging.handlers.QueueHandler(q)
            logger.addHandler(qh)
        else:
            for h in handlers:
                logger.addHandler(h)

        return cls(cfg=cfg, logger=logger, q=q, listener=listener)

    def shutdown(self):
        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            pass

    # 便捷方法：统一结构化字段
    def log(self, level: str, msg: str, **fields: Any):
        if not self.cfg.enabled:
            return
        lvl = getattr(logging, level.upper(), logging.INFO)
        extra = {"extra": fields}
        self.logger.log(lvl, msg, extra=extra)

    # 语义化封装
    def episode_start(self, episode: int, **kwargs: Any):
        self.log("INFO", "episode_start", episode=episode, **kwargs)

    def episode_end(self, episode: int, reward_sum: float, **kwargs: Any):
        self.log("INFO", "episode_end", episode=episode, reward_sum=reward_sum, **kwargs)

    def step_before(self, episode: int, step: int, obs: Dict[str, Any], **kwargs: Any):
        self.log("DEBUG", "step_before", episode=episode, step=step, obs=obs, **kwargs)

    def step_after(self, episode: int, step: int, actions: Dict[str, Any], reward: Dict[str, float], info: Dict[str, Any], **kwargs: Any):
        # 关键指标高亮：允许在 JSON 中标注字段，如 metrics={"loss":...,"lr":...}
        self.log("INFO", "step_after", episode=episode, step=step, actions=actions, reward=reward, info=info, **kwargs)

    def policy_update(self, episode: int, step: int, metrics: Dict[str, Any]):
        self.log("INFO", "policy_update", episode=episode, step=step, metrics=metrics)

    def interference(self, episode: Optional[int], step: int, strength: float, kind: str, unit: str, **kwargs: Any):
        """记录干扰强度日志（结构化 JSON）。

        Args:
            episode: 回合编号（可选，env 内部可传 None）。
            step: 步编号。
            strength: 干扰强度（已按 unit 标准化，如 dB 或米）。
            kind: 干扰类型（"power" 或 "distance"）。
            unit: 度量单位（如 "dB" 或 "meter"）。
            **kwargs: 额外字段（如 agent/raw_strength/raw_unit）。

        设计：
        - 消息前缀固定为 "[INTERFERENCE]"，便于后续筛选。
        - 保持与现有 JSON 格式一致（ts/level/name/msg + extra）。
        - 通过队列异步写入，降低性能影响。
        """
        self.log(
            "INFO",
            "[INTERFERENCE]",
            episode=episode,
            step=step,
            strength=strength,
            kind=kind,
            unit=unit,
            **kwargs,
        )