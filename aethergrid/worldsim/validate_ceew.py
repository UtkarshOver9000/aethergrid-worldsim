"""Reality check: how do the simulated households compare with real ones?

    python -m aethergrid.worldsim.validate_ceew --ceew-dir data/ceew

Real side: CEEW smart-meter data from about 100 households in Mathura and
Bareilly, Uttar Pradesh (Agrawal et al., 2021, Harvard Dataverse,
doi:10.7910/DVN/GOCHJH, CC0), 3-minute readings aggregated to hourly kWh.
Only complete days with grid supply in every hour are used, from July 2020,
the same month as the simulated scenario date (15 July).

Simulated side: the district's 24 societies in the "raw" arm (no coordination,
no community solar), exactly as generate_district.py configures them.

The comparison is per household per day: daily energy, the 24-hour load shape
and the evening peak. Results go to reports/ceew_validation.json and a figure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

CEEW_FILES = ["CEEW - Smart meter data Bareilly 2020.csv", "CEEW - Smart meter data Mathura 2020.csv"]
MONTH = 7
MIN_SUPPLY_VOLTAGE = 100.0


def household_days(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw 3-minute CEEW rows -> one row per (meter, day) with 24 hourly kWh values.

    Keeps July only, hours with at least 15 of 20 readings and grid supply in at least
    90% of them, and days where all 24 hours pass.
    """
    raw = raw.copy()
    raw["x_Timestamp"] = pd.to_datetime(raw["x_Timestamp"], errors="coerce", format="mixed")
    for col in ("t_kWh", "z_Avg Voltage (Volt)"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.dropna(subset=["x_Timestamp", "t_kWh"])
    raw = raw[raw["x_Timestamp"].dt.month == MONTH]
    raw["hour"] = raw["x_Timestamp"].dt.floor("h")
    raw["ok"] = raw["z_Avg Voltage (Volt)"] >= MIN_SUPPLY_VOLTAGE
    hourly = raw.groupby(["meter", "hour"]).agg(kwh=("t_kWh", "sum"), n=("t_kWh", "size"), ok=("ok", "sum")).reset_index()
    hourly = hourly[(hourly["n"] >= 15) & (hourly["ok"] >= hourly["n"] * 0.9)]
    hourly["day"] = hourly["hour"].dt.normalize()
    hourly["h"] = hourly["hour"].dt.hour
    wide = hourly.pivot_table(index=["meter", "day"], columns="h", values="kwh")
    return wide.dropna()


def real_household_days(ceew_dir: Path) -> pd.DataFrame:
    cols = ["x_Timestamp", "t_kWh", "z_Avg Voltage (Volt)", "meter"]
    return pd.concat([household_days(pd.read_csv(Path(ceew_dir) / name, usecols=cols)) for name in CEEW_FILES])


def simulated_household_days() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Hourly net grid import and gross demand (net + rooftop solar) per simulated household for one day."""
    from aethergrid.worldsim.engine.society import simulate_society
    from aethergrid.worldsim.generate_district import ARMS, DATE, PAIRS, _society
    from aethergrid.worldsim.schemas.scenario import WorldSimScenario

    net_rows, gross_rows = [], []
    for key, seed, n, ev, solar, _stress, _deployed, _label in PAIRS:
        scenario = WorldSimScenario(name=key, scenario=key, date=DATE, seed=seed, duration_hours=24, events=[])
        # The transformer rating only matters when curtailment is on; the raw arm never curtails.
        society = _society(key, seed, n, ev, solar, rating=1000.0)
        result = simulate_society(scenario, society, base_seed=seed, **ARMS["raw"])
        steps_per_hour = int(round(1 / result.dt_hours))
        for series in result.house_series:
            net = np.asarray(series.kw[: 24 * steps_per_hour]).reshape(24, steps_per_hour).mean(axis=1)
            solar = np.asarray(series.solar_kw[: 24 * steps_per_hour]).reshape(24, steps_per_hour).mean(axis=1)
            net_rows.append(net)
            gross_rows.append(net + solar)
    return pd.DataFrame(net_rows), pd.DataFrame(gross_rows)


def summarize(days: pd.DataFrame) -> dict:
    daily = days.sum(axis=1)
    shape = days.div(daily.replace(0, np.nan), axis=0).mean()
    evening = days.loc[:, 18:22].sum(axis=1) / daily.replace(0, np.nan)
    return {
        "household_days": int(len(days)),
        "daily_kwh": {p: round(float(np.percentile(daily, q)), 2) for p, q in
                      (("p10", 10), ("p25", 25), ("median", 50), ("p75", 75), ("p90", 90))},
        "daily_kwh_mean": round(float(daily.mean()), 2),
        "peak_hour_of_mean_shape": int(shape.idxmax()),
        "share_of_energy_18_to_23h": round(float(evening.mean()), 4),
        "mean_shape": [round(float(v), 5) for v in shape.values],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare simulated households with real CEEW smart-meter data")
    parser.add_argument("--ceew-dir", type=Path, default=Path("data/ceew"))
    parser.add_argument("--out", type=Path, default=Path("reports/ceew_validation.json"))
    args = parser.parse_args()

    real = real_household_days(args.ceew_dir)
    sim_net, sim_gross = simulated_household_days()
    real_s, net_s, gross_s = summarize(real), summarize(sim_net), summarize(sim_gross)
    shape_corr = float(np.corrcoef(real_s["mean_shape"], gross_s["mean_shape"])[0, 1])
    report = {
        "real": {"source": "CEEW smart meters, Mathura + Bareilly, July 2020 (doi:10.7910/DVN/GOCHJH)",
                 "households": int(real.index.get_level_values(0).nunique()), **real_s},
        "simulated_net_grid_import": {"source": "district raw arm, 24 societies, 15 July", **net_s},
        "simulated_gross_demand": {"source": "net import + rooftop solar", **gross_s},
        "comparison": {
            "median_daily_kwh_ratio_sim_gross_to_real": round(gross_s["daily_kwh"]["median"] / real_s["daily_kwh"]["median"], 2),
            "hourly_shape_correlation_sim_gross_vs_real": round(shape_corr, 3),
            "peak_hour_real": real_s["peak_hour_of_mean_shape"],
            "peak_hour_sim": gross_s["peak_hour_of_mean_shape"],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    hours = np.arange(24)
    axes[0].plot(hours, real_s["mean_shape"], marker="o", label=f"real: {report['real']['households']} UP households, July 2020")
    axes[0].plot(hours, gross_s["mean_shape"], marker="o", label="simulated: gross household demand")
    axes[0].set(title="Average daily load shape (share of the day's energy)", xlabel="hour of day", ylabel="share")
    axes[0].legend()
    axes[1].hist(real.sum(axis=1), bins=40, alpha=0.6, density=True, label="real household-days")
    axes[1].hist(sim_gross.sum(axis=1), bins=40, alpha=0.6, density=True, label="simulated households")
    axes[1].set(title="Daily energy per household", xlabel="kWh per day", ylabel="density")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(args.out.parent / "ceew_validation.png", dpi=130)
    print(json.dumps({k: v for k, v in report.items()}, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main()
