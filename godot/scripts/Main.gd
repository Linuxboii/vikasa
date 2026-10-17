extends Node3D

@onready var client = $SimulationClient
@onready var world = $WorldView
@onready var hud = $Interface/HUD
@onready var inspector = $Interface/CreatureInspector
@onready var tools = $Interface/WorldTools
var latest_state: Dictionary = {}
var selected_id := -1
var following := false
var director := false
var photo_mode := false
var ui_hidden := false
var skip_intro := false
var view_mode := "natural"
var quality: QualityManager
var _intro_played := false
var _director_timer := 0.0
var _director_recent: Array = []
var _director_wide := false
var _hot: Dictionary = {}
var _peak_generation := -1
var _clock_accumulator := 0.0
var _clash_pattern := RegEx.create_from_string("(\\d+) won a clash with creature (\\d+)")

func _ready() -> void:
	quality = QualityManager.new()
	add_child(quality)
	quality.changed.connect(world.apply_quality)
	hud.perf.client = client
	hud.perf.quality = quality
	hud.minimap.setup(world)
	client.state_updated.connect(_on_state)
	client.frame_updated.connect(_on_frame)
	client.connection_changed.connect(_on_connection)
	client.command_completed.connect(_on_command)
	world.creature_clicked.connect(_select)
	world.creature_focused.connect(_focus)
	world.world_clicked.connect(_on_ground)
	hud.pause_requested.connect(_pause)
	hud.step_requested.connect(func(): client.send_command({"action": "step", "count": 1}))
	hud.speed_requested.connect(func(speed: int): client.send_command({"action": "speed", "ticks_per_second": speed}))
	hud.inspect_requested.connect(func(): _open_inspector(selected_id >= 0))
	hud.world_tools_requested.connect(_toggle_tools)
	hud.reset_requested.connect(func(): following = false; world.reset_camera(); hud.set_following(false))
	hud.follow_requested.connect(_toggle_follow)
	hud.restart_requested.connect(func(): _select(-1); hud.feed.clear(); hud.legends.reset(); _peak_generation = -1; client.send_command({"action": "restart"}))
	hud.director_requested.connect(func(): set_director(not director))
	hud.lens_requested.connect(func(): set_view_mode(ViewModes.next(view_mode)))
	hud.daylight_requested.connect(_cycle_daylight)
	hud.legends_requested.connect(_toggle_legends)
	hud.photo_requested.connect(func(): set_photo_mode(not photo_mode))
	hud.help_requested.connect(func(): hud.help.visible = not hud.help.visible)
	hud.feed.focus_requested.connect(_focus)
	hud.feed.event_arrived.connect(_on_event)
	hud.legends.focus_requested.connect(_focus)
	hud.minimap.jump_requested.connect(_jump)
	inspector.closed.connect(func(): _open_inspector(false))
	tools.command_requested.connect(_tool_command)
	tools.placement_changed.connect(func(active: bool): world.placement_mode = active; hud.set_hint("Click the habitat to place food · Escape cancels" if active else "Right-drag to orbit · Wheel to zoom · Click an animal to observe"))
	client.request_state()

func _on_frame(frame: Dictionary) -> void:
	world.set_frame(frame)
	hud.set_frame(frame)

func _on_state(state: Dictionary) -> void:
	latest_state = state
	world.set_state(state)
	hud.set_state(state)
	tools.set_state(state)
	var selected := _selected()
	if selected_id >= 0 and selected.is_empty():
		_select(-1)
		hud.set_notice("The selected animal is no longer alive. Select another animal to observe.")
	else:
		hud.set_selection(selected)
		inspector.set_creature(selected)
	_check_milestones(state)
	if not _intro_played and not state.get("creatures", []).is_empty():
		_intro_played = true
		if not skip_intro:
			world.play_intro()
			hud.cinematic.show_title()

func _process(delta: float) -> void:
	var env: Dictionary = latest_state.get("environment", {})
	var season_name: String = world.atmos.conditions.get("season", str(env.get("season", "spring")))
	var tick := int(client.last_frame.get("tick", latest_state.get("tick", 0)))
	var paused := bool(client.last_frame.get("paused", latest_state.get("paused", false)))
	_clock_accumulator += delta
	if client.connected and _clock_accumulator >= 0.25:
		_clock_accumulator = 0.0
		hud.set_clock("%s · %s · Year %d · Tick %d%s" % [season_name.capitalize(), world.atmos.clock_label(), tick / 384 + 1, tick, " · Paused" if paused else ""])
	for key in _hot.keys():
		_hot[key] -= delta
		if _hot[key] <= 0.0: _hot.erase(key)
	if director: _direct(delta)

func _on_connection(connected: bool, message: String) -> void:
	hud.set_connection(connected, message)
	tools.set_connected(connected)
	if not connected:
		latest_state = {}
		_select(-1)
		world.clear_snapshot()
		hud.set_notice(message, true)

func _on_command(action: String, ok: bool, message: String) -> void:
	hud.set_notice(message, not ok)
	tools.set_notice(message, not ok)
	if ok and action == "food_burst": hud.cinematic.flash("Food bloom scattered")

func _tool_command(payload: Dictionary) -> void:
	client.send_command(payload)

func _on_event(item: Dictionary) -> void:
	var kind := str(item.get("kind", ""))
	var id := int(item.get("creature_id", -1)) if item.get("creature_id") != null else -1
	if kind == "fight":
		var found := _clash_pattern.search(str(item.get("text", "")))
		if found:
			world.flash_clash(int(found.get_string(1)), int(found.get_string(2)))
			_hot[int(found.get_string(1))] = 10.0
	elif kind == "birth" and id >= 0:
		_hot[id] = 12.0
	elif kind == "weather":
		hud.cinematic.flash(str(item.get("text", "")).replace("Field study scheduled ", "Incoming: ").replace(" pressure for", " for"))

func _check_milestones(state: Dictionary) -> void:
	var deepest := -1
	for c in state.get("creatures", []): deepest = maxi(deepest, int(c.get("generation", 0)))
	if _peak_generation >= 0 and deepest > _peak_generation and deepest >= 2:
		hud.feed.push("milestone", "Generation %d is alive — the population is evolving." % deepest)
	_peak_generation = maxi(_peak_generation, deepest)

func _selected() -> Dictionary:
	for creature in latest_state.get("creatures", []):
		if int(creature.get("id", -1)) == selected_id: return creature
	return {}

func _select(id: int) -> void:
	selected_id = id
	if id < 0:
		following = false
		world.set_follow(-1)
		hud.set_following(false)
	world.set_selected(id)
	if following: world.set_follow(id)
	if not latest_state.is_empty(): world.set_state(latest_state)
	hud.set_selection(_selected())
	inspector.set_creature(_selected())
	tools.set_open(false)
	_open_inspector(id >= 0 and not director)

func _focus(id: int) -> void:
	if not world.swarm.agents.has(id):
		hud.cinematic.flash("Animal #%d is no longer alive" % id)
		return
	_select(id)
	following = true
	world.set_follow(id)
	world.camera.goal_distance = 22.0
	hud.set_following(true)

func _jump(normalized: Vector2) -> void:
	following = false
	hud.set_following(false)
	world.follow_id = -1
	world.focus(world.swarm.to_world(normalized * Vector2(world.width, world.height)))

func _open_inspector(open: bool) -> void:
	inspector.set_open(open)
	if open:
		hud.legends.visible = false
		hud.legends_button.set_pressed_no_signal(false)
	hud.set_right_panel_open(inspector.visible or tools.visible)

func _toggle_tools() -> void:
	inspector.set_open(false)
	hud.legends.visible = false
	hud.legends_button.set_pressed_no_signal(false)
	tools.set_open(not tools.visible)
	hud.set_right_panel_open(inspector.visible or tools.visible)

func _toggle_legends() -> void:
	var open: bool = not hud.legends.visible
	if open:
		inspector.set_open(false)
		tools.set_open(false)
		hud.legends.set_state(latest_state)
	hud.legends.visible = open
	hud.legends_button.set_pressed_no_signal(open)
	hud.set_right_panel_open(inspector.visible or tools.visible)

func _on_ground(position: Vector2) -> void:
	if tools.placing_food:
		tools.place_food(position)
		world.emit_food_burst(position)
	else:
		_select(-1)

func _pause() -> void:
	client.send_command({"action": "resume" if latest_state.get("paused", false) else "pause"})

func _toggle_follow() -> void:
	following = not following
	world.set_follow(selected_id if following else -1)
	hud.set_following(following)

func _cycle_daylight() -> void:
	var mode: String = world.atmos.cycle_daylight()
	hud.set_daylight(mode)
	hud.cinematic.flash({"cycle": "Daylight follows the clock", "day": "Daylight locked to midday", "golden": "Golden hour", "night": "Night · watch the eyes and the fireflies"}[mode])

func set_view_mode(mode: String) -> void:
	view_mode = mode
	world.swarm.set_view_mode(mode)
	hud.set_lens(mode)
	hud.cinematic.flash("Lens · " + str(ViewModes.LABELS[mode]))

func set_ui_hidden(hidden: bool) -> void:
	ui_hidden = hidden
	hud.set_chrome_visible(not hidden)
	inspector.visible = inspector.visible and not hidden
	tools.visible = tools.visible and not hidden

func set_photo_mode(on: bool) -> void:
	photo_mode = on
	if on and director: set_director(false)
	set_ui_hidden(on)
	world.camera.auto_orbit = 0.05 if on else 0.0
	if on: hud.cinematic.flash("Photo mode · F12 saves · P or Esc returns")

func set_director(on: bool) -> void:
	director = on
	if on and photo_mode:
		photo_mode = false
	hud.set_director(on)
	set_ui_hidden(on)
	if on:
		_director_timer = 0.0
		hud.cinematic.flash("Director's cut · the camera finds the story")
	else:
		world.camera.auto_orbit = 0.0
		world.camera.stiffness = 5.0
		world.set_follow(selected_id if following else -1)

func _direct(delta: float) -> void:
	_director_timer -= delta
	if _director_timer > 0.0: return
	var swarm: CreatureSwarm = world.swarm
	if swarm.agents.is_empty(): return
	_director_wide = not _director_wide and randf() < 0.3
	var camera: CameraRig = world.camera
	camera.stiffness = 1.2
	camera.auto_orbit = (0.10 if randf() < 0.5 else -0.10)
	if _director_wide:
		_director_timer = 7.0
		world.follow_id = -1
		camera.goal_target = Vector3(randf_range(-15, 15), 0, randf_range(-10, 10))
		camera.goal_distance = randf_range(58.0, 80.0)
		camera.goal_pitch = randf_range(0.42, 0.62)
		hud.cinematic.caption("The biome", "%s · %d animals · %s" % [str(world.atmos.conditions.get("season", "")).capitalize(), swarm.count(), world.atmos.clock_label()])
		return
	var best := -1
	var best_score := -1.0
	for agent in swarm.agents.values():
		if agent.dying >= 0.0 or agent.row.is_empty(): continue
		var row: Dictionary = agent.row
		var score := randf() * 1.5
		score += {7: 5.0, 3: 3.0, 4: 3.0, 5: 3.0, 1: 1.0}.get(int(row.behavior), 0.0)
		if int(row.flags) & 1: score += 2.0
		if int(row.flags) & 4: score += 1.5
		score += _hot.get(agent.id, 0.0) * 0.6
		if agent.id in _director_recent: score -= 8.0
		if score > best_score:
			best_score = score
			best = agent.id
	if best < 0: return
	_director_recent.append(best)
	if _director_recent.size() > 4: _director_recent.pop_front()
	_director_timer = randf_range(8.0, 11.0)
	world.follow_id = best
	world.selected_id = best
	world.swarm.set_selected(best)
	selected_id = best
	camera.goal_distance = randf_range(13.0, 22.0)
	camera.goal_pitch = randf_range(0.28, 0.5)
	var row: Dictionary = swarm.row_of(best)
	var reason := ""
	for creature in latest_state.get("creatures", []):
		if int(creature.get("id", -1)) == best:
			reason = BehaviorPresentation.reason(creature)
			break
	var traits: Array = []
	if int(row.flags) & 1: traits.append("Alpha")
	if int(row.flags) & 4: traits.append("Young")
	if _hot.has(best): traits.append("In the news")
	var heading := "#%d · Generation %d%s" % [best, int(row.generation), (" · " + ", ".join(traits)) if not traits.is_empty() else ""]
	hud.cinematic.caption(heading, "%s — %s" % [ViewModes.BEHAVIOR_LABELS[clampi(int(row.behavior), 0, 7)], reason])

func _save_screenshot() -> void:
	await RenderingServer.frame_post_draw
	var folder := OS.get_system_dir(OS.SYSTEM_DIR_PICTURES).path_join("Vikasa")
	DirAccess.make_dir_recursive_absolute(folder)
	var stamp := Time.get_datetime_string_from_system().replace(":", "-")
	var path := folder.path_join("vikasa-%s.png" % stamp)
	var error := get_viewport().get_texture().get_image().save_png(path)
	hud.cinematic.flash("Saved " + path if error == OK else "Screenshot failed (%d)" % error)

func _select_next(step: int) -> void:
	var ids: Array = world.swarm.agents.keys().filter(func(id): return world.swarm.agents[id].dying < 0.0)
	if ids.is_empty(): return
	ids.sort()
	var index := ids.find(selected_id)
	_select(ids[(index + step + ids.size()) % ids.size()] if index >= 0 else ids[0])
	if following: world.set_follow(selected_id)

func _unhandled_key_input(event: InputEvent) -> void:
	if not (event is InputEventKey and event.pressed and not event.echo): return
	var handled := true
	match event.keycode:
		KEY_ESCAPE:
			if hud.help.visible: hud.help.visible = false
			elif director: set_director(false)
			elif photo_mode: set_photo_mode(false)
			elif ui_hidden: set_ui_hidden(false)
			else:
				tools.cancel_placement()
				tools.set_open(false)
				_open_inspector(false)
				hud.legends.visible = false
				hud.legends_button.set_pressed_no_signal(false)
				hud.set_right_panel_open(false)
		KEY_SPACE: _pause()
		KEY_1: hud.speed_requested.emit(16)
		KEY_2: hud.speed_requested.emit(48)
		KEY_3: hud.speed_requested.emit(120)
		KEY_C: set_director(not director)
		KEY_V: set_view_mode(ViewModes.next(view_mode))
		KEY_N: _cycle_daylight()
		KEY_L: _toggle_legends()
		KEY_G: hud.graphs_button.button_pressed = not hud.graphs_button.button_pressed; hud.observatory.visible = hud.graphs_button.button_pressed
		KEY_T: _toggle_tools()
		KEY_M: hud.toggle_minimap()
		KEY_H: set_ui_hidden(not ui_hidden)
		KEY_P: set_photo_mode(not photo_mode)
		KEY_F: if selected_id >= 0: _toggle_follow()
		KEY_TAB: _select_next(-1 if event.shift_pressed else 1)
		KEY_F1, KEY_SLASH: hud.help.visible = not hud.help.visible
		KEY_F3: hud.perf.visible = not hud.perf.visible
		KEY_F4: hud.cinematic.flash("Quality · " + quality.cycle())
		KEY_F12: _save_screenshot()
		_: handled = false
	if handled: get_viewport().set_input_as_handled()
