extends SceneTree
## Capture real local bridge data and validate both large and compact layouts.
func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var main = load("res://Main.tscn").instantiate()
	root.add_child(main)
	await create_timer(3.0).timeout
	if not main.client.connected:
		push_error("Presentation capture needs the local bridge")
		quit(1)
		return
	var args := OS.get_cmdline_user_args()
	if "--genetics" in args:
		main.hud.observatory.tab = 2
		main.hud.observatory._configure()
		main.hud.observatory.set_state(main.latest_state)
	if "--evolution" in args:
		main.hud.observatory.tab = 3
		main.hud.observatory._configure()
		main.hud.observatory.set_state(main.latest_state)
	if "--ecology" in args:
		main.hud.observatory.tab = 4
		main.hud.observatory._configure()
		main.hud.observatory.set_state(main.latest_state)
	if "--tools" in args: main.tools.set_open(true)
	if "--habitat-map" in args:
		await process_frame
		main.hud.observatory.habitat_map.get_parent().get_parent().scroll_vertical = 10000
	if "--selected" in args and not main.latest_state.creatures.is_empty():
		var subject: Dictionary = main.latest_state.creatures[0]
		var separation := INF
		for creature in main.latest_state.creatures:
			var d := Vector2(creature.position[0], creature.position[1]).distance_to(Vector2(600, 380))
			if d < separation: subject = creature; separation = d
		main._select(int(subject.id))
		main.world.set_follow(int(subject.id))
		main.world.distance = 44
		main.world._update_camera()
	await create_timer(0.4).timeout
	await RenderingServer.frame_post_draw
	var mode := "genetics" if "--genetics" in args else "overview"
	if "--evolution" in args: mode = "evolution"
	if "--ecology" in args: mode = "ecology"
	if "--habitat-map" in args: mode = "habitat-map"
	if "--tools" in args: mode = "weather-tools"
	if "--selected" in args: mode = "selected"
	var path := "user://presentation-%dx%d-%s.png" % [root.size.x, root.size.y, mode]
	root.get_texture().get_image().save_png(path)
	print("CAPTURE ", OS.get_user_data_dir(), "/", path.get_file())
	var top: Rect2 = main.hud.get_node("TopStatus").get_global_rect()
	var dock: Rect2 = main.hud.get_node("ObservationDock").get_global_rect()
	var charts: Rect2 = main.hud.observatory.get_global_rect()
	assert(top.end.x <= root.size.x and dock.end.y <= root.size.y, "HUD exceeds viewport")
	assert(charts.position.y >= top.end.y and charts.end.y <= dock.position.y, "Charts overlap HUD")
	print("LAYOUT PASS ", root.size, " history=", main.latest_state.get("history", []).size())
	main.queue_free()
	await process_frame
	quit(0)
