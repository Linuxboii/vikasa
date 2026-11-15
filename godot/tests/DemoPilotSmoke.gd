extends SceneTree
## Headless check of the presentation autopilot (`vikasa godot --demo`).
## Run: godot --headless --path godot -s res://tests/DemoPilotSmoke.gd

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("_run")

func check(condition: bool, message: String) -> void:
	if not condition: failures.append(message)

func _run() -> void:
	var main = load("res://Main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	main.get_node("SimulationClient").stop_polling()
	main.stagger = false
	main.skip_intro = true
	main.start_demo()
	await process_frame
	var pilot: DemoPilot = main.demo_pilot
	check(pilot != null and pilot.active, "Autopilot did not start")
	pilot._process(5.0)
	check(pilot.elapsed == 0.0, "Tour clock ran before the first animals appeared")
	main._intro_played = true
	pilot._process(10.0)
	check(main.director, "Director camera did not start at the first step")
	check(pilot._title.text == "Vikasa · Living Biome", "First narration missing")
	pilot._process(45.0)
	check(main.view_mode == "dynasty", "Dynasty lens step did not apply")
	pilot._process(36.0)
	check(main.view_mode == "natural", "Lens did not return to natural")
	check(main.world.atmos.daylight_mode == "night", "Night step did not apply")
	pilot._process(200.0)
	check(pilot.elapsed < DemoPilot.LOOP_AT, "Tour did not loop")
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_A
	pilot._input(key)
	check(not pilot.active, "A key press did not hand control back")
	check(not main.director, "Director stayed on after the presenter took control")
	check(main.world.atmos.daylight_mode == "cycle", "Daylight was not restored")
	await create_timer(1.0).timeout
	check(main.demo_pilot == null, "Autopilot overlay was not removed")
	if failures.is_empty(): print("DEMO PILOT SMOKE PASS: start gate, narration, director, lenses, night, loop, hand-back")
	else:
		for failure in failures: push_error(failure)
		print("DEMO PILOT SMOKE FAIL")
	main.queue_free()
	quit(1 if not failures.is_empty() else 0)
