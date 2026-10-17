extends MultiMeshInstance3D
class_name FoodField
## All food patches as one instanced draw of glowberry clusters. Rebuilt only
## when a frame arrives; growth and sway are animated in the shader.

const CAPACITY := 1024
const STRIDE := 20
var _material: ShaderMaterial
var _buffer := PackedFloat32Array()
var _born: Dictionary = {}
var clock := 0.0

func _ready() -> void:
	name = "FoodPatches"
	var cluster := MeshMerge.merge([
		[MeshMerge.sphere(0.16, 8, 5), Transform3D(Basis(), Vector3(0, 0.16, 0))],
		[MeshMerge.sphere(0.12, 7, 4), Transform3D(Basis(), Vector3(0.17, 0.11, 0.06))],
		[MeshMerge.sphere(0.12, 7, 4), Transform3D(Basis(), Vector3(-0.12, 0.10, 0.14))],
		[MeshMerge.sphere(0.11, 7, 4), Transform3D(Basis(), Vector3(-0.05, 0.12, -0.17))],
		[MeshMerge.sphere(0.09, 6, 4), Transform3D(Basis(), Vector3(0.04, 0.33, 0.02))],
	])
	multimesh = MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = true
	multimesh.use_custom_data = true
	multimesh.instance_count = CAPACITY
	multimesh.visible_instance_count = 0
	multimesh.mesh = cluster
	_material = ShaderMaterial.new()
	_material.shader = load("res://shaders/food.gdshader")
	material_override = _material
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	custom_aabb = AABB(Vector3(-200, -5, -200), Vector3(400, 10, 400))
	_buffer.resize(CAPACITY * STRIDE)

func clear() -> void:
	_born.clear()
	multimesh.visible_instance_count = 0

func apply_frame(frame: Dictionary, swarm: CreatureSwarm, quiet: bool) -> Array:
	## Returns world positions of food that appeared since the last frame.
	var data: PackedFloat32Array = frame.data
	var stride := int(frame.resource_stride)
	var offset := int(frame.resource_offset)
	var count := mini(int(frame.resource_count), CAPACITY)
	var maximum := maxf(1.0, float(frame.get("maximum_energy", 230.0)) * 0.25)
	var seen: Dictionary = {}
	var fresh: Array = []
	for i in count:
		var o := offset + i * stride
		var id := int(data[o])
		var at := swarm.to_world(Vector2(data[o + 1], data[o + 2]))
		seen[id] = true
		if not _born.has(id):
			_born[id] = -10.0 if quiet else clock
			if not quiet: fresh.append(at)
		var s := 1.0 + clampf(data[o + 3] / maximum, 0.0, 1.0) * 0.8
		var b := i * STRIDE
		var spin := float(id % 17) * 0.37
		var basis := Basis(Vector3.UP, spin).scaled(Vector3(s, s, s))
		_buffer[b] = basis.x.x; _buffer[b + 1] = basis.y.x; _buffer[b + 2] = basis.z.x; _buffer[b + 3] = at.x
		_buffer[b + 4] = basis.x.y; _buffer[b + 5] = basis.y.y; _buffer[b + 6] = basis.z.y; _buffer[b + 7] = at.y - 0.05
		_buffer[b + 8] = basis.x.z; _buffer[b + 9] = basis.y.z; _buffer[b + 10] = basis.z.z; _buffer[b + 11] = at.z
		_buffer[b + 12] = 1.0; _buffer[b + 13] = 1.0; _buffer[b + 14] = 1.0; _buffer[b + 15] = 1.0
		var born: float = _born[id]
		_buffer[b + 16] = -100.0 if clock - born > 1.5 else fmod(born, 64.0); _buffer[b + 17] = clampf(data[o + 3] / maximum, 0.0, 1.0); _buffer[b + 18] = fposmod(float(id) * 0.1373, 1.0); _buffer[b + 19] = 0.0
	for id in _born.keys():
		if not seen.has(id): _born.erase(id)
	multimesh.buffer = _buffer
	multimesh.visible_instance_count = count
	return fresh

func tick(delta: float, night: float) -> void:
	clock += delta
	_material.set_shader_parameter("clock", clock)
	_material.set_shader_parameter("night", night)
