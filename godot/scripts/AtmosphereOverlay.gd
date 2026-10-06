extends Control
## Cheap weather cues, independent of simulation decisions and random streams.
var weather := ""
var clock := 0.0
var active := true

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)

func set_state(state: Dictionary) -> void:
	var events: Array = state.get("environment", {}).get("active_events", [])
	weather = str(events[0].get("kind", "")) if not events.is_empty() else ""
	active = not bool(state.get("paused", false))
	queue_redraw()

func _process(delta: float) -> void:
	if weather in ["storm", "flood", "wildfire", "cold"] and active:
		clock += delta
		queue_redraw()

func _draw() -> void:
	var tint := Color.TRANSPARENT
	if weather in ["storm", "flood"]: tint = Color("#243c6326")
	elif weather in ["wildfire", "heat", "drought"]: tint = Color("#e9863222")
	elif weather == "cold": tint = Color("#c7e5ff20")
	draw_rect(Rect2(Vector2.ZERO, size), tint)
	# Framing leaves a luminous open habitat between the dark instrument panels.
	for i in range(12):
		var alpha := 0.10 * (1.0 - float(i) / 12.0)
		draw_rect(Rect2(0, size.y - 12 * (i + 1), size.x, 12), Color(0.03, 0.07, 0.10, alpha))
	if weather in ["storm", "flood"]:
		for i in range(75):
			var x := fposmod(i * 181.3 + clock * 130, size.x)
			var y := fposmod(i * 97.1 + clock * 530, size.y)
			draw_line(Vector2(x, y), Vector2(x - 8, y + 22), Color("#d3eaff56"), 1, true)
	elif weather in ["wildfire", "cold"]:
		for i in range(45):
			var x := fposmod(i * 127.8 + sin(clock + i) * 16, size.x)
			var y := fposmod(i * 89.3 - clock * (37 if weather == "wildfire" else -25), size.y)
			draw_circle(Vector2(x, y), 1.5, Color("#ffb668b0") if weather == "wildfire" else Color("#ecf5ffa0"))
	var center := Vector2(size.x - 57, 123)
	draw_arc(center, 26, 0, TAU, 32, Color("#eff2dc66"), 1, true)
	draw_line(center + Vector2(0, -20), center + Vector2(0, 20), BiomeUI.ACCENT, 1)
	draw_line(center + Vector2(-20, 0), center + Vector2(20, 0), Color("#eff2dc66"), 1)
	draw_string(get_theme_default_font(), center + Vector2(-4, -31), "N", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, BiomeUI.ACCENT)
