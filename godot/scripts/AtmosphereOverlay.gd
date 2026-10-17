extends Control
## Screen-space mood: a soft vignette plus a faint weather tint. Precipitation
## itself is 3D (WeatherFX); this layer only frames the habitat.
var weather := ""

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	resized.connect(queue_redraw)

func set_state(state: Dictionary) -> void:
	var events: Array = state.get("environment", {}).get("active_events", [])
	var next := str(events[0].get("kind", "")) if not events.is_empty() else ""
	if next != weather:
		weather = next
		queue_redraw()

func _draw() -> void:
	var tint := Color.TRANSPARENT
	if weather in ["storm", "flood"]: tint = Color("#1a2c4a22")
	elif weather in ["wildfire", "heat", "drought"]: tint = Color("#e9863214")
	elif weather == "cold": tint = Color("#c7e5ff14")
	elif weather == "disease": tint = Color("#8fdc6a10")
	if tint.a > 0.0: draw_rect(Rect2(Vector2.ZERO, size), tint)
	for i in range(10):
		var alpha := 0.07 * (1.0 - float(i) / 10.0)
		var band := 14.0 * (i + 1)
		draw_rect(Rect2(0, size.y - band, size.x, 14), Color(0.02, 0.05, 0.07, alpha))
		draw_rect(Rect2(0, band - 14, size.x, 14), Color(0.02, 0.05, 0.07, alpha * 0.7))
