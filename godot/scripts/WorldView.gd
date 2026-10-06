extends Node3D

signal world_clicked(world_position: Vector2)
signal creature_clicked(creature_id: int)

const SCALE := 0.1
const Animal := preload("res://scripts/CreatureView.gd")
const Land := preload("res://scripts/Habitat.gd")
var placement_mode := false
var camera: Camera3D
var habitat: Node3D
var creatures_root: Node3D
var resources_root: Node3D
var creature_views: Dictionary = {}
var resource_views: Dictionary = {}
var data_by_id: Dictionary = {}
var width := 1200.0
var height := 760.0
var seed_value := -1
var target := Vector3.ZERO
var yaw := 0.24
var pitch := 0.82
var distance := 90.0
var dragging := false
var selected_id := -1
var follow_id := -1
var environment: Environment
var sun: DirectionalLight3D
var _paused := false
var _weather_kind := ""

func _ready() -> void:
	environment = Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color("#a6b79b")
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color("#d4ddbf")
	environment.ambient_light_energy = 0.45
	environment.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	var sky := WorldEnvironment.new()
	sky.environment = environment
	add_child(sky)
	sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -28, 0)
	sun.light_color = Color("#ffe7bb")
	sun.light_energy = 0.85
	sun.shadow_enabled = true
	add_child(sun)
	creatures_root = Node3D.new()
	creatures_root.name = "LivingPopulation"
	add_child(creatures_root)
	resources_root = Node3D.new()
	resources_root.name = "FoodPatches"
	add_child(resources_root)
	camera = Camera3D.new()
	camera.fov = 48.0
	camera.far = 400.0
	camera.current = true
	add_child(camera)
	_rebuild(2026)
	reset_camera()

func _rebuild(seed_number: int) -> void:
	if is_instance_valid(habitat): habitat.queue_free()
	habitat = Land.new()
	habitat.name = "Habitat"
	habitat.build(width, height, SCALE, seed_number)
	add_child(habitat)
	seed_value = seed_number

func set_state(state: Dictionary) -> void:
	_paused = bool(state.get("paused", false))
	var world: Dictionary = state.get("world", {})
	var new_width := maxf(1.0, float(world.get("width", width)))
	var new_height := maxf(1.0, float(world.get("height", height)))
	var new_seed := int(state.get("seed", 2026))
	var dimensions_changed := new_width != width or new_height != height
	width = new_width
	height = new_height
	if dimensions_changed or seed_value != new_seed:
		for view in creature_views.values(): view.queue_free()
		creature_views.clear()
		_rebuild(new_seed)
		reset_camera()
	var seen: Dictionary = {}
	data_by_id.clear()
	for data in state.get("creatures", []):
		if not data is Dictionary: continue
		var id := int(data.get("id", -1))
		seen[id] = true
		data_by_id[id] = data
		if not creature_views.has(id):
			var view = Animal.new()
			view.name = "Creature_%d" % id
			view.configure(data, SCALE, width, height)
			creatures_root.add_child(view)
			# Place immediately at spawn; interpolation starts on the next frame.
			view.position = _position(data.get("position", [0, 0]))
			creature_views[id] = view
		creature_views[id].set_selected(id == selected_id)
		if _paused:
			creature_views[id].update_state(data, 0.0)
			creature_views[id].position = _position(data.get("position", [0, 0]))
	for id in creature_views.keys():
		if not seen.has(id):
			creature_views[id].queue_free()
			creature_views.erase(id)
	_sync_resources(state.get("resources", []))
	var conditions: Dictionary = state.get("environment", {})
	sun.light_energy = lerpf(0.75, 0.95, clampf(float(conditions.get("temperature", 0.5)), 0, 1))
	var events: Array = conditions.get("active_events", [])
	_weather_kind = str(events[0].get("kind", "")) if not events.is_empty() else ""
	environment.background_color = Color("#8b9e9b") if _weather_kind == "storm" else Color("#a6b79b")
	sun.light_color = Color("#b8c9d2") if _weather_kind == "storm" else (Color("#efd1a6") if _weather_kind in ["heat", "wildfire", "drought"] else Color("#ffe7bb"))
	sun.light_energy *= 0.7 if _weather_kind == "storm" else 1.0

func clear_snapshot() -> void:
	_paused = true
	_weather_kind = ""
	environment.background_color = Color("#a6b79b")
	sun.light_color = Color("#ffe7bb")
	sun.light_energy = 0.85
	data_by_id.clear()
	for view in creature_views.values(): view.queue_free()
	creature_views.clear()
	for view in resource_views.values(): view.queue_free()
	resource_views.clear()
	set_selected(-1)
	set_follow(-1)

func _sync_resources(items: Array) -> void:
	var seen: Dictionary = {}
	for data in items:
		if not data is Dictionary: continue
		var id := int(data.get("id", -1))
		seen[id] = true
		if not resource_views.has(id):
			var patch := MeshInstance3D.new()
			var mesh := SphereMesh.new()
			mesh.radial_segments = 10
			mesh.rings = 6
			patch.mesh = mesh
			patch.scale = Vector3(0.22, 0.18, 0.22)
			var material := StandardMaterial3D.new()
			material.albedo_color = Color("#dec16e")
			material.roughness = 0.9
			patch.material_override = material
			resources_root.add_child(patch)
			resource_views[id] = patch
		resource_views[id].position = _position(data.get("position", [0, 0])) + Vector3(0, 0.3, 0)
	for id in resource_views.keys():
		if not seen.has(id):
			resource_views[id].queue_free()
			resource_views.erase(id)

func _position(point: Array) -> Vector3:
	if point.size() < 2: return Vector3.ZERO
	return Vector3((float(point[0]) - width * 0.5) * SCALE, 0, (float(point[1]) - height * 0.5) * SCALE)

func _process(delta: float) -> void:
	for id in creature_views:
		if data_by_id.has(id) and not _paused:
			creature_views[id].update_state(data_by_id[id], delta)
	if follow_id >= 0 and creature_views.has(follow_id):
		target = target.lerp(creature_views[follow_id].position, minf(delta * 4.0, 1.0))
		_update_camera()

func set_selected(id: int) -> void:
	selected_id = id
	for key in creature_views: creature_views[key].set_selected(key == id)

func set_follow(id: int) -> void:
	follow_id = id
	if id >= 0 and creature_views.has(id):
		target = creature_views[id].position
		distance = minf(distance, 27.0)
		_update_camera()

func reset_camera() -> void:
	follow_id = -1
	target = Vector3.ZERO
	yaw = 0.24
	pitch = 0.82
	distance = maxf(42.0, Vector2(width, height).length() * SCALE * 0.67)
	_update_camera()

func _update_camera() -> void:
	var horizontal := distance * cos(pitch)
	camera.position = target + Vector3(sin(yaw) * horizontal, distance * sin(pitch), cos(yaw) * horizontal)
	camera.look_at(target, Vector3.UP)

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			dragging = event.pressed
			get_viewport().set_input_as_handled()
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			distance = clampf(distance + (-5.0 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 5.0), 10.0, 190.0)
			_update_camera()
			get_viewport().set_input_as_handled()
		elif event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			_click(event.position)
	elif event is InputEventMouseMotion and dragging:
		yaw -= event.relative.x * 0.006
		pitch = clampf(pitch - event.relative.y * 0.004, 0.35, 1.3)
		_update_camera()

func _click(screen: Vector2) -> void:
	if not placement_mode:
		var closest := 25.0
		var choice := -1
		for id in creature_views:
			var point: Vector3 = creature_views[id].position + Vector3(0, 0.7, 0)
			if camera.is_position_behind(point): continue
			var separation := camera.unproject_position(point).distance_to(screen)
			if separation < closest:
				closest = separation
				choice = id
		if choice >= 0:
			creature_clicked.emit(choice)
			return
	var origin := camera.project_ray_origin(screen)
	var ray := camera.project_ray_normal(screen)
	if absf(ray.y) < 0.0001: return
	var along := -origin.y / ray.y
	if along <= 0: return
	var hit := origin + ray * along
	var normalized := Vector2(hit.x / (width * SCALE) + 0.5, hit.z / (height * SCALE) + 0.5)
	if normalized.x < 0 or normalized.y < 0 or normalized.x > 1 or normalized.y > 1: return
	world_clicked.emit(normalized)
