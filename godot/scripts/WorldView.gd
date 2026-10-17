extends Node3D
## The living 3D habitat. Owns the camera, atmosphere, terrain, population,
## food, effects and overlays, and turns simulation frames into motion.

signal world_clicked(world_position: Vector2)
signal creature_clicked(creature_id: int)
signal creature_focused(creature_id: int)

const SCALE := 0.1
const BEHAVIORS := ["explore", "forage", "rest", "seek_mate", "care", "flee", "patrol", "challenge"]

var placement_mode := false
var camera: CameraRig
var atmos: Atmos
var habitat: Habitat
var swarm: CreatureSwarm
var food: FoodField
var fx: LifeFX
var weather_fx: WeatherFX
var overlays: Overlays
var width := 720.0
var height := 480.0
var seed_value := -1
var selected_id := -1
var follow_id := -1
var details: Dictionary = {}
var running := false
var speed_scale := 1.0
var cinematic := false
var intro_remaining := 0.0
var grass_density := 1.0
var _last_frame_ms := -100000
var _frames_seen := 0
var _dragging := false
var _panning := false
var _last_click_ms := 0
var _last_click_id := -1

func _ready() -> void:
	atmos = Atmos.new()
	add_child(atmos)
	camera = CameraRig.new()
	camera.name = "Camera"
	add_child(camera)
	swarm = CreatureSwarm.new()
	swarm.name = "LivingPopulation"
	add_child(swarm)
	food = FoodField.new()
	add_child(food)
	fx = LifeFX.new()
	add_child(fx)
	weather_fx = WeatherFX.new()
	add_child(weather_fx)
	overlays = Overlays.new()
	add_child(overlays)
	swarm.born.connect(func(_id: int, at: Vector3): fx.emit(LifeFX.Kind.BIRTH, at))
	swarm.died.connect(func(_id: int, at: Vector3): fx.emit(LifeFX.Kind.DEATH, at))
	swarm.crowned.connect(func(_id: int, at: Vector3): fx.emit(LifeFX.Kind.CROWN, at))
	weather_fx.lightning.connect(_on_lightning)
	_rebuild(2026)
	reset_camera()
	camera.snap()

func _rebuild(seed_number: int) -> void:
	if is_instance_valid(habitat): habitat.queue_free()
	habitat = Habitat.new()
	habitat.name = "Habitat"
	habitat.build(width, height, SCALE, seed_number)
	add_child(habitat)
	habitat.set_grass_density(grass_density)
	seed_value = seed_number
	swarm.configure(width, height, SCALE)
	weather_fx.area = Vector2(width, height) * SCALE * 0.55

## Full explanatory state (~2.5 Hz). Motion comes from frames; when no frame
## stream is available (older bridge, tests) the state doubles as a frame.
func set_state(state: Dictionary) -> void:
	var world: Dictionary = state.get("world", {})
	_resize_world(float(world.get("width", width)), float(world.get("height", height)), int(state.get("seed", 2026)))
	habitat.set_biomass(state.get("habitat"))
	details = {}
	for creature in state.get("creatures", []):
		if creature is Dictionary and int(creature.get("id", -1)) == selected_id:
			details = creature
			break
	if Time.get_ticks_msec() - _last_frame_ms > 1500:
		_apply_frame(frame_from_state(state), true)

func set_frame(frame: Dictionary) -> void:
	_last_frame_ms = Time.get_ticks_msec()
	_apply_frame(frame, false)

func _apply_frame(frame: Dictionary, from_state: bool) -> void:
	_resize_world(float(frame.width), float(frame.height), seed_value)
	running = not bool(frame.paused)
	speed_scale = maxf(0.0, float(frame.actual_ticks_per_second)) / 48.0 if running else 0.0
	swarm.apply_frame(frame)
	food.apply_frame(frame, swarm, from_state or _frames_seen == 0)
	atmos.set_frame(frame)
	_frames_seen += 1

func _resize_world(new_width: float, new_height: float, new_seed: int) -> void:
	new_width = maxf(1.0, new_width)
	new_height = maxf(1.0, new_height)
	if new_width == width and new_height == height and new_seed == seed_value: return
	width = new_width
	height = new_height
	swarm.clear()
	food.clear()
	_rebuild(new_seed)
	reset_camera()

static func frame_from_state(state: Dictionary) -> Dictionary:
	var creatures: Array = state.get("creatures", [])
	var resources: Array = state.get("resources", [])
	var data := PackedFloat32Array()
	var stride := 18
	data.resize(creatures.size() * stride + resources.size() * 4)
	var o := 0
	for c in creatures:
		if not c is Dictionary: continue
		var pos: Array = c.get("position", [0, 0])
		var vel: Array = c.get("velocity", [0, 0])
		var flags := 0
		if c.get("alpha", false): flags |= 1
		if float(c.get("injury", 0.0)) > 0.12: flags |= 2
		var parents: Array = c.get("parents", []) if c.get("parents") is Array else []
		if not parents.is_empty() and int(c.get("age", 999)) < 240: flags |= 4
		var row := [c.get("id", 0), pos[0], pos[1], vel[0] if vel.size() > 1 else 0.0, vel[1] if vel.size() > 1 else 0.0,
			c.get("energy_ratio", 1.0), maxi(0, BEHAVIORS.find(str(c.get("behavior", "explore")))), c.get("size", 4.0),
			c.get("speed", 2.0), c.get("perception", 80.0), c.get("aggression", 0.3), c.get("resilience", 0.5),
			c.get("sociability", 0.5), flags, c.get("founder", c.get("id", 0)), c.get("generation", 0), c.get("age", 0), c.get("injury", 0.0)]
		for v in row:
			data[o] = float(v)
			o += 1
	var resource_offset := o
	var count := o / stride
	for r in resources:
		if not r is Dictionary: continue
		var pos: Array = r.get("position", [0, 0])
		for v in [r.get("id", 0), pos[0], pos[1], r.get("energy", 30.0)]:
			data[o] = float(v)
			o += 1
	data.resize(o)
	var world: Dictionary = state.get("world", {})
	var env: Dictionary = state.get("environment", {})
	var events: Array = env.get("active_events", [])
	return {
		"tick": int(state.get("tick", 0)), "count": count, "resource_count": (o - resource_offset) / 4,
		"stride": stride, "resource_stride": 4, "paused": bool(state.get("paused", true)),
		"ticks_per_second": float(state.get("ticks_per_second", 48)), "actual_ticks_per_second": float(state.get("actual_ticks_per_second", 0)),
		"season_phase": float(["spring", "summer", "autumn", "winter"].find(str(env.get("season", "spring")))) + 0.5,
		"weather": str(events[0].get("kind", "")) if not events.is_empty() else "",
		"weather_intensity": float(events[0].get("intensity", 1.0)) if not events.is_empty() else 0.0,
		"width": float(world.get("width", 720)), "height": float(world.get("height", 480)),
		"maximum_energy": float(world.get("maximum_energy", 230.0)),
		"offset": 0, "resource_offset": resource_offset, "data": data,
	}

func clear_snapshot() -> void:
	running = false
	swarm.clear()
	food.clear()
	details = {}
	set_selected(-1)
	set_follow(-1)
	_frames_seen = 0
	_last_frame_ms = -100000

func set_selected(id: int) -> void:
	selected_id = id
	swarm.set_selected(id)
	if id < 0: details = {}

func set_follow(id: int) -> void:
	follow_id = id
	if id >= 0:
		var at := swarm.position_of(id)
		if at != Vector3.INF: camera.goal_target = at
		camera.goal_distance = minf(camera.goal_distance, 26.0)
		camera.goal_pitch = minf(camera.goal_pitch, 0.62)

func reset_camera() -> void:
	follow_id = -1
	camera.auto_orbit = 0.0
	camera.goal_target = Vector3.ZERO
	camera.goal_yaw = 0.24
	camera.goal_pitch = 0.78
	camera.goal_distance = maxf(42.0, Vector2(width, height).length() * SCALE * 0.72)

func play_intro() -> void:
	intro_remaining = 5.5
	camera.target = Vector3(0, 0, 0)
	camera.yaw = -1.6
	camera.pitch = 1.25
	camera.distance = 230.0
	reset_camera()
	camera.stiffness = 0.9

func focus(point: Vector3, distance: float = -1.0) -> void:
	camera.goal_target = point
	if distance > 0.0: camera.goal_distance = distance

func emit_food_burst(normalized: Vector2) -> void:
	fx.emit(LifeFX.Kind.FOOD, swarm.to_world(normalized * Vector2(width, height)), 1.6)

func flash_clash(winner: int, loser: int) -> void:
	var a := swarm.position_of(winner)
	var b := swarm.position_of(loser)
	if a != Vector3.INF and b != Vector3.INF: fx.emit(LifeFX.Kind.CLASH, a.lerp(b, 0.5) + Vector3(0, 0.6, 0))
	elif a != Vector3.INF: fx.emit(LifeFX.Kind.CLASH, a + Vector3(0, 0.6, 0))

func apply_quality(settings: Dictionary) -> void:
	var viewport := get_viewport()
	viewport.scaling_3d_scale = float(settings.render_scale)
	viewport.msaa_3d = settings.msaa
	atmos.glow_allowed = bool(settings.glow)
	atmos.sun.shadow_enabled = bool(settings.shadows)
	grass_density = float(settings.grass)
	habitat.set_grass_density(grass_density)
	swarm.lod_distance = float(settings.lod)
	fx.budget = float(settings.fx)
	weather_fx.budget = float(settings.fx)

func _on_lightning(at: Vector3) -> void:
	atmos.strike()
	var near := clampf(1.0 - camera.position.distance_to(at) / 120.0, 0.0, 1.0)
	camera.shake(0.25 + near * 0.6)
	fx.emit(LifeFX.Kind.CLASH, at + Vector3(0, 0.3, 0), 2.5)

func _process(delta: float) -> void:
	atmos.update(delta, running, speed_scale)
	var conditions := atmos.conditions
	habitat.set_conditions(conditions)
	swarm.set_night(atmos.night)
	swarm.update(delta, camera)
	food.tick(delta, atmos.night)
	fx.tick(delta)
	var center := Vector3(clampf(camera.target.x, -width * SCALE * 0.4, width * SCALE * 0.4), 0, clampf(camera.target.z, -height * SCALE * 0.4, height * SCALE * 0.4))
	weather_fx.update(delta, {"clock": conditions.clock, "wind": conditions.wind, "night": atmos.night, "weather": conditions.weather, "intensity": conditions.intensity, "center": center})
	overlays.update(conditions.clock, swarm, selected_id, details)
	if follow_id >= 0:
		var at := swarm.position_of(follow_id)
		if at != Vector3.INF: camera.goal_target = at
	_keyboard(delta)
	if intro_remaining > 0.0:
		intro_remaining -= delta
		camera.stiffness = lerpf(0.9, 5.0, clampf(1.0 - intro_remaining / 5.5, 0.0, 1.0))
		if intro_remaining <= 0.0: camera.stiffness = 5.0
	camera.update(delta)

func _keyboard(delta: float) -> void:
	if get_viewport().gui_get_focus_owner() is LineEdit: return
	var move := Vector2.ZERO
	if Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP): move.y += 1
	if Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN): move.y -= 1
	if Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT): move.x -= 1
	if Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT): move.x += 1
	if move != Vector2.ZERO:
		follow_id = -1
		camera.pan(move.normalized() * delta * 900.0)
	if Input.is_physical_key_pressed(KEY_Q): camera.goal_yaw += delta * 1.2
	if Input.is_physical_key_pressed(KEY_E): camera.goal_yaw -= delta * 1.2

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_RIGHT:
			_dragging = event.pressed
			get_viewport().set_input_as_handled()
		elif event.button_index == MOUSE_BUTTON_MIDDLE:
			_panning = event.pressed
			get_viewport().set_input_as_handled()
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			camera.zoom(-1.0 if event.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0)
			get_viewport().set_input_as_handled()
		elif event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
			_click(event.position)
	elif event is InputEventMouseMotion:
		if _dragging:
			camera.orbit(event.relative.x, event.relative.y)
		elif _panning:
			follow_id = -1
			camera.pan(Vector2(-event.relative.x, event.relative.y) * 1.4)

func _click(screen: Vector2) -> void:
	if not placement_mode:
		var choice := swarm.pick(screen, camera)
		if choice >= 0:
			var now := Time.get_ticks_msec()
			if choice == _last_click_id and now - _last_click_ms < 380:
				creature_focused.emit(choice)
			else:
				creature_clicked.emit(choice)
			_last_click_ms = now
			_last_click_id = choice
			return
	var hit := camera.ground_point(screen)
	if hit == Vector3.INF: return
	var normalized := Vector2(hit.x / (width * SCALE) + 0.5, hit.z / (height * SCALE) + 0.5)
	if normalized.x < 0 or normalized.y < 0 or normalized.x > 1 or normalized.y > 1: return
	world_clicked.emit(normalized)
