"""
fea_validation.py  –  Fusion 360 Script
Path B: FEA validation of the optimised pump impeller.

Runs two studies on the active Fusion document (impeller.f3d):
  1. Modal Frequencies  – confirm no natural freq coincides with operating harmonics
  2. Static Stress       – confirm FoS ≥ 3 under 3000 RPM centrifugal load

Writes a plain-text engineering summary to fea_report.txt alongside this script.

How to run
----------
1. Open impeller.f3d in Autodesk Fusion.
2. Scripts and Add-Ins → Scripts → Add → point at this folder → Run.

Fusion internal units: centimetres (lengths), radians (angles).
"""

import adsk.core
import adsk.fusion
import traceback
import math
import os

# ── Design constants ────────────────────────────────────────────────────────
RPM               = 3000
OMEGA_RAD_S       = 2.0 * math.pi * RPM / 60.0   # 314.159 rad/s
N_BLADES          = 6
SHAFT_BORE_R_CM   = 0.5          # 10 mm bore → r = 5 mm = 0.5 cm (Fusion uses cm)
SHAFT_BORE_TOL_CM = 0.05         # ±0.5 mm search tolerance

# ── Analysis thresholds ─────────────────────────────────────────────────────
N_MODES           = 10
BLADE_PASS_HZ     = N_BLADES * (RPM / 60.0)       # 300 Hz
FREQ_MARGIN       = 1.5          # deformation modes must be > 1.5 × blade_pass
AL6061_YIELD_MPA  = 270.0
MIN_FOS           = 3.0

# ── Danger harmonics (10 % band either side triggers a warning) ─────────────
HARMONICS_HZ      = [RPM / 60.0, BLADE_PASS_HZ, 2.0 * BLADE_PASS_HZ]   # 50, 300, 600 Hz


# ────────────────────────────────────────────────────────────────────────────
# Geometry helpers
# ────────────────────────────────────────────────────────────────────────────

def find_shaft_bore_face(root_component):
    """
    Return the inner cylindrical BRep face whose radius matches the shaft bore.
    Fusion stores geometry in centimetres; SHAFT_BORE_R_CM = 0.5 cm = 5 mm.
    """
    for body in root_component.bRepBodies:
        for face in body.faces:
            geom = face.geometry
            if geom.surfaceType == adsk.core.SurfaceTypes.CylinderSurfaceType:
                cyl = adsk.core.Cylinder.cast(geom)
                if abs(cyl.radius - SHAFT_BORE_R_CM) <= SHAFT_BORE_TOL_CM:
                    return face
    return None


def all_bodies(root_component):
    col = adsk.core.ObjectCollection.create()
    for body in root_component.bRepBodies:
        col.add(body)
    return col


# ────────────────────────────────────────────────────────────────────────────
# Study builders
# ────────────────────────────────────────────────────────────────────────────

def run_modal_study(design, bore_face):
    """
    Create, configure, and solve a Modal Frequencies study.
    Returns (study, [freq_hz, ...]) — frequencies are the N_MODES raw values;
    rigid-body modes (< 1 Hz) are included so the caller can filter them.
    """
    studies = design.simulationStudies

    # VERIFY: exact enum name in your Fusion build.
    # Common alternatives: ModalSimulationStudyType, ModalFrequenciesStudyType
    study = studies.add(
        adsk.fusion.SimulationStudyTypes.ModalFrequenciesSimulationStudyType,
        "Modal_Validation"
    )

    # Number of modes to extract
    # VERIFY: property may be study.modalSettings.numberOfModes in some builds
    study.numberOfModes = N_MODES

    # Fixed constraint on shaft bore inner surface
    bore_col = adsk.core.ObjectCollection.create()
    bore_col.add(bore_face)
    # VERIFY: method may be addFixedConstraint(entities) or addFixed(entities)
    study.simulationConstraints.addFixedConstraint(bore_col)

    study.solve()

    freqs = []
    for i in range(study.numberOfModes):
        result = study.results.item(i)
        freqs.append(result.frequency)   # Hz
    return study, freqs


def run_static_study(design, bore_face):
    """
    Create, configure, and solve a Static Stress study with rotational body load.
    Returns (study, max_von_mises_MPa).
    """
    studies = design.simulationStudies

    # VERIFY: exact enum name in your Fusion build.
    # Common alternative: StaticStressSimulationStudyType
    study = studies.add(
        adsk.fusion.SimulationStudyTypes.StaticStressSimulationStudyType,
        "Static_Stress_Validation"
    )

    # Fixed constraint on shaft bore
    bore_col = adsk.core.ObjectCollection.create()
    bore_col.add(bore_face)
    study.simulationConstraints.addFixedConstraint(bore_col)

    # Rotational (centrifugal) body load
    # VERIFY: addBodyLoad signature and BodyLoadType enum value.
    # Some builds use addRotationalBodyLoad(bodies, axis_point, axis_dir, omega_rad_s).
    root = design.rootComponent
    body_col = all_bodies(root)

    origin    = adsk.core.Point3D.create(0, 0, 0)
    z_axis    = adsk.core.Vector3D.create(0, 0, 1)

    study.simulationLoads.addBodyLoad(
        body_col,
        adsk.fusion.SimulationBodyLoadTypes.AngularVelocitySimulationBodyLoadType,
        origin,
        z_axis,
        OMEGA_RAD_S
    )

    study.solve()

    # VERIFY: property name for max stress result.
    # Alternatives: study.results.maximumVonMisesStress (Pa)
    max_vm_pa  = study.results.maximumVonMisesStress
    max_vm_mpa = max_vm_pa / 1.0e6
    return study, max_vm_mpa


# ────────────────────────────────────────────────────────────────────────────
# Report generator
# ────────────────────────────────────────────────────────────────────────────

def generate_report(freqs_hz, max_vm_mpa):
    lines = []
    SEP = "=" * 62

    lines += [
        SEP,
        "  IMPELLER FEA VALIDATION REPORT",
        f"  Design : D=100 mm, b=8 mm, β=29.08°, 6 blades, Al 6061",
        f"  Speed  : {RPM} RPM  |  ω = {OMEGA_RAD_S:.2f} rad/s",
        SEP,
    ]

    # ── Modal ────────────────────────────────────────────────────────────────
    lines.append("\n── MODAL FREQUENCIES ──")
    lines.append(f"Blade-pass freq : {BLADE_PASS_HZ:.0f} Hz")
    lines.append(f"Required margin : first deformation mode > {FREQ_MARGIN * BLADE_PASS_HZ:.0f} Hz")

    deformation_modes = [f for f in freqs_hz if f > 1.0]
    lines.append(f"\n{'#':<5}{'Freq (Hz)':<14}{'Near harmonic?':<20}{'Margin OK?'}")
    lines.append("-" * 55)

    modal_pass = True
    for i, f in enumerate(deformation_modes[:6], 1):
        near = any(abs(f - h) / h < 0.10 for h in HARMONICS_HZ)
        margin_ok = f > FREQ_MARGIN * BLADE_PASS_HZ
        if near or not margin_ok:
            modal_pass = False
        near_str   = "YES  ← WARN" if near      else "no"
        margin_str = "yes"          if margin_ok else "NO  ← WARN"
        lines.append(f"  {i:<4}{f:<14.1f}{near_str:<20}{margin_str}")

    verdict = "PASS" if modal_pass else "FAIL"
    lines.append(f"\nModal verdict : {verdict}")
    if not modal_pass:
        lines.append("  Mitigation :")
        lines.append("    • Add 2 mm fillets at blade root  (raises blade-flap mode)")
        lines.append("    • Increase blade thickness from 2 mm → 2.5 mm")
        lines.append("    • Stiffen hub (increase disc thickness)")

    # ── Static stress ────────────────────────────────────────────────────────
    lines.append("\n── STATIC STRESS  (rotational load @ 3000 RPM) ──")
    fos = AL6061_YIELD_MPA / max_vm_mpa
    stress_pass = fos >= MIN_FOS
    lines += [
        f"Max von Mises  : {max_vm_mpa:.1f} MPa",
        f"Yield strength : {AL6061_YIELD_MPA:.0f} MPa  (Al 6061)",
        f"Safety factor  : {fos:.2f}   (required ≥ {MIN_FOS:.1f})",
    ]
    verdict = "PASS" if stress_pass else "FAIL"
    lines.append(f"\nStress verdict : {verdict}")
    if not stress_pass:
        lines.append("  Mitigation (cheapest first) :")
        lines.append("    1. 2 mm fillets at blade-hub junction  (cuts stress concentration)")
        lines.append("    2. Blade thickness 2 mm → 2.5 mm")
        lines.append("    3. Switch to Al 7075-T6  (σ_y ≈ 503 MPa, FoS budget doubles)")

    # ── Overall ──────────────────────────────────────────────────────────────
    overall = "PASS ✓" if (modal_pass and stress_pass) else "FAIL ✗  — address warnings above"
    lines += [
        "",
        SEP,
        f"  OVERALL : {overall}",
        SEP,
    ]

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────

def run(context):
    ui = None
    try:
        app    = adsk.core.Application.get()
        ui     = app.userInterface
        design = adsk.fusion.Design.cast(app.activeProduct)

        if not design:
            ui.messageBox(
                "No active Fusion design found.\n"
                "Open impeller.f3d before running this script."
            )
            return

        root = design.rootComponent

        # ── Locate shaft bore ────────────────────────────────────────────────
        bore_face = find_shaft_bore_face(root)
        if bore_face is None:
            ui.messageBox(
                f"Could not auto-detect shaft bore face (r ≈ {SHAFT_BORE_R_CM * 10:.0f} mm).\n\n"
                "Check that:\n"
                "  • The model is fully reconstructed (no error flags in browser tree)\n"
                "  • SHAFT_BORE_R_CM in the script matches the actual bore radius"
            )
            return

        # ── Modal study ──────────────────────────────────────────────────────
        ui.messageBox(
            "Step 1 / 2 — Running Modal Frequencies study.\n"
            "This typically takes 30 – 60 s.  Click OK to start."
        )
        _, freqs = run_modal_study(design, bore_face)

        # ── Static stress study ──────────────────────────────────────────────
        ui.messageBox(
            "Step 2 / 2 — Running Static Stress study.\n"
            "This typically takes 30 – 60 s.  Click OK to start."
        )
        _, max_vm_mpa = run_static_study(design, bore_face)

        # ── Report ───────────────────────────────────────────────────────────
        report = generate_report(freqs, max_vm_mpa)

        script_dir  = os.path.dirname(os.path.abspath(__file__))
        report_path = os.path.join(script_dir, "fea_report.txt")
        with open(report_path, "w", encoding="utf-8") as fh:
            fh.write(report)

        # Show first ~800 chars in the dialog; full report is on disk
        preview = report[:800] + ("\n…  (see fea_report.txt for full output)" if len(report) > 800 else "")
        ui.messageBox(f"FEA complete.  Report saved to:\n{report_path}\n\n{preview}")

    except Exception:
        if ui:
            ui.messageBox("Script failed:\n\n" + traceback.format_exc())
        raise
