extends Control

signal pause_requested
signal step_requested
signal speed_requested(ticks_per_second: int)
signal inspect_requested
signal world_tools_requested
signal reset_requested
signal follow_requested

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

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var top := PanelContainer.new()
	top.name = "TopStatus"
	top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	top.offset_left = 24
	top.offset_right = -24
	top.offset_top = 18
	top.offset_bottom = 86
	BiomeUI.panel(top)
	add_child(top)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 24)
	top.add_child(row)
	var brand := BiomeUI.label("Vikasa", 27, BiomeUI.ACCENT)
	row.add_child(brand)
	season = BiomeUI.label("Living biome · Waiting for simulation", 16, BiomeUI.MUTED)
	season.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(season)
	population = BiomeUI.label("— animals", 19)
	row.add_child(population)
	weather = BiomeUI.label("Seasonal cycle", 16, BiomeUI.ACCENT)
	row.add_child(weather)
	status = BiomeUI.label("Connecting…", 14, BiomeUI.MUTED)
	row.add_child(status)
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
	summary.add_theme_constant_override("separation", 20)
	content.add_child(summary)
	var words := VBoxContainer.new()
	words.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	summary.add_child(words)
	title = BiomeUI.label("Observe the living biome", 23)
	words.add_child(title)
	reason = BiomeUI.paragraph("Click an animal to see what it needs and why it acts.", 15)
	words.add_child(reason)
	needs = HBoxContainer.new()
	needs.add_theme_constant_override("separation", 18)
	summary.add_child(needs)
	for key in ["Energy", "Hunger", "Health", "Safety"]:
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
	for speed in [{"name": "Natural", "value": 8}, {"name": "Fast", "value": 24}, {"name": "Very fast", "value": 60}]:
		var value := int(speed.value)
		var button := _button(actions, str(speed.name), "%d simulation ticks per second" % value, func(): speed_requested.emit(value))
		button.toggle_mode = true
		speed_buttons[value] = button
	inspect_button = _button(actions, "Inspect", "Open details for the selected animal", func(): inspect_requested.emit(), false)
	follow_button = _button(actions, "Follow", "Bring the camera close and follow the selected animal", func(): follow_requested.emit(), false)
	follow_button.toggle_mode = true
	_button(actions, "Reset view", "Return to the whole habitat", func(): reset_requested.emit(), false)
	tools_button = _button(actions, "World tools", "Place food or schedule environmental pressures", func(): world_tools_requested.emit(), false)
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
	needs.add_theme_constant_override("separation", 8 if narrow else 18)
	for child in needs.get_children(): child.custom_minimum_size.x = 76 if narrow else 106
	$ObservationDock.offset_top = -250 if narrow else -210
	season.add_theme_font_size_override("font_size", 14 if narrow else 16)

func set_state(state: Dictionary) -> void:
	_paused = bool(state.get("paused", false))
	pause_button.text = "Resume" if _paused else "Pause"
	pause_button.tooltip_text = "Space · Resume the simulation" if _paused else "Space · Pause the simulation"
	step_button.disabled = not _connected or not _paused
	var env: Dictionary = state.get("environment", {})
	season.text = "%s · Tick %d%s" % [str(env.get("season", "spring")).capitalize(), int(state.get("tick", 0)), " · Paused" if _paused else ""]
	population.text = "%d animals" % int(state.get("population", 0))
	var events: Array = env.get("active_events", [])
	weather.text = str(events[0].get("kind", "Weather")).capitalize() + " active" if not events.is_empty() else "Seasonal cycle"
	var rate := float(state.get("ticks_per_second", 8))
	for value in speed_buttons: speed_buttons[value].set_pressed_no_signal(is_equal_approx(rate, float(value)))
	if int(state.get("population", 0)) == 0: set_notice("The habitat is empty. Start a new run to observe another population.", false)
	elif notice.text.begins_with("The habitat is empty"): set_notice("Select an animal to begin observing.", false)

func set_selection(creature: Dictionary) -> void:
	var has_selection := not creature.is_empty()
	inspect_button.disabled = not has_selection
	follow_button.disabled = not has_selection
	needs.visible = has_selection
	if not has_selection:
		title.text = "Observe the living biome"
		reason.text = "Click an animal to see what it needs and why it acts."
		return
	title.text = "Animal #%d · %s" % [int(creature.get("id", -1)), str(creature.get("behavior", "explore")).replace("_", " ").capitalize()]
	if notice.text == "Select an animal to begin observing.": notice.text = "Animals choose their own actions · Observe their changing needs."
	reason.text = str(creature.get("behavior_reason", "Exploring the habitat"))
	var drives: Dictionary = creature.get("drives", {})
	var values := {"Energy": float(creature.get("energy_ratio", 0)), "Hunger": float(creature.get("hunger", 0)), "Health": 1.0 - float(creature.get("injury", 0)), "Safety": 1.0 - float(drives.get("danger_avoidance", 0))}
	for key in values:
		bars[key].value = clampf(values[key], 0, 1)
		captions[key].text = key + " " + BiomeUI.percent(values[key])

func set_connection(value: bool, message: String) -> void:
	_connected = value
	status.text = "Live" if value else "Offline"
	status.add_theme_color_override("font_color", Color("#b8d3a7") if value else Color("#e0b48a"))
	for button in _controls: button.disabled = not value
	step_button.disabled = not value or not _paused
	if not value: set_notice(message, true)
	elif notice.text.begins_with("Simulation offline") or notice.text.begins_with("Connecting"): set_notice("Select an animal to begin observing.", false)

func set_notice(message: String, error: bool = false) -> void:
	notice.text = message
	notice.add_theme_color_override("font_color", Color("#ecc09f") if error else BiomeUI.ACCENT)

func set_hint(message: String) -> void:
	hint.text = message

func set_following(value: bool) -> void:
	follow_button.set_pressed_no_signal(value)
	follow_button.text = "Following" if value else "Follow"
