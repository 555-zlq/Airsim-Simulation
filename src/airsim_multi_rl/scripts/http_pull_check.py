from __future__ import annotations
"""
WSL 拉取式 UE HTTP 自检脚本。

功能：
- 访问 Windows 上 UE 的 Jammer REST 服务（/ping, /jammers, /jammer_power）
- 统计响应耗时，验证数据字段与单位
- 可与项目配置一致运行（使用 UERPCConfig 字段）

用法：
  PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check \
    --base http://<WIN_HOST_IP>:8080 --name BP_Jammer_Actor --x 10 --y 0 --z 0

若未提供 --base，将尝试自动探测 Windows 主机 IP 并拼接为 http://<IP>:8080。
"""

import argparse
import os
import time
import json
import subprocess
import sys
from typing import Optional

import requests


def _detect_win_host_ip() -> Optional[str]:
    """在 WSL 内自动探测 Windows 主机可达 IP（默认网关）。"""
    try:
        out = subprocess.check_output(
            "ip route | awk '/default/ {print $3}'",
            shell=True,
            text=True,
        ).strip()
        return out or None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="UE HTTP 拉取式自检")
    parser.add_argument("--base", type=str, default="", help="UE HTTP 基地址，如 http://<WIN_HOST_IP>:8080")
    parser.add_argument("--timeout", type=float, default=0.5, help="HTTP 超时（秒）")
    parser.add_argument("--name", type=str, default="BP_Jammer_Actor", help="用于功率查询的 Jammer 名称")
    parser.add_argument("--x", type=float, default=10.0, help="查询位置 X（米）")
    parser.add_argument("--y", type=float, default=0.0, help="查询位置 Y（米）")
    parser.add_argument("--z", type=float, default=0.0, help="查询位置 Z（米）")
    parser.add_argument("--cm_per_m", type=float, default=100.0, help="单位换算：1m = cm_per_m cm")
    args = parser.parse_args()

    base = args.base
    if not base:
        ip = os.environ.get("WIN_HOST_IP") or _detect_win_host_ip()
        if not ip:
            print("[Error] 无法探测 Windows 主机 IP，请使用 --base 指定，例如 http://172.26.48.1:8080")
            sys.exit(2)
        base = f"http://{ip}:8080"

    print(f"[Config] base={base} timeout={args.timeout}s cm_per_m={args.cm_per_m}")

    # 1) /ping
    t0 = time.perf_counter()
    r = requests.get(f"{base}/ping", timeout=args.timeout)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        r.raise_for_status()
        data = r.json()
        print(f"[Ping] ok latency_ms={latency_ms} data={data}")
    except Exception as e:
        print(f"[Ping] fail latency_ms={latency_ms} err={e}")
        sys.exit(1)

    # 2) /jammers
    t0 = time.perf_counter()
    r = requests.get(f"{base}/jammers", timeout=args.timeout)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    try:
        r.raise_for_status()
        jammers = r.json().get("jammers", [])
        print(f"[Jammers] ok latency_ms={latency_ms} count={len(jammers)}")
        if jammers:
            print("[Jammers] sample=", json.dumps(jammers[:1], ensure_ascii=False))
    except Exception as e:
        print(f"[Jammers] fail latency_ms={latency_ms} err={e}")
        sys.exit(1)

    # 3) /jammer_power 按位置查询（米→厘米转换由 UE 端负责或此处传米即可，若 UE 端要求 cm 可按需乘以 cm_per_m）
    # 依据指南，GET 支持 x/y/z 为 cm；这里提供两个调用：米直接传入、或转换为 cm 传入。
    # 优先尝试直接传米；若返回 0 或 error，可切换 cm 调用。

    name = args.name
    x_m, y_m, z_m = args.x, args.y, args.z

    # 3.1 直接传米（部分实现允许）
    t0 = time.perf_counter()
    r = requests.get(
        f"{base}/jammer_power",
        params={"name": name, "x": x_m, "y": y_m, "z": z_m},
        timeout=args.timeout,
    )
    lat1 = int((time.perf_counter() - t0) * 1000)
    ok1, power1 = False, 0.0
    try:
        r.raise_for_status()
        data = r.json()
        if "error" not in data:
            ok1 = True
            power1 = float(data.get("power", 0.0))
        print(f"[Power/m] ok={ok1} latency_ms={lat1} name={name} power={power1}")
    except Exception as e:
        print(f"[Power/m] fail latency_ms={lat1} err={e}")

    # 3.2 传厘米
    x_cm, y_cm, z_cm = x_m * args.cm_per_m, y_m * args.cm_per_m, z_m * args.cm_per_m
    t0 = time.perf_counter()
    r = requests.get(
        f"{base}/jammer_power",
        params={"name": name, "x": x_cm, "y": y_cm, "z": z_cm},
        timeout=args.timeout,
    )
    lat2 = int((time.perf_counter() - t0) * 1000)
    ok2, power2 = False, 0.0
    try:
        r.raise_for_status()
        data = r.json()
        if "error" not in data:
            ok2 = True
            power2 = float(data.get("power", 0.0))
        print(f"[Power/cm] ok={ok2} latency_ms={lat2} name={name} power={power2}")
    except Exception as e:
        print(f"[Power/cm] fail latency_ms={lat2} err={e}")

    # 成功判定：至少有一种方式返回非错误 JSON，且可提取 power 字段
    if not (ok1 or ok2):
        print("[Result] 失败：/jammer_power 未返回有效功率（请检查名称拼写、IsJamming、单位 cm/m）")
        sys.exit(1)

    print("[Result] 成功：拉取式自检通过。建议在 config/default.yaml 设置 ue_rpc.http_base 并开启 power 模式进行端到端测试。")


if __name__ == "__main__":
    main()