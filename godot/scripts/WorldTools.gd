extends PanelContainer

signal command_requested(payload: Dictionary)
signal placement_changed(active: bool)
var placing_food := false
var weather_choice: OptionButton
var explanation: Label
var notice: Label
var schedule_button: Button
var food_button: Button
var connected := false
var duration: SpinBox
var intensity: HSlider
var intensity_label: Label
var events: Array = [
	{"kind": "drought", "label": "Drought", "intensity": 0.25, "description": "Food dries out, new growth slows and reserves fall. Prolonged shortage can cause starvation."},
	{"kind": "heat", "label": "Heat wave", "intensity": 1.7, "description": "Heat raises metabolic cost and exposure injury. Resilience reduces damage; low reserves increase vulnerability."},
	{"kind": "storm", "label": "Storm", "intensity": 1.4, "description": "Rain and wind damage food and injure exposed creatures. A prolonged storm can kill vulnerable animals."},
	{"kind": "wildfire", "label": "Wildfire", "intensity": 1.2, "description": "Fire destroys stored food and causes exposure damage. Watch deaths rise and resilient survivors remain."},
	{"kind": "cold", "label": "Cold snap", "intensity": 1.8, "description": "Cold increases energy demand and exposure damage. Stored reserves become critical."},
	{"kind": "disease", "label": "Disease pressure", "intensity": 1.4, "description": "Sustained health pressure can kill vulnerable animals. This is an exposure model, not simulated contagion."},
	{"kind": "abundance", "label": "Food bloom", "intensity": 1.5, "description": "Increase food productivity temporarily and observe the population response."}
]

func _ready() -> void:
	anchor_left = 1
	anchor_right = 1
	anchor_bottom = 1
	offset_left = -396
	offset_right = -24
	offset_top = 104
	offset_bottom = -240
	BiomeUI.panel(self)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 10)
	scroll.add_child(content)
	var row := HBoxContainer.new()
	content.add_child(row)
	var title := BiomeUI.label("World tools", 25, BiomeUI.ACCENT)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(title)
	var close := BiomeUI.button("Close", "Escape · Close world tools")
	close.pressed.connect(func(): cancel_placement(); set_open(false))
	row.add_child(close)
	content.add_child(BiomeUI.paragraph("Change the climate. Trace the consequences.", 13))
	content.add_child(BiomeUI.label("Food placement", 18))
	food_button = BiomeUI.button("Place food patch", "Then click the habitat. Escape cancels.")
	food_button.pressed.connect(func(): placing_food = not placing_food; placement_changed.emit(placing_food); food_button.text = "Cancel placement" if placing_food else "Place food patch")
	content.add_child(food_button)
	content.add_child(BiomeUI.paragraph("Choose this tool, then click a place in the habitat. It adds food at the next simulation tick.", 14))
	content.add_child(BiomeUI.label("Environmental pressure", 18))
	weather_choice = OptionButton.new()
	weather_choice.custom_minimum_size.y = 40
	weather_choice.add_theme_font_size_override("font_size", 16)
	for event in events: weather_choice.add_item(event.label)
	weather_choice.item_selected.connect(func(_index: int): intensity.value = events[weather_choice.selected].intensity; _describe())
	content.add_child(weather_choice)
	explanation = BiomeUI.paragraph("", 15)
	content.add_child(explanation)
	intensity_label = BiomeUI.label("Severity", 14, BiomeUI.ACCENT)
	content.add_child(intensity_label)
	intensity = HSlider.new()
	intensity.min_value = 0.1
	intensity.max_value = 2.5
	intensity.step = 0.05
	intensity.value = 0.25
	intensity.value_changed.connect(func(_value: float): _describe())
	content.add_child(intensity)
	var duration_row := HBoxContainer.new()
	content.add_child(duration_row)
	var duration_text := BiomeUI.label("Duration · ticks", 14)
	duration_text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	duration_row.add_child(duration_text)
	duration = SpinBox.new()
	duration.min_value = 16
	duration.max_value = 960
	duration.step = 16
	duration.value = 160
	duration_row.add_child(duration)
	schedule_button = BiomeUI.button("Apply weather", "Apply the selected pressure starting next tick")
	schedule_button.pressed.connect(_schedule)
	content.add_child(schedule_button)
	notice = BiomeUI.paragraph("", 15, BiomeUI.ACCENT)
	content.add_child(notice)
	# Put climate controls first; food placement stays reachable below them.
	var weather_controls: Array = content.get_children().slice(5, 12)
	for i in weather_controls.size(): content.move_child(weather_controls[i], i + 1)
	_describe()
	set_connected(false)
	hide()
	get_viewport().size_changed.connect(_resize)
	_resize()

func _resize() -> void:
	offset_left = -minf(390, get_viewport_rect().size.x - 32)
	offset_right = -16
	offset_top = 82
	offset_bottom = -256 if get_viewport_rect().size.x < 1150 else -212

func _describe() -> void:
	explanation.text = str(events[weather_choice.selected].description)
	if is_instance_valid(intensity_label):
		intensity_label.text = ("Food growth retained · %.0f%%" % (intensity.value * 100)) if events[weather_choice.selected].kind == "drought" else "Pressure · %.2f×" % intensity.value

func _process(_delta: float) -> void:
	var dock := get_parent().get_node_or_null("HUD/ObservationDock") as Control
	if dock: offset_bottom = dock.offset_top - 12

func _schedule() -> void:
	cancel_placement()
	var event: Dictionary = events[weather_choice.selected]
	command_requested.emit({"action": "weather", "kind": event.kind, "intensity": intensity.value, "duration": int(duration.value)})

func set_open(open: bool) -> void:
	visible = open
	if not open: cancel_placement()

func set_connected(value: bool) -> void:
	connected = value
	food_button.disabled = not value
	schedule_button.disabled = not value
	weather_choice.disabled = not value
	if not value: cancel_placement()

func set_state(_state: Dictionary) -> void:
	pass

func set_notice(message: String, error: bool = false) -> void:
	notice.text = message
	notice.add_theme_color_override("font_color", Color("#ecc09f") if error else BiomeUI.ACCENT)

func cancel_placement() -> void:
	if not placing_food: return
	placing_food = false
	food_button.text = "Place food patch"
	placement_changed.emit(false)

func place_food(position: Vector2) -> void:
	if not connected or not placing_food: return
	command_requested.emit({"action": "food", "x": clampf(position.x, 0, 1), "y": clampf(position.y, 0, 1)})
	cancel_placement()
