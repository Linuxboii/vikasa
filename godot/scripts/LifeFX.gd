extends MultiMeshInstance3D
class_name LifeFX
## Ring-buffer pool of GPU particles for births, deaths, clashes, food and
## alpha crowning. Emitting writes a few instances; the shader animates them.

enum Kind { BIRTH, DEATH, CLASH, FOOD, CROWN }
const CAPACITY := 2048
const COUNTS := {Kind.BIRTH: 26, Kind.DEATH: 22, Kind.CLASH: 18, Kind.FOOD: 14, Kind.CROWN: 30}

var clock := 0.0
var _cursor := 0
var _material: ShaderMaterial
var budget := 1.0

func _ready() -> void:
	name = "LifeEvents"
	var mesh := QuadMesh.new()
	mesh.size = Vector2(1, 1)
	multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_custom_data = true
	multimesh.instance_count = CAPACITY
	multimesh.mesh = mesh
	for i in CAPACITY:
		multimesh.set_instance_transform(i, Transform3D(Basis(Vector3(-1000.0, 0, 0), Vector3.UP, Vector3.BACK), Vector3.ZERO))
	_material = ShaderMaterial.new()
	_material.shader = load("res://shaders/life_fx.gdshader")
	material_override = _material
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	custom_aabb = AABB(Vector3(-200, -10, -200), Vector3(400, 40, 400))

func emit(kind: int, at: Vector3, scale_factor: float = 1.0) -> void:
	var count := maxi(4, int(COUNTS[kind] * budget))
	for i in count:
		# Start time rides in the float32 transform; custom data may be half precision.
		multimesh.set_instance_transform(_cursor, Transform3D(Basis(Vector3(clock, 0, 0), Vector3.UP, Vector3.BACK), at))
		multimesh.set_instance_custom_data(_cursor, Color(0.0, float(kind), randf() * 100.0, scale_factor))
		_cursor = (_cursor + 1) % CAPACITY

func tick(delta: float) -> void:
	clock += delta
	_material.set_shader_parameter("clock", clock)
