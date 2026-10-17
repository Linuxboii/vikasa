extends SceneTree
## Measures real frame cost of the full Main scene against a live local bridge.
## Usage: godot --path godot --script res://tests/PerfProbe.gd -- [--port 8766] [--seconds 12] [--uncapped]
## Prints one machine-readable PERF line so before/after runs can be compared.

func _initialize() -> void:
	call_deferred("_run")

func _arg(name: String, fallback: String) -> String:
	var args := OS.get_cmdline_user_args()
	var index := args.find(name)
	return args[index + 1] if index >= 0 and index + 1 < args.size() else fallback

func _run() -> void:
	var args := OS.get_cmdline_user_args()
	if "--uncapped" in args:
		Engine.max_fps = 0
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	if "--maxfps" in args:
		Engine.max_fps = int(_arg("--maxfps", "60"))
	if "--vsync" in args:
		DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if _arg("--vsync", "on") == "on" else DisplayServer.VSYNC_DISABLED)
	var main = load("res://Main.tscn").instantiate()
	main.get_node("SimulationClient").api = "http://127.0.0.1:" + _arg("--port", "8766")
	root.add_child(main)
	main.skip_intro = true
	await create_timer(1.0).timeout
	main.quality.persist = false
	if "--tier" in args:
		main.quality.mode = ["battery", "balanced", "high", "ultra"][int(_arg("--tier", "2"))]
		main.quality.tier = int(_arg("--tier", "2"))
		main.quality.apply()
	if "--hide-ui" in args: main.set_ui_hidden(true)
	if "--select" in args:
		await create_timer(1.0).timeout
		main._select(main.world.swarm.agents.keys()[0])
		if "--legends" in args: main._toggle_legends()
		if "--no-overlays" in args: main.world.overlays.enabled = false
		if "--no-inspector" in args: main.inspector.set_open(false)
	if "--msaa" in args: root.msaa_3d = int(_arg("--msaa", "0"))
	if "--fxaa" in args: root.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
	if "--grass" in args: main.world.habitat.set_grass_density(float(_arg("--grass", "1")))
	if "--glow" in args: main.world.atmos.glow_allowed = _arg("--glow", "1") == "1"
	if "--shadows" in args: main.world.atmos.sun.shadow_enabled = _arg("--shadows", "1") == "1"
	if "--scale" in args: root.scaling_3d_scale = float(_arg("--scale", "1"))
	if "--no-hud" in args: main.hud.visible = false
	await create_timer(3.0).timeout
	if not main.client.connected:
		push_error("PerfProbe needs a running bridge")
		quit(1)
		return
	if "--frame-mode" in args:
		main.client.frame_updated.disconnect(main._on_frame)
		match _arg("--frame-mode", "none"):
			"swarm": main.client.frame_updated.connect(func(f): main.world.swarm.apply_frame(f))
			"food": main.client.frame_updated.connect(func(f): main.world.food.apply_frame(f, main.world.swarm, false))
			"full": main.client.frame_updated.connect(main._on_frame)
	if "--freeze" in args: main.client.stop_polling()
	if "--no-frames" in args: main.client.streaming = false; main.client._frame_timer.stop()
	if "--no-state" in args: main.client._timer.stop(); main.client._timer.timeout.disconnect(main.client.request_state)
	if "--warm" in args: await create_timer(float(_arg("--warm", "0"))).timeout
	var seconds := float(_arg("--seconds", "12"))
	var frames: PackedFloat32Array = []
	var draw_calls := 0.0
	var objects := 0.0
	var samples := 0
	var flags := {"state": false, "frame": false}
	main.client.state_updated.connect(func(_s): flags.state = true)
	main.client.frame_updated.connect(func(_f): flags.frame = true)
	var buckets := {"state": PackedFloat32Array(), "frame": PackedFloat32Array(), "none": PackedFloat32Array()}
	var started := Time.get_ticks_usec()
	var last := started
	while Time.get_ticks_usec() - started < int(seconds * 1_000_000.0):
		await process_frame
		var now := Time.get_ticks_usec()
		frames.append(float(now - last) / 1000.0)
		# Attribute the frame that *follows* an arrival (layout/draw happen there).
		buckets["state" if flags.state else ("frame" if flags.frame else "none")].append(float(now - last) / 1000.0)
		flags.state = false
		flags.frame = false
		last = now
		draw_calls += Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
		objects += Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
		samples += 1
	var sorted := frames.duplicate()
	sorted.sort()
	var total := 0.0
	for value in frames: total += value
	var mean := total / maxf(1.0, frames.size())
	var p99 := sorted[mini(sorted.size() - 1, int(sorted.size() * 0.99))]
	var over_17 := 0
	var over_25 := 0
	for value in frames:
		if value > 17.5: over_17 += 1
		if value > 25.0: over_25 += 1
	print("PERF fps=%.1f mean_ms=%.2f p99_ms=%.2f slow_frames=%.1f%% very_slow=%.1f%% draw_calls=%.0f objects=%.0f population=%d nodes=%d quality=%s frame_latency_ms=%.0f refresh_hz=%.1f" % [
		1000.0 / mean, mean, p99, 100.0 * over_17 / frames.size(), 100.0 * over_25 / frames.size(),
		draw_calls / maxf(1, samples), objects / maxf(1, samples),
		int(main.latest_state.get("population", 0)), get_node_count(), main.quality.describe(), main.client.frame_latency_ms, DisplayServer.screen_get_refresh_rate()])
	for key in buckets:
		var values: PackedFloat32Array = buckets[key]
		if values.is_empty(): continue
		var total_ms := 0.0
		var worst := 0.0
		for v in values:
			total_ms += v
			worst = maxf(worst, v)
		print("ARRIVAL %s frames=%d mean=%.1f worst=%.1f" % [key, values.size(), total_ms / values.size(), worst])
	if "--breakdown" in args:
		var state: Dictionary = main.latest_state
		var parts := {
			"world.set_state": func(): main.world.set_state(state),
			"hud.set_state": func(): main.hud.set_state(state),
			"observatory": func(): main.hud.observatory.set_state(state),
			"feed": func(): main.hud.feed.ingest(state.get("feed", [])),
			"tools.set_state": func(): main.tools.set_state(state),
			"inspector": func(): main.inspector.set_creature(state.creatures[0]),
			"main._on_state": func(): main._on_state(state),
			"json.parse": func(): JSON.parse_string(JSON.stringify(state)),
			"swarm.apply_frame": func(): main.world.swarm.apply_frame(main.client.last_frame),
			"food.apply_frame": func(): main.world.food.apply_frame(main.client.last_frame, main.world.swarm, false),
			"world.set_frame": func(): main.world.set_frame(main.client.last_frame),
			"hud.set_frame": func(): main.hud.set_frame(main.client.last_frame),
			"swarm.update": func(): main.world.swarm.update(0.016, main.world.camera),
			"world._process": func(): main.world._process(0.016),
		}
		for key in parts:
			var started_at := Time.get_ticks_usec()
			for i in 10: parts[key].call()
			print("BREAKDOWN %s %.2f ms" % [key, (Time.get_ticks_usec() - started_at) / 10000.0])
	main.queue_free()
	await process_frame
	quit(0)
