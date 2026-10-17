extends Control
const ObservatoryView := preload("res://scripts/Observatory.gd")
const Atmosphere := preload("res://scripts/AtmosphereOverlay.gd")

signal pause_requested
signal step_requested
signal speed_requested(ticks_per_second: int)
signal inspect_requested
signal world_tools_requested
signal reset_requested
signal follow_requested
signal restart_requested
signal director_requested
signal lens_requested
signal daylight_requested
signal legends_requested
signal photo_requested
signal help_requested

var status: Label
var population: Label
var season: Label
var weather: Label
var title: Label
var reason: Label
var hint: Label
var notice: Label
var pause_button: Button
var step_button: Button
var inspect_button: Button
var follow_button: Button
var tools_button: Button
var director_button: Button
var lens_button: Button
var daylight_button: Button
var legends_button: Button
var needs: HBoxContainer
var bars: Dictionary = {}
var captions: Dictionary = {}
var speed_buttons: Dictionary = {}
var _connected := false
var _paused := false
var _controls: Array[Button] = []
var summary_row: HBoxContainer
var words: VBoxContainer
var _has_selection := false
var observatory: PanelContainer
var atmosphere: Control
var telemetry: Label
var graphs_button: Button
var vitals: Label
var sparkline: Control
var feed: EventFeed
var minimap: Minimap
var legends: LegendsPanel
var help: HelpOverlay
var perf: PerfOverlay
var cinematic: CinematicLayer
var lens_legend: PanelContainer
var _lens_title: Label
var _lens_keys: HFlowContainer
var _population_history := PackedFloat32Array()
var _frame_population := -1
var _right_panel_open := false
var _chrome := true
var minimap_wanted := true

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	atmosphere = Atmosphere.new()
	add_child(atmosphere)
	_build_top()
	observatory = ObservatoryView.new()
	add_child(observatory)
	_build_dock()
	feed = EventFeed.new()
	feed.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	feed.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	feed.offset_top = 100
	feed.offset_right = -18
	add_child(feed)
	minimap = Minimap.new()
	minimap.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	minimap.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	minimap.grow_vertical = Control.GROW_DIRECTION_BEGIN
	add_child(minimap)
	_build_lens_legend()
	legends = LegendsPanel.new()
	legends.set_anchors_and_offsets_preset(Control.PRESET_RIGHT_WIDE)
	legends.offset_left = -396
	legends.offset_right = -24
	legends.offset_top = 104
	legends.offset_bottom = -240
	legends.closed.connect(func(): legends.visible = false; _layout())
	add_child(legends)
	perf = PerfOverlay.new()
	perf.set_anchors_and_offsets_preset(Control.PRESET_TOP_LEFT)
	perf.offset_left = 346
	perf.offset_top = 100
	add_child(perf)
	help = HelpOverlay.new()
	add_child(help)
	cinematic = CinematicLayer.new()
	add_child(cinematic)
	set_connection(false, "Connecting to the simulation…")
	set_selection({})
	get_viewport().size_changed.connect(_resize)
	_resize()

func _build_top() -> void:
	var top := PanelContainer.new()
	top.name = "TopStatus"
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 16
	top.offset_right = -16
	top.offset_top = 12
	top.offset_bottom = 84
	BiomeUI.panel(top)
	var top_style := top.get_theme_stylebox("panel") as StyleBoxFlat
	top_style.content_margin_top = 10
	top_style.content_margin_bottom = 10
	add_child(top)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 24)
	top.add_child(row)
	var brand_box := VBoxContainer.new()
	brand_box.add_theme_constant_override("separation", -2)
	row.add_child(brand_box)
	brand_box.add_child(BiomeUI.label("VIKASA", 28, BiomeUI.ACCENT))
	brand_box.add_child(BiomeUI.label("L I V I N G   B I O M E", 10, BiomeUI.MUTED))
	season = BiomeUI.label("Living biome · Waiting for simulation", 16, BiomeUI.MUTED)
	season.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(season)
	sparkline = Control.new()
	sparkline.custom_minimum_size = Vector2(120, 34)
	sparkline.tooltip_text = "Population over the last minutes"
	sparkline.draw.connect(_draw_sparkline)
	row.add_child(sparkline)
	population = BiomeUI.label("— animals", 19)
	row.add_child(population)
	vitals = BiomeUI.label("", 14, BiomeUI.MUTED)
	vitals.tooltip_text = "Total births · total deaths since the habitat began"
	row.add_child(vitals)
	weather = BiomeUI.label("Seasonal cycle", 16, BiomeUI.ACCENT)
	row.add_child(weather)
	status = BiomeUI.label("Connecting…", 14, BiomeUI.MUTED)
	row.add_child(status)
	telemetry = BiomeUI.label("— ticks/s", 13, BiomeUI.TEAL)
	row.add_child(telemetry)

func _build_dock() -> void:
	var bottom := PanelContainer.new()
	bottom.name = "ObservationDock"
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_left = 16
	bottom.offset_right = -16
	bottom.offset_top = -210
	bottom.offset_bottom = -12
	BiomeUI.panel(bottom)
	add_child(bottom)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 10)
	bottom.add_child(content)
	var summary := HBoxContainer.new()
	summary_row = summary
	summary.add_theme_constant_override("separation", 20)
	content.add_child(summary)
	words = VBoxContainer.new()
	words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.add_child(words)
	title = BiomeUI.label("Observe the living biome", 23)
	words.add_child(title)
	reason = BiomeUI.paragraph("Click an animal to see what it needs and why it acts.", 15)
	words.add_child(reason)
	needs = HBoxContainer.new()
	needs.add_theme_constant_override("separation", 18)
	summary.add_child(needs)
	for key in ["Energy", "Hunger", "Health", "Instinct"]:
		var box := VBoxContainer.new()
		box.custom_minimum_size.x = 106
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		needs.add_child(box)
		var caption := BiomeUI.label(key, 14, BiomeUI.MUTED)
		box.add_child(caption)
		captions[key] = caption
		var color := Color("#c6b475") if key == "Hunger" else Color("#abc28e")
		var bar := BiomeUI.meter(color)
		box.add_child(bar)
		bars[key] = bar
	needs.hide()
	var actions := HFlowContainer.new()
	actions.add_theme_constant_override("h_separation", 8)
	actions.add_theme_constant_override("v_separation", 6)
	content.add_child(actions)
	pause_button = _button(actions, "Pause", "Space · Pause or resume the simulation", func(): pause_requested.emit())
	step_button = _button(actions, "Step", "Advance one tick while paused", func(): step_requested.emit())
	for speed in [{"name": "Observe · 16", "value": 16, "key": "1"}, {"name": "Present · 48", "value": 48, "key": "2"}, {"name": "Accelerate · 120", "value": 120, "key": "3"}]:
		var value := int(speed.value)
		var button := _button(actions, str(speed.name), "%s · %d simulation ticks per second" % [speed.key, value], func(): speed_requested.emit(value))
		button.toggle_mode = true
		speed_buttons[value] = button
	_separator(actions)
	inspect_button = _button(actions, "Inspect", "Open details for the selected animal", func(): inspect_requested.emit(), false)
	follow_button = _button(actions, "Follow", "F · Bring the camera close and follow the selected animal", func(): follow_requested.emit(), false)
	follow_button.toggle_mode = true
	_button(actions, "Reset view", "Return to the whole habitat", func(): reset_requested.emit(), false)
	_separator(actions)
	director_button = _button(actions, "Director", "C · Cinematic camera that finds births, clashes, alphas and families on its own", func(): director_requested.emit(), false)
	director_button.toggle_mode = true
	lens_button = _button(actions, "Lens · Natural", "V · Recolour animals by action, energy, dynasty, generation or temperament", func(): lens_requested.emit(), false)
	daylight_button = _button(actions, "Daylight · Cycle", "N · Presentation daylight: cycle, day, golden hour, night", func(): daylight_requested.emit(), false)
	legends_button = _button(actions, "Legends", "L · Living record holders", func(): legends_requested.emit(), false)
	legends_button.toggle_mode = true
	_button(actions, "Photo", "P · Hide the interface and slowly orbit · F12 saves a screenshot", func(): photo_requested.emit(), false)
	_separator(actions)
	tools_button = _button(actions, "World tools", "T · Place food or schedule environmental pressures", func(): world_tools_requested.emit(), false)
	graphs_button = _button(actions, "Graphs", "G · Toggle live population, survival and genetic charts", func(): observatory.visible = not observatory.visible; _layout(), false)
	graphs_button.toggle_mode = true
	graphs_button.button_pressed = true
	_button(actions, "Restart biome", "Begin again with the same seed and a fresh population", func(): restart_requested.emit())
	_button(actions, "?", "F1 · Field guide: every shortcut", func(): help_requested.emit(), false)
	hint = BiomeUI.label("Right-drag to orbit · Wheel to zoom · Click an animal to observe", 13, BiomeUI.MUTED)
	content.add_child(hint)
	notice = BiomeUI.paragraph("Connecting to the simulation…", 14, BiomeUI.ACCENT)
	content.add_child(notice)

func _separator(parent: Container) -> void:
	var line := VSeparator.new()
	line.custom_minimum_size.x = 6
	line.modulate = Color(1, 1, 1, 0.25)
	parent.add_child(line)

func _build_lens_legend() -> void:
	lens_legend = PanelContainer.new()
	lens_legend.name = "LensLegend"
	BiomeUI.panel(lens_legend, 0.85)
	lens_legend.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
	lens_legend.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	lens_legend.grow_vertical = Control.GROW_DIRECTION_BEGIN
	lens_legend.custom_minimum_size.x = 264
	lens_legend.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 6)
	lens_legend.add_child(box)
	_lens_title = BiomeUI.label("", 14, BiomeUI.ACCENT)
	box.add_child(_lens_title)
	_lens_keys = HFlowContainer.new()
	_lens_keys.add_theme_constant_override("h_separation", 6)
	_lens_keys.add_theme_constant_override("v_separation", 4)
	_lens_keys.custom_minimum_size.x = 230
	box.add_child(_lens_keys)
	add_child(lens_legend)
	lens_legend.visible = false

func set_lens(mode: String) -> void:
	lens_button.text = "Lens · " + str(ViewModes.LABELS[mode]).get_slice(" ", 0).replace("Current", "Action")
	lens_legend.visible = mode != "natural"
	_lens_title.text = str(ViewModes.LABELS[mode])
	for child in _lens_keys.get_children(): child.queue_free()
	var desc := BiomeUI.paragraph(str(ViewModes.DESCRIPTIONS[mode]), 12)
	desc.custom_minimum_size.x = 230
	_lens_keys.add_child(desc)
	if mode == "behavior":
		for i in ViewModes.BEHAVIOR_LABELS.size():
			_lens_keys.add_child(BiomeUI.chip(ViewModes.BEHAVIOR_LABELS[i], ViewModes.BEHAVIOR_COLORS[i], 11))
	elif mode == "energy":
		for pair in [["Starving", Color("#d9483b")], ["Low", Color("#e8b84a")], ["Full", Color("#5fd47f")]]:
			_lens_keys.add_child(BiomeUI.chip(pair[0], pair[1], 11))
	elif mode == "generation":
		for pair in [["Founders", Color("#7a4fc0")], ["Gen 7", Color("#2f8f8a")], ["Gen 14+", Color("#f2d35b")]]:
			_lens_keys.add_child(BiomeUI.chip(pair[0], pair[1], 11))
	elif mode == "temperament":
		for pair in [["Aggressive", Color("#e0533f")], ["Balanced", Color("#e9e3d4")], ["Sociable", Color("#4f8fe0")]]:
			_lens_keys.add_child(BiomeUI.chip(pair[0], pair[1], 11))
	_layout()

func set_daylight(mode: String) -> void:
	daylight_button.text = "Daylight · " + {"cycle": "Cycle", "day": "Day", "golden": "Golden", "night": "Night"}[mode]

func set_director(on: bool) -> void:
	director_button.set_pressed_no_signal(on)
	cinematic.set_letterbox(on)

func set_right_panel_open(open: bool) -> void:
	_right_panel_open = open
	_layout()

func _button(parent: Container, text: String, tip: String, callback: Callable, needs_connection: bool = true) -> Button:
	var button := BiomeUI.button(text, tip)
	button.name = text.replace(" ", "").replace("·", "").replace("?", "Help")
	button.pressed.connect(callback)
	parent.add_child(button)
	if needs_connection: _controls.append(button)
	return button

func _resize() -> void:
	var narrow := get_viewport_rect().size.x < 1150
	# Reflow selected summary above meters rather than squeezing the action line.
	if narrow and needs.get_parent() == summary_row:
		summary_row.remove_child(needs)
		$ObservationDock.get_child(0).add_child(needs)
		$ObservationDock.get_child(0).move_child(needs, 1)
	elif not narrow and needs.get_parent() != summary_row:
		needs.get_parent().remove_child(needs)
		summary_row.add_child(needs)
	needs.add_theme_constant_override("separation", 8 if narrow else 18)
	for child in needs.get_children(): child.custom_minimum_size.x = 100 if narrow else 122
	$TopStatus.get_child(0).add_theme_constant_override("separation", 14 if narrow else 24)
	season.add_theme_font_size_override("font_size", 14 if narrow else 16)
	weather.add_theme_font_size_override("font_size", 14 if narrow else 16)
	telemetry.visible = not narrow
	sparkline.visible = not narrow
	vitals.visible = not narrow
	_layout()

func _layout() -> void:
	var dock_height := ($ObservationDock.get_child(0) as Container).get_combined_minimum_size().y + 40
	$ObservationDock.offset_top = -dock_height - 12
	var above_dock := -dock_height - 24
	minimap.offset_bottom = above_dock
	minimap.offset_right = -16
	minimap.offset_top = above_dock - minimap.custom_minimum_size.y
	minimap.offset_left = -16 - minimap.custom_minimum_size.x
	lens_legend.offset_right = -16
	lens_legend.offset_bottom = minimap.offset_top - 10
	var right_open := _right_panel_open or legends.visible
	minimap.visible = _chrome and minimap_wanted and not right_open
	feed.offset_right = -412 if right_open else -18
	legends.offset_bottom = above_dock
	observatory.offset_bottom = above_dock

func toggle_minimap() -> void:
	minimap_wanted = not minimap_wanted
	_layout()

func _process(_delta: float) -> void:
	# Size to the current content after container reflow; keep the bottom anchored.
	var content := $ObservationDock.get_child(0) as Container
	var wanted := -content.get_combined_minimum_size().y - 52
	if not is_equal_approx($ObservationDock.offset_top, wanted): _layout()

func set_frame(frame: Dictionary) -> void:
	var count := int(frame.count)
	if count != _frame_population:
		_frame_population = count
		population.text = "%d animals" % count
	vitals.text = "▲ %d  ▼ %d" % [int(frame.total_births), int(frame.total_deaths)]

func set_clock(text: String) -> void:
	# Changing label text reshapes it and re-sorts the bar; only on real change.
	if season.text != text: season.text = text

func set_state(state: Dictionary) -> void:
	_paused = bool(state.get("paused", false))
	pause_button.text = "Resume" if _paused else "Pause"
	status.text = "Paused" if _paused else "Running"
	pause_button.tooltip_text = "Space · Resume the simulation" if _paused else "Space · Pause the simulation"
	step_button.disabled = not _connected or not _paused
	var env: Dictionary = state.get("environment", {})
	if _frame_population < 0: population.text = "%d animals" % int(state.get("population", 0))
	_population_history.append(float(state.get("population", 0)))
	if _population_history.size() > 160: _population_history = _population_history.slice(_population_history.size() - 160)
	sparkline.queue_redraw()
	telemetry.text = "%.1f ticks/s · %d FPS" % [float(state.get("actual_ticks_per_second", 0)), roundi(Engine.get_frames_per_second())]
	telemetry.tooltip_text = "Measured simulation speed and rendered frames per second."
	observatory.set_state(state)
	atmosphere.set_state(state)
	if legends.visible: legends.set_state(state)
	feed.ingest(state.get("feed", []))
	var events: Array = env.get("active_events", [])
	weather.text = str(events[0].get("kind", "Weather")).capitalize() + " active" if not events.is_empty() else "Seasonal cycle"
	var rate := float(state.get("ticks_per_second", 48))
	for value in speed_buttons: speed_buttons[value].set_pressed_no_signal(is_equal_approx(rate, float(value)))
	if int(state.get("population", 0)) == 0: set_notice("Population extinct. Restart the simulation to begin a new seeded habitat.", false)
	elif notice.text.begins_with("Population extinct"): set_notice("Select an animal to begin observing.", false)

func _draw_sparkline() -> void:
	var size := sparkline.size
	if _population_history.size() < 2: return
	var peak := -INF
	var low := INF
	for v in _population_history:
		peak = maxf(peak, v)
		low = minf(low, v)
	# Scale to the observed band (with a floor) so changes stay legible.
	var span := maxf(10.0, peak - low)
	low = maxf(0.0, (peak + low) * 0.5 - span * 0.6)
	span *= 1.2
	var points := PackedVector2Array()
	var fill := PackedVector2Array([Vector2(0, size.y)])
	for i in _population_history.size():
		var p := Vector2(size.x * i / float(_population_history.size() - 1), size.y - 3 - clampf((_population_history[i] - low) / span, 0.0, 1.0) * (size.y - 6))
		points.append(p)
		fill.append(p)
	fill.append(Vector2(size.x, size.y))
	sparkline.draw_colored_polygon(fill, Color(0.48, 0.88, 0.76, 0.12))
	sparkline.draw_polyline(points, BiomeUI.TEAL, 1.6, true)

func set_selection(creature: Dictionary) -> void:
	var has_selection := not creature.is_empty()
	_has_selection = has_selection
	inspect_button.disabled = not has_selection or not _connected
	follow_button.disabled = not has_selection or not _connected
	needs.visible = has_selection
	if not has_selection:
		title.text = "Every life leaves a trace."
		reason.text = "Select a creature to follow its instincts. Press C for the director's cut, V to change lens, F1 for every shortcut."
		hint.visible = false
		return
	hint.visible = true
	var generation := " · Gen %d" % int(creature.generation) if creature.has("generation") else ""
	title.text = "Animal #%d%s · %s" % [int(creature.get("id", -1)), generation, BehaviorPresentation.action(creature)]
	if notice.text == "Select an animal to begin observing.": notice.text = "Animals choose their own actions · Observe their changing needs."
	reason.text = BehaviorPresentation.reason(creature)
	var raw_drives: Variant = creature.get("drives", {})
	var drives: Dictionary = raw_drives if raw_drives is Dictionary else {}
	var strongest := BehaviorPresentation.dominant(drives)
	var injury: Variant = BehaviorPresentation.ratio(creature, "injury")
	var values := {"Energy": BehaviorPresentation.ratio(creature, "energy_ratio"), "Hunger": BehaviorPresentation.ratio(creature, "hunger"), "Health": null if injury == null else 1.0 - float(injury), "Instinct": BehaviorPresentation.ratio(drives, strongest)}
	for key in values:
		var color := Color("#d7c080") if key == "Hunger" else Color("#b4cfa8")
		if key == "Instinct" and not strongest.is_empty(): color = BehaviorPresentation.DRIVES[strongest].color
		BehaviorPresentation.meter(bars[key], values[key], color)
		if values[key] != null:
			bars[key].tooltip_text = {"Energy": "Usable energy reserve; higher means more reserve.", "Hunger": "Food need; higher means greater hunger.", "Health": "Health remaining; higher means less injury.", "Instinct": "Strongest current pressure; high urgency can influence the next action."}[key]
		captions[key].text = (str(BehaviorPresentation.DRIVES[strongest].label) if key == "Instinct" and not strongest.is_empty() else key) + " " + BehaviorPresentation.percent(values[key])
		if key == "Instinct": captions[key].tooltip_text = "Dominant instinct · " + BehaviorPresentation.urgency(values[key])

func set_connection(value: bool, message: String) -> void:
	_connected = value
	status.text = "Live" if value else "Offline"
	status.add_theme_color_override("font_color", Color("#b8d3a7") if value else Color("#e0b48a"))
	for button in _controls: button.disabled = not value
	step_button.disabled = not value or not _paused
	inspect_button.disabled = not value or not _has_selection
	follow_button.disabled = not value or not _has_selection
	if not value:
		population.text = "— animals"
		_frame_population = -1
		season.text = "Waiting for live simulation"
		weather.text = ""
		for button in speed_buttons.values(): button.set_pressed_no_signal(false)
		set_notice(message, true)
	elif notice.text.begins_with("Simulation offline") or notice.text.begins_with("Connecting"): set_notice("Select an animal to begin observing.", false)

func set_notice(message: String, error: bool = false) -> void:
	notice.text = message
	notice.visible = error or not message.begins_with("Select an animal") and not message.begins_with("Animals choose")
	notice.add_theme_color_override("font_color", Color("#ecc09f") if error else BiomeUI.ACCENT)

func set_hint(message: String) -> void:
	hint.text = message

func set_following(value: bool) -> void:
	follow_button.set_pressed_no_signal(value)
	follow_button.text = "Following" if value else "Follow"

## Hide every panel but keep the cinematic layer (photo mode, director).
func set_chrome_visible(on: bool) -> void:
	_chrome = on
	for node in [$TopStatus, $ObservationDock, feed, atmosphere]: node.visible = on
	observatory.visible = on and graphs_button.button_pressed
	lens_legend.visible = on and lens_button.text != "Lens · Natural"
	legends.visible = on and legends_button.button_pressed
	_layout()
