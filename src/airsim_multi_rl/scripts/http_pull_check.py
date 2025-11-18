from __future__ import annotations
"""
WSL 拉取式 UE HTTP 自检脚本。

功能：
- 访问 Windows 上 UE 的 Jammer REST 服务（/ping, /jammers, /jammer_power）
- 统计响应耗时，验证数据字段与单位
- 可与项目配置一致运行（使用 UERPCConfig 字段）

用法：
  PYTHONPATH=src python -m airsim_multi_rl.scripts.http_pull_check \
    --base http://<WIN_HOST_IP>:18080 --name BP_Jammer_Actor --x 10 --y 0 --z 0

若未提供 --base，将尝试自动探测 Windows 主机 IP 并拼接为 http://<IP>:18080。
若提供的 --name 未在 /jammers 列表中，脚本将自动回退为列表中的第一个名称并提示。
此外支持 `--names a,b,c` 传入多个名称，脚本会逐一测试并输出每个名称的功率查询结果。
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
    """在 WSL 内自动探测 Windows 主机可达 IP。

    策略：
    1) 优先选择 `ip route` 中 **默认路由**且设备为 `eth*|ens*|enp*|wsl*` 的网关地址；
       排除 `docker0/br-*/veth/lo` 等虚拟网桥，避免误拿 `172.17.0.1`。
    2) 若未找到，回退到 `/etc/resolv.conf` 中的 `nameserver`（部分 WSL 版本中即为宿主机 NAT IP）。
    """
    # 1) 解析 ip route，优先筛选真实网卡默认路由
    try:
        out = subprocess.check_output("ip route", shell=True, text=True)
        gw_candidate: Optional[str] = None
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("default"):
                continue
            parts = line.split()
            # 期望格式：default via <GW> dev <DEV>
            if len(parts) >= 5:
                via = parts[2]
                dev = parts[4]
                # 排除 docker/bridge/veth/lo 虚拟设备
                bad = (dev.startswith("docker") or dev.startswith("br-") or dev.startswith("veth") or dev == "lo")
                good = (dev.startswith("eth") or dev.startswith("ens") or dev.startswith("enp") or dev.startswith("wsl"))
                if good and not bad:
                    gw_candidate = via
                    break
        # 若未匹配设备，退回到首个 default via
        if not gw_candidate:
            for line in out.splitlines():
                line = line.strip()
                if not line.startswith("default"):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    gw_candidate = parts[2]
                    break
        if gw_candidate:
            return gw_candidate
    except Exception:
        pass

    # 2) 回退：从 resolv.conf 读取 nameserver
    try:
        ns = subprocess.check_output(
            "grep -m1 '^nameserver' /etc/resolv.conf | awk '{print $2}'",
            shell=True,
            text=True,
        ).strip()
        return ns or None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="UE HTTP 拉取式自检")
    parser.add_argument("--base", type=str, default="", help="UE HTTP 基地址，如 http://<WIN_HOST_IP>:18080")
    parser.add_argument("--port", type=int, default=18080, help="当未提供 --base 时使用的端口")
    parser.add_argument("--timeout", type=float, default=0.5, help="HTTP 超时（秒）")
    parser.add_argument("--name", type=str, default="BP_Jammer_Actor", help="用于功率查询的 Jammer 名称（若未在 /jammers 列表中也会直接尝试查询）")
    parser.add_argument("--names", type=str, default="", help="逗号分隔的 Jammer 名称列表，如 A,B,C")
    parser.add_argument("--x", type=float, default=10.0, help="查询位置 X（米）")
    parser.add_argument("--y", type=float, default=0.0, help="查询位置 Y（米）")
    parser.add_argument("--z", type=float, default=0.0, help="查询位置 Z（米）")
    parser.add_argument("--cm_per_m", type=float, default=100.0, help="单位换算：1m = cm_per_m cm")
    args = parser.parse_args()

    base = args.base
    if not base:
        ip = os.environ.get("WIN_HOST_IP") or _detect_win_host_ip()
        if not ip:
            print(f"[Error] 无法探测 Windows 主机 IP，请使用 --base 指定，例如 http://172.26.48.1:{args.port}")
            sys.exit(2)
        base = f"http://{ip}:{args.port}"

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
        # 记录所有返回的 Jammer 名称集合（用于规范化匹配与提示）
        names = [j.get("name") for j in jammers if isinstance(j, dict) and j.get("name")]
    except Exception as e:
        print(f"[Jammers] fail latency_ms={latency_ms} err={e}")
        sys.exit(1)

    # 3) /jammer_power 按位置查询（支持多名称循环测试）
    # 依据指南，GET 支持 x/y/z 为 cm；这里提供两个调用：米直接传入、或转换为 cm 传入。
    # 优先尝试直接传米；若返回 0 或 error，可切换 cm 调用。

    # 解析待测试名称列表
    names = [j.get("name") for j in jammers if isinstance(j, dict) and j.get("name")]
    target_names = [s.strip() for s in args.names.split(",") if s.strip()] if args.names else [args.name]

    def _normalize(s: str) -> str:
        # 名称规范化：统一小写并移除下划线，兼容 BP_JammerActor_2 vs BP_JammerActor2
        return s.lower().replace("_", "")

    def _candidate_list(desired: str, pool: list[str]) -> list[str]:
        """为给定期望名称构造尝试列表。

        逻辑：
        1) 首先直接使用用户传入的名称（即使不在 /jammers 返回中也尝试）。
        2) 如在返回列表中存在规范化等价名（移除下划线、忽略大小写），加入该等价名。
        3) 如返回列表非空，加入列表首个名称作为最终回退。
        """
        tries: list[str] = []
        # 1) 直接使用用户输入
        tries.append(desired)
        # 2) 规范化等价匹配
        nd = _normalize(desired)
        for p in pool:
            if _normalize(p) == nd and p not in tries:
                tries.append(p)
                break
        # 3) 最终回退：首个返回名称（若存在）
        if pool:
            first = pool[0]
            if first not in tries:
                print(f"[Name] 提供的名称 '{desired}' 不在 /jammers 列表中，将尝试规范化匹配与回退：{first}")
                tries.append(first)
        return tries

    # 逐一测试每个名称
    any_success = False
    x_m, y_m, z_m = args.x, args.y, args.z
    for desired in target_names:
        # 构造尝试名称列表
        tries = _candidate_list(desired, names)
        used_name = None
        # 逐个尝试：优先米，失败再厘米；任何一次成功即认为该名称通过
        for name in tries:
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

            if ok1 or ok2:
                used_name = name
                any_success = True
                break

        if used_name is None:
            print(f"[Name] '{desired}' 通过所有尝试均未查询到有效功率（请检查名称拼写或 UE 服务实现）")
        else:
            # 若最终使用的是回退名称，额外提示一次
            if used_name != desired:
                print(f"[Name] '{desired}' 未直接命中，已使用 '{used_name}' 完成查询")

    # 成功判定：至少有一个名称的至少一种方式返回非错误 JSON，且可提取 power 字段
    if not any_success:
        print("[Result] 失败：/jammer_power 未返回有效功率（请检查名称拼写、IsJamming、单位 cm/m）")
        sys.exit(1)

    print("[Result] 成功：拉取式自检通过（多个名称已测试）。建议在 config/default.yaml 设置 ue_rpc.http_base 并开启 power 模式进行端到端测试。")


if __name__ == "__main__":
    main()