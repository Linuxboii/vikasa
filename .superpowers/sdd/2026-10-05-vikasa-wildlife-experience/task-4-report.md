# Task 4 report

## Polish follow-up (2026-10-06)

The original Task 4 worker report was not present in the SDD folder when this follow-up began, so this report records the verification and polish continuation.

### Changes

- Refined the procedural quadruped with a longer, lower torso, clearer shoulder/haunch transitions, jaw and nose, small sensory ears, coat pattern marks, articulated capsule limbs, toes and claws, a tapered gene-linked tail, and dorsal ridges.
- Improved the geometry harness's phenotype staging, naturalistic lighting/background, optional close-up framing, and checks for silhouette, anatomy, injury/alpha marks, posture transition, and selection.
- Corrected the claw harness assertion to count the `CylinderMesh` geometry under each leg. Godot assigns anonymous names to repeated moved siblings, so string-name matching undercounted valid claw meshes.

### Verification

Ran from `C:\Users\paran\Documents\Codex\2026-10-04\i-x20\outputs\vikasa` using `tmp\godot-runtime\Godot_v4.7.2-stable_win64_console.exe`:

```powershell
& $godot --headless --editor --path godot --quit
# exit 0; project/scripts/scenes parsed

& $godot --headless --path godot res://tests/CreatureViewHarness.tscn
# exit 0; "CreatureView harness passed: three phenotypes, four legs/feet, missing optional keys, action transitions and selection."

& $godot --headless --path godot res://tests/CreatureViewHarness.tscn -- --close-up
# exit 0; same harness pass message with close-up camera mode selected
```

### Visual QA evidence and limitation

- Inspected the existing non-headless capture `godot/tmp/creature-close00000000.png` (timestamp 2026-10-05 23:44 local). The parent reviewer confirmed that this capture reflects the visual-polish geometry; the only harness-only fix in this follow-up changes how claw meshes are counted and does not affect rendering. It shows a low quadrupedal silhouette, distinct tail/limb/head forms, muted habitat lighting, and the close-up gallery framing.
- Attempted a fresh capture with `--headless --path godot --write-movie godot/tmp/creature-polish.png --fixed-fps 2 res://tests/CreatureViewHarness.tscn -- --close-up`. Godot's dummy headless renderer had no viewport texture (`write_begin ... d.is_null()`) and crashed; no new screenshot was produced by that path. The headless parser and both functional harness runs pass, but a fresh rendered-image inspection remains unverified.
- The full Main scene's pre-existing `Habitat.gd` `MultiMeshInstance3D.multimesh` runtime issue remains outside Task 4 scope; no Habitat file was changed.

### Reviewer fix round (2026-10-06)

- Preserve the genome-derived base coat color and calculate low-energy tint from that stable color on every update. Repeated low-energy polling no longer compounds the gray tint, and full energy recovery restores the exact original coat.
- Use the inherited speed gene to scale visual stride length. The gene is clamped to the configured `0.5..4.0` interval and mapped to a bounded `0.85..1.15` gait factor; this is presentation-only and uses no simulation randomness.
- Extended the harness to poll low energy repeatedly before recovery and assert exact coat restoration, and to assert that low/high speed genes produce distinct stride factors within the declared bounds.

Verification from `C:\Users\paran\Documents\Codex\2026-10-04\i-x20\outputs\vikasa` using `tmp\godot-runtime\Godot_v4.7.2-stable_win64_console.exe`:

```powershell
& $godot --headless --editor --path godot --quit
# exit 0; scripts and scenes parsed

& $godot --headless --path godot res://tests/CreatureViewHarness.tscn
# exit 0; harness passed

& $godot --headless --path godot res://tests/CreatureViewHarness.tscn -- --close-up
# exit 0; harness passed in close-up mode

git diff --check
# exit 0; no whitespace errors (Git emitted only existing LF/CRLF normalization warnings)
```
