extends SceneTree

var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("_run")

func check(condition: bool, message: String) -> void:
	if not condition: failures.append(message)

func _run() -> void:
	var main = load("res://Main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	var world = main.get_node("WorldView")
	var hud = main.get_node("Interface/HUD")
	var inspector = main.get_node("Interface/CreatureInspector")
	var tools = main.get_node("Interface/WorldTools")
	var client = main.get_node("SimulationClient")
	# Keep this fixture smoke independent of any host bridge process.
	client._timer.stop()
	client._request.cancel_request()
	client._busy = false
	for contract in [
		[world, ["set_state", "set_selected", "set_follow", "reset_camera", "clear_snapshot"], ["world_clicked", "creature_clicked"]],
		[hud, ["set_state", "set_selection"], ["pause_requested", "step_requested", "speed_requested", "inspect_requested", "world_tools_requested", "reset_requested", "follow_requested"]],
		[inspector, ["set_creature", "set_open"], ["closed"]],
		[tools, ["set_state", "set_open"], ["command_requested", "placement_changed"]],
		[client, ["request_state", "send_command"], ["state_updated", "connection_changed", "command_completed"]]
	]:
		for method in contract[1]: check(contract[0].has_method(method), "Missing method " + method)
		for event in contract[2]: check(contract[0].has_signal(event), "Missing signal " + event)
	var animals: Array = []
	for i in range(18):
		animals.append({"id": i, "position": [450 + (i % 6) * 55, 285 + (i / 6) * 65], "velocity": [0.8, 0.3], "size": 4.0 + i * 0.1, "speed": 2.5, "perception": 2.2, "metabolism": 0.6,
			"energy_ratio": 0.7, "hunger": 0.3, "injury": 0.08, "age": 195, "aggression": 0.25, "resilience": 0.6, "sociability": 0.5,
			"behavior": "forage", "behavior_reason": "Following food scent because hunger is rising.", "dependent_ids": [17] if i == 3 else [],
			"drives": {"survival": 0.2, "foraging": 0.6, "mating": 0.1, "offspring_care": 0.0, "danger_avoidance": 0.1, "territory": 0.3}, "parents": []})
	var state := {"world": {"width": 1200, "height": 760}, "seed": 2026, "population": animals.size(), "tick": 240,
		"paused": true, "ticks_per_second": 2, "creatures": animals, "resources": [{"id": 1, "position": [590, 310]}],
		"environment": {"season": "summer", "temperature": 0.7, "active_events": []}}
	main._on_connection(true, "Connected")
	main._on_state(state)
	check(world.creature_views.size() == 18, "Animals did not synchronize")
	var crowded: Dictionary = state.duplicate(true)
	crowded.creatures = []
	crowded.resources = []
	for i in range(260):
		crowded.creatures.append({"id": i, "position": [300 + i % 40, 250 + i % 30], "velocity": [0.4, 0.1], "size": 4.0, "speed": 2.0, "energy_ratio": 0.8})
	for i in range(400):
		crowded.resources.append({"id": i, "position": [250 + i % 50, 220 + i % 35]})
	main._on_state(crowded)
	check(world.creature_views.size() <= 180, "Population rendering exceeded the safe visual budget")
	check(world.resource_views.size() <= 240, "Food rendering exceeded the safe visual budget")
	main._on_state(state)
	var gait_before: float = world.creature_views[0]._gait_phase
	world._process(0.25)
	check(is_equal_approx(gait_before, world.creature_views[0]._gait_phase), "Paused gait advanced")
	check(hud.step_button.disabled == false, "Paused step should be enabled")
	main._select(3)
	check(inspector.visible and hud.needs.visible, "Selection summary did not open")
	check(hud.title.text.contains("#3") and hud.reason.text.contains("hunger"), "Action explanation mismatch")
	main._toggle_follow()
	check(world.follow_id == 3, "Follow failed")
	main._on_ground(Vector2(0.3, 0.3))
	check(main.selected_id == -1 and not main.following and world.follow_id == -1, "Empty click did not dismiss selection/follow")
	main._select(3)
	main._toggle_follow()
	var death_state: Dictionary = state.duplicate(true)
	death_state.creatures = death_state.creatures.filter(func(animal: Dictionary): return int(animal.id) != 3)
	main._on_state(death_state)
	check(main.selected_id == -1 and not main.following and hud.notice.text.contains("no longer alive"), "Selected death did not clear follow/explain")
	main._on_state(state)
	main._select(3)
	var running: Dictionary = state.duplicate(true)
	running.paused = false
	running.ticks_per_second = 48
	main._on_state(running)
	check(hud.status.text == "Running" and hud.step_button.disabled and hud.speed_buttons[48].button_pressed, "Running/speed state mismatch")
	check(hud.observatory.visible and hud.observatory.graphs.size() == 3, "Live observatory graphs missing")
	main._on_state(state)
	var payloads: Array = []
	tools.command_requested.connect(func(payload: Dictionary): payloads.append(payload))
	tools.placing_food = true
	tools.placement_changed.emit(true)
	main._on_ground(Vector2(0.5, 0.5))
	check(payloads.size() == 1 and payloads[0].action == "food" and payloads[0].x == 0.5, "Food command contract mismatch")
	check(not tools.placing_food and not world.placement_mode, "Placement failed to finish")
	tools.placing_food = true
	tools.placement_changed.emit(true)
	var escape := InputEventKey.new()
	escape.keycode = KEY_ESCAPE
	escape.pressed = true
	main._unhandled_key_input(escape)
	check(not tools.placing_food and not inspector.visible, "Escape did not cancel")
	tools.weather_choice.select(3)
	tools._schedule()
	check(payloads.size() == 2 and payloads[1].kind == "wildfire" and payloads[1].duration == 160, "Weather command mismatch")
	main._on_connection(false, "Simulation offline · Reconnecting")
	check(hud.pause_button.disabled and tools.food_button.disabled, "Offline controls not disabled")
	check(hud.notice.text.contains("offline"), "Offline message missing")
	check(world.creature_views.is_empty() and main.latest_state.is_empty(), "Offline snapshot remained selectable")
	main._on_state({"world": state.world, "seed": 2026, "population": 0, "creatures": [], "resources": [], "paused": true})
	check(world.creature_views.is_empty() and not hud.needs.visible, "Empty world did not clear selection")
	check(hud.notice.text.contains("extinct"), "Extinction recovery prompt missing")
	# Optional presentation capture: fixture, never described as a natural outcome.
	var args := OS.get_cmdline_user_args()
	if "--capture" in args:
		main._on_connection(true, "Connected")
		main._on_state(state)
		main._select(3)
		main.world.reset_camera()
		main.world.distance = 62
		main.world._update_camera()
		for frame in range(12): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://task5-selected.png")
		main.inspector.set_open(false)
		main._select(-1)
		for frame in range(3): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://task5-overview.png")
		main._on_connection(false, "Simulation offline · Start vikasa godot; reconnecting automatically.")
		for frame in range(3): await process_frame
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("user://task5-offline.png")
		print("Capture directory: ", OS.get_user_data_dir())
	if failures.is_empty(): print("SCENE CONTRACT SMOKE PASS: contracts, sync, selection, follow, food, weather, Escape, offline and empty states")
	else:
		for failure in failures: push_error(failure)
	main.queue_free()
	await process_frame
	quit(0 if failures.is_empty() else 1)
