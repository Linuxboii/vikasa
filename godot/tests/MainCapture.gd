extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var main = load("res://Main.tscn").instantiate()
	var args := OS.get_cmdline_user_args()
	# Set the endpoint before ready issues its initial request.
	main.get_node("SimulationClient").api = "http://127.0.0.1:18765" if "--offline" in args else "http://127.0.0.1:8766"
	root.add_child(main)
	await create_timer(4.5).timeout
	var client = main.get_node("SimulationClient")
	if "--offline" in args:
		assert(not client.connected)
	else:
		if not client.connected or main.latest_state.get("creatures", []).is_empty():
			push_error("Live bridge capture failed: " + main.hud.notice.text)
			main.queue_free()
			quit(1)
			return
		main._select(int(main.latest_state.creatures[0].id))
		if "--tools" in args:
			main.inspector.set_open(false)
			main.tools.set_open(true)
		print("Live bridge tick ", main.latest_state.get("tick"), " population ", main.latest_state.get("population"))
	for frame in range(10): await process_frame
	await RenderingServer.frame_post_draw
	var filename := "task5-main-offline.png" if "--offline" in args else ("task5-main-tools.png" if "--tools" in args else "task5-main-live.png")
	if "--narrow" in args: filename = filename.replace(".png", "-narrow.png")
	root.get_texture().get_image().save_png("user://" + filename)
	print("Full Main capture: ", OS.get_user_data_dir(), "/", filename)
	main.queue_free()
	await process_frame
	quit()
