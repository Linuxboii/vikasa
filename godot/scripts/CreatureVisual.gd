extends Node3D
class_name CreatureVisual

var creature_id: int
var body: MeshInstance3D
var crest: MeshInstance3D
var halo: MeshInstance3D
var eye_left: MeshInstance3D
var eye_right: MeshInstance3D
var pulse_phase: float = 0.0
var target_position: Vector3 = Vector3.ZERO
var target_heading: float = 0.0
var energy_ratio: float = 1.0
var selected: bool = false

func configure(data: Dictionary, scale_factor: float, world_width: float, world_height: float) -> void:
	creature_id = int(data.id)
	pulse_phase = float(creature_id % 29) * 0.31
	var size_gene := float(data.get("size", 3.0))
	var aggression := float(data.get("aggression", 0.25))
	var resilience := float(data.get("resilience", 0.5))
	var hue := fposmod(0.25 + size_gene * 0.035 + resilience * 0.17, 1.0)
	var skin := Color.from_hsv(hue, 0.43 + aggression * 0.18, 0.66 + resilience * 0.22)
	var underbelly := skin.lightened(0.23)
	var glow := Color.from_hsv(fposmod(hue + 0.13, 1.0), 0.48, 0.98)
	var body_radius := (0.36 + size_gene * 0.085) * scale_factor
	var material := _material(skin, 0.27, 0.16)

	body = _sphere("Body", Vector3(0, body_radius * 0.83, 0), Vector3(body_radius * 1.48, body_radius * 0.8, body_radius), material, 24, 16)
	var belly := _sphere("Belly", Vector3(body_radius * 0.18, body_radius * 0.51, body_radius * 0.1), Vector3(body_radius * 0.93, body_radius * 0.48, body_radius * 0.79), _material(underbelly, 0.36), 20, 12)
	var head := _sphere("Head", Vector3(body_radius * 1.16, body_radius * 1.16, 0), Vector3(body_radius * 0.57, body_radius * 0.52, body_radius * 0.53), material, 20, 14)
	var muzzle := _sphere("Muzzle", Vector3(body_radius * 1.47, body_radius * 0.98, 0), Vector3(body_radius * 0.27, body_radius * 0.19, body_radius * 0.28), _material(underbelly, 0.38), 16, 10)
	eye_left = _sphere("EyeLeft", Vector3(body_radius * 1.34, body_radius * 1.36, body_radius * 0.39), Vector3.ONE * body_radius * 0.12, _material(Color("#f1cf78"), 0.2, 0.58), 12, 8)
	eye_right = _sphere("EyeRight", Vector3(body_radius * 1.34, body_radius * 1.36, -body_radius * 0.39), Vector3.ONE * body_radius * 0.12, eye_left.mesh.material_override, 12, 8)
	crest = _sphere("LivingCrest", Vector3(body_radius * 0.63, body_radius * 1.64, 0), Vector3(body_radius * (0.34 + aggression * 0.24), body_radius * (0.55 + aggression * 0.42), body_radius * 0.36), _material(glow, 0.3, 0.24), 16, 10)
	var tail := _sphere("Tail", Vector3(-body_radius * 1.58, body_radius * 0.8, 0), Vector3(body_radius * 0.82, body_radius * 0.16, body_radius * 0.18), _material(skin.darkened(0.12), 0.34), 16, 8)
	tail.rotation.z = -0.12
	for side in [-1.0, 1.0]:
		for leg_index in range(2):
			var leg := _capsule("Leg", body_radius * 0.11, body_radius * 0.48, _material(skin.darkened(0.17), 0.42))
			leg.position = Vector3(body_radius * (0.65 if leg_index == 0 else -0.56), body_radius * 0.2, side * body_radius * 0.54)
			leg.rotation.z = -0.12 if leg_index == 0 else 0.14
		var frill := _sphere("SensoryFin", Vector3(-body_radius * 0.18, body_radius * 1.35, side * body_radius * 0.62), Vector3(body_radius * 0.58, body_radius * 0.14, body_radius * 0.09), _material(glow.darkened(0.12), 0.3, 0.2), 14, 8)
		frill.rotation.y = side * 0.27
	if float(data.get("injury", 0.0)) > 0.25:
		var scar := _sphere("HealingMark", Vector3(0, body_radius * 1.47, body_radius * 0.56), Vector3(body_radius * 0.25, body_radius * 0.13, body_radius * 0.1), _material(Color("#d89065"), 0.4), 12, 8)
		scar.rotation.z = -0.45
	if bool(data.get("alpha", false)):
		halo = MeshInstance3D.new()
		var torus := TorusMesh.new()
		torus.inner_radius = body_radius * 0.8
		torus.outer_radius = body_radius * 0.89
		halo.mesh = torus
		halo.material_override = _material(Color("#e6bd70"), 0.22, 0.45)
		halo.position.y = body_radius * 2.0
		add_child(halo)
	target_position = _world_position(data.position, scale_factor, world_width, world_height)
	target_heading = -atan2(float(data.velocity[1]), float(data.velocity[0]))
	energy_ratio = float(data.get("energy_ratio", 1.0))
	position = target_position
	rotation.y = target_heading

func update_state(data: Dictionary, scale_factor: float, delta: float, world_width: float, world_height: float) -> void:
	target_position = _world_position(data.position, scale_factor, world_width, world_height)
	target_heading = -atan2(float(data.velocity[1]), float(data.velocity[0]))
	energy_ratio = float(data.get("energy_ratio", 1.0))
	position = position.lerp(target_position, min(1.0, delta * 8.0))
	rotation.y = lerp_angle(rotation.y, target_heading, min(1.0, delta * 6.0))
	var breath := 1.0 + sin(Time.get_ticks_msec() * 0.003 + pulse_phase) * 0.025
	if body:
		body.scale.y = breath
	if halo:
		halo.rotation.y += delta * 0.65
	var dim := 0.55 + energy_ratio * 0.45
	if body and body.material_override is StandardMaterial3D:
		(body.material_override as StandardMaterial3D).albedo_color.a = dim

func set_selected(value: bool) -> void:
	selected = value
	if body and body.material_override is StandardMaterial3D:
		(body.material_override as StandardMaterial3D).emission_energy_multiplier = 0.4 if value else 0.16

static func _world_position(raw: Array, scale_factor: float, world_width: float, world_height: float) -> Vector3:
	return Vector3(float(raw[0]) * scale_factor - world_width * scale_factor * 0.5, 0.0, float(raw[1]) * scale_factor - world_height * scale_factor * 0.5)

func _sphere(node_name: String, at: Vector3, dimensions: Vector3, material: Material, rings: int, radial: int) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = node_name
	var mesh := SphereMesh.new()
	mesh.radial_segments = radial
	mesh.rings = rings
	mesh.radius = 1.0
	mesh.height = 2.0
	mesh_instance.mesh = mesh
	mesh_instance.material_override = material
	mesh_instance.position = at
	mesh_instance.scale = dimensions
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mesh_instance)
	return mesh_instance

func _capsule(node_name: String, radius: float, height: float, material: Material) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = node_name
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = max(height, radius * 2.0)
	mesh.radial_segments = 8
	mesh_instance.mesh = mesh
	mesh_instance.material_override = material
	mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mesh_instance)
	return mesh_instance

func _material(color: Color, roughness: float, glow_energy: float = 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	material.metallic = 0.04
	material.emission_enabled = glow_energy > 0.0
	material.emission = color
	material.emission_energy_multiplier = glow_energy
	return material
