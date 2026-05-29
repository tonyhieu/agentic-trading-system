"""QD-AFG structural variant afg-qd-s11 — submit_fraction=1.0, windows=((13, 17),).
Generated for quality_diversity_experiment afg arm (structural pass).
13-17h, hi sel
"""
from execution_algos._qd_afg_template import get_execution_algorithm as _base


def get_execution_algorithm(exec_id: str = "MY_GENERIC_ALGO", **_ignored):
    return _base(
        exec_id=exec_id,
        window_seconds=10.0,
        flow_threshold=2.0,
        submit_fraction=1.0,
        windows=((13, 17),),
        cascade_reentry=True,
    )
