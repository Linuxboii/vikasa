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
	body = _ellipsoid("Body", Vector3(-0.02, _base_body_y, 0), Vector3(1.30, 0.49, 0.59), _mat(hide), 24, 16)
	_ellipsoid("Flank", Vector3(0.02, _base_body_y - 0.22, 0), Vector3(0.92, 0.28, 0.49), _mat(underside), 20, 12)
	var shoulder := _ellipsoid("Shoulder", Vector3(0.65, _base_body_y + 0.03, 0), Vector3(0.54, 0.43, 0.49), _mat(hide), 18, 12)
	shoulder.rotation.z = -0.10
	var haunch := _ellipsoid("Haunch", Vector3(-0.72, _base_body_y - 0.01, 0), Vector3(0.58, 0.47, 0.53), _mat(hide), 18, 12)
	haunch.rotation.z = 0.08
	neck = _ellipsoid("Neck", Vector3(0.83, _base_body_y + 0.08, 0), Vector3(0.48, 0.32, 0.36), _mat(hide), 18, 12)
	head = _ellipsoid("Head", Vector3(1.12, _base_body_y + 0.20, 0), Vector3(0.40, 0.31, 0.38), _mat(hide), 20, 14)
	muzzle = _ellipsoid("Muzzle", Vector3(1.43, _base_body_y + 0.06, 0), Vector3(0.36, 0.18, 0.25), _mat(underside), 16, 10)
	for side in [-1.0, 1.0]:
		_ellipsoid("Eye", Vector3(1.20, _base_body_y + 0.27, side * 0.335), Vector3(0.075, 0.09, 0.045), _mat(Color("#27332b")), 12, 8)
		var ear := _cone("SensoryEar", Vector3(0.92, _base_body_y + 0.45, side * 0.22), 0.16 + perception * 0.08, 0.38 + perception * 0.20, _mat(accent), 10)
		ear.rotation.z = -0.18
		ear.rotation.x = side * 0.35
	for fore in [true, false]:
		for side in [-1.0, 1.0]:
			var hip := Node3D.new()
			hip.name = ("Fore" if fore else "Hind") + ("Near" if side > 0.0 else "Far") + "Leg"
			hip.position = Vector3(0.82 if fore else -0.81, _base_body_y - 0.18, side * 0.39)
			add_child(hip)
			legs.append(hip)
			var upper := _ellipsoid("UpperLimb", Vector3(0, -0.14, 0), Vector3(0.15, 0.31, 0.15), _mat(dark), 14, 10)
			remove_child(upper)
			hip.add_child(upper)
			_ellipsoid_under(hip, "LowerLimb", Vector3(0.015, -0.24, 0), Vector3(0.105, 0.25, 0.11), _mat(dark))
			_ellipsoid_under(hip, "Foot", Vector3(0.09, -0.34, 0), Vector3(0.22, 0.105, 0.155), _mat(dark))
	tail = Node3D.new()
	tail.name = "TailRoot"
	tail.position = Vector3(-1.03, _base_body_y + 0.04, 0)
	add_child(tail)
	_ellipsoid_under(tail, "Tail", Vector3(-0.36, -0.08, 0), Vector3(0.52, 0.12, 0.14), _mat(dark)).rotation.z = -0.12
	_ellipsoid_under(tail, "TailTip", Vector3(-0.78, -0.14, 0), Vector3(0.22, 0.10, 0.12), _mat(accent)).rotation.z = -0.25
	for i in range(3):
		var ridge := _cone("BackRidge", Vector3(-0.28 + i * 0.29, _base_body_y + 0.40, 0), 0.11 + aggression * 0.035, 0.20 + sociability * 0.08, _mat(accent), 8)
		ridge.rotation.z = PI
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
