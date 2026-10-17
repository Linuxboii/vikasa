extends SceneTree
## Captures the live showcase for docs and visual review.
## godot --path godot --script res://tests/ShowcaseCapture.gd -- --port 8766 --name overview
##   [--wait 6] [--select] [--follow] [--daylight night|golden|day] [--view dynasty]
##   [--weather storm] [--hide-ui] [--distance 30] [--pitch 0.5] [--yaw 0.3]

func _initialize() -> void:
	call_deferred("_run")

func _arg(name: String, fallback: String) -> String:
	var args := OS.get_cmdline_user_args()
	var index := args.find(name)
	return args[index + 1] if index >= 0 and index + 1 < args.size() else fallback

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	var main = load("res://Main.tscn").instantiate()
	main.get_node("SimulationClient").api = "http://127.0.0.1:" + _arg("--port", "8766")
	main.skip_intro = true
	root.add_child(main)
	main.quality.persist = false
	main.quality.mode = "high"
	main.quality.tier = int(_arg("--tier", "2"))
	main.quality.apply()
	await create_timer(2.5).timeout
	if not main.client.connected:
		push_error("ShowcaseCapture needs a running bridge")
		quit(1)
		return
	var world = main.world
	if "--daylight" in args:
		world.atmos.daylight_mode = _arg("--daylight", "day")
	if "--view" in args and main.has_method("set_view_mode"):
		main.set_view_mode(_arg("--view", "natural"))
	if "--weather" in args:
		main.client.send_command({"action": "weather", "kind": _arg("--weather", "storm"), "intensity": float(_arg("--intensity", "1.0")), "duration": int(_arg("--duration", "90"))})
	await create_timer(float(_arg("--wait", "5"))).timeout
	if "--select" in args or "--follow" in args:
		var best := -1
		var best_distance := INF
		for id in world.swarm.agents:
			var d: float = world.swarm.position_of(id).length()
			if d < best_distance:
				best_distance = d
				best = id
		main._select(best)
		if "--follow" in args: main._toggle_follow()
	if "--director" in args:
		main.set_director(true)
		await create_timer(float(_arg("--director", "9"))).timeout
	if "--legends" in args: main._toggle_legends()
	if "--help" in args: main.hud.help.visible = true
	if "--perf" in args: main.hud.perf.visible = true
	if "--hide-ui" in args and main.has_method("set_ui_hidden"):
		main.set_ui_hidden(true)
	if "--focus" in args:
		var xz := _arg("--focus", "0,0").split(",")
		world.follow_id = -1
		world.focus(Vector3(float(xz[0]), 0, float(xz[1])))
	if "--distance" in args: world.camera.goal_distance = float(_arg("--distance", "60"))
	if "--pitch" in args: world.camera.goal_pitch = float(_arg("--pitch", "0.7"))
	if "--yaw" in args: world.camera.goal_yaw = float(_arg("--yaw", "0.24"))
	await create_timer(float(_arg("--settle", "2.5"))).timeout
	await RenderingServer.frame_post_draw
	var image := root.get_texture().get_image()
	var path := "user://showcase-%s.png" % _arg("--name", "overview")
	if "--docs" in args:
		# Documentation gallery: 1600 px wide JPEGs keep the repository light.
		var width := mini(1600, image.get_width())
		image.resize(width, int(image.get_height() * float(width) / image.get_width()), Image.INTERPOLATE_LANCZOS)
		path = ProjectSettings.globalize_path("res://").path_join("../docs/images/%s.jpg" % _arg("--name", "overview")).simplify_path()
		image.save_jpg(path, 0.88)
	else:
		image.save_png(path)
	print("CAPTURE ", ProjectSettings.globalize_path(path), " fps=", Engine.get_frames_per_second())
	main.queue_free()
	await process_frame
	quit(0)
