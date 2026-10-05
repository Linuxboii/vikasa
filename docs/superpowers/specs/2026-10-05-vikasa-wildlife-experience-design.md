# Vikasa Wildlife Experience and Instinct Model

**Status:** Design approved by user; awaiting written-spec review  
**Date:** 2026-10-05  
**Supersedes:** the previous experimental Godot HUD and the behavioral assumptions they exposed; it does not approve the broader unimplemented ecosystem roadmap.

## 1. Intent

Make Vikasa easy and inviting to observe for someone who has never used the simulator. The habitat and creatures must be the visual focus. The interface should borrow the legibility and direct manipulation of a life simulation such as The Sims, without copying its human framing. Organisms should read as low-slung, four-legged wild animals; their actions should follow visible survival and social pressures rather than arbitrary wandering, labels, or player commands.

The six approved instinct families are survival, foraging, mating, offspring care, danger avoidance, and territory. Presentation quality is the primary acceptance concern, followed by clarity of the simulation. Preserve the existing deterministic Python engine and local bridge where practical; improve their structure instead of replacing them wholesale.

## 2. Current-state diagnosis

- `godot/scripts/Main.gd` owns scene construction, API polling, camera, creature/resource synchronization, input, command dispatch, environment lighting, and both information panels. This makes layout changes risky and leaves no clear separation between play, inspect, and intervention.
- Two always-visible data columns and a crowded bottom row compete with the habitat. The field has no clear visual hierarchy between essential life information and research detail.
- `CreatureVisual.gd` assembles spheres and capsules into a tall, upright face-and-torso composition. Its silhouette reads as humanoid even though no human form is intended.
- The Python engine currently steers mostly toward food or alpha encounters, with wandering when neither applies. Mating is proximity/eligibility-based. Hunger is derived from energy, not an independent decision policy; offspring have no care phase; territory and explicit danger avoidance are absent.
- The UI exposes satisfaction and many population figures but does not answer the user's central question: “What is this creature trying to do, and why?”
- Existing documentation includes both delivered features and a much larger aspirational v2 roadmap. It must be reconciled so that planned behavior is never described as already implemented.

## 3. Product principles

1. **Habitat first:** the world receives the largest uninterrupted area; overlays and controls remain visually subordinate.
2. **Progressive disclosure:** show only essential run status at rest. Detailed population, history, genetics, and research measures appear when requested.
3. **Explain behavior in plain language:** show the current action and strongest motive (“following food scent — hunger is high”), with optional scores for research use.
4. **Animals, not people:** four-point ground contact, horizontal spine, animal-like head/muzzle, tail, and genome-shaped appendages. No upright posture, human shoulders/arms, or portrait-like face framing.
5. **Instincts are pressures, not scripts:** behavior emerges from changing needs, perceived opportunities, costs, and risks. Avoid fixed loops such as “alpha always attacks”.
6. **Determinism remains observable:** for a fixed configuration, seed, and intervention sequence, the same simulation decisions and outcomes recur. Rendering and UI state never consume simulation randomness.
7. **Presentation is part of correctness:** readable at the supported window size, usable without the inspector, and clear in normal, selection, paused, alert, empty, and disconnected states.

## 4. Experience design

### 4.1 Primary screen

The default screen is a wide, uncluttered habitat view. It has three compact zones:

```text
┌ world name · year/season · population · weather · menu ┐
│                                                       │
│             living habitat (primary view)             │
│       creatures, food/water/cover, subtle alerts       │
│                                                       │
├ selected creature: action + 3-4 clear need meters ────┤
│ pause · step · natural / fast / very fast · observe    │
└───────────────────────────────────────────────────────┘
```

- The always-visible top strip contains only world/season, living population, one salient environmental condition, and access to secondary views.
- The bottom dock provides pause/resume, single step, a small set of labeled time speeds, and observation/intervention tools. Every control uses plain-language names, tooltips, visible pressed/disabled states, and keyboard focus.
- The selected creature's action and primary needs occupy a distinct, readable portion of the dock. With no selection, show a helpful observation hint instead.
- Selecting an animal opens one inspector drawer, not two permanent columns. Its default summary answers current action, dominant instinct, energy/hunger, health/injury, age, and nearby dependents. Genetics, satisfaction history, combat, and lineage sit in secondary collapsible sections.
- Clicking an inspector creature centers/follows it; clicking open habitat space dismisses selection unless a placement mode is active. Camera orbit/zoom remain discoverable and recoverable with a reset-view control.
- Weather and food controls are grouped under “World tools” and are visually distinct from observation/time controls, preventing accidental intervention.

### 4.2 Visual language and habitat

- Use a cohesive naturalist palette: warm earth/leaf base, a restrained pale accent for selection, and distinct but muted semantic colors for hunger, health, danger, and reproduction.
- Establish typography by role: large readable value or creature name, concise action line, sentence-case labels, and small tabular figures for changing counters. Avoid many tiny all-caps labels.
- Terrain uses meaningful, consistent cues: edible resources, water access, and shelter/cover must be visually distinguishable from decorative ground detail. Weather overlays are legible without hiding animals.
- Creature selection uses a restrained outline/ground marker, not a crown/halo that confuses dominance with selection. Alpha/challenge and injury have separate subtle signals.
- Activity feedback is attached to creatures as short action labels/icons only when useful; do not permanently label every animal.
- Support resizing by scaling/reflowing dock and inspector; the habitat must not be obscured by fixed width side panels at smaller windows.

## 5. Creature visual contract

Replace the existing upright primitive assembly with an explicitly quadrupedal, ground-hugging procedural creature model:

- Main body is elongated along the travel axis, with body center low and weight carried over four articulated legs.
- Head extends forward from the spine; muzzle and sensory features point along travel. Tail extends back from the pelvis. All appendages remain anatomically attached and grounded.
- Procedural form uses a coherent custom mesh or a small number of carefully blended volumes, not a stack of same-sized spheres. Silhouette variety comes from size, proportions, head/body ratio, leg length, tail shape, and crest/sensory shape. The current six body genes and three temperament traits inform bounded shape/material variation without inventing unsupported genes.
- A gait phase animates front/rear leg pairs with body bob proportional to speed; resting, feeding, fleeing, courtship, caring, and threat display have distinguishable low-cost poses or cues. Blend transitions rather than teleporting poses.
- Materials are matte, natural, and readable under the chosen habitat lighting. Energy state must not make the body transparent. Color variation remains contrast-safe against the ground.
- LOD or reduced-detail behavior must preserve visible silhouette and selection at typical camera distances.

## 6. Instinct and behavior model

### 6.1 State and perception

Each creature needs a bounded, serializable current behavior, its start tick, selected target (if any), and normalized drive values for inspection. A new `BehaviorController`-like module owns decision scoring; `SimulationEngine` continues to own ordering, movement, energy, encounters, reproduction, and death. Decisions run in stable creature-ID order and query existing spatial hashes rather than introducing all-pairs work.

The behavior inventory is deliberately compact: forage, rest/recover, seek mate, tend young, avoid threat, patrol/return to home range, challenge/defend, and explore. “Explore” is a fallback, not the default for a creature with an urgent need. Alpha status never implies aggression by itself.

### 6.2 Drive definitions

All drive signals are normalized to `[0, 1]`, bounded, and explainable in the inspector.

- **Survival:** increases as normalized energy reserve falls or injury/health worsens. For example, `D_survival = clamp(0.65 * (1 - E/Emax) + 0.35 * I, 0, 1)`.
- **Foraging:** hunger urgency modulated by sensed food reward and travel cost. Food-seeking is not useful when no patch is perceived; in that case the creature searches locally or explores while preserving energy.
- **Mating:** zero unless maturity, cooldown, and energy readiness allow reproduction; otherwise combines readiness and the best compatible nearby mate's proximity/availability. Encountering a mate does not force reproduction if survival is urgent.
- **Offspring care:** nonzero only for a living dependent offspring within a care radius. It is stronger for younger/more vulnerable young and when the young are hungry/injured or exposed. Care creates a proximity/guarding action and measurable juvenile benefit; it must not duplicate reproduction count.
- **Danger avoidance:** combines local threat, relative size/aggression, injury, and active hazards. A strong immediate danger response can override all non-emergency actions.
- **Territory:** attraction to a persistent home center/range, moderated by food/water, crowding, and danger. A challenger may provoke a low-frequency display/contest only when motivation, relative strength, and local conditions make it worthwhile; territory maintenance is not constant combat.

The existing heritable body genome and temperament remain the source of individual differences. Size/speed/perception/metabolism/reproductive traits influence the costs and opportunities an animal experiences; inherited aggression modulates defense/challenge, resilience modulates injury and hazard response, and sociability modulates care, courtship, and tolerance. These traits already inherit with mutation and are filtered by survival/reproductive outcomes, so repeated generations can adapt without inventing a hidden “instinct gene” or treating a single lifetime behavior as evolution.

Initial home range is centered near birthplace with a seeded radius. Home position/radius and behavior state persist in checkpoints; bounded offspring variation lets ranges adapt across generations. Migration is allowed when expected habitat utility outside the range exceeds home utility by a configurable margin for a sustained period.

### 6.3 Action scoring and persistence

For creature `i` and candidate action `a`, compute a bounded utility:

```text
U(i,a) = Σ_k w(a,k) · D(i,k)
       + expected_reward(i,a)
       - movement_energy_cost(i,a)
       - exposure_risk(i,a)
       - social_conflict_cost(i,a)
```

where `k` ranges over the six drives and `w(a,k)` is a documented action/drive affinity. Rewards are based on what this creature can currently perceive, not hidden global resources. Risks include predicted hazard exposure and contest injury/death probabilities. Invalid actions receive negative infinity (for example, mating while immature, or care with no dependent young).

To avoid robotic action switching, retain the current valid action unless another action exceeds it by a configurable hysteresis margin, except that a danger response or critical survival threshold can preempt immediately. Use a seeded softmax tie-break among near-equal valid scores, or deterministic score/ID ordering if it is simpler to audit; whichever is selected, document it and keep all RNG in the engine. Do not inject per-render-frame decisions.

Movement uses the selected action target and smooth steering. Seek-food chooses the best perceived patch by expected gain minus path cost; retreat chooses a low-threat direction; care approaches or follows dependents and can transfer a bounded amount of surplus parental energy to a hungry dependent at an explicit parent energy cost; patrol samples the home-range boundary; rest minimizes movement while injured/energy-poor. Reproduction occurs only when the mating action is selected and both partners remain eligible. A courtship/avoidance state prevents instant pair churn.

### 6.4 Naturalism, safety, and observability

- Hunger, low energy, and injury increase foraging/rest urgency; starvation remains delayed rather than instant.
- Wild encounters remain uncommon except under credible competition/defense pressure. Fight probability has an explicit upper cap; lethality rises with pre-existing injury/weakness and is logged with cause. Winners may become more likely to defend/challenge, but high injury, danger, or energy deficit can suppress that tendency.
- Dependent young receive a documented care benefit when a parent stays nearby; care consumes energy/time and therefore creates a trade-off.
- Every chosen action records a concise reason from its leading drive/reward/risk terms. This is for UI explanation and debugging, not a player-facing raw formula dump.
- Parameters live in validated configuration with backwards-compatible defaults. Values and score weights are documented in `docs/MATHEMATICS.md` and `docs/SCIENTIFIC_MODEL.md`.

## 7. Data contracts and persistence

- Extend organism/checkpoint snapshots with action state, action-start tick, drive vector, home range, and any care state needed to resume a run exactly.
- Extend the local bridge payload with only UI-required information: current behavior/reason, normalized drive values, target IDs/coordinates when safe, dependent IDs, and home range. Preserve existing endpoints/commands unless the redesign proves a contract change necessary.
- Bump checkpoint schema from v2 only if new persisted state requires it. Provide deterministic v1 and v2 migration defaults; never overwrite source checkpoints during load/migration.
- Rendering reads snapshots only. Input commands are validated and routed through one UI command service. UI polling cadence must not change simulation tick ordering.
- Keep current CLI, batch, export, and existing Pygame entry point behavior unless explicitly listed as affected. The new Godot experience remains the primary visual frontend.

## 8. Structural refactor boundaries

Split the Godot responsibilities into a small scene tree with clear ownership:

- `WorldView`: camera, terrain, resource/environment visuals, and world-coordinate conversions.
- `CreatureView`/`CreatureFactory`: animal mesh, gait, action animation, selection feedback.
- `HUD`: top status, bottom time controls, selected-creature needs strip.
- `CreatureInspector`: focused details and progressive-disclosure sections.
- `WorldTools`: validated food/weather interventions and placement mode.
- `SimulationClient`: polling, command requests, connection/retry state, and typed parsing boundary.

Prefer dedicated `.tscn` sub-scenes and small scripts over constructing all controls in a single large script. Keep visual scripts unaware of engine internals. Data keys should be centralized or clearly documented and have safe defaults. UI update rates should avoid recreating whole panel trees every poll; update existing controls and use bounded history lists.

Python ownership is similarly explicit: drive calculation/action utility belongs in a focused behavior module; engine tick owns deterministic orchestration; environment/space/reproduction modules keep their distinct concerns. Avoid extracting modules without reducing coupling or test complexity.

## 9. Documentation and truthfulness

Update all user-facing and project design documentation touched or contradicted by the redesign:

- `README.md`: what the experience is, installation/run commands, controls, supported features, and limitations.
- `docs/ARCHITECTURE.md`: actual ownership/data flow, modular Godot scene, engine/bridge boundaries, checkpoint versioning.
- `docs/SCIENTIFIC_MODEL.md`: implemented instincts, action selection, care/home-range assumptions, fight/starvation limits, and the distinction between modeled behavior and cognition.
- `docs/MATHEMATICS.md`: equations, normalization, action weights/configuration, hysteresis/choice policy, and examples.
- `docs/EXPERIMENTS.md`: reproducible scenarios that demonstrate each instinct and environmental interactions; no unsupported claims about realism.
- `docs/DEMO_SCRIPT.md`: refreshed demonstration flow that visibly answers “what is it doing/why?” and shows selection/control clarity.
- Existing `docs/superpowers/specs/*` and `docs/superpowers/plans/*`: mark superseded plans/specs as historical with links to this design and the eventual delivered contract; remove or clearly label aspirational acceptance/deployment claims that do not apply. Do not rewrite history as though the new scope had always existed.
- Any UI screenshots/images that are retained in the README or demos must be regenerated from the actual redesigned app; do not leave stale screenshots depicting the rejected UI.

## 10. Acceptance criteria

1. The habitat remains the dominant visual region at target resolution; no permanent twin sidebars or multi-row control wall.
2. The bottom dock and inspector have clear hierarchy, readable labels, predictable selection/dismissal, responsive layout, hover/pressed/focus states, and clear offline/empty/paused/error states.
3. Ordinary creatures read immediately as wild quadrupeds in silhouette; no current humanoid body assembly remains. Gait and action cues are visible at normal observation scale.
4. Every creature has an inspectable current action and six normalized drives. Action and displayed reason match the behavior actually executed.
5. All six instincts measurably affect action choice; parental energy transfer measurably affects dependent survival/development; heritable traits produce measurable between-generation adaptation; home-range affinity measurably affects patrol while scarcity can drive migration.
6. Urgent danger/survival appropriately overrides mating/exploration. Poor health, energy, exposure, and travel have explicit costs.
7. Low-frequency contest behavior remains possible, but alpha status alone does not cause attacks. Lethality is rare in healthy matchups and rises under injury/weakness; death cause and encounter outcomes are observable.
8. Repeated same-seed runs with the same interventions produce equivalent state and action history; UI speed/frame/window state does not affect results.
9. Existing checkpoints migrate without source overwrite and resumed state preserves action/drive/home-range behavior.
10. Existing CLI and Python UI still start; Godot scene parses and launches with a connected bridge; the key controls are exercised interactively.
11. All documentation named in section 9 matches the implementation, states model limitations, and does not claim aspirational species/speciation, world systems, or deployment steps are complete.
12. Visual review is completed on the normal window, selected creature, paused run, active environmental pressure, empty selection, narrow window, and bridge-disconnected state. If image capture is unavailable, report that limitation rather than claiming visual verification.

## 11. Exclusions

- Human-like cognition, language, or a literal generated religion.
- Claiming the simulation is biologically predictive or “as realistic as real life.” It remains an explainable artificial-life approximation.
- Full species taxonomy/speciation, detailed ecology grids, disease transmission, or the wider unimplemented v2 roadmap unless implementation discovery shows a direct dependency and the user re-approves the scope.
- Photorealistic downloaded assets or new paid/external services. Procedural models and the current local stack are preferred.
- Replacing the working simulation engine, bridge, CLI, or checkpoint system wholesale.

