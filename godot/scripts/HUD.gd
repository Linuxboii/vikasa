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

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	atmosphere = Atmosphere.new()
	add_child(atmosphere)
	var top := PanelContainer.new()
	top.name = "TopStatus"
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 24
	top.offset_right = -24
	top.offset_top = 18
	top.offset_bottom = 86
	BiomeUI.panel(top)
	var top_style := top.get_theme_stylebox("panel") as StyleBoxFlat
	top_style.content_margin_top = 10
	top_style.content_margin_bottom = 10
	add_child(top)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 24)
	top.add_child(row)
	var brand_box := VBoxContainer.new()
	brand_box.add_theme_constant_override("separation", 0)
	row.add_child(brand_box)
	var brand := BiomeUI.label("VIKASA", 28, BiomeUI.ACCENT)
	brand_box.add_child(brand)
	brand_box.add_child(BiomeUI.label("L I V I N G   B I O M E", 10, BiomeUI.MUTED))
	season = BiomeUI.label("Living biome · Waiting for simulation", 16, BiomeUI.MUTED)
	season.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(season)
	population = BiomeUI.label("— animals", 19)
	row.add_child(population)
	weather = BiomeUI.label("Seasonal cycle", 16, BiomeUI.ACCENT)
	row.add_child(weather)
	status = BiomeUI.label("Connecting…", 14, BiomeUI.MUTED)
	row.add_child(status)
	telemetry = BiomeUI.label("— ticks/s", 13, Color("#7be0c2"))
	row.add_child(telemetry)
	observatory = ObservatoryView.new()
	add_child(observatory)
	var bottom := PanelContainer.new()
	bottom.name = "ObservationDock"
	bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	bottom.offset_left = 24
	bottom.offset_right = -24
	bottom.offset_top = -210
	bottom.offset_bottom = -18
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
	for speed in [{"name": "Observe · 16", "value": 16}, {"name": "Present · 48", "value": 48}, {"name": "Accelerate · 120", "value": 120}]:
		var value := int(speed.value)
		var button := _button(actions, str(speed.name), "%d simulation ticks per second" % value, func(): speed_requested.emit(value))
		button.toggle_mode = true
		speed_buttons[value] = button
	inspect_button = _button(actions, "Inspect", "Open details for the selected animal", func(): inspect_requested.emit(), false)
	follow_button = _button(actions, "Follow", "Bring the camera close and follow the selected animal", func(): follow_requested.emit(), false)
	follow_button.toggle_mode = true
	_button(actions, "Reset view", "Return to the whole habitat", func(): reset_requested.emit(), false)
	tools_button = _button(actions, "World tools", "Place food or schedule environmental pressures", func(): world_tools_requested.emit(), false)
	graphs_button = _button(actions, "Graphs", "Toggle live population, survival and genetic charts", func(): observatory.visible = not observatory.visible, false)
	graphs_button.toggle_mode = true
	graphs_button.button_pressed = true
	_button(actions, "Restart biome", "Begin again with the same seed and a fresh population", func(): restart_requested.emit())
	hint = BiomeUI.label("Right-drag to orbit · Wheel to zoom · Click an animal to observe", 13, BiomeUI.MUTED)
	content.add_child(hint)
	notice = BiomeUI.paragraph("Connecting to the simulation…", 14, BiomeUI.ACCENT)
	content.add_child(notice)
	set_connection(false, "Connecting to the simulation…")
	set_selection({})
	get_viewport().size_changed.connect(_resize)
	_resize()

func _button(parent: Container, text: String, tip: String, callback: Callable, needs_connection: bool = true) -> Button:
	var button := BiomeUI.button(text, tip)
	button.name = text.replace(" ", "")
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
	$TopStatus.offset_top = 12
	$TopStatus.offset_bottom = 84
	$ObservationDock.offset_bottom = -12
	$TopStatus.get_child(0).add_theme_constant_override("separation", 14 if narrow else 24)
	season.add_theme_font_size_override("font_size", 14 if narrow else 16)
	weather.add_theme_font_size_override("font_size", 14 if narrow else 16)
	telemetry.visible = not narrow
	$TopStatus.offset_left = 16
	$TopStatus.offset_right = -16
	$ObservationDock.offset_left = 16
	$ObservationDock.offset_right = -16

func _process(_delta: float) -> void:
	# Size to the current content after container reflow; keep the bottom anchored.
	var content := $ObservationDock.get_child(0) as Container
	$ObservationDock.offset_top = -content.get_combined_minimum_size().y - 40

func set_state(state: Dictionary) -> void:
	_paused = bool(state.get("paused", false))
	pause_button.text = "Resume" if _paused else "Pause"
	status.text = "Paused" if _paused else "Running"
	pause_button.tooltip_text = "Space · Resume the simulation" if _paused else "Space · Pause the simulation"
	step_button.disabled = not _connected or not _paused
	var env: Dictionary = state.get("environment", {})
	season.text = "%s · Tick %d%s" % [str(env.get("season", "spring")).capitalize(), int(state.get("tick", 0)), " · Paused" if _paused else ""]
	population.text = "%d animals" % int(state.get("population", 0))
	telemetry.text = "%.1f ticks/s · %d FPS" % [float(state.get("actual_ticks_per_second", 0)), roundi(Engine.get_frames_per_second())]
	telemetry.tooltip_text = "Measured simulation speed. Requested speed adapts to available CPU time."
	observatory.set_state(state)
	atmosphere.set_state(state)
	var events: Array = env.get("active_events", [])
	weather.text = str(events[0].get("kind", "Weather")).capitalize() + " active" if not events.is_empty() else "Seasonal cycle"
	var rate := float(state.get("ticks_per_second", 48))
	for value in speed_buttons: speed_buttons[value].set_pressed_no_signal(is_equal_approx(rate, float(value)))
	if int(state.get("population", 0)) == 0: set_notice("Population extinct. Restart the simulation to begin a new seeded habitat.", false)
	elif notice.text.begins_with("Population extinct"): set_notice("Select an animal to begin observing.", false)

func set_selection(creature: Dictionary) -> void:
	var has_selection := not creature.is_empty()
	_has_selection = has_selection
	inspect_button.disabled = not has_selection or not _connected
	follow_button.disabled = not has_selection or not _connected
	needs.visible = has_selection
	_resize()
	if not has_selection:
		title.text = "Every life leaves a trace."
		reason.text = "Select a creature to follow its instincts. Open World tools to test the limits of survival."
		hint.visible = false
		return
	hint.visible = true
	title.text = "Animal #%d · %s" % [int(creature.get("id", -1)), BehaviorPresentation.action(creature)]
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
