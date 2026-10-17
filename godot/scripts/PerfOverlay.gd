extends PanelContainer
class_name PerfOverlay
## F3: live frame-time graph and renderer counters, for proving the showcase
## stays smooth on the machine it runs on.

var client: Node
var quality: Node
var _label: Label
var _graph: Control
var _times := PackedFloat32Array()
var _accumulator := 0.0

func _ready() -> void:
	name = "Performance"
	BiomeUI.panel(self, 0.88)
	custom_minimum_size = Vector2(280, 0)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var box := VBoxContainer.new()
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(box)
	_label = BiomeUI.label("", 12, BiomeUI.INK)
	box.add_child(_label)
	_graph = Control.new()
	_graph.custom_minimum_size = Vector2(240, 56)
	_graph.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_graph.draw.connect(_draw_graph)
	box.add_child(_graph)
	visible = false

func _process(delta: float) -> void:
	if not visible: return
	_times.append(delta * 1000.0)
	if _times.size() > 120: _times = _times.slice(_times.size() - 120)
	_accumulator += delta
	if _accumulator < 0.25: return
	_accumulator = 0.0
	var worst := 0.0
	var total := 0.0
	for t in _times:
		worst = maxf(worst, t)
		total += t
	var lines := [
		"%d FPS · %.1f ms avg · %.1f ms worst" % [Engine.get_frames_per_second(), total / maxf(1, _times.size()), worst],
		"%d draw calls · %d objects · %dk primitives" % [Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME), Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME), int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME) / 1000.0)],
		"%d nodes · %.0f MB video · %.0f MB static" % [Performance.get_monitor(Performance.OBJECT_NODE_COUNT), Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0, Performance.get_monitor(Performance.MEMORY_STATIC) / 1048576.0],
	]
	if client: lines.append("bridge: %s %.0f frames/s · state %.0f ms" % [client.transport, client.frames_per_second, client.state_latency_ms])
	if quality: lines.append("quality: %s · render scale %d%%" % [quality.describe(), roundi(get_viewport().scaling_3d_scale * 100.0)])
	_label.text = "\n".join(lines)
	_graph.queue_redraw()

func _draw_graph() -> void:
	var size := _graph.size
	_graph.draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, 0.25))
	for budget in [16.67, 33.3]:
		var y: float = size.y - budget / 50.0 * size.y
		_graph.draw_line(Vector2(0, y), Vector2(size.x, y), Color(1, 1, 1, 0.18), 1)
	if _times.size() < 2: return
	var points := PackedVector2Array()
	for i in _times.size():
		points.append(Vector2(size.x * i / 119.0, size.y - clampf(_times[i] / 50.0, 0.0, 1.0) * size.y))
	_graph.draw_polyline(points, BiomeUI.TEAL, 1.5, true)
