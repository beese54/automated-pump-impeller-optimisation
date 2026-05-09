# Automated Pump Impeller Optimisation

Parametric impeller optimisation built in Autodesk Fusion 360 with Claude Code as an AI co-pilot, running as a Fusion script plugin.

**Status:** POC complete. Optimisation converged at β = 29.08°, delivering a 15% improvement in volumetric flow rate over the baseline design. All structural safety checks passed.

---

## Final Design Specification

| Parameter | Value |
|---|---|
| Outer diameter | 100 mm |
| Blade width | 8 mm |
| Blade angle (β) | 29.08° |
| Number of blades | 6 |
| Shaft bore | ⌀10 mm |
| Material | Aluminium 6061 |
| Operating speed | 3,000 RPM |

---

## Files in This Repository

| File | Purpose |
|---|---|
| `impeller.step` | Solid model export — suitable for any CFD/FEA tool outside Fusion |
| `fluid_domain.step` | Cylindrical fluid volume around the impeller, with the impeller solid carved out — ready as the rotating zone in a CFD MRF setup |
| `fea_validation.py` | Fusion 360 script — runs Modal Frequencies + Static Stress studies automatically and writes a plain-text report |
| `fea_validation.manifest` | Fusion script manifest — required by Fusion to register the script |
| `README.md` | This document |

**Not tracked (see .gitignore):**
- `impeller.f3d` — Fusion native binary, not version-controllable
- `fea_report.txt` — generated output, reproducible by running the script
- `fea_validation/` — Fusion AppData copy of the script, auto-deployed
- `animation_frames/` — exported PNG frames, large binary files
- `.claude/` — local Claude Code session settings

---

## How to Run the FEA Validation Script

1. Open `impeller.f3d` in Autodesk Fusion 360
2. Go to **Utilities → Scripts and Add-Ins → Scripts**
3. Click **Add** and point at the `fea_validation` folder
4. Click **Run**

The script runs two studies automatically:
- **Modal Frequencies** — confirms no natural frequency coincides with operating harmonics (50 Hz, 300 Hz, 600 Hz)
- **Static Stress** — confirms the design survives centrifugal loading at 3,000 RPM with a safety factor ≥ 3

Results are written to `fea_report.txt` and shown as a plain-text summary in Fusion.

---

## Optimisation Approach

The blade angle sweep used the proxy formula:

```
Q = π · D · b · sin(β)
```

where Q is volumetric flow rate, D is diameter, b is blade width, and β is the blade outlet angle. Hundreds of angle combinations were tested automatically via a Python script running inside Fusion, with the geometry rebuilding on each iteration.

The proxy formula converges fast but ignores hydraulic losses (slip, viscous friction, recirculation). Real-world Q at the same RPM is typically 70–85% of the proxy value. CFD would close this gap — see the next phase roadmap below.

---

## Structural Validation Results

| Check | Threshold | Result |
|---|---|---|
| Modal — first deformation mode | > 450 Hz (1.5× blade-pass) | PASS |
| Static stress safety factor | ≥ 3.0 (Al 6061, σ_y = 270 MPa) | PASS ✓ |
| Safety margin | ≥ 3× | ~65× (significantly over-engineered for this load) |

---

## Next Phase Roadmap

### Path A — CFD Validation

The proxy-based +15% flow claim should be verified with a full CFD solve. The `fluid_domain.step` file is ready to use as the rotating zone in an MRF setup.

Recommended tools:
- **SimScale** — cloud-based, REST API, ~10 min steady-state solve, best for an agentic loop
- **OpenFOAM** — highest fidelity, free, requires meshing infrastructure
- **Autodesk CFD** — closest to the Fusion ecosystem, separate license

Target metrics per CFD run: volumetric flow rate Q, static pressure rise ΔP, hydraulic efficiency η, and slip factor σ.

> **Note on `fluid_domain.step`:** the shaft-bore region remains fluid in this export (no shaft solid). If shaft blockage matters for your solver, add a ⌀10 mm cylinder along the central axis in your CFD pre-processor before meshing.

### Path B — Coupled Optimisation

The current optimiser only maximised Q. A coupled optimiser would jointly satisfy:

- Q ≥ 1.15 × Q_baseline (hydraulic)
- σ_max ≤ σ_yield / 3 (structural static)
- f₁_def ≥ 1.5 × f_blade_pass (vibration)

With Fusion's Simulation API driving the studies and Python orchestrating, each iteration runs in ~1 minute on local hardware — a 20-iteration sweep finishes in under half an hour.

---

## Tools Used

- **Autodesk Fusion 360** — CAD, parametric modelling, FEA simulation
- **Claude Code** — automation scripts, result interpretation, AI co-pilot running as a Fusion plugin
- **Python** — scripting via the Fusion 360 API (`adsk.core`, `adsk.fusion`)
