extends Node3D

const API := "http://127.0.0.1:8765"
const SCALE := 0.1
const CreatureView := preload("res://scripts/CreatureVisual.gd")
const HabitatView := preload("res://scripts/Habitat.gd")

var camera: Camera3D
var camera_target := Vector3(0.0, 0.0, 0.0)
var camera_yaw := 0.24
var camera_pitch := 0.82
var camera_distance := 71.0
var dragging_camera := false
var drop_food_mode := false
var scene_root: Node3D
var creatures_root: Node3D
var resources_root: Node3D
var creature_views: Dictionary = {}
var resource_views: Dictionary = {}
var selected_creature_id := -1
var latest_state: Dictionary = {}
var world_width := 1200.0
var world_height := 760.0
var poll_busy := false
var environment_node: WorldEnvironment
var biome_root: Node3D
var habitat_node: Habitat
var habitat_dimensions := Vector2.ZERO
var habitat_seed := -1
var header_status: Label
var header_population: Label
var header_tick: Label
var header_food: Label
var header_turnover: Label
var left_content: VBoxContainer
var right_content: VBoxContainer
var connection_timer: Timer

func _ready() -> void:
	_build_world()
	_build_interface()
	connection_timer = Timer.new()
	connection_timer.wait_time = 0.22
	connection_timer.timeout.connect(_request_state)
	add_child(connection_timer)
	connection_timer.start()
	_request_state()

func _build_world() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sky_material := ProceduralSkyMaterial.new()
	sky_material.sky_top_color = Color("#173b35")
	sky_material.sky_horizon_color = Color("#8ba57a")
	sky_material.ground_bottom_color = Color("#1a342b")
	sky_material.ground_horizon_color = Color("#899a70")
	sky.sky_material = sky_material
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("#a8c59a")
	env.ambient_light_energy = 0.72
	env.reflected_light_source = Environment.REFLECTION_SOURCE_BG
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_light_color = Color("#78937b")
	env.fog_density = 0.0045
	env.fog_sky_affect = 0.5
	environment_node = WorldEnvironment.new()
	environment_node.environment = env
	add_child(environment_node)
	var sun := DirectionalLight3D.new()
	sun.name = "WarmCanopyLight"
	sun.rotation_degrees = Vector3(-52, -28, 0)
	sun.light_color = Color("#ffe1a2")
	sun.light_energy = 1.35
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 100.0
	add_child(sun)
	var fill := OmniLight3D.new()
	fill.name = "AmbientBiomeFill"
	fill.position = Vector3(-18, 18, 10)
	fill.light_color = Color("#7bd6b5")
	fill.light_energy = 0.5
	fill.omni_range = 56.0
	add_child(fill)
	biome_root = Node3D.new()
	biome_root.name = "Biome"
	add_child(biome_root)
	_rebuild_habitat(2026)
	creatures_root = Node3D.new()
	creatures_root.name = "LivingPopulation"
	add_child(creatures_root)
	resources_root = Node3D.new()
	resources_root.name = "FoodPatches"
	add_child(resources_root)
	camera = Camera3D.new()
	camera.name = "OrbitCamera"
	camera.fov = 47.0
	camera.near = 0.1
	camera.far = 240.0
	camera.current = true
	add_child(camera)
	_update_camera()

func _build_interface() -> void:
	var ui := Control.new()
	ui.name = "ResearchInterface"
	ui.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ui.mouse_filter = Control.MOUSE_FILTER_PASS
	add_child(ui)
	var header := PanelContainer.new()
	header.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	header.offset_left = 18
	header.offset_top = 14
	header.offset_right = -18
	header.offset_bottom = 83
	_apply_panel(header, Color("#14241fe8"), Color("#a5c79455"), 12)
	ui.add_child(header)
	var header_row := HBoxContainer.new()
	header_row.add_theme_constant_override("separation", 18)
	header.add_child(header_row)
	var brand := Label.new()
	brand.text = "VIKASA  /  LIVING BIOME"
	brand.add_theme_font_size_override("font_size", 21)
	brand.add_theme_color_override("font_color", Color("#d7e8c9"))
	brand.custom_minimum_size.x = 310
	header_row.add_child(brand)
	header_population = _header_metric(header_row, "LIFE", "—", Color("#9de0b0"))
	header_tick = _header_metric(header_row, "TICK", "—", Color("#ead28a"))
	header_food = _header_metric(header_row, "FOOD PATCHES", "—", Color("#f0c579"))
	header_turnover = _header_metric(header_row, "BORN / LOST", "—", Color("#d8a895"))
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header_row.add_child(spacer)
	header_status = Label.new()
	header_status.text = "CONNECTING TO FIELD ENGINE…"
	header_status.add_theme_font_size_override("font_size", 11)
	header_status.add_theme_color_override("font_color", Color("#83d4af"))
	header_row.add_child(header_status)
	var left_panel := PanelContainer.new()
	left_panel.anchor_left = 0
	left_panel.anchor_top = 0.115
	left_panel.anchor_right = 0
	left_panel.anchor_bottom = 0.75
	left_panel.offset_left = 18
	left_panel.offset_top = 0
	left_panel.offset_right = 298
	left_panel.offset_bottom = 0
	_apply_panel(left_panel, Color("#14241fe8"), Color("#a5c79448"), 10)
	ui.add_child(left_panel)
	var left_scroll := ScrollContainer.new()
	left_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	left_panel.add_child(left_scroll)
	left_content = VBoxContainer.new()
	left_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left_content.add_theme_constant_override("separation", 8)
	left_scroll.add_child(left_content)
	var right_panel := PanelContainer.new()
	right_panel.anchor_left = 1
	right_panel.anchor_top = 0.115
	right_panel.anchor_right = 1
	right_panel.anchor_bottom = 0.75
	right_panel.offset_left = -345
	right_panel.offset_top = 0
	right_panel.offset_right = -18
	right_panel.offset_bottom = 0
	_apply_panel(right_panel, Color("#14241fe8"), Color("#a5c79448"), 10)
	ui.add_child(right_panel)
	var right_scroll := ScrollContainer.new()
	right_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	right_panel.add_child(right_scroll)
	right_content = VBoxContainer.new()
	right_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right_content.add_theme_constant_override("separation", 8)
	right_scroll.add_child(right_content)
	var toolbar := PanelContainer.new()
	toolbar.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	toolbar.offset_left = 18
	toolbar.offset_top = -112
	toolbar.offset_right = -18
	toolbar.offset_bottom = -14
	_apply_panel(toolbar, Color("#14241ff2"), Color("#a5c79455"), 10)
	ui.add_child(toolbar)
	var toolbar_content := VBoxContainer.new()
	toolbar_content.add_theme_constant_override("separation", 6)
	toolbar.add_child(toolbar_content)
	var control_row := HBoxContainer.new()
	control_row.add_theme_constant_override("separation", 8)
	toolbar_content.add_child(control_row)
	_add_button(control_row, "Ⅱ  Pause", _toggle_pause)
	_add_button(control_row, "Step 1", func(): _send_command({"action":"step", "count":1}))
	_add_button(control_row, "Step 10", func(): _send_command({"action":"step", "count":10}))
	_add_text(control_row, "TIME RATE", 10, Color("#92a78c"))
	for speed in [1, 4, 12, 36]:
		_add_button(control_row, str(speed) + "×", func(): _send_command({"action":"speed", "ticks_per_second":speed}))
	_add_button(control_row, "＋ Drop food patch", _toggle_food_drop)
	var spacer2 := Control.new()
	spacer2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	control_row.add_child(spacer2)
	_add_text(control_row, "WEATHER STUDY", 10, Color("#92a78c"))
	for weather in [{"kind":"drought", "name":"Drought", "intensity":0.45}, {"kind":"heat", "name":"Heat", "intensity":1.7}, {"kind":"storm", "name":"Storm", "intensity":1.4}, {"kind":"wildfire", "name":"Fire", "intensity":0.7}, {"kind":"abundance", "name":"Bloom", "intensity":1.5}]:
		var item: Dictionary = weather
		_add_button(control_row, item.name, func(): _send_command({"action":"weather", "kind":item.kind, "intensity":item.intensity, "duration":48}))
	var footnote := Label.new()
	footnote.text = "Drag with right mouse to orbit  ·  Wheel to zoom  ·  Click a creature to inspect  ·  Click the ground after “Drop food patch” to enrich one place  ·  Environmental studies are scheduled interventions, not instant edits."
	footnote.add_theme_font_size_override("font_size", 10)
	footnote.add_theme_color_override("font_color", Color("#a4b6a1"))
	toolbar_content.add_child(footnote)
	_refresh_panels()

func _header_metric(parent: HBoxContainer, title: String, value: String, color: Color) -> Label:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 0)
	var number := Label.new()
	number.text = value
	number.add_theme_font_size_override("font_size", 17)
	number.add_theme_color_override("font_color", color)
	var caption := Label.new()
	caption.text = title
	caption.add_theme_font_size_override("font_size", 9)
	caption.add_theme_color_override("font_color", Color("#9aab9e"))
	box.add_child(number)
	box.add_child(caption)
	parent.add_child(box)
	return number

func _apply_panel(panel: PanelContainer, color: Color, border: Color, radius: int) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = border
	style.set_border_width_all(1)
	style.set_corner_radius_all(radius)
	style.content_margin_left = 13
	style.content_margin_right = 13
	style.content_margin_top = 11
	style.content_margin_bottom = 11
	style.shadow_color = Color("#07120f88")
	style.shadow_size = 14
	panel.add_theme_stylebox_override("panel", style)

func _add_button(parent: Container, text: String, action: Callable) -> void:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size = Vector2(0, 30)
	button.focus_mode = Control.FOCUS_ALL
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color("#203a30")
	normal.border_color = Color("#819f7d66")
	normal.set_border_width_all(1)
	normal.set_corner_radius_all(6)
	normal.content_margin_left = 9
	normal.content_margin_right = 9
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color("#315342")
	hover.border_color = Color("#b1d59b")
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", hover)
	button.add_theme_color_override("font_color", Color("#deebd8"))
	button.add_theme_font_size_override("font_size", 11)
	button.pressed.connect(action)
	parent.add_child(button)

func _add_text(parent: Container, text: String, size: int, color: Color) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)

func _request_state() -> void:
	if poll_busy:
		return
	poll_busy = true
	var request := HTTPRequest.new()
	request.timeout = 1.8
	request.request_completed.connect(_on_state_received.bind(request))
	add_child(request)
	var error := request.request(API + "/state")
	if error != OK:
		poll_busy = false
		request.queue_free()
		header_status.text = "FIELD ENGINE OFFLINE · RUN vikasa godot"
		header_status.add_theme_color_override("font_color", Color("#e6a078"))

func _on_state_received(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray, request: HTTPRequest) -> void:
	poll_busy = false
	request.queue_free()
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		header_status.text = "RECONNECTING TO FIELD ENGINE…"
		header_status.add_theme_color_override("font_color", Color("#e6a078"))
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary:
		return
	latest_state = parsed
	var world: Dictionary = latest_state.get("world", {})
	world_width = float(world.get("width", world_width))
	world_height = float(world.get("height", world_height))
	var seed_value := int(latest_state.get("seed", 2026))
	if habitat_dimensions != Vector2(world_width, world_height) or habitat_seed != seed_value:
		_rebuild_habitat(seed_value)
		camera_distance = maxf(70.0, Vector2(world_width * SCALE, world_height * SCALE).length() * 0.57)
		_update_camera()
	header_status.text = "●  LIVE · " + str(latest_state.get("environment", {}).get("season", "spring")).to_upper()
	header_status.add_theme_color_override("font_color", Color("#93dda9"))
	header_population.text = str(latest_state.get("population", 0))
	header_tick.text = str(latest_state.get("tick", 0))
	header_food.text = str(latest_state.get("food_count", 0))
	header_turnover.text = str(latest_state.get("births", 0)) + " / " + str(latest_state.get("deaths", 0))
	_sync_creatures(latest_state.get("creatures", []))
	_sync_resources(latest_state.get("resources", []))
	_apply_atmosphere(latest_state.get("environment", {}))
	_refresh_panels()

func _rebuild_habitat(seed_value: int) -> void:
	if habitat_node and is_instance_valid(habitat_node):
		habitat_node.queue_free()
	habitat_node = HabitatView.new()
	habitat_node.name = "ProceduralHabitat"
	habitat_node.build(world_width * SCALE, world_height * SCALE, 1.0, seed_value)
	biome_root.add_child(habitat_node)
	habitat_dimensions = Vector2(world_width, world_height)
	habitat_seed = seed_value

func _sync_creatures(items: Array) -> void:
	var seen: Dictionary = {}
	for data in items:
		var key := int(data.id)
		seen[key] = true
		if not creature_views.has(key):
			var view := CreatureView.new()
			view.name = "Creature_%d" % key
			view.configure(data, SCALE, world_width, world_height)
			creatures_root.add_child(view)
			creature_views[key] = view
		var creature_view: CreatureVisual = creature_views[key]
		creature_view.update_state(data, SCALE, get_process_delta_time(), world_width, world_height)
		creature_view.set_selected(key == selected_creature_id)
	for key in creature_views.keys():
		if not seen.has(key):
			creature_views[key].queue_free()
			creature_views.erase(key)
	if selected_creature_id >= 0 and not seen.has(selected_creature_id):
		selected_creature_id = -1

func _sync_resources(items: Array) -> void:
	var seen: Dictionary = {}
	for data in items:
		var key := int(data.id)
		seen[key] = true
		if not resource_views.has(key):
			var patch := MeshInstance3D.new()
			patch.name = "Food_%d" % key
			var mesh := SphereMesh.new()
			mesh.radial_segments = 12
			mesh.rings = 8
			patch.mesh = mesh
			patch.scale = Vector3(0.15, 0.17, 0.15)
			var material := StandardMaterial3D.new()
			material.albedo_color = Color("#f4cb73")
			material.emission_enabled = true
			material.emission = Color("#f4c465")
			material.emission_energy_multiplier = 0.55
			material.roughness = 0.29
			patch.material_override = material
			resources_root.add_child(patch)
			resource_views[key] = patch
		var marker: MeshInstance3D = resource_views[key]
		marker.position = Vector3(float(data.position[0]) * SCALE - world_width * SCALE * 0.5, 0.28, float(data.position[1]) * SCALE - world_height * SCALE * 0.5)
	for key in resource_views.keys():
		if not seen.has(key):
			resource_views[key].queue_free()
			resource_views.erase(key)

func _apply_atmosphere(info: Dictionary) -> void:
	if not environment_node:
		return
	var pressure := float(info.get("health_pressure", 0.0))
	var rainfall := float(info.get("rainfall", 0.6))
	environment_node.environment.fog_density = 0.0038 + pressure * 0.0015
	var sun := get_node_or_null("WarmCanopyLight") as DirectionalLight3D
	if sun:
		sun.light_energy = lerpf(0.95, 1.52, clampf(float(info.get("temperature", 0.55)), 0.0, 1.0))
	var fill := get_node_or_null("AmbientBiomeFill") as OmniLight3D
	if fill:
		fill.light_energy = lerpf(0.72, 0.28, clampf(rainfall, 0.0, 1.0))

func _refresh_panels() -> void:
	if not is_instance_valid(left_content) or not is_instance_valid(right_content):
		return
	_clear_children(left_content)
	_clear_children(right_content)
	if latest_state.is_empty():
		_add_text(left_content, "FIELD MONITOR", 12, Color("#b5d2a3"))
		_add_text(left_content, "Waiting for the deterministic ecosystem engine. Run this project with `vikasa godot` to start the live world.", 12, Color("#d7e1d1"))
		return
	var environment_data: Dictionary = latest_state.get("environment", {})
	_add_section_title(left_content, "BIOME CONDITIONS")
	_add_pair(left_content, "Season", str(environment_data.get("season", "spring")).capitalize())
	_add_pair(left_content, "Air temperature", _percent(environment_data.get("temperature", 0.5)) + " · relative")
	_add_pair(left_content, "Rain / water", _percent(environment_data.get("rainfall", 0.5)) + " · seasonal")
	_add_pair(left_content, "Food productivity", "×" + str(snappedf(float(environment_data.get("seasonal_productivity", 1.0)), 0.01)))
	_add_pair(left_content, "Active pressures", _event_names(environment_data.get("active_events", [])))
	_add_rule(left_content)
	_add_section_title(left_content, "POPULATION ECOLOGY")
	_add_pair(left_content, "Living creatures", str(latest_state.get("population", 0)))
	_add_pair(left_content, "Food patches", str(latest_state.get("food_count", 0)))
	_add_pair(left_content, "Mean satisfaction", _percent(latest_state.get("mean_satisfaction", 0.0)))
	_add_pair(left_content, "Hungry / starving", str(latest_state.get("starving_count", 0)))
	_add_pair(left_content, "Alpha individuals", str(latest_state.get("alpha_count", 0)))
	_add_pair(left_content, "Total births / deaths", str(latest_state.get("total_births", 0)) + " / " + str(latest_state.get("total_deaths", 0)))
	_add_rule(left_content)
	_add_section_title(left_content, "SHARED CULTURE")
	var traditions: Array = latest_state.get("traditions", [])
	if traditions.is_empty():
		_add_paragraph(left_content, "No shared belief has formed yet. Repeated experiences and contact can produce traditions over long runs; nothing is pre-scripted.")
	else:
		for tradition in traditions:
			_add_pair(left_content, str(tradition.name), str(tradition.followers) + " followers · " + str(tradition.ritual_count) + " gatherings")
			_add_paragraph(left_content, "Observed cue: " + str(tradition.signal) + ". Practice: " + str(tradition.ritual) + ".")
	_add_rule(left_content)
	_add_section_title(left_content, "FIELD CHRONICLE")
	var chronicle: Array = latest_state.get("chronicle", [])
	if chronicle.is_empty():
		_add_paragraph(left_content, "New births, deaths, encounters, weather events and cultural changes will appear here.")
	else:
		for event in chronicle.slice(maxi(0, chronicle.size() - 5), chronicle.size()):
			_add_paragraph(left_content, "T" + str(event.get("tick", 0)) + "  ·  " + str(event.get("text", "")))
	var selected := _selected_data()
	if selected.is_empty():
		_add_section_title(right_content, "SPECIMEN INSPECTOR")
		_add_paragraph(right_content, "Click a creature in the habitat to open its life history. Size, crest, posture and light are shaped by inherited physical and behavioral traits.")
		_add_pair(right_content, "World seed", str(latest_state.get("seed", "—")))
		_add_pair(right_content, "Simulation tick", str(latest_state.get("tick", 0)))
	else:
		_add_section_title(right_content, "SPECIMEN · #%s" % str(selected.id))
		_add_pair(right_content, "Social rank", "Alpha · repeated wins" if selected.get("alpha", false) else "No alpha status")
		_add_pair(right_content, "Age", str(selected.age) + " ticks")
		_add_pair(right_content, "Energy reserve", str(selected.energy) + " · " + _percent(selected.energy_ratio))
		_add_pair(right_content, "Hunger", _percent(selected.hunger))
		_add_pair(right_content, "Injury", _percent(selected.injury))
		_add_pair(right_content, "Satisfaction", _percent(selected.satisfaction))
		var axes: Dictionary = selected.get("satisfaction_vector", {})
		_add_mini_bar(right_content, "Energy security", float(axes.get("energy", 0.0)), Color("#a7d783"))
		_add_mini_bar(right_content, "Offspring", float(axes.get("offspring", 0.0)), Color("#d6bf79"))
		_add_mini_bar(right_content, "Food acquired", float(axes.get("food", 0.0)), Color("#e8a86f"))
		_add_mini_bar(right_content, "Fights won", float(axes.get("fights", 0.0)), Color("#da937f"))
		_add_rule(right_content)
		_add_section_title(right_content, "INHERITED ADAPTATIONS")
		_add_pair(right_content, "Aggression / resilience", _percent(selected.aggression) + " / " + _percent(selected.resilience))
		_add_pair(right_content, "Sociability", _percent(selected.sociability))
		_add_pair(right_content, "Body / movement", str(snappedf(float(selected.size), 0.01)) + " / " + str(snappedf(float(selected.speed), 0.01)))
		_add_pair(right_content, "Foraging perception", str(snappedf(float(selected.perception), 0.1)))
		_add_pair(right_content, "Wins / losses", str(selected.fights_won) + " / " + str(selected.fights_lost))
		_add_pair(right_content, "Food eaten / offspring", str(selected.food_acquired) + " / " + str(selected.offspring))
		_add_pair(right_content, "Lineage", "Founder" if selected.parents.is_empty() else "From #" + str(selected.parents[0]) + " and #" + str(selected.parents[1]))
		_add_pair(right_content, "Belief group", _belief_name(selected.get("belief_id", null)))
		if selected.get("alpha", false):
			_add_paragraph(right_content, "Winning increases its chance of seeking another close encounter. It is an emergent risk pattern, not a commanded player action.")
		if float(selected.injury) > 0.2:
			_add_paragraph(right_content, "Healing burden raises energy use; a damaged creature has less time to find food and recover.")

func _selected_data() -> Dictionary:
	for item in latest_state.get("creatures", []):
		if int(item.id) == selected_creature_id:
			return item
	return {}

func _belief_name(belief_id: Variant) -> String:
	if belief_id == null:
		return "No shared tradition"
	for item in latest_state.get("traditions", []):
		if int(item.id) == int(belief_id):
			return str(item.name)
	return "Tradition recorded"

func _event_names(events: Array) -> String:
	if events.is_empty():
		return "Seasonal cycle"
	var names: Array[String] = []
	for item in events:
		names.append(str(item.get("kind", "event")).capitalize())
	return ", ".join(names)

func _add_section_title(parent: VBoxContainer, text: String) -> void:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 11)
	label.add_theme_color_override("font_color", Color("#b8d89e"))
	parent.add_child(label)

func _add_pair(parent: VBoxContainer, key: String, value: String) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	var left := Label.new()
	left.text = key
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	left.add_theme_font_size_override("font_size", 11)
	left.add_theme_color_override("font_color", Color("#a9b7a7"))
	var right := Label.new()
	right.text = value
	right.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	right.add_theme_font_size_override("font_size", 11)
	right.add_theme_color_override("font_color", Color("#e3eadc"))
	row.add_child(left)
	row.add_child(right)
	parent.add_child(row)

func _add_paragraph(parent: VBoxContainer, text: String) -> void:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 11)
	label.add_theme_color_override("font_color", Color("#cad5c7"))
	parent.add_child(label)

func _add_mini_bar(parent: VBoxContainer, title: String, value: float, color: Color) -> void:
	var label := Label.new()
	label.text = title + "  ·  " + _percent(value)
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_color_override("font_color", Color("#b8c7b1"))
	parent.add_child(label)
	var bar := ProgressBar.new()
	bar.min_value = 0.0
	bar.max_value = 1.0
	bar.value = clampf(value, 0.0, 1.0)
	bar.show_percentage = false
	bar.custom_minimum_size.y = 7
	var fill := StyleBoxFlat.new()
	fill.bg_color = color
	fill.set_corner_radius_all(3)
	bar.add_theme_stylebox_override("fill", fill)
	var track := StyleBoxFlat.new()
	track.bg_color = Color("#3b4b40")
	track.set_corner_radius_all(3)
	bar.add_theme_stylebox_override("background", track)
	parent.add_child(bar)

func _add_rule(parent: VBoxContainer) -> void:
	var line := ColorRect.new()
	line.color = Color("#b4cc9d33")
	line.custom_minimum_size.y = 1
	parent.add_child(line)

func _clear_children(parent: Node) -> void:
	for child in parent.get_children():
		child.queue_free()

func _percent(value: Variant) -> String:
	return str(roundi(float(value) * 100.0)) + "%"

func _toggle_pause() -> void:
	if bool(latest_state.get("paused", false)):
		_send_command({"action":"resume"})
	else:
		_send_command({"action":"pause"})

func _toggle_food_drop() -> void:
	drop_food_mode = not drop_food_mode
	header_status.text = "CLICK GROUND TO PLACE FOOD" if drop_food_mode else "●  LIVE FIELD STUDY"

func _send_command(value: Dictionary) -> void:
	var request := HTTPRequest.new()
	request.timeout = 2.0
	request.request_completed.connect(_on_command_result.bind(request))
	add_child(request)
	var error := request.request(API + "/command", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(value))
	if error != OK:
		header_status.text = "COMMAND COULD NOT REACH FIELD ENGINE"
		request.queue_free()

func _on_command_result(result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray, request: HTTPRequest) -> void:
	request.queue_free()
	if result != HTTPRequest.RESULT_SUCCESS or response_code >= 400:
		var message: Variant = JSON.parse_string(body.get_string_from_utf8())
		header_status.text = str(message.get("error", "Field command failed")) if message is Dictionary else "FIELD COMMAND FAILED"

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse := event as InputEventMouseButton
		if mouse.button_index == MOUSE_BUTTON_RIGHT:
			dragging_camera = mouse.pressed
			get_viewport().set_input_as_handled()
		elif mouse.button_index == MOUSE_BUTTON_WHEEL_UP and mouse.pressed:
			camera_distance = max(34.0, camera_distance - 4.0)
			_update_camera()
		elif mouse.button_index == MOUSE_BUTTON_WHEEL_DOWN and mouse.pressed:
			camera_distance = min(115.0, camera_distance + 4.0)
			_update_camera()
		elif mouse.button_index == MOUSE_BUTTON_LEFT and mouse.pressed:
			_handle_world_click(mouse.position)
	elif event is InputEventMouseMotion and dragging_camera:
		camera_yaw -= (event as InputEventMouseMotion).relative.x * 0.006
		camera_pitch = clampf(camera_pitch - (event as InputEventMouseMotion).relative.y * 0.004, 0.42, 1.25)
		_update_camera()
	elif event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_SPACE:
			_toggle_pause()
		elif event.keycode == KEY_ESCAPE:
			drop_food_mode = false

func _handle_world_click(screen_position: Vector2) -> void:
	var hovered := get_viewport().gui_get_hovered_control()
	if hovered != null:
		return
	if drop_food_mode:
		var origin := camera.project_ray_origin(screen_position)
		var direction := camera.project_ray_normal(screen_position)
		if absf(direction.y) < 0.0001:
			return
		var distance := -origin.y / direction.y
		if distance <= 0.0:
			return
		var point := origin + direction * distance
		var x := clampf((point.x + world_width * SCALE * 0.5) / (world_width * SCALE), 0.0, 1.0)
		var y := clampf((point.z + world_height * SCALE * 0.5) / (world_height * SCALE), 0.0, 1.0)
		_send_command({"action":"food", "x":x, "y":y})
		drop_food_mode = false
		return
	var closest := 28.0
	var choice := -1
	for item in latest_state.get("creatures", []):
		var world_position := Vector3(float(item.position[0]) * SCALE - world_width * SCALE * 0.5, 0.6, float(item.position[1]) * SCALE - world_height * SCALE * 0.5)
		var projected := camera.unproject_position(world_position)
		var distance := projected.distance_to(screen_position)
		if distance < closest:
			closest = distance
			choice = int(item.id)
	selected_creature_id = choice
	_refresh_panels()

func _update_camera() -> void:
	if not camera:
		return
	var horizontal := camera_distance * cos(camera_pitch)
	camera.position = camera_target + Vector3(sin(camera_yaw) * horizontal, camera_distance * sin(camera_pitch), cos(camera_yaw) * horizontal)
	camera.look_at(camera_target, Vector3.UP)

