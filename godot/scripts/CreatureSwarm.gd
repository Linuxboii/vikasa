extends Node3D
class_name CreatureSwarm
## Renders the whole population with two GPU-instanced draw calls (near/far LOD)
## plus one for soft contact shadows. Frames arrive at ~20–30 Hz; every agent
## glides from where it is drawn to the newest sample over one measured frame
## interval, so motion stays continuous at any display rate.

signal born(id: int, at: Vector3)
signal died(id: int, at: Vector3)
signal crowned(id: int, at: Vector3)

const STRIDE := 20
const CAPACITY := 640
const BIRTH_SECONDS := 0.8
const DEATH_SECONDS := 1.6

class Agent:
	var id := 0
	var x := 0.0
	var y := 0.0
	var vx := 0.0
	var vy := 0.0
	var energy := 1.0
	var behavior := 0
	var size := 4.0
	var speed := 2.0
	var perception := 80.0
	var aggression := 0.3
	var resilience := 0.5
	var sociability := 0.5
	var bridge_flags := 0
	var founder := 0
	var generation := 0
	var age := 0
	var injury := 0.0
	var known := false
	var look_key := -1
	var pos := Vector2.ZERO
	var from := Vector2.ZERO
	var to := Vector2.ZERO
	var progress := 1.0
	var heading := 0.0
	var gait := 0.0
	var rest := 0.0
	var dip := 0.0
	var age_seconds := 10.0
	var dying := -1.0
	var coat := Color.WHITE
	var flags := 0
	var size_scale := 1.0
	var world := Vector3.ZERO

	func to_row() -> Dictionary:
		return {"id": id, "x": x, "y": y, "vx": vx, "vy": vy, "energy": energy, "behavior": behavior,
			"size": size, "speed": speed, "perception": perception, "aggression": aggression,
			"resilience": resilience, "sociability": sociability, "flags": bridge_flags,
			"founder": founder, "generation": generation, "age": age, "injury": injury}

var scale_factor := 0.1
var width := 720.0
var height := 480.0
var agents: Dictionary = {}
var selected_id := -1
var view_mode := "natural"
var lod_distance := 46.0
var paused := false
var ground_speed := 1.0
var _interval := 0.05
var _last_arrival := -1.0
var _last_tick := -1
var _near: MultiMeshInstance3D
var _far: MultiMeshInstance3D
var _shadows: MultiMeshInstance3D
var _near_buffer := PackedFloat32Array()
var _far_buffer := PackedFloat32Array()
var _shadow_buffer := PackedFloat32Array()
var material: ShaderMaterial
var _clock := 0.0

func _ready() -> void:
	material = ShaderMaterial.new()
	material.shader = load("res://shaders/creature.gdshader")
	_near = _instanced(CreatureMesh.build(true), material, "NearPopulation")
	_far = _instanced(CreatureMesh.build(false), material, "FarPopulation")
	var shadow_material := ShaderMaterial.new()
	shadow_material.shader = load("res://shaders/contact_shadow.gdshader")
	var quad := QuadMesh.new()
	quad.size = Vector2(1, 1)
	quad.orientation = PlaneMesh.FACE_Y
	_shadows = _instanced(quad, shadow_material, "ContactShadows")
	_near_buffer.resize(CAPACITY * STRIDE)
	_far_buffer.resize(CAPACITY * STRIDE)
	_shadow_buffer.resize(CAPACITY * STRIDE)

func _instanced(mesh: Mesh, mat: Material, node_name: String) -> MultiMeshInstance3D:
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.use_custom_data = true
	multimesh.instance_count = CAPACITY
	multimesh.visible_instance_count = 0
	multimesh.mesh = mesh
	var instance := MultiMeshInstance3D.new()
	instance.name = node_name
	instance.multimesh = multimesh
	instance.material_override = mat
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	# Animals roam the whole plate; a fixed bound avoids per-frame AABB rebuilds.
	instance.custom_aabb = AABB(Vector3(-200, -5, -200), Vector3(400, 20, 400))
	add_child(instance)
	return instance

func configure(world_width: float, world_height: float, world_scale: float) -> void:
	width = world_width
	height = world_height
	scale_factor = world_scale

func clear() -> void:
	agents.clear()
	_last_tick = -1
	_last_arrival = -1.0
	for node in [_near, _far, _shadows]: node.multimesh.visible_instance_count = 0

func count() -> int:
	var total := 0
	for agent in agents.values(): if agent.dying < 0.0: total += 1
	return total

func to_world(point: Vector2) -> Vector3:
	return Vector3((point.x - width * 0.5) * scale_factor, 0.0, (point.y - height * 0.5) * scale_factor)

func position_of(id: int) -> Vector3:
	var agent: Agent = agents.get(id)
	return agent.world if agent != null else Vector3.INF

func row_of(id: int) -> Dictionary:
	var agent: Agent = agents.get(id)
	return agent.to_row() if agent != null and agent.dying < 0.0 and agent.known else {}

func apply_frame(frame: Dictionary) -> void:
	var now := Time.get_ticks_msec() / 1000.0
	var tick := int(frame.tick)
	paused = bool(frame.paused)
	var restarted := tick < _last_tick
	var first := _last_tick < 0 or restarted
	if restarted:
		agents.clear()
	if _last_arrival > 0.0 and not first and tick != _last_tick:
		_interval = lerpf(_interval, clampf(now - _last_arrival, 0.025, 0.5), 0.25)
	_last_arrival = now
	_last_tick = tick
	ground_speed = maxf(0.0, float(frame.actual_ticks_per_second)) * scale_factor
	var data: PackedFloat32Array = frame.data
	var stride := int(frame.stride)
	var offset := int(frame.offset)
	var seen: Dictionary = {}
	# Hot path (~25 Hz): typed fields only, no per-animal Dictionary allocation.
	for i in int(frame.count):
		var o := offset + i * stride
		var id := int(data[o])
		seen[id] = true
		var target := Vector2(data[o + 1], data[o + 2])
		var flags := int(data[o + 13])
		var agent: Agent = agents.get(id)
		if agent == null:
			agent = Agent.new()
			agent.id = id
			agent.pos = target
			agent.from = target
			agent.heading = -atan2(data[o + 4], data[o + 3])
			agent.age_seconds = 10.0 if first else 0.0
			agent.gait = randf() * TAU
			agents[id] = agent
			if not first: born.emit(id, to_world(target))
		elif agent.dying >= 0.0:
			agent.dying = -1.0
		elif not first and flags & 1 and not (agent.bridge_flags & 1):
			crowned.emit(id, to_world(target))
		agent.from = agent.pos
		agent.to = target
		agent.progress = 0.0 if not paused else 1.0
		if paused or agent.from.distance_to(target) > 40.0:
			agent.pos = target
			agent.from = target
		agent.x = target.x
		agent.y = target.y
		agent.vx = data[o + 3]
		agent.vy = data[o + 4]
		agent.energy = data[o + 5]
		agent.behavior = int(data[o + 6])
		agent.size = data[o + 7]
		agent.speed = data[o + 8]
		agent.perception = data[o + 9]
		agent.aggression = data[o + 10]
		agent.resilience = data[o + 11]
		agent.sociability = data[o + 12]
		agent.bridge_flags = flags
		agent.founder = int(data[o + 14])
		agent.generation = int(data[o + 15])
		agent.age = int(data[o + 16])
		agent.injury = data[o + 17]
		agent.known = true
		# Recompute colour/shape only when something visible changed.
		var key := agent.behavior | (flags << 3) | (int(agent.energy * 20.0) << 9) | (mini(agent.age / 24, 10) << 15) | (int(id == selected_id) << 20)
		if key != agent.look_key:
			agent.look_key = key
			_refresh_look(agent)
	for id in agents.keys():
		var agent: Agent = agents[id]
		if not seen.has(id) and agent.dying < 0.0:
			if first:
				agents.erase(id)
			else:
				agent.dying = 0.0
				died.emit(id, agent.world)

func _refresh_look(agent: Agent) -> void:
	agent.coat = ViewModes.coat(view_mode, agent.to_row())
	var perception := clampf((agent.perception - 25.0) / 125.0, 0.0, 1.0)
	var behavior := agent.behavior
	var bridge_flags := agent.bridge_flags
	var flags := 0
	if agent.id == selected_id: flags |= 1
	if bridge_flags & 1: flags |= 2
	if bridge_flags & 2: flags |= 4
	if behavior == 7: flags |= 8
	flags |= roundi(perception * 3.0) << 4
	flags |= roundi((1.0 - agent.sociability) * 3.0) << 6
	flags |= roundi(agent.aggression * 3.0) << 8
	if behavior == 3 or behavior == 4: flags |= 1024
	agent.flags = flags
	agent.size_scale = clampf(0.78 + agent.size * 0.075, 0.9, 1.4)
	if bridge_flags & 4:
		agent.size_scale *= 0.55 + 0.45 * clampf(float(agent.age) / 240.0, 0.0, 1.0)

func set_view_mode(mode: String) -> void:
	view_mode = mode
	for agent in agents.values():
		if agent.known: _refresh_look(agent)

func set_selected(id: int) -> void:
	var previous: Agent = agents.get(selected_id)
	selected_id = id
	if previous != null and previous.known: _refresh_look(previous)
	var current: Agent = agents.get(id)
	if current != null and current.known: _refresh_look(current)

func set_night(value: float) -> void:
	material.set_shader_parameter("night", value)

func update(delta: float, camera: Camera3D) -> void:
	_clock += delta
	material.set_shader_parameter("clock", _clock)
	var eye := camera.global_position if camera else Vector3.ZERO
	var near_count := 0
	var far_count := 0
	var shadow_count := 0
	var gone: Array = []
	var stride_length := 1.25
	for agent: Agent in agents.values():
		var behavior := agent.behavior
		var sink := 0.0
		var grow := 1.0
		if agent.dying >= 0.0:
			agent.dying += delta
			if agent.dying >= DEATH_SECONDS:
				gone.append(agent.id)
				continue
			var fade := agent.dying / DEATH_SECONDS
			sink = fade * fade * 1.1
			grow = 1.0 - fade * 0.35
		else:
			agent.age_seconds += delta
			if agent.age_seconds < BIRTH_SECONDS:
				var t := agent.age_seconds / BIRTH_SECONDS
				grow = 1.0 + sin(t * PI * 1.5) * 0.25 * (1.0 - t) - (1.0 - t) * (1.0 - t)
				grow = maxf(0.05, grow)
		if not paused and agent.dying < 0.0:
			agent.progress = minf(1.0, agent.progress + delta / _interval)
			agent.pos = agent.from.lerp(agent.to, agent.progress)
		var velocity := Vector2(agent.vx, agent.vy)
		var speed := velocity.length()
		if speed > 0.02 and agent.dying < 0.0:
			agent.heading = lerp_angle(agent.heading, -atan2(velocity.y, velocity.x), clampf(delta * 6.0, 0.0, 1.0))
		var moving := 0.0 if paused or agent.dying >= 0.0 else speed
		var resting := 1.0 if behavior == 2 or behavior == 4 else 0.0
		agent.rest = move_toward(agent.rest, resting, delta * 1.6)
		var dip_target := -0.18 if behavior == 1 else (0.09 if behavior == 7 else (-0.05 if behavior == 5 else 0.0))
		agent.dip = lerpf(agent.dip, dip_target, clampf(delta * 4.0, 0.0, 1.0))
		# Gait cadence follows real ground speed so feet do not skate.
		var ground := moving * ground_speed
		agent.gait = fposmod(agent.gait + minf(18.0, ground / stride_length * TAU) * delta, TAU)
		var locomotion := clampf(moving / 1.6, 0.0, 1.0) * (1.0 - agent.rest)
		var stride := remap(clampf(agent.speed, 0.5, 4.0), 0.5, 4.0, 0.85, 1.15)
		agent.world = to_world(agent.pos) + Vector3(0, -sink, 0)
		var s := agent.size_scale * grow
		var basis := Basis(Vector3.UP, agent.heading).scaled(Vector3(s, s * (1.0 + (agent.size_scale - 1.0) * 0.15) / agent.size_scale, s))
		var coat := agent.coat
		if agent.dying >= 0.0: coat = coat.lerp(Color("#d8e4ec"), agent.dying / DEATH_SECONDS)
		var dip01 := clampf((agent.dip + 0.25) / 0.5, 0.0, 1.0)
		var custom := Color(agent.gait, locomotion * stride, agent.rest, float(agent.flags))
		var detailed := agent.id == selected_id or eye.distance_squared_to(agent.world) < lod_distance * lod_distance
		if detailed and near_count < CAPACITY:
			_write(_near_buffer, near_count, basis, agent.world, Color(coat.r, coat.g, coat.b, dip01), custom)
			near_count += 1
		elif far_count < CAPACITY:
			_write(_far_buffer, far_count, basis, agent.world, Color(coat.r, coat.g, coat.b, dip01), custom)
			far_count += 1
		if shadow_count < CAPACITY:
			var footprint := 3.4 * s
			var shade := 0.55 * grow * (1.0 - clampf(agent.dying, 0.0, 1.0)) if agent.dying >= 0.0 else 0.55 * minf(1.0, grow)
			_write(_shadow_buffer, shadow_count, Basis(Vector3.UP, agent.heading).scaled(Vector3(footprint, 1.0, footprint * 0.55)), to_world(agent.pos) + Vector3(0, 0.06, 0), Color(0, 0, 0, shade), Color())
			shadow_count += 1
	for id in gone: agents.erase(id)
	_commit(_near, _near_buffer, near_count)
	_commit(_far, _far_buffer, far_count)
	_commit(_shadows, _shadow_buffer, shadow_count)

func _write(buffer: PackedFloat32Array, index: int, basis: Basis, origin: Vector3, color: Color, custom: Color) -> void:
	var o := index * STRIDE
	buffer[o] = basis.x.x; buffer[o + 1] = basis.y.x; buffer[o + 2] = basis.z.x; buffer[o + 3] = origin.x
	buffer[o + 4] = basis.x.y; buffer[o + 5] = basis.y.y; buffer[o + 6] = basis.z.y; buffer[o + 7] = origin.y
	buffer[o + 8] = basis.x.z; buffer[o + 9] = basis.y.z; buffer[o + 10] = basis.z.z; buffer[o + 11] = origin.z
	buffer[o + 12] = color.r; buffer[o + 13] = color.g; buffer[o + 14] = color.b; buffer[o + 15] = color.a
	buffer[o + 16] = custom.r; buffer[o + 17] = custom.g; buffer[o + 18] = custom.b; buffer[o + 19] = custom.a

func _commit(instance: MultiMeshInstance3D, buffer: PackedFloat32Array, used: int) -> void:
	instance.multimesh.buffer = buffer
	instance.multimesh.visible_instance_count = used

func pick(screen: Vector2, camera: Camera3D, radius: float = 26.0) -> int:
	var best := radius
	var choice := -1
	for agent: Agent in agents.values():
		if agent.dying >= 0.0: continue
		var point := agent.world + Vector3(0, 0.7 * agent.size_scale, 0)
		if camera.is_position_behind(point): continue
		var separation := camera.unproject_position(point).distance_to(screen)
		if separation < best:
			best = separation
			choice = agent.id
	return choice
