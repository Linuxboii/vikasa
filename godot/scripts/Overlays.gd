extends Node3D
class_name Overlays
## Explanatory geometry for the selected animal: a live halo, its sensing
## radius, its home range, the thing it is heading for, and glowing threads
## to living parents and dependent young.

var halo: MeshInstance3D
var sense: MeshInstance3D
var home: MeshInstance3D
var threads: MeshInstance3D
var _lines: ImmediateMesh
var _materials: Array[ShaderMaterial] = []
var show_sense := true
var enabled := true

func _ready() -> void:
	name = "SelectionOverlays"
	halo = _ring(Color(1.0, 0.82, 0.42, 1.0), 0.09, 0.0, 0.0, 2.2)
	sense = _ring(Color(0.45, 0.85, 1.0, 0.55), 0.012, 48.0, 0.05, 1.4)
	home = _ring(Color(0.55, 1.0, 0.65, 0.5), 0.02, 24.0, -0.03, 1.2)
	(home.material_override as ShaderMaterial).set_shader_parameter("fill", 0.4)
	_lines = ImmediateMesh.new()
	threads = MeshInstance3D.new()
	threads.mesh = _lines
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.vertex_color_use_as_albedo = true
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	material.no_depth_test = false
	threads.material_override = material
	threads.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(threads)
	hide_all()

func _ring(color: Color, width: float, dashes: float, speed: float, energy: float) -> MeshInstance3D:
	var quad := QuadMesh.new()
	quad.orientation = PlaneMesh.FACE_Y
	quad.size = Vector2(2, 2)
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/ring.gdshader")
	material.set_shader_parameter("color", color)
	material.set_shader_parameter("width", width)
	material.set_shader_parameter("dashes", dashes)
	material.set_shader_parameter("speed", speed)
	material.set_shader_parameter("energy", energy)
	_materials.append(material)
	var node := MeshInstance3D.new()
	node.mesh = quad
	node.material_override = material
	node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(node)
	return node

func hide_all() -> void:
	for node in [halo, sense, home, threads]: node.visible = false
	_lines.clear_surfaces()

func update(clock: float, swarm: CreatureSwarm, selected: int, details: Dictionary) -> void:
	if not enabled:
		hide_all()
		return
	for material in _materials: material.set_shader_parameter("clock", clock)
	var at := swarm.position_of(selected)
	if selected < 0 or at == Vector3.INF:
		hide_all()
		return
	var row := swarm.row_of(selected)
	var body: float = 1.5 * (swarm.agents[selected].size_scale if swarm.agents.has(selected) else 1.0)
	halo.visible = true
	halo.position = at + Vector3(0, 0.08, 0)
	var pulse := 1.0 + sin(clock * 3.0) * 0.06
	halo.scale = Vector3.ONE * body * pulse
	halo.rotation.y = clock * 0.6
	var s := swarm.scale_factor
	if show_sense and not row.is_empty():
		sense.visible = true
		sense.position = at + Vector3(0, 0.1, 0)
		sense.scale = Vector3.ONE * maxf(1.0, float(row.perception) * s)
	else:
		sense.visible = false
	var home_range: Variant = details.get("home_range")
	if home_range is Dictionary and home_range.get("center") is Array:
		var center: Array = home_range.center
		home.visible = true
		home.position = swarm.to_world(Vector2(float(center[0]), float(center[1]))) + Vector3(0, 0.07, 0)
		home.scale = Vector3.ONE * maxf(0.6, float(home_range.get("radius", 24.0)) * s)
	else:
		home.visible = false
	_lines.clear_surfaces()
	var segments: Array = []
	var target: Variant = details.get("target_position")
	if target is Array and target.size() >= 2:
		segments.append([at, swarm.to_world(Vector2(float(target[0]), float(target[1]))), Color(1.0, 0.86, 0.5, 0.9), 0.4])
	for parent in details.get("parents", []):
		var p := swarm.position_of(int(parent))
		if p != Vector3.INF: segments.append([at, p, Color(1.0, 0.72, 0.35, 0.8), 3.0])
	for child in details.get("dependent_ids", []):
		var c := swarm.position_of(int(child))
		if c != Vector3.INF: segments.append([at, c, Color(0.5, 1.0, 0.65, 0.85), 2.0])
	if segments.is_empty():
		threads.visible = false
		return
	threads.visible = true
	_lines.surface_begin(Mesh.PRIMITIVE_LINES)
	for segment in segments:
		var a: Vector3 = segment[0] + Vector3(0, 1.0, 0)
		var b: Vector3 = segment[1] + Vector3(0, 1.0, 0)
		var lift: float = segment[3]
		var color: Color = segment[2]
		var steps := 18
		for i in steps:
			var t0 := float(i) / steps
			var t1 := float(i + 1) / steps
			# Arc upward; a travelling bright bead shows direction of the bond.
			var bead := 1.0 - clampf(absf(fposmod(clock * 0.6, 1.0) - t0) * 6.0, 0.0, 1.0)
			_lines.surface_set_color(Color(color.r, color.g, color.b, color.a * (0.45 + bead)))
			_lines.surface_add_vertex(a.lerp(b, t0) + Vector3(0, sin(t0 * PI) * lift, 0))
			_lines.surface_add_vertex(a.lerp(b, t1) + Vector3(0, sin(t1 * PI) * lift, 0))
	_lines.surface_end()
