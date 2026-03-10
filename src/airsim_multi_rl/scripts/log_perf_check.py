from __future__ import annotations

"""
干扰日志性能微基准脚本：评估每次日志调用的平均开销。

说明：
- 使用 RLLogger 的异步队列写入（QueueHandler/QueueListener），测量主循环调用开销。
- 默认同时测试 power(dB) 与 distance(meter) 两种干扰日志。
- 输出总耗时与每次调用的平均耗时，评估是否满足性能要求。

使用：
    PYTHONPATH=src python -m airsim_multi_rl.scripts.log_perf_check --n 10000
    # 指定模式：power 或 distance 或 both
    PYTHONPATH=src python -m airsim_multi_rl.scripts.log_perf_check --n 15000 --mode power
"""

import argparse
import time
from typing import Literal

from airsim_multi_rl.config import EnvConfig
from airsim_multi_rl.utils.logging import RLLogger, _to_db


def run_once(n: int, mode: Literal["power", "distance"]) -> float:
    """运行一次指定模式的日志压测，返回总耗时秒。

    参数：
    - n：日志次数
    - mode："power" 或 "distance"
    """
    cfg = EnvConfig()
    # 将日志写入性能专用文件，避免污染训练日志
    cfg.logging.file_path = "logs/log_perf.log"
    cfg.logging.enabled = True
    cfg.logging.queue = True  # 强制启用队列，符合性能要求
    cfg.logging.level = "INFO"
    logger = RLLogger.create(cfg.logging)

    t0 = time.perf_counter()
    if mode == "power":
        # 记录 n 次 dB 干扰日志（模拟不同强度）
        for i in range(1, n + 1):
            raw_p = 0.1 + 0.01 * (i % 10)  # 模拟功率值
            logger.interference(
                episode=None,
                step=i,
                strength=_to_db(raw_p),
                kind="power",
                unit="dB",
                phase="perf",
                agent="Perf",
                raw_strength=raw_p,
                raw_unit="power",
            )
    else:
        # 记录 n 次距离干扰日志
        for i in range(1, n + 1):
            d = 1.0 + 0.05 * (i % 20)
            logger.interference(
                episode=None,
                step=i,
                strength=d,
                kind="distance",
                unit="meter",
                phase="perf",
                agent="Perf",
                raw_strength=d,
                raw_unit="meter",
            )
    total = time.perf_counter() - t0
    # 停止监听器，确保写入完成
    logger.shutdown()
    return float(total)


def main():
    parser = argparse.ArgumentParser(description="干扰日志性能微基准")
    parser.add_argument("--n", type=int, default=10000, help="日志次数（默认 10000）")
    parser.add_argument("--mode", type=str, default="both", choices=["power", "distance", "both"], help="测试模式")
    args = parser.parse_args()

    if args.mode == "both":
        total_p = run_once(args.n, "power")
        total_d = run_once(args.n, "distance")
        print(f"power: {args.n} logs, total={total_p:.3f}s, avg={total_p/args.n*1000:.3f} ms/log")
        print(f"distance: {args.n} logs, total={total_d:.3f}s, avg={total_d/args.n*1000:.3f} ms/log")
    else:
        total = run_once(args.n, args.mode)  # type: ignore[arg-type]
        print(f"{args.mode}: {args.n} logs, total={total:.3f}s, avg={total/args.n*1000:.3f} ms/log")


if __name__ == "__main__":
    main()