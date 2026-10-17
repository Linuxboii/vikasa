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
	var main = load("res://Main.tscn").instantiate()
	main.get_node("SimulationClient").api = "http://127.0.0.1:" + _arg("--port", "8766")
	root.add_child(main)
	await create_timer(4.0).timeout
	if not main.client.connected:
		push_error("PerfProbe needs a running bridge")
		quit(1)
		return
	var seconds := float(_arg("--seconds", "12"))
	var frames: PackedFloat32Array = []
	var draw_calls := 0.0
	var objects := 0.0
	var samples := 0
	var started := Time.get_ticks_usec()
	var last := started
	while Time.get_ticks_usec() - started < int(seconds * 1_000_000.0):
		await process_frame
		var now := Time.get_ticks_usec()
		frames.append(float(now - last) / 1000.0)
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
	print("PERF fps=%.1f mean_ms=%.2f p99_ms=%.2f draw_calls=%.0f objects=%.0f population=%d nodes=%d" % [
		1000.0 / mean, mean, p99, draw_calls / maxf(1, samples), objects / maxf(1, samples),
		int(main.latest_state.get("population", 0)), get_node_count()])
	main.queue_free()
	await process_frame
	quit(0)
