extends Control
class_name Minimap
## Top-down radar of the whole biome: every animal (in the active lens
## colour), food, pools, the selected animal and the camera's ground footprint.
## Click or drag to fly the camera.

signal jump_requested(normalized: Vector2)

var world: Node3D
var _accumulator := 0.0
var _dragging := false

func setup(world_view: Node3D) -> void:
	world = world_view

func _ready() -> void:
	name = "Minimap"
	custom_minimum_size = Vector2(264, 176)
	mouse_filter = Control.MOUSE_FILTER_STOP
	mouse_default_cursor_shape = Control.CURSOR_CROSS
	tooltip_text = "Radar · click or drag to move the camera (M toggles)"

func _process(delta: float) -> void:
	_accumulator += delta
	if _accumulator >= 1.0 / 15.0 and is_visible_in_tree():
		_accumulator = 0.0
		queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		_dragging = event.pressed
		if event.pressed: _jump(event.position)
		accept_event()
	elif event is InputEventMouseMotion and _dragging:
		_jump(event.position)
		accept_event()

func _jump(at: Vector2) -> void:
	var inner := _inner()
	jump_requested.emit(((at - inner.position) / inner.size).clamp(Vector2.ZERO, Vector2.ONE))

func _inner() -> Rect2:
	return Rect2(Vector2(8, 8), size - Vector2(16, 16))

func _to_map(point: Vector3, inner: Rect2) -> Vector2:
	var w: float = world.width * world.SCALE
	var h: float = world.height * world.SCALE
	return inner.position + Vector2(point.x / w + 0.5, point.z / h + 0.5) * inner.size

func _draw() -> void:
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color("#0b1820d9")
	panel.border_color = Color("#7be0c244")
	panel.set_border_width_all(1)
	panel.set_corner_radius_all(12)
	draw_style_box(panel, Rect2(Vector2.ZERO, size))
	if world == null: return
	var inner := _inner()
	draw_rect(inner, Color("#2c4a35"))
	for i in range(1, 6):
		var x := inner.position.x + inner.size.x * i / 6.0
		draw_line(Vector2(x, inner.position.y), Vector2(x, inner.end.y), Color(1, 1, 1, 0.04), 1)
	for i in range(1, 4):
		var y := inner.position.y + inner.size.y * i / 4.0
		draw_line(Vector2(inner.position.x, y), Vector2(inner.end.x, y), Color(1, 1, 1, 0.04), 1)
	var habitat: Habitat = world.habitat
	if habitat:
		for pool in habitat._pools():
			var c := _to_map(Vector3(pool.x, 0, pool.y), inner)
			var r := Vector2(habitat.width * 0.058, habitat.depth * 0.068) / Vector2(habitat.width, habitat.depth) * inner.size
			draw_set_transform(c, 0.0, Vector2(1.0, r.y / maxf(0.001, r.x)))
			draw_circle(Vector2.ZERO, r.x, Color("#3f8a95"))
			draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	var swarm: CreatureSwarm = world.swarm
	var food: FoodField = world.food
	if food and food.multimesh:
		# CPU-side copy: reading MultiMesh.buffer back from the renderer is costly.
		var buffer := food._buffer
		for i in food.multimesh.visible_instance_count:
			var o := i * FoodField.STRIDE
			draw_rect(Rect2(_to_map(Vector3(buffer[o + 3], 0, buffer[o + 11]), inner) - Vector2(1, 1), Vector2(2, 2)), Color("#e8b0d0aa"))
	for agent in swarm.agents.values():
		if agent.dying >= 0.0: continue
		var p := _to_map(agent.world, inner)
		draw_circle(p, 2.3, agent.coat.lightened(0.15))
	if world.selected_id >= 0:
		var at: Vector3 = swarm.position_of(world.selected_id)
		if at != Vector3.INF:
			var p := _to_map(at, inner)
			var pulse := 6.0 + sin(Time.get_ticks_msec() * 0.006) * 1.5
			draw_arc(p, pulse, 0, TAU, 24, BiomeUI.ACCENT, 1.5, true)
	var camera: CameraRig = world.camera
	var viewport_size := get_viewport().get_visible_rect().size
	var corners: PackedVector2Array = []
	for screen in [Vector2(0, viewport_size.y * 0.12), Vector2(viewport_size.x, viewport_size.y * 0.12), viewport_size, Vector2(0, viewport_size.y)]:
		var hit := camera.ground_point(screen)
		if hit == Vector3.INF:
			hit = camera.target + (camera.project_ray_normal(screen) * Vector3(1, 0, 1)).normalized() * 160.0
		var m := _to_map(hit, inner)
		corners.append(m.clamp(inner.position - Vector2(30, 30), inner.end + Vector2(30, 30)))
	corners.append(corners[0])
	draw_polyline(corners, Color("#f0cd8acc"), 1.4, true)
	draw_string(BiomeUI.font(), Vector2(14, size.y - 12), "RADAR", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color("#9db9b8aa"))
