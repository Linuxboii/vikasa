extends Control
## Snapshot loci, not a time series. Observes engine data without changing it.
var population: Dictionary = {}
var frequencies: Array = []
var heterozygosity: Array = []
var hover_index := -1

func _ready() -> void:
	custom_minimum_size = Vector2(220, 160)
	focus_mode = Control.FOCUS_ALL
	mouse_filter = Control.MOUSE_FILTER_STOP
	resized.connect(queue_redraw)

func set_population(value: Variant) -> void:
	population = value if value is Dictionary else {}
	frequencies = population.get("allele_frequency", []) if population.get("allele_frequency") is Array else []
	heterozygosity = population.get("observed_heterozygosity", []) if population.get("observed_heterozygosity") is Array else []
	hover_index = mini(hover_index, frequencies.size() - 1)
	_update_tooltip()
	queue_redraw()

func _gui_input(event: InputEvent) -> void:
	if frequencies.is_empty(): return
	if event is InputEventMouseMotion:
		hover_index = clampi(int((event.position.x - 30) / maxf(1, size.x - 38) * frequencies.size()), 0, frequencies.size() - 1)
	elif event is InputEventKey and event.pressed:
		if event.keycode == KEY_RIGHT: hover_index = mini(hover_index + 1, frequencies.size() - 1)
		elif event.keycode == KEY_LEFT: hover_index = maxi(hover_index - 1, 0)
		elif event.keycode == KEY_HOME: hover_index = 0
		elif event.keycode == KEY_END: hover_index = frequencies.size() - 1
		else: return
		accept_event()
	_update_tooltip()
	queue_redraw()

func _update_tooltip() -> void:
	tooltip_text = ""
	if hover_index < 0: return
	tooltip_text = "Locus %d · allele 1 frequency %.1f%%" % [hover_index + 1, float(frequencies[hover_index]) * 100]
	if hover_index < heterozygosity.size():
		tooltip_text += "\nHeterozygous individuals %.1f%%" % (float(heterozygosity[hover_index]) * 100)
	tooltip_text += "\n%d living individuals · snapshot, not adaptation" % int(population.get("individuals", 0))

func _draw() -> void:
	var font := ThemeDB.fallback_font
	var mint := Color("#7be0c2")
	var gold := Color("#e9c786")
	draw_string(font, Vector2(0, 15), "Linked chromosomes · current population", HORIZONTAL_ALIGNMENT_LEFT, -1, 12, BiomeUI.INK)
	draw_string(font, Vector2(0, 31), "Allele 1 frequency", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, mint)
	draw_string(font, Vector2(110, 31), "Heterozygotes", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, gold)
	if frequencies.is_empty():
		draw_string(font, Vector2(0, 72), "No living chromosome measurements", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, BiomeUI.MUTED)
		return
	var plot := Rect2(30, 43, maxf(1, size.x - 38), maxf(1, size.y - 66))
	for fraction in [0.0, 0.5, 1.0]:
		var y: float = plot.end.y - float(fraction) * plot.size.y
		draw_line(Vector2(plot.position.x, y), Vector2(plot.end.x, y), Color(1, 1, 1, 0.1))
		draw_string(font, Vector2(0, y + 3), "%d%%" % int(fraction * 100), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, BiomeUI.MUTED)
	var step := plot.size.x / frequencies.size()
	for i in frequencies.size():
		var x := plot.position.x + i * step
		if i == hover_index: draw_rect(Rect2(x, plot.position.y, step, plot.size.y), Color(1, 1, 1, 0.08))
		var height := clampf(float(frequencies[i]), 0, 1) * plot.size.y
		draw_rect(Rect2(x + step * 0.12, plot.end.y - height, step * 0.33, height), mint)
		if i < heterozygosity.size():
			height = clampf(float(heterozygosity[i]), 0, 1) * plot.size.y
			draw_rect(Rect2(x + step * 0.52, plot.end.y - height, step * 0.33, height), gold)
		if i % maxi(1, ceili(frequencies.size() / 16.0)) == 0:
			draw_string(font, Vector2(x + step * 0.25, plot.end.y + 14), str(i + 1), HORIZONTAL_ALIGNMENT_LEFT, -1, 9, BiomeUI.MUTED)
	if has_focus(): draw_rect(Rect2(Vector2.ZERO, size), BiomeUI.ACCENT, false)
