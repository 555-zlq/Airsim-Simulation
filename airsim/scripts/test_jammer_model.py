from __future__ import annotations
import sys
from pathlib import Path
import numpy as np

repo_root = Path(__file__).resolve().parents[2]
airsim_dir = repo_root / "airsim"
sys.path.insert(0, str(airsim_dir))

from airsim_marl.envs.jammer import CommJammerModel
from airsim_marl.config import EnvConfig


class FakeWorld:
    def __init__(self):
        self.jammer_positions = {"BP_Jammer_1": np.array([0.0, 0.0, -3.0], dtype=np.float32)}

    def refresh_jammers(self):
        pass


def main():
    cfg = EnvConfig()
    cfg.jammer_eirp_dbm = 40.0
    cfg.jammer_gain_max_dbi = 10.0
    cfg.jammer_main_lobe_width_deg = 30.0
    cfg.jammer_narrow_bw_hz = 1e6
    world = FakeWorld()
    jammer = CommJammerModel(world, cfg)
    target_pos = np.array([10.0, 0.0, -3.0], dtype=np.float32)
    freq = 2.4e9
    jammer.update_pointing("Drone1", target_pos, dt_s=0.2, detected_freq_hz=freq)
    sinr = jammer.sinr_db(target_pos, target_tx_dbm=20.0, freq_hz=freq)
    per = jammer.per_from_sinr(sinr)
    print(f"sinr_db={sinr:.3f} per={per:.3f}")


if __name__ == "__main__":
    main()

