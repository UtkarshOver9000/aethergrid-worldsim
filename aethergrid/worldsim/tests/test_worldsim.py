from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from aethergrid.worldsim.engine.society import simulate_society
from aethergrid.worldsim.generate_district import ARMS, CONTROLLED_FIELDS, PAIRS, _society
from aethergrid.worldsim.schemas.scenario import WorldSimScenario
from aethergrid.worldsim.validate_ceew import household_days, summarize

FIXTURE = Path(__file__).parent / "ceew_sample_bareilly_2020-07-01.csv"


@pytest.fixture(scope="module")
def small_society():
    scenario = WorldSimScenario(name="t", scenario="t", date="2026-07-15", seed=7, duration_hours=24, events=[])
    society = _society("t", 7, 12, 0.4, 0.4, rating=1000.0)
    return simulate_society(scenario, society, base_seed=7, **ARMS["raw"])


def test_society_runs_a_full_day(small_society):
    r = small_society
    assert len(r.house_series) == 12
    n = len(r.index)
    assert n == 96  # 15-minute ticks
    for s in r.house_series:
        assert len(s.kw) == n and np.isfinite(s.kw).all()
        assert (np.asarray(s.solar_kw) >= 0).all()
    assert (r.transformer_kva >= 0).all()


def test_raw_arm_never_curtails(small_society):
    assert float(np.sum(small_society.total_curtailed_kwh_by_tick)) == 0.0


def test_same_seed_is_reproducible():
    scenario = WorldSimScenario(name="t", scenario="t", date="2026-07-15", seed=3, duration_hours=24, events=[])
    society = _society("t", 3, 6, 0.4, 0.4, rating=1000.0)
    a = simulate_society(scenario, society, base_seed=3, **ARMS["raw"])
    b = simulate_society(scenario, society, base_seed=3, **ARMS["raw"])
    assert np.allclose(np.stack([s.kw for s in a.house_series]), np.stack([s.kw for s in b.house_series]))


def test_district_pairs_are_matched_on_controlled_fields():
    assert len(PAIRS) == 24
    assert len({p[0] for p in PAIRS}) == 24
    assert set(CONTROLLED_FIELDS) >= {"n_households", "ev_penetration", "solar_penetration", "seed"}


def test_household_days_from_real_ceew_sample():
    raw = pd.read_csv(FIXTURE)
    days = household_days(raw)
    assert len(days) == 6  # 3 real Bareilly households x 2 complete days
    assert list(days.columns) == list(range(24))
    assert (days.values >= 0).all()
    stats = summarize(days)
    assert stats["household_days"] == 6
    assert abs(sum(stats["mean_shape"]) - 1.0) < 1e-3
    assert 0 <= stats["peak_hour_of_mean_shape"] <= 23
