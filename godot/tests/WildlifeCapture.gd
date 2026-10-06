extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var main = load("res://Main.tscn").instantiate()
	main.get_node("SimulationClient").api = "http://127.0.0.1:18767" if "--offline" in args else "http://127.0.0.1:8767"
	root.add_child(main)
	await create_timer(4.5).timeout
	if "--offline" not in args:
		if not main.client.connected or main.latest_state.get("creatures", []).is_empty():
			push_error("Wildlife capture: bridge not ready")
			quit(1)
			return
		if "--selected" in args:
			# Choose a central animal so the drawer does not cover the subject.
			var best: Dictionary = main.latest_state.creatures[0]
			var best_distance := INF
			for animal in main.latest_state.creatures:
				var d := Vector2(animal.position[0], animal.position[1]).distance_to(Vector2(600, 380))
				if d < best_distance: best_distance = d; best = animal
			main._select(int(best.id))
			main.world.set_follow(int(best.id))
			main.world.distance = 44
			main.world._update_camera()
			if "--instincts" in args:
				var content = main.inspector.get_child(0).get_child(0)
				for child in content.get_children():
					if child is Button and child.text.begins_with("Instincts"):
						child.button_pressed = true
			if "--choices" in args:
				var content = main.inspector.get_child(0).get_child(0)
				for child in content.get_children():
					if child is Button and child.text.begins_with("Action choices"): child.button_pressed = true
				await process_frame
				main.inspector.get_child(0).ensure_control_visible(main.inspector.scores_label)
		if "--crowded" in args:
			# A labeled rendering stress fixture, never a claimed natural population.
			var fixture: Dictionary = main.latest_state.duplicate(true)
			var animals: Array = []
			for i in range(600):
				var animal: Dictionary = fixture.creatures[i % fixture.creatures.size()].duplicate(true)
				animal.id = i + 10000
				animal.position = [40 + (i % 30) * 38, 35 + (i / 30) * 34]
				animals.append(animal)
			fixture.creatures = animals
			fixture.population = 600
			fixture.paused = true
			main.client._timer.stop()
			main.client._request.cancel_request()
			main._on_state(fixture)
			main.hud.set_notice("600-animal rendering fixture · controlled visual stress check")
		print("Actual showcase tick=", main.latest_state.tick, " population=", main.latest_state.population, " paused=", main.latest_state.paused, " weather=", main.world._weather_kind)
	for frame in range(12): await process_frame
	Input.warp_mouse(Vector2(8, 8))
	await create_timer(0.5).timeout
	var size := root.size
	print("Layout viewport=", size, " dock=", main.hud.get_node("ObservationDock").get_global_rect(), " top=", main.hud.get_node("TopStatus").get_global_rect())
	assert(main.hud.get_node("TopStatus").get_global_rect().end.x <= size.x)
	assert(main.hud.get_node("ObservationDock").get_global_rect().end.y <= size.y)
	if "--selected" in args:
		assert(main.hud.reason.get_global_rect().end.x <= size.x and main.hud.reason.get_global_rect().end.y <= size.y)
		assert(main.inspector.get_global_rect().size.y > 140)
		assert(main.inspector.get_global_rect().end.y <= main.hud.get_node("ObservationDock").get_global_rect().position.y - 10, "Drawer overlaps the needs dock")
	elif "--offline" not in args and "--crowded" not in args:
		var clear_height: float = main.hud.get_node("ObservationDock").get_global_rect().position.y - main.hud.get_node("TopStatus").get_global_rect().end.y
		print("Clear center=", clear_height / float(size.y), " needs=", main.hud.needs.visible, " notice=", main.hud.notice.visible, ": ", main.hud.notice.text)
		if clear_height / float(size.y) < 0.7:
			push_error("Unobstructed center below 70%")
			main.queue_free()
			quit(1)
			return
	await RenderingServer.frame_post_draw
	var mode := "offline" if "--offline" in args else ("selected" if "--selected" in args else "overview")
	if "--instincts" in args: mode = "instincts"
	if "--choices" in args: mode = "choices"
	if "--crowded" in args: mode = "crowded-fixture"
	var path := "user://wildlife-%dx%d-%s.png" % [size.x, size.y, mode]
	root.get_texture().get_image().save_png(path)
	print("Wildlife capture: ", OS.get_user_data_dir(), "/", path.get_file())
	main.queue_free()
	await process_frame
	quit()
