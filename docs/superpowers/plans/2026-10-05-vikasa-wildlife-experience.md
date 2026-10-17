# Vikasa Wildlife Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Vikasa's confusing, humanoid-looking observation screen with a polished habitat-first wildlife simulation whose six inspectable instincts produce deterministic, explainable animal behavior.

**Architecture:** Preserve the deterministic Python engine and local HTTP bridge. Add a focused behavior-decision module and persisted behavior/home-range state, split Godot responsibilities into world, creature, HUD, inspector, tools, and client scenes/scripts, and reconcile every project document with the implemented scope.

**Tech Stack:** Python 3.12, NumPy, Pygame (preserved existing frontend), Godot 4.7 GDScript, current local HTTP bridge, pytest suite already in repository, PowerShell on Windows.

**Spec:** `docs/superpowers/specs/2026-10-05-vikasa-wildlife-experience-design.md`

## Global Constraints

- “Presentation quality is the primary acceptance concern, followed by clarity of the simulation.”
- “for a fixed configuration, seed, and intervention sequence, the same simulation decisions and outcomes recur.”
- “Rendering and UI state never consume simulation randomness.”
- “Alpha status never implies aggression by itself.”
- “Use normalized drive signals bounded to `[0, 1]`.”
- “A strong immediate danger response can override all non-emergency actions.”
- “Do not add paid/external services; procedural models and the current local stack are preferred.”
- “Do not replace the working simulation engine, bridge, CLI, or checkpoint system wholesale.”
- Keep existing Python UI, CLI, batch, export, and checkpoint workflows working.
- Do not represent the model as literal cognition, biology, or religion.

## Review Focus

1. Empty, malformed, or migrated behavior state in an old checkpoint must load to a safe `explore`/`rest` state without changing the source checkpoint; pin with v1/v2 migration and round-trip continuation cases in Task 3.
2. A creature with imminent danger and depleted energy must flee/rest rather than mate, explore, or challenge; pin action preemption in Task 2.
3. No perceived food, mate, dependent, or threat must invalidate its corresponding action and must not create an all-pairs scan; pin candidate filtering and spatial-hash usage in Tasks 1–2.
4. Several nearly equal action utilities must not cause frame-rate-dependent oscillation; pin hysteresis and same-seed action sequences in Tasks 2–3.
5. Narrow windows, missing selection, empty population, and bridge disconnect must leave a usable observation screen with a recovery/control path; validate responsive and connection states in Tasks 5–6.

---

## File map

| Area | Files | Responsibility |
|---|---|---|
| Decision model | `src/evolution_sim/simulation/behavior.py` (new), `src/evolution_sim/model/entities.py`, `src/evolution_sim/config.py` | Bounded drives, available action scores, persistent action/home-range state, validated behavior configuration. |
| Engine/persistence | `src/evolution_sim/simulation/engine.py`, `src/evolution_sim/simulation/snapshots.py`, `src/evolution_sim/io/checkpoints.py`, `src/evolution_sim/bridge.py` | Stable tick orchestration, behavior execution, parenting/care, migration, and the UI snapshot contract. |
| Python verification | `tests/simulation/test_behavior.py` (new), `tests/simulation/test_engine.py`, `tests/simulation/test_reproducibility.py`, `tests/io/test_checkpoints.py` | Decision rules, ecological outcomes, deterministic replay, and checkpoint compatibility. |
| Godot composition | `godot/Main.tscn`, `godot/scripts/Main.gd`, `godot/scripts/WorldView.gd` + `.tscn`, `godot/scripts/CreatureView.gd` + `.tscn`, `godot/scripts/HUD.gd` + `.tscn`, `godot/scripts/CreatureInspector.gd` + `.tscn`, `godot/scripts/WorldTools.gd` + `.tscn`, `godot/scripts/SimulationClient.gd` | One responsibility per scene/script and a primary full-size habitat viewport. |
| Godot verification | `godot/scripts/*`, `tests/test_documentation.py`, manual visual review | Script parsing, bridge/runtime states, mouse/keyboard interaction, and screenshots/review conditions. |
| Documentation | `README.md`, `docs/ARCHITECTURE.md`, `docs/SCIENTIFIC_MODEL.md`, `docs/MATHEMATICS.md`, `docs/EXPERIMENTS.md`, `docs/DEMO_SCRIPT.md`, prior specs/plans under `docs/superpowers/` | Accurate actual model, equations, controls, demonstrations, and clear historical status for superseded roadmap docs. |

## Interfaces fixed by this plan

- `ActionName(StrEnum)`: `EXPLORE`, `FORAGE`, `REST`, `SEEK_MATE`, `CARE`, `FLEE`, `PATROL`, `CHALLENGE`.
- `InstinctVector`: immutable six-value tuple in the stable order survival, foraging, mating, offspring care, danger avoidance, territory; construction validates finite values in `[0, 1]`.
- `BehaviorPerception`: immutable tick-local tuple collections for food, threats, eligible mates, and dependent offspring, plus local hazard/terrain values. Every collection is supplied from existing spatial indexes.
- `BehaviorState`: current action, start tick, target kind/id/position, six drives, per-action utility breakdown, and plain-language reason. It is stored with the creature and serialized.
- `BehaviorDecision`: next `BehaviorState` plus a finite bounded score map for UI/research explanation.
- `BehaviorController.choose(creature, perception, tick, config) -> BehaviorDecision`: pure with respect to simulation state except for an explicitly supplied engine RNG used only for seeded tie-breaks; no wall-clock or renderer dependencies.
- Bridge creature JSON keys add `behavior`, `behavior_reason`, `behavior_started_tick`, `drives` with six named normalized values, `behavior_scores`, `target`, `home_center`, `home_radius`, and `dependent_ids`. Existing state/command routes remain unchanged.
- UI sends existing pause/resume/step/speed/food/weather actions via `SimulationClient`; UI scripts never mutate engine state directly.

### Task 1: Behavior state, validated configuration, and perceptions

**Files:**
- Create: `src/evolution_sim/simulation/behavior.py`
- Modify: `src/evolution_sim/model/entities.py`
- Modify: `src/evolution_sim/config.py`
- Modify: `src/evolution_sim/simulation/snapshots.py`
- Create: `tests/simulation/test_behavior.py`
- Modify: `tests/test_config.py`
- Modify: `tests/model/test_entities.py`

**Interfaces:**
- Produces the enums/dataclasses in “Interfaces fixed by this plan”.
- `Creature` stores `behavior_state` and a two-dimensional `home_center` vector plus finite-positive `home_radius`; because the entity itself does not own world dimensions, engine creation and checkpoint migration enforce the world-relative upper bound `min(world_width, world_height) / 2`. Founder/offspring constructors must initialize independent arrays, never share mutable NumPy arrays.
- `BehaviorConfig` has bounded `hysteresis_margin`, `softmax_temperature`, `dependent_age_ticks`, `care_radius`, `care_energy_rate`, `danger_preempt_threshold`, and `territory_migration_margin`, all with defaults that preserve loading existing JSON configs.

- [ ] **Step 1: Add failing state/config cases.** Create tests that reject six-drive vectors of the wrong length, NaN, infinity, and out-of-range values; reject negative/out-of-range behavior settings; and prove two default creatures do not share home-center storage.
- [ ] **Step 2: Run the narrow cases.** Run `pytest tests/simulation/test_behavior.py tests/model/test_entities.py tests/test_config.py -q`; expected: new imports/fields/validation fail until implemented.
- [ ] **Step 3: Implement the state types and defaults.** Add enum/dataclasses and the nested `BehaviorConfig` to strict config parsing. Use the vector order specified above as the only serialization/UI order. Give legacy configs defaults instead of requiring new JSON keys.
- [ ] **Step 4: Attach state to creatures and snapshots.** Initialize `home_center` from a copy of founder position, default radius 24 (valid for every current config because each world dimension is at least 64), and `BehaviorState` with safe `EXPLORE`; add snapshot fields without removing current field names. Leave world-relative radius clamping to engine creation (Task 2) and checkpoint migration (Task 3), where dimensions are available.
- [ ] **Step 5: Run focused validation.** Run the narrow test command from Step 2 and `python -m compileall -q src/evolution_sim`; expected: all targeted cases pass and Python compiles.
- [ ] **Step 6: Commit the slice.** `git add src/evolution_sim/model/entities.py src/evolution_sim/config.py src/evolution_sim/simulation/behavior.py src/evolution_sim/simulation/snapshots.py tests/simulation/test_behavior.py tests/model/test_entities.py tests/test_config.py && git commit -m "feat: add persisted wildlife behavior state"`.

### Task 2: Drive calculations, utility arbitration, and engine integration

**Files:**
- Modify: `src/evolution_sim/simulation/behavior.py`
- Modify: `src/evolution_sim/simulation/engine.py`
- Modify: `src/evolution_sim/model/entities.py`
- Modify: `tests/simulation/test_behavior.py`
- Modify: `tests/simulation/test_engine.py`
- Modify: `tests/simulation/test_reproducibility.py`
- Modify: `src/evolution_sim/model/math2d.py` (only if measured profiling confirms the existing 2D distance helper is a hot-path bottleneck)
- Modify: `tests/model/test_math2d.py` (only when the measured helper optimization is included)

**Interfaces:**
- Consumes `BehaviorConfig`, `BehaviorState`, `BehaviorPerception`, and seeded `np.random.Generator` from Task 1.
- `SimulationEngine._behavior_perception(creature_id) -> BehaviorPerception` builds candidates with spatial hashes and filters by eligibility/dependence.
- `SimulationEngine._choose_behavior(creature_id) -> None` stores the chosen `BehaviorState`; stable creature-ID/tick order is mandatory.
- `SimulationEngine._execute_behavior(creature_id) -> None` steers according to action/target and applies action costs; it does not duplicate fight, feeding, or birth resolution.

- [ ] **Step 1: Pin drive normalization and action filtering.** Add unit cases for hunger/energy/injury survival urgency; no mate/dependent/food candidates; danger max pressure; and invalid-action suppression. For survival use the spec seed equation `clamp(0.65 * (1 - energy / maximum) + 0.35 * injury, 0, 1)` so expected values are exact.
- [ ] **Step 2: Pin arbitration and persistence.** Add cases where danger preempts every action; survival suppresses mating; care target is the nearest living dependent in radius; territory competes with resource scarcity; the current action persists when a new utility is below the hysteresis margin; and same-seed near-tie decisions match.
- [ ] **Step 3: Run focused tests to observe failures.** Run `pytest tests/simulation/test_behavior.py -q`; expected: new drive/action cases fail before implementation.
- [ ] **Step 4: Implement documented utility terms.** Score each valid action with drive affinity, perceived reward, movement energy cost, exposure risk, and social conflict cost. Apply emergency preemption first, hysteresis second, seeded tie-break only for near-equal top scores. Keep scores finite and clamp any displayed score to a documented normalized range.
- [ ] **Step 5: Integrate stable engine actions.** Replace alpha/random food steering in `_move_creatures` with perception/choose/execute calls. Keep `_resolve_fights`, `_resolve_consumption`, and `_resolve_reproduction` as single authoritative outcome resolvers. Clamp every founder/offspring home radius to `min(world_width, world_height) / 2`. Challenge uses aggression and local contest pressure but alpha alone adds no automatic attack probability. Care action stays near dependent young and transfers bounded surplus energy while retaining a parent reserve. Patrol chooses seeded nonzero targets on or near the home-range boundary, including when already at home center; scarcity plus sustained outside utility can move home center gradually rather than teleport it.
- [ ] **Step 6: Add engine-level examples.** In `test_engine.py`, use fixed seeds and controlled worlds to confirm forage consumes food, flee increases distance from a threat/hazard, rest costs less movement energy, care transfers energy only to a dependent, and mating requires eligible pair selection. In reproducibility tests, compare per-tick behavior/action logs between two runs.
- [ ] **Step 7: Run focused verification.** Run `pytest tests/simulation/test_behavior.py tests/simulation/test_engine.py tests/simulation/test_reproducibility.py tests/model/test_math2d.py -q`; expected: new and existing engine cases pass with invariant validation enabled.
- [ ] **Step 8: Commit the behavior slice.** Stage only the Task 2 behavior/engine/entity/test files; include `math2d.py` and `test_math2d.py` only when profiling confirms the helper is a bottleneck and the scalar 2D implementation is covered by equivalence tests. Commit with `feat: arbitrate wildlife behavior from needs and risk`.

### Task 3: Checkpoint migration and bridge contract

**Files:**
- Modify: `src/evolution_sim/io/checkpoints.py`
- Modify: `src/evolution_sim/simulation/snapshots.py`
- Modify: `src/evolution_sim/bridge.py`
- Modify: `tests/io/test_checkpoints.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Bridge `/state` adds the named UI fields exactly as specified; `/command` request/response stays compatible.
- New checkpoint version is the next integer after current v2. Loaders accept v1, v2, and new schema; migration defaults behavior to `EXPLORE`, initializes a bounded home range from saved position/seed, and preserves RNG state/tick/IDs.

- [ ] **Step 1: Add failing compatibility tests.** Assert v1/v2 migration does not modify source bytes; migrated creatures have six finite drives and valid home ranges; new version round-trips continued action selection exactly; future schema rejection remains clear.
- [ ] **Step 2: Run checkpoint/CLI cases.** Run `pytest tests/io/test_checkpoints.py tests/test_cli.py -q`; expected: new state assertions fail.
- [ ] **Step 3: Implement migration and round-trip.** Extend serializers/readers with behavior/home-range/action target fields. Missing optional action targets remain `None`; validate IDs and clamp home radius to `min(config.world.width, config.world.height) / 2` before accepting checkpoint. Keep migration pure until explicit save.
- [ ] **Step 4: Extend bridge serialization.** Emit six named drives and the action reason/target/home range/dependents from immutable state snapshots. Bound reason length and keep payload JSON finite/serializable. Preserve local-only bind and existing command validation.
- [ ] **Step 5: Verify compatibility.** Run the test command from Step 2 plus `python -m compileall -q src/evolution_sim`; query local state only when the app is running and confirm old field names remain.
- [ ] **Step 6: Commit persistence/bridge slice.** `git add src/evolution_sim/io/checkpoints.py src/evolution_sim/simulation/snapshots.py src/evolution_sim/bridge.py tests/io/test_checkpoints.py tests/test_cli.py && git commit -m "feat: persist and expose wildlife action state"`.

### Task 4: Build coherent quadrupedal creature models and action animation

**Files:**
- Create: `godot/scripts/CreatureView.gd`
- Create: `godot/scenes/CreatureView.tscn`
- Create: `godot/tests/CreatureViewHarness.gd`
- Create: `godot/tests/CreatureViewHarness.tscn`
- Remove after replacement: `godot/scripts/CreatureVisual.gd` and its generated `.uid`
- Modify: Godot creature visuals only; no changes to Python simulation logic in this task.

**Interfaces:**
- `CreatureView.configure(data: Dictionary, scale_factor: float, world_width: float, world_height: float) -> void`
- `CreatureView.update_state(data: Dictionary, delta: float) -> void`
- `CreatureView.set_selected(value: bool) -> void`
- `CreatureView` interprets `behavior`, `velocity`, `size`, `speed`, `perception`, `aggression`, `resilience`, `sociability`, `injury`, and `alpha`; missing optional keys use neutral defaults.

- [ ] **Step 1: Add a geometry/animation verification scene.** Create `godot/tests/CreatureViewHarness.tscn` and `.gd`, instantiating three fixed phenotype dictionaries at low/medium/high size/aggression. Assert four leg nodes exist, foot anchors sit below body center, and action state updates without missing keys.
- [ ] **Step 2: Run parser before implementation.** Run `Godot_v4.7.2-stable_win64_console.exe --headless --editor --path godot --quit`; expected: new scene/script references fail until created.
- [ ] **Step 3: Build the animal silhouette.** Use an elongated body along +X, low spine, forward muzzle/head, four individually transformable legs, tail behind pelvis, and genome-shaped ears/crest/sensory fins. Use joined/custom mesh surfaces or overlapping carefully scaled volumes; never create upright torso/arm anatomy.
- [ ] **Step 4: Add bounded gait and action poses.** Advance gait only from simulation velocity/state, not simulation RNG. Walk/run animate diagonal leg pairs with a small body counter-bob. Rest/feed/care/patrol/challenge/flee change a small set of explicit pose/visual cues with smoothed interpolation.
- [ ] **Step 5: Add readable material and selection states.** Use matte palette, opaque low-energy colors, no humanoid face framing, selection ground ring/outline, and separate minor injury/alpha signals.
- [ ] **Step 6: Replace old factory references.** Update only consumers after Task 5 scene hierarchy integration or use a temporary compatibility preload matching `configure/update_state/set_selected`.
- [ ] **Step 7: Run the geometry scene and parser.** Parse the Godot project and launch the debug scene for a visual check from three camera distances; acceptance: clearly quadrupedal from every view and gait not tangled at high speed.
- [ ] **Step 8: Commit creature-model slice.** `git add godot/scripts/CreatureView.gd godot/scenes/CreatureView.tscn godot/tests/CreatureViewHarness.gd godot/tests/CreatureViewHarness.tscn godot/scripts/CreatureVisual.gd && git commit -m "feat: render quadrupedal wildlife with natural gait"`.

### Task 5: Split the Godot application into focused scenes and scripts

**Files:**
- Modify: `godot/Main.tscn`
- Replace: `godot/scripts/Main.gd`
- Create: `godot/scenes/WorldView.tscn`, `godot/scripts/WorldView.gd`
- Create: `godot/scenes/HUD.tscn`, `godot/scripts/HUD.gd`
- Create: `godot/scenes/CreatureInspector.tscn`, `godot/scripts/CreatureInspector.gd`
- Create: `godot/scenes/WorldTools.tscn`, `godot/scripts/WorldTools.gd`
- Create: `godot/scripts/SimulationClient.gd`
- Modify: Task 4 `CreatureView` integration

**Interfaces:**
- `SimulationClient.state_updated(state: Dictionary)`, `connection_changed(connected: bool, message: String)`, `command_completed(action: String, ok: bool, message: String)` signals; public `request_state()` and `send_command(payload: Dictionary)` methods.
- `WorldView.set_state(state: Dictionary)`, `set_selected(creature_id: int)`, `set_follow(creature_id: int)`, `reset_camera()`, and `world_clicked(world_position: Vector2)` signal.
- `HUD.set_state(state: Dictionary)`, `set_selection(creature: Dictionary)`, and signals `pause_requested`, `step_requested`, `speed_requested(ticks_per_second: int)`, `inspect_requested`, `world_tools_requested`.
- `CreatureInspector.set_creature(data: Dictionary)`, `set_open(open: bool)`, and `closed` signal.
- `WorldTools.set_state(state: Dictionary)`, `set_open(open: bool)`, and `command_requested(payload: Dictionary)` signal.

- [ ] **Step 1: Create scene-contract smoke checks.** Check Main scene loads all named child scenes and each exposes required methods/signals; add a Godot headless smoke script or use editor parser plus runtime instantiation to verify.
- [ ] **Step 2: Create `SimulationClient`.** Move HTTP requests, polling timer, retry/backoff, state parse, and command response handling out of `Main.gd`; enforce one in-flight state request and display offline/connected state through signals.
- [ ] **Step 3: Create `WorldView`.** Move habitat/camera/creature/resource sync and world projection into this script; avoid repeated full-node creation and preserve centered coordinate mapping.
- [ ] **Step 4: Create `HUD`.** Make top HUD show world/season/population and one active weather alert. Bottom dock has named pause, step, three practical speeds, selected action/reason, and at most four primary needs. The unselected state prompts how to select.
- [ ] **Step 5: Create `CreatureInspector`.** Show a readable summary first (name/ID, action and reason, energy/hunger, injury/age, nearby dependents), then collapsible Instincts, Genome, Encounters, and Lineage sections. Do not show satisfaction component charts in the default view.
- [ ] **Step 6: Create `WorldTools`.** Group weather and food placement behind one discoverable tools button. Every placed food intervention uses the existing command contract; Escape cancels placement; show an inline explanation before scheduling weather.
- [ ] **Step 7: Reduce `Main.gd` to composition and routing.** It wires signals, remembers selection/follow state, switches tool modes, and routes commands through `SimulationClient`; it does not construct individual controls, poll HTTP, implement mesh behavior, or calculate creature metrics.
- [ ] **Step 8: Run Godot parse and scene smoke.** Run Godot headless editor parse and launch scene with/without Python bridge; expected: normal habitat with a useful disconnected banner, then live state and input updates after bridge connection.
- [ ] **Step 9: Commit modular UI slice.** `git add godot && git commit -m "refactor: separate Vikasa habitat HUD and inspector"`.

### Task 6: Present instincts clearly and complete interaction/accessibility states

**Files:**
- Modify: `godot/scripts/HUD.gd`, `godot/scenes/HUD.tscn`
- Modify: `godot/scripts/CreatureInspector.gd`, `godot/scenes/CreatureInspector.tscn`
- Modify: `godot/scripts/WorldView.gd`
- Modify: `godot/project.godot`
- Add/update actual screenshot evidence under `docs/images/` only from the redesigned build.

**Interfaces:**
- HUD gets six named drive values and action reason from bridge; visual primary meters are energy, hunger, health, and the currently dominant instinct (not six equal-weight tiny charts).
- Inspector lists all six drives with plain-language descriptions, normal range/urgency color, and top two competing action scores on demand.

- [ ] **Step 1: Pin UI data mapping.** Add a lightweight GDScript check mapping each six-key bridge drive to its correct label/value/color and test that absent optional values produce “unknown”/neutral, not a fabricated 0% emergency.
- [ ] **Step 2: Add action explanation.** For each action, map to a short verb phrase and reason; if `behavior_reason` is absent, display “Exploring nearby” rather than a parser error.
- [ ] **Step 3: Complete states and interaction.** Add paused/running emphasis, active time-speed state, offline retry state, empty-population/extinction recovery, inspector no-selection prompt, selected-death clear state, hover/focus/pressed feedback, Escape close/cancel, click-empty dismiss, and reset-camera/follow-selection behavior.
- [ ] **Step 4: Check resize and visual hierarchy.** At 1280×720 and 1600×900, verify the habitat occupies at least 70% of the unobstructed center when no inspector is open; at 960×600, inspector becomes an overlay/drawer and controls wrap without hiding the selection/action line.
- [ ] **Step 5: Perform live visual review.** Launch Godot with showcase config and inspect normal, selected animal, paused, active weather, very high population, bridge disconnected, and narrow-window states. Capture fresh screenshots only if the visuals meet the spec; remove or replace stale app screenshots referenced from README.
- [ ] **Step 6: Commit interaction/visual-review slice.** `git add godot docs/images && git commit -m "feat: clarify wildlife needs and simulation controls"`.

### Task 7: Reconcile all documentation and historical plans

**Files:**
- Modify: `README.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/SCIENTIFIC_MODEL.md`
- Modify: `docs/MATHEMATICS.md`
- Modify: `docs/EXPERIMENTS.md`
- Modify: `docs/DEMO_SCRIPT.md`
- Modify: `docs/superpowers/specs/2026-10-04-vikasa-design.md`
- Modify: `docs/superpowers/specs/2026-10-04-vikasa-ecosystem-v2-design.md`
- Modify: `docs/superpowers/plans/2026-10-04-vikasa.md`
- Modify: `docs/superpowers/plans/2026-10-04-vikasa-ecosystem-v2.md`
- Modify: `tests/test_documentation.py`

- [ ] **Step 1: Add documentation contract checks.** Assert README contains launch commands, controls, instincts, and limitations; architecture/math/scientific docs contain the action-arbitration contract and checkpoint compatibility; superseded plans contain “historical/superseded” status and point to the delivered docs.
- [ ] **Step 2: Run documentation checks to see existing mismatch.** Run `pytest tests/test_documentation.py -q`; expected: new requirements fail before docs are updated.
- [ ] **Step 3: Update README for actual usage.** Document one recommended launch path, how to observe/select/follow/pause/change speed/inspect/use world tools, requirements, known limitations, and where the math/science details live. Remove stale UI images and claims.
- [ ] **Step 4: Update architecture/science/math.** Describe actual ownership and data flow, checkpoint version/migrations, six drive equations and utilities/hysteresis/costs, action state, home range, dependent care, inherited trait effects, deterministic choices, and calibrated limitations. Ensure no unimplemented feature is written in present tense.
- [ ] **Step 5: Update experiments/demo.** Include same-seed reproducibility, low-food survival/foraging, hazard avoidance, dependent care trade-offs, mate readiness, territory scarcity/migration, and mutation selection experiments with actual CLI/config commands. Write demo steps around the in-world action/reason and selected needs.
- [ ] **Step 6: Mark old docs historical.** Preserve original planning intent while adding a top note that the plan/spec is historical and superseded, link to this approved spec and current implementation docs, and remove any language that confuses planned v2 deployment/remote push with delivered work.
- [ ] **Step 7: Run docs verification.** Run `pytest tests/test_documentation.py -q` and `git diff --check`; expected: no outdated present-tense system claims, no broken relative links, only extant command names.
- [ ] **Step 8: Commit documentation slice.** `git add README.md docs tests/test_documentation.py && git commit -m "docs: align Vikasa guidance with wildlife model"`.

### Task 8: Integrated validation and handoff

**Files:**
- No new files expected unless validation finds a contract fix in its owning task.

- [ ] **Step 1: Run targeted and existing Python validation.** Run behavior, engine, reproducibility, checkpoint, CLI, docs tests; run `python -m compileall -q src/evolution_sim`; run `vikasa validate --config config/showcase.json`; run `git diff --check`.
- [ ] **Step 2: Run Godot validation.** Run Godot 4.7.2 headless editor parse; instantiate Main scene; run connected and disconnected launches; exercise selection, follow, camera reset/orbit, pause/resume, one step, speed, food placement/cancel, weather scheduling, inspector sections, resize, and selection after death.
- [ ] **Step 3: Check deterministic action history.** Run two equal showcase engines for a bounded tick interval with equal interventions; compare snapshots/action logs/checkpoint continuation. Do not compare screenshots as a determinism signal.
- [ ] **Step 4: Review visual evidence and diff.** Confirm quadruped silhouette at three zoom levels, leg gait, habitat area ratio, text sizes/contrast, no dashboard wall, and complete documentation screenshots. Review `git status --short` and `git diff --stat`; keep prior task changes and user work intact.
- [ ] **Step 5: Summarize honestly.** Report implemented behavior, major visible changes, docs updated, exact validation run, and any visual/runtime limitation. Do not claim biological realism, religion, or unimplemented species roadmap.

## Plan self-review

- **Spec coverage:** UI hierarchy and responsive states: Tasks 5–6; quadruped models/gait: Task 4; six drives/action arbitration/care/territory/risk: Tasks 1–2; persistence and bridge: Task 3; deterministic behavior: Tasks 2–3 and 8; all documentation: Task 7; visual review/limitations: Tasks 6 and 8.
- **Placeholder scan:** no TBD/TODO steps are used; every planned component and validation command is named.
- **Interface consistency:** later scene work consumes the exact `BehaviorState` and bridge contract from Tasks 1–3; component public signals/methods are established in Task 5 and consumed by Main composition.
- **Review focus coverage:** each of the five failure modes maps to a named test or manual acceptance step in Tasks 1–6.
- **Scope check:** the plan does not include the broader aspirational species taxonomy/ecosystem roadmap, wholesale engine migration, cloud/paid services, or claims of human cognition.

