# AETHERGRID — 3D World Simulation

A browser-based 3D simulation of a 24-society electricity district, built for
SIH 2026 (AI-Based Electricity Demand Optimization in Smart Buildings).

**Live:** deployed as a static site on Vercel.
**Local:** `python -m http.server 8020` then open
<http://localhost:8020/viz3d/index.html>.

## What it is

Twenty-four societies (~1,300 households) on one shared feeder. Six run under
GridBrain coordination; eighteen run unmanaged and genuinely trip. Every number
the renderer draws comes from a real simulation run in `aethergrid/worldsim/` —
the browser only plays back pre-generated JSON, it never computes physics.

## The matched-triplet design

Each society is simulated three ways, sharing an identical seed, household
count, EV/solar penetration and transformer rating. Only the deployment flags
differ:

| arm | curtailment | solar-sync | station | meaning |
|---|---|---|---|---|
| `raw` | off | off | 0 | nothing deployed |
| `ai` | on | on | 0 | coordination only — **zero capex** |
| `full` | on | on | 60 kWp | coordination + community solar station |

So `(ai − raw)` is the value of coordination alone and `(full − ai)` is what the
solar hardware adds. Reporting the bundled figure as "what the AI saved" would
credit a hardware purchase to the algorithm. `generate_district.py` asserts the
controlled fields are identical across arms and fails if they ever drift.

**Result across the district:** coordination alone accounts for the large
majority of the peak reduction and removes every transformer trip, at zero
capital cost. The solar station is real added value but is the smaller half —
and it costs money. Solar generates nothing after sunset, so it cannot shave an
evening peak; it is a cost lever, not a peak lever. That is stated in the UI
rather than averaged away.

## Honesty rules

- Illustrative values are labelled as such: the demonstration tariff
  (₹7.2/kWh), export rate, ₹1,200/kVA capex default, and the simplified
  IEC-style transformer-ageing curve.
- Real cited constants: CEA grid emission factor (0.716 kg CO₂/kWh), TNERC
  HT-I-A tariff structure, RDSS programme milestones.
- Anything the engine does not model — voltage quality, harmonics, crew
  restoration times, the operations console — is badged as a callout or a
  mockup, never presented as simulated output.

## Layout

```
viz3d/          the 3D renderer (Three.js via CDN importmap, no build step)
commercial3d/   the commercial pitch slideshow
viz/data/       pre-generated simulation output the renderer reads
aethergrid/worldsim/   the Python simulation engine
```

## Regenerating the data

```bash
pip install -r requirements.txt
python -m aethergrid.worldsim.generate_scenarios
python -m aethergrid.worldsim.generate_colony
python -m aethergrid.worldsim.generate_whatif
python -m aethergrid.worldsim.generate_solar_sync
python -m aethergrid.worldsim.generate_district
```

Runs are deterministic: the same seed produces byte-identical output.

## Deployment

Static — no build step. `vercel.json` redirects `/` and `/worldsim` to
`/viz3d/index.html` and `/commercial` to `/commercial3d/index.html`.
`.vercelignore` excludes the Python engine and the unused per-society detail
exports, keeping the deployed payload around 42 MB.
