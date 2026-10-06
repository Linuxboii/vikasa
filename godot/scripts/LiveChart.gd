extends Control
## Bounded, interactive plots. Values come directly from engine metric samples.
var samples: Array = []
var series: Array = []
var heading := "Population"
var normalized := false
var hover_index := -1

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	custom_minimum_size = Vector2(220, 112)
	resized.connect(queue_redraw)
	mouse_exited.connect(func(): hover_index = -1; queue_redraw())

func configure(title: String, fields: Array, ratios: bool = false) -> void:
	heading = title
	series = fields
	normalized = ratios
	queue_redraw()

func set_samples(values: Array) -> void:
	samples = values.slice(maxi(0, values.size() - 180))
	hover_index = mini(hover_index, samples.size() - 1)
	queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and not samples.is_empty():
		hover_index = clampi(roundi((event.position.x - 30) / maxf(1, size.x - 38) * (samples.size() - 1)), 0, samples.size() - 1)
		queue_redraw()

func _draw() -> void:
	var font := get_theme_default_font()
	draw_string(font, Vector2(0, 14), heading, HORIZONTAL_ALIGNMENT_LEFT, -1, 14, BiomeUI.INK)
	var area := Rect2(30, 34, maxf(1, size.x - 38), maxf(24, size.y - 53))
	var ceiling := 1.0 if normalized else 0.1
	for sample in samples:
		for field in series:
			if not normalized: ceiling = maxf(ceiling, float(sample.get(field.key, 0)))
	if not normalized:
		var scale := pow(10.0, floor(log(ceiling) / log(10.0)))
		ceiling = ceil(ceiling / scale) * scale
	for i in range(3):
		var y := area.position.y + area.size.y * float(i) / 2.0
		draw_line(Vector2(area.position.x, y), Vector2(area.end.x, y), Color("#93b2b51e"), 1)
		var value := (1.0 - float(i) / 2.0) * ceiling
		var label := "%.1f" % value if not normalized and ceiling < 5 else "%d" % roundi(value * (100 if normalized else 1))
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
			var x := area.position.x + (float(sample.get("tick", 0)) - first_tick) / tick_span * area.size.x
			var y := area.end.y - clampf(float(sample.get(field.key, 0)) / ceiling, 0, 1) * area.size.y
			points.append(Vector2(x, y))
		if points.size() > 1: draw_polyline(points, color, 1.8, true)
		draw_circle(points[-1], 2.5, color)
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
			text += " · %s %.1f%s" % [field.label, float(sample.get(field.key, 0)) * (100 if normalized else 1), "%" if normalized else ""]
		tooltip_text = text
