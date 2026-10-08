extends Control
## Bounded, interactive plots. Values come directly from engine metric samples.
var samples: Array = []
var series: Array = []
var heading := "Population"
var normalized := false
var signed_values := false
var hover_index := -1

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	custom_minimum_size = Vector2(220, 112)
	resized.connect(queue_redraw)
	mouse_exited.connect(func(): hover_index = -1; queue_redraw())

func configure(title: String, fields: Array, ratios: bool = false, signed_axis: bool = false) -> void:
	heading = title
	series = fields
	normalized = ratios
	signed_values = signed_axis
	queue_redraw()

func set_samples(values: Array) -> void:
	samples = values.slice(maxi(0, values.size() - 180))
	hover_index = mini(hover_index, samples.size() - 1)
	queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and not samples.is_empty():
		var fraction := clampf((event.position.x - 30) / maxf(1, size.x - 38), 0, 1)
		var target_tick := lerpf(float(samples[0].tick), float(samples[-1].tick), fraction)
		hover_index = 0
		for index in range(1, samples.size()):
			if absf(float(samples[index].tick) - target_tick) < absf(float(samples[hover_index].tick) - target_tick):
				hover_index = index
		queue_redraw()

func vertical_bounds() -> Vector2:
	if normalized: return Vector2(0, 1)
	var magnitude := 0.1
	for sample in samples:
		for field in series:
			if sample.get(field.key) == null: continue
			var value := float(sample.get(field.key, 0))
			magnitude = maxf(magnitude, absf(value) if signed_values else value)
	var scale := pow(10.0, floor(log(magnitude) / log(10.0)))
	var high: float = ceilf(magnitude / scale) * scale
	return Vector2(-high if signed_values else 0.0, high)

func axis_label(value: float) -> String:
	if normalized: return "%d" % roundi(value * 100)
	if absf(value) >= 1000000: return "%.1fM" % (value / 1000000)
	if absf(value) >= 10000: return "%.0fk" % (value / 1000)
	if absf(value) >= 1000: return "%.1fk" % (value / 1000)
	if signed_values: return "%.2f" % value
	return "%.1f" % value if absf(value) < 5 else "%d" % roundi(value)

func _draw() -> void:
	var font := get_theme_default_font()
	draw_string(font, Vector2(0, 14), heading, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, BiomeUI.INK)
	var area := Rect2(30, 34, maxf(1, size.x - 38), maxf(24, size.y - 53))
	var limits := vertical_bounds()
	var span := maxf(0.000001, limits.y - limits.x)
	for i in range(3):
		var y := area.position.y + area.size.y * float(i) / 2.0
		draw_line(Vector2(area.position.x, y), Vector2(area.end.x, y), Color("#93b2b51e"), 1)
		var value := limits.y - float(i) / 2.0 * span
		var label := axis_label(value)
		draw_string(font, Vector2(0, y + 4), label, HORIZONTAL_ALIGNMENT_LEFT, 28, 10, BiomeUI.MUTED)
	if samples.is_empty():
		draw_string(font, area.position + Vector2(8, 25), "Sampling the living world…", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, BiomeUI.MUTED)
		return
	var first_tick := float(samples[0].get("tick", 0))
	var tick_span := maxf(1, float(samples[-1].get("tick", 0)) - first_tick)
	for sample in samples:
		if float(sample.get("health_pressure", 0)) > 0.0:
			var x := area.position.x + (float(sample.tick) - first_tick) / tick_span * area.size.x
			draw_line(Vector2(x, area.position.y), Vector2(x, area.end.y), Color("#efa27012"), 3)
	var legend_x := 0.0
	for field in series:
		var color: Color = field.color
		var points := PackedVector2Array()
		for sample in samples:
			if sample.get(field.key) == null:
				if points.size() > 1: draw_polyline(points, color, 1.8, true)
				points.clear()
				continue
			var x := area.position.x + (float(sample.get("tick", 0)) - first_tick) / tick_span * area.size.x
			var y := area.end.y - clampf((float(sample.get(field.key, 0)) - limits.x) / span, 0, 1) * area.size.y
			points.append(Vector2(x, y))
		if points.size() > 1: draw_polyline(points, color, 1.8, true)
		if not points.is_empty(): draw_circle(points[-1], 2.5, color)
		draw_circle(Vector2(legend_x + 3, 26), 2, color)
		draw_string(font, Vector2(legend_x + 10, 29), str(field.label), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, BiomeUI.MUTED)
		legend_x += font.get_string_size(str(field.label), HORIZONTAL_ALIGNMENT_LEFT, -1, 10).x + 24
	draw_string(font, Vector2(area.position.x, size.y - 2), "%d" % first_tick, HORIZONTAL_ALIGNMENT_LEFT, -1, 10, BiomeUI.MUTED)
	draw_string(font, Vector2(area.end.x - 55, size.y - 2), "t %d" % int(samples[-1].tick), HORIZONTAL_ALIGNMENT_RIGHT, 55, 10, BiomeUI.MUTED)
	if hover_index >= 0:
		var sample: Dictionary = samples[hover_index]
		var x := area.position.x + (float(sample.tick) - first_tick) / tick_span * area.size.x
		draw_line(Vector2(x, area.position.y), Vector2(x, area.end.y), BiomeUI.ACCENT, 1)
		var text := "t%d" % int(sample.tick)
		for field in series:
			if sample.get(field.key) == null:
				text += " · %s unavailable" % field.label
				continue
			text += " · %s %.1f%s" % [field.label, float(sample.get(field.key, 0)) * (100 if normalized else 1), "%" if normalized else ""]
		tooltip_text = text
