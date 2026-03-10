from __future__ import annotations
import os
import csv
from airsim_multi_rl.config import EnvConfig
from airsim_multi_rl.runners.trajectory_playback import run_trajectory
from airsim_multi_rl.envs.dummy_client import DummyClient


def test_trajectory_csv_written(tmp_path):
    cfg = EnvConfig()
    cfg.logging.file_path = str(tmp_path / "train.log")
    # 配置简化路径与输出
    setattr(cfg, "trajectory", {
        "dt": 0.1,
        "speed": 0.5,
        "yaw_align": False,
        "csv_enabled": True,
        "csv_path": str(tmp_path / "trajectory.csv"),
        "waypoints": {
            "Drone1": [[-10.0, 0.0, -3.0], [-9.5, 0.5, -3.0], [-9.0, 1.0, -3.0]],
            "Drone2": [[0.0, -10.0, -3.0], [0.5, -9.5, -3.0], [1.0, -9.0, -3.0]],
            "Drone3": [[10.0, 0.0, -3.0], [9.5, -0.5, -3.0], [9.0, -1.0, -3.0]],
        },
    })
    client = DummyClient(tuple(cfg.agent_names))
    summary = run_trajectory(cfg, client=client, episodes=1, steps_per_ep=5)
    csv_path = cfg.trajectory["csv_path"]  # type: ignore[index]
    assert os.path.isfile(csv_path)
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert len(rows) > 1
    header = rows[0]
    assert header == ["episode", "step", "agent", "x", "y", "z", "dist_to_goal", "jammer_power", "reward", "collided", "oob", "reached_goal", "timestamp"]
    assert any(r[2] == "Drone1" for r in rows[1:])
    assert all(len(r) == len(header) for r in rows)
    assert any(k.endswith(".reward_sum") for k in summary.keys())
