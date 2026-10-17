extends Node3D
class_name WeatherFX
## Precipitation, airborne motes, fireflies and lightning. Particles are fully
## procedural on the GPU; the CPU only chooses a mode and an intensity.

signal lightning(at: Vector3)

const MODES := {"storm": 0, "flood": 0, "cold": 1, "wildfire": 2, "disease": 3, "abundance": 4, "drought": 5, "heat": 5}
const CAPACITY := 6000
const FIREFLIES := 260

var precipitation: MultiMeshInstance3D
var fireflies: MultiMeshInstance3D
var bolt: MeshInstance3D
var _bolt_mesh: ImmediateMesh
var _precip_material: ShaderMaterial
var _firefly_material: ShaderMaterial
var _bolt_life := 0.0
var _next_strike := 3.0
var budget := 1.0
var area := Vector2(40, 28)
var kind := ""

func _ready() -> void:
	name = "Weather"
	_precip_material = _material()
	_firefly_material = _material()
	_firefly_material.set_shader_parameter("mode", 6)
	precipitation = _system(CAPACITY, _precip_material)
	fireflies = _system(FIREFLIES, _firefly_material)
	_bolt_mesh = ImmediateMesh.new()
	bolt = MeshInstance3D.new()
	bolt.mesh = _bolt_mesh
	var glow := StandardMaterial3D.new()
	glow.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	glow.albedo_color = Color(0.85, 0.9, 1.0)
	glow.emission_enabled = true
	glow.emission = Color(0.7, 0.8, 1.0)
	glow.emission_energy_multiplier = 8.0
	bolt.material_override = glow
	bolt.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(bolt)

func _material() -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/weather.gdshader")
	return material

func _system(count: int, material: ShaderMaterial) -> MultiMeshInstance3D:
	var mesh := QuadMesh.new()
	mesh.size = Vector2(1, 1)
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.instance_count = count
	multimesh.visible_instance_count = 0
	multimesh.mesh = mesh
	var node := MultiMeshInstance3D.new()
	node.multimesh = multimesh
	node.material_override = material
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	node.custom_aabb = AABB(Vector3(-200, -10, -200), Vector3(400, 60, 400))
	add_child(node)
	return node

## conditions: clock, wind, night, weather, intensity, center
func update(delta: float, conditions: Dictionary) -> void:
	kind = str(conditions.weather)
	var intensity := clampf(float(conditions.intensity), 0.0, 3.0)
	for material in [_precip_material, _firefly_material]:
		material.set_shader_parameter("clock", conditions.clock)
		material.set_shader_parameter("wind", conditions.wind)
		material.set_shader_parameter("center", conditions.center)
		material.set_shader_parameter("area", area)
	var mode: int = MODES.get(kind, -1)
	if mode >= 0:
		_precip_material.set_shader_parameter("mode", mode)
		var share := 1.0 if mode == 0 else (0.45 if mode == 1 else 0.22)
		precipitation.multimesh.visible_instance_count = int(CAPACITY * share * budget * clampf(0.45 + intensity * 0.4, 0.3, 1.0))
		_precip_material.set_shader_parameter("intensity", 1.0)
	else:
		precipitation.multimesh.visible_instance_count = 0
	var night := float(conditions.night)
	var calm := kind not in ["storm", "flood", "cold", "wildfire"]
	fireflies.multimesh.visible_instance_count = int(FIREFLIES * budget) if night > 0.35 and calm else 0
	_firefly_material.set_shader_parameter("intensity", clampf((night - 0.35) * 2.0, 0.0, 1.0))
	_update_lightning(delta, intensity, conditions.center)

func _update_lightning(delta: float, intensity: float, center: Vector3) -> void:
	if _bolt_life > 0.0:
		_bolt_life -= delta
		bolt.visible = _bolt_life > 0.0 and fmod(_bolt_life, 0.08) > 0.025
	if kind != "storm":
		return
	_next_strike -= delta * (0.6 + intensity * 0.5)
	if _next_strike <= 0.0:
		_next_strike = randf_range(2.5, 7.0)
		var strike := center + Vector3(randf_range(-area.x, area.x) * 0.8, 0.0, randf_range(-area.y, area.y) * 0.8)
		_draw_bolt(strike)
		lightning.emit(strike)

func _draw_bolt(strike: Vector3) -> void:
	_bolt_mesh.clear_surfaces()
	_bolt_mesh.surface_begin(Mesh.PRIMITIVE_TRIANGLES)
	var top := strike + Vector3(randf_range(-6, 6), 46.0, randf_range(-6, 6))
	var points: Array[Vector3] = []
	var segments := 14
	for i in range(segments + 1):
		var t := float(i) / segments
		var p := top.lerp(strike, t)
		if i > 0 and i < segments: p += Vector3(randf_range(-1.6, 1.6), 0, randf_range(-1.6, 1.6))
		points.append(p)
	for i in range(segments):
		var a := points[i]
		var b := points[i + 1]
		var w := 0.22 * (1.0 - float(i) / segments) + 0.06
		for v in [a + Vector3(-w, 0, 0), b + Vector3(-w, 0, 0), b + Vector3(w, 0, 0), a + Vector3(-w, 0, 0), b + Vector3(w, 0, 0), a + Vector3(w, 0, 0),
				a + Vector3(0, 0, -w), b + Vector3(0, 0, -w), b + Vector3(0, 0, w), a + Vector3(0, 0, -w), b + Vector3(0, 0, w), a + Vector3(0, 0, w)]:
			_bolt_mesh.surface_add_vertex(v)
	_bolt_mesh.surface_end()
	_bolt_life = 0.32
	bolt.visible = true
