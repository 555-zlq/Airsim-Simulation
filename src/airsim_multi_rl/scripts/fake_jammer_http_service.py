from __future__ import annotations

"""
简易本地 Jammer HTTP 假服务（用于离线/本地自检）。

提供与 UE 蓝图服务一致的三个端点：
- GET /ping -> {"status":"ok"}
- GET /jammers -> {"jammers":[{name, location(cm), basePower, isJamming}]}
- GET /jammer_power?name=...&x=..&y=..&z=.. -> {"power": float}

用途：
- 在无法连接到 Windows/UE 的场景下，本地验证 `http_pull_check.py` 的多名称与单位逻辑。

注意：
- 功率计算为演示用，非真实物理模型。默认根据与 Jammer 的距离（cm）做简单衰减。
"""

import json
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class _Jammer:
    """Jammer 结构（演示用）。"""

    def __init__(self, name: str, x_cm: float, y_cm: float, z_cm: float, base_power: float = 100.0, is_jamming: bool = True):
        self.name = name
        self.x_cm = float(x_cm)
        self.y_cm = float(y_cm)
        self.z_cm = float(z_cm)
        self.base_power = float(base_power)
        self.is_jamming = bool(is_jamming)

    def location_dict(self) -> dict:
        # UE 风格位置字段（单位 cm）
        return {"X": self.x_cm, "Y": self.y_cm, "Z": self.z_cm}


class _Handler(BaseHTTPRequestHandler):
    # 预置三个 Jammer（名称与你的 UE 一致）：
    _jammers = [
        _Jammer("BP_JammerActor", 0.0, 0.0, 0.0, base_power=120.0, is_jamming=True),
        _Jammer("BP_JammerActor2", 2000.0, 0.0, 0.0, base_power=80.0, is_jamming=True),
        _Jammer("BP_JammerActor3", -1000.0, 1500.0, 0.0, base_power=60.0, is_jamming=False),
    ]

    def _send_json(self, obj: dict, code: int = 200):
        # 统一 JSON 输出与 CORS 头，便于调试
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802 (HTTP 方法命名约定)
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/ping":
            self._send_json({"status": "ok"})
            return
        if parsed.path == "/jammers":
            out = []
            for j in self._jammers:
                out.append({
                    "name": j.name,
                    "location": j.location_dict(),
                    "radius": 600.0,  # cm（示例）
                    "basePower": j.base_power,
                    "isJamming": j.is_jamming,
                })
            self._send_json({"jammers": out})
            return
        if parsed.path == "/jammer_power":
            name = (qs.get("name", [""])[0] or "").strip()
            # 容错解析：无法转换则回退为 0
            def _to_float(value_list, default: float = 0.0) -> float:
                try:
                    v = (value_list or [str(default)])[0]
                    return float(v)
                except Exception:
                    return float(default)

            x_cm = _to_float(qs.get("x"), 0.0)
            y_cm = _to_float(qs.get("y"), 0.0)
            z_cm = _to_float(qs.get("z"), 0.0)

            # 查找 Jammer
            target = None
            for j in self._jammers:
                # 兼容名称变体：移除下划线并小写比较
                def _norm(s: str) -> str:
                    return s.lower().replace("_", "")

                if j.name == name or _norm(j.name) == _norm(name):
                    target = j
                    break
            if target is None:
                self._send_json({"error": "not_found"}, code=404)
                return

            # 简单功率模型：base_power 按距离（cm）做线性衰减（示例）
            dx = x_cm - target.x_cm
            dy = y_cm - target.y_cm
            dz = z_cm - target.z_cm
            d = (dx * dx + dy * dy + dz * dz) ** 0.5
            # 防止除零与负值，距离越远功率越低（演示用）
            power = max(0.0, target.base_power * (1.0 - min(d / 5000.0, 0.95)))

            self._send_json({"power": float(power)})
            return

        # 未知路径
        self._send_json({"error": "not_found"}, code=404)


def main():
    parser = argparse.ArgumentParser(description="Jammer 假服务（本地调试用）")
    parser.add_argument("--port", type=int, default=18080, help="监听端口（默认 18080）")
    args = parser.parse_args()
    server = HTTPServer(("0.0.0.0", args.port), _Handler)
    print(f"[FakeJammer] listening on http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()