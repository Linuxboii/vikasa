extends Node3D
class_name CreatureView

## Procedural ground-hugging animal. Presentation reads snapshots only.
var creature_id := -1
var body: MeshInstance3D
var head: MeshInstance3D
var neck: MeshInstance3D
var muzzle: MeshInstance3D
var selected_ring: MeshInstance3D
var legs: Array[Node3D] = []
var tail: Node3D
var alpha_mark: MeshInstance3D
var injury_mark: MeshInstance3D
var _scale_factor := 0.1
var _world_width := 1200.0
var _world_height := 760.0
var _size_scale := 1.0
var _gait_phase := 0.0
var _speed := 0.0
var _energy_ratio := 1.0
var _injury := 0.0
var _behavior := "explore"
var _selected := false
var _pose_blend := 0.0
var _base_body_y := 0.70

func configure(data: Dictionary, scale_factor: float, world_width: float, world_height: float) -> void:
	_scale_factor = scale_factor
	_world_width = world_width
	_world_height = world_height
	creature_id = int(data.get("id", -1))
	var size_gene := float(data.get("size", 4.0))
	var aggression := clampf(float(data.get("aggression", 0.25)), 0.0, 1.0)
	var resilience := clampf(float(data.get("resilience", 0.5)), 0.0, 1.0)
	var perception := clampf(float(data.get("perception", 2.0)) / 4.0, 0.0, 1.0)
	var sociability := clampf(float(data.get("sociability", 0.5)), 0.0, 1.0)
	_size_scale = clampf(0.78 + size_gene * 0.075, 0.9, 1.4)
	# Most size variation is horizontal so the silhouette remains ground-hugging.
	scale = Vector3(_size_scale, 1.0 + (_size_scale - 1.0) * 0.15, _size_scale)
	_base_body_y = 0.70 * _size_scale
	var hue := fposmod(0.10 + size_gene * 0.013 + resilience * 0.06, 1.0)
	var hide := Color.from_hsv(hue, 0.42 + aggression * 0.10, 0.40 + resilience * 0.08)
	var underside := hide.lightened(0.20)
	var accent := Color.from_hsv(fposmod(hue + 0.10, 1.0), 0.38, 0.64)
	var dark := hide.darkened(0.32)
	body = _ellipsoid("Body", Vector3(-0.02, _base_body_y, 0), Vector3(1.46, 0.37, 0.51), _mat(hide), 18, 12)
	_ellipsoid("Belly", Vector3(0.0, _base_body_y - 0.23, 0), Vector3(0.88, 0.22, 0.42), _mat(underside), 16, 10)
	var shoulder := _ellipsoid("Shoulder", Vector3(0.70, _base_body_y + 0.01, 0), Vector3(0.44, 0.37, 0.43), _mat(hide), 16, 10)
	shoulder.rotation.z = -0.10
	var haunch := _ellipsoid("Haunch", Vector3(-0.79, _base_body_y - 0.01, 0), Vector3(0.49, 0.39, 0.45), _mat(hide), 16, 10)
	haunch.rotation.z = 0.08
	neck = _ellipsoid("Neck", Vector3(0.91, _base_body_y + 0.09, 0), Vector3(0.39, 0.28, 0.31), _mat(hide), 16, 10)
	head = _ellipsoid("Head", Vector3(1.20, _base_body_y + 0.19, 0), Vector3(0.31, 0.25, 0.30), _mat(hide), 16, 10)
	muzzle = _ellipsoid("Muzzle", Vector3(1.50, _base_body_y + 0.08, 0), Vector3(0.41, 0.14, 0.21), _mat(underside), 16, 10)
	_ellipsoid("Jaw", Vector3(1.43, _base_body_y - 0.01, 0), Vector3(0.32, 0.105, 0.18), _mat(dark.lightened(0.12)), 14, 8)
	_ellipsoid("Nose", Vector3(1.84, _base_body_y + 0.10, 0), Vector3(0.10, 0.085, 0.15), _mat(dark), 12, 8)
	for side in [-1.0, 1.0]:
		_ellipsoid("Eye", Vector3(1.27, _base_body_y + 0.25, side * 0.255), Vector3(0.052, 0.064, 0.036), _mat(Color("#222720")), 12, 8)
		_ellipsoid("Nostril", Vector3(1.89, _base_body_y + 0.12, side * 0.091), Vector3(0.035, 0.026, 0.018), _mat(Color("#211d18")), 8, 6)
		var ear := _cone("SensoryEar", Vector3(1.03, _base_body_y + 0.39, side * 0.19), 0.105 + perception * 0.045, 0.24 + perception * 0.17, _mat(dark.lightened(0.18)), 9)
		ear.rotation.z = -0.42
		ear.rotation.x = side * 0.35
		# Small flattened coat marks provide gene-linked pattern variation, not jewelry.
		for mark_index in range(2 + roundi(sociability * 2.0)):
			var mark_x := -0.76 + mark_index * 0.25
			var mark_color := dark.lightened(0.20 if mark_index % 2 == 0 else 0.0)
			var coat_mark := _ellipsoid("CoatMark", Vector3(mark_x, _base_body_y + 0.15, side * 0.485), Vector3(0.095 + perception * 0.025, 0.075, 0.028), _mat(mark_color), 10, 6)
			coat_mark.rotation.z = 0.18
	for fore in [true, false]:
		for side in [-1.0, 1.0]:
			var hip := Node3D.new()
			hip.name = ("Fore" if fore else "Hind") + ("Near" if side > 0.0 else "Far") + "Leg"
			hip.position = Vector3(0.84 if fore else -0.84, _base_body_y - 0.12, side * 0.34)
			add_child(hip)
			legs.append(hip)
			var upper := _capsule_under(hip, "UpperLimb", 0.125, 0.43, _mat(dark))
			upper.position.y = -0.16
			upper.rotation.z = 0.10 if fore else -0.16
			_ellipsoid_under(hip, "Knee", Vector3(0.015, -0.30, 0), Vector3(0.13, 0.13, 0.125), _mat(dark.lightened(0.12)))
			var lower := _capsule_under(hip, "LowerLimb", 0.085, 0.34, _mat(dark))
			lower.position = Vector3(0.025, -0.31, 0)
			lower.rotation.z = -0.06 if fore else 0.12
			_ellipsoid_under(hip, "Foot", Vector3(0.10, -0.41, 0), Vector3(0.25, 0.095, 0.16), _mat(dark))
			for toe in [-1.0, 0.0, 1.0]:
				_ellipsoid_under(hip, "Toe", Vector3(0.25, -0.405, toe * 0.084), Vector3(0.085, 0.045, 0.052), _mat(dark.lightened(0.08)))
				var claw := _cone_under(hip, "Claw", Vector3(0.315, -0.415, toe * 0.084), 0.035, 0.11, _mat(Color("#352e24")), 7)
				claw.rotation.z = -PI / 2.0
	tail = Node3D.new()
	tail.name = "TailRoot"
	var tail_length := 0.48 + (1.0 - sociability) * 0.38
	tail.position = Vector3(-1.11, _base_body_y + 0.03, 0)
	add_child(tail)
	_ellipsoid_under(tail, "Tail", Vector3(-tail_length * 0.62, -0.07, 0), Vector3(tail_length, 0.105, 0.12), _mat(dark)).rotation.z = -0.12
	_ellipsoid_under(tail, "TailTip", Vector3(-tail_length * 1.18, -0.12, 0), Vector3(0.20, 0.085, 0.10), _mat(accent)).rotation.z = -0.25
	for i in range(2 + roundi(aggression * 3.0)):
		var ridge := _ellipsoid("DorsalRidge", Vector3(-0.36 + i * 0.20, _base_body_y + 0.31, 0), Vector3(0.105, 0.10 + aggression * 0.075, 0.15), _mat(accent.darkened(0.10)), 10, 6)
		ridge.rotation.z = -0.15
	alpha_mark = _ellipsoid("AlphaMark", Vector3(-0.19, _base_body_y + 0.36, 0), Vector3(0.20, 0.045, 0.39), _mat(Color("#d3ad69")), 14, 8)
	alpha_mark.visible = false
	injury_mark = _ellipsoid("InjuryMark", Vector3(0.26, _base_body_y + 0.22, 0.40), Vector3(0.25, 0.035, 0.09), _mat(Color("#a85d48")), 14, 8)
	injury_mark.visible = false
	var ring := TorusMesh.new()
	ring.inner_radius = 0.90 * _size_scale
	ring.outer_radius = 0.95 * _size_scale
	ring.rings = 6
	ring.ring_segments = 32
	selected_ring = MeshInstance3D.new()
	selected_ring.name = "SelectionGroundRing"
	selected_ring.mesh = ring
	selected_ring.material_override = _mat(Color("#e6d29c"))
	selected_ring.position.y = 0.035
	selected_ring.visible = false
	add_child(selected_ring)
	update_state(data, 0.0)

func update_state(data: Dictionary, delta: float, scale_factor: float = -1.0, world_width: float = -1.0, world_height: float = -1.0) -> void:
	# Optional position arguments preserve the previous Main.gd call contract.
	if scale_factor > 0.0: _scale_factor = scale_factor
	if world_width > 0.0: _world_width = world_width
	if world_height > 0.0: _world_height = world_height
	var pos: Array = data.get("position", [0.0, 0.0])
	var vel: Array = data.get("velocity", [0.0, 0.0])
	if pos.size() >= 2:
		var target := Vector3(float(pos[0]) * _scale_factor - _world_width * _scale_factor * 0.5, 0, float(pos[1]) * _scale_factor - _world_height * _scale_factor * 0.5)
		position = position.lerp(target, clampf(delta * 7, 0, 1))
	var vx := float(vel[0]) if vel.size() >= 2 else 0.0
	var vz := float(vel[1]) if vel.size() >= 2 else 0.0
	_speed = sqrt(vx * vx + vz * vz)
	if _speed > 0.0001: rotation.y = lerp_angle(rotation.y, -atan2(vz, vx), clampf(delta * 6, 0, 1))
	_energy_ratio = clampf(float(data.get("energy_ratio", 1.0)), 0, 1)
	_injury = clampf(float(data.get("injury", 0.0)), 0, 1)
	_behavior = str(data.get("behavior", "explore")).to_lower()
	var resting := _behavior in ["rest", "care"]
	var feeding := _behavior == "forage"
	var displaying := _behavior == "challenge"
	var fleeing := _behavior == "flee"
	_pose_blend = move_toward(_pose_blend, 1.0 if resting else 0.0, clampf(delta * 2.8, 0, 1))
	_gait_phase = fposmod(_gait_phase + delta * clampf(_speed * 5.5, 0, 13), TAU)
	var locomotion := clampf(_speed / 1.8, 0, 1) * (1.0 - _pose_blend)
	for index in legs.size():
		var swing := sin(_gait_phase + (PI if index == 1 or index == 2 else 0.0)) * 0.45 * locomotion
		legs[index].rotation.z = lerpf(legs[index].rotation.z, swing, clampf(delta * 8, 0, 1))
	if body:
		var breath := sin(Time.get_ticks_msec() * 0.002 + float(creature_id % 19)) * 0.018
		var stride_bob := absf(sin(_gait_phase * 2)) * 0.05 * locomotion
		body.position.y = lerpf(body.position.y, _base_body_y + breath + stride_bob - 0.07 * _pose_blend, clampf(delta * 5, 0, 1))
	if head and neck and muzzle:
		var dip := -0.18 if feeding else (0.09 if displaying else (-0.05 if fleeing else 0.0))
		head.position.y = lerpf(head.position.y, _base_body_y + 0.20 + dip, clampf(delta * 4, 0, 1))
		neck.position.y = lerpf(neck.position.y, _base_body_y + 0.08 + dip * 0.55, clampf(delta * 4, 0, 1))
		muzzle.position.y = lerpf(muzzle.position.y, _base_body_y + 0.06 + dip, clampf(delta * 4, 0, 1))
	if tail: tail.rotation.z = lerpf(tail.rotation.z, sin(_gait_phase * 0.5) * 0.11 + (0.18 if _behavior == "challenge" else 0.0), clampf(delta * 3, 0, 1))
	if selected_ring: selected_ring.visible = _selected
	if alpha_mark: alpha_mark.visible = bool(data.get("alpha", false))
	if injury_mark: injury_mark.visible = _injury > 0.12
	if body and body.material_override is StandardMaterial3D:
		var material := body.material_override as StandardMaterial3D
		material.albedo_color = material.albedo_color.lerp(Color("#55534a"), (1.0 - _energy_ratio) * 0.30)

func set_selected(value: bool) -> void:
	_selected = value
	if selected_ring: selected_ring.visible = value

func _ellipsoid(node_name: String, at: Vector3, dimensions: Vector3, material: Material, radial: int = 18, rings: int = 12) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	var mesh := SphereMesh.new()
	mesh.radial_segments = radial
	mesh.rings = rings
	mesh.radius = 1
	mesh.height = 2
	instance.mesh = mesh
	instance.material_override = material
	instance.position = at
	instance.scale = dimensions
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(instance)
	return instance

func _ellipsoid_under(parent: Node3D, node_name: String, at: Vector3, dimensions: Vector3, material: Material) -> MeshInstance3D:
	var instance := _ellipsoid(node_name, at, dimensions, material, 14, 10)
	remove_child(instance)
	parent.add_child(instance)
	return instance

func _capsule_under(parent: Node3D, node_name: String, radius: float, height: float, material: Material) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 10
	mesh.rings = 4
	instance.mesh = mesh
	instance.material_override = material
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	parent.add_child(instance)
	return instance

func _cone_under(parent: Node3D, node_name: String, at: Vector3, radius: float, height: float, material: Material, radial: int) -> MeshInstance3D:
	var instance := _cone(node_name, at, radius, height, material, radial)
	remove_child(instance)
	parent.add_child(instance)
	return instance

func _cone(node_name: String, at: Vector3, radius: float, height: float, material: Material, radial: int) -> MeshInstance3D:
	var instance := MeshInstance3D.new()
	instance.name = node_name
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.0
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = radial
	instance.mesh = mesh
	instance.material_override = material
	instance.position = at
	instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(instance)
	return instance

func _mat(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.88
	material.metallic = 0
	return material
