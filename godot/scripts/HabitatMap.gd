extends Control
## Actual finite-field cells, not decorative terrain or inferred food density.
var habitat: Dictionary = {}
var hovered_cell := Vector2i(-1, -1)

func _ready() -> void:
	name = "HabitatMap"
	custom_minimum_size = Vector2(220, 145)
	mouse_filter = Control.MOUSE_FILTER_STOP
	resized.connect(queue_redraw)
	mouse_exited.connect(func(): hovered_cell = Vector2i(-1, -1); tooltip_text = "")

func set_habitat(value) -> void:
	habitat = value if value is Dictionary else {}
	_update_tooltip()
	queue_redraw()

func _area() -> Rect2:
	return Rect2(0, 28, maxf(1, size.x), maxf(1, size.y - 48))

func _gui_input(event: InputEvent) -> void:
	if not event is InputEventMouseMotion or habitat.is_empty(): return
	var area := _area()
	if not area.has_point(event.position):
		hovered_cell = Vector2i(-1, -1)
		_update_tooltip()
		return
	var columns := int(habitat.get("columns", 0))
	var rows := int(habitat.get("rows", 0))
	if columns < 1 or rows < 1: return
	var cell: Vector2 = (event.position - area.position) / area.size
	var column := clampi(int(cell.x * columns), 0, columns - 1)
	var row := clampi(int(cell.y * rows), 0, rows - 1)
	hovered_cell = Vector2i(column, row)
	_update_tooltip()

func _update_tooltip() -> void:
	if habitat.is_empty() or hovered_cell.x < 0 or hovered_cell.y < 0 or hovered_cell.x >= int(habitat.get("columns", 0)) or hovered_cell.y >= int(habitat.get("rows", 0)):
		tooltip_text = ""
		return
	var column := hovered_cell.x
	var row := hovered_cell.y
	tooltip_text = "Cell (%d, %d) · plant energy %.1f · soil water %.0f%%" % [column, row, float(habitat.biomass[row][column]), float(habitat.water[row][column]) * 100]

func _draw() -> void:
	var font := get_theme_default_font()
	draw_string(font, Vector2(0, 15), "Habitat field · hover to inspect", HORIZONTAL_ALIGNMENT_LEFT, -1, 13, BiomeUI.INK)
	if habitat.is_empty():
		draw_string(font, Vector2(4, 55), "No spatial field in this configuration", HORIZONTAL_ALIGNMENT_LEFT, -1, 11, BiomeUI.MUTED)
		return
	var columns := int(habitat.get("columns", 0))
	var rows := int(habitat.get("rows", 0))
	if columns < 1 or rows < 1: return
	var area := _area()
	var cell_size := area.size / Vector2(columns, rows)
	var capacity := maxf(0.001, float(habitat.get("capacity", 1)))
	for row in range(rows):
		for column in range(columns):
			var plant := clampf(float(habitat.biomass[row][column]) / capacity, 0, 1)
			var moisture := clampf(float(habitat.water[row][column]), 0, 1)
			var color := Color("#4b3530").lerp(Color("#7be0a1"), plant)
			var cell := Rect2(area.position + Vector2(column, row) * cell_size, cell_size)
			draw_rect(cell.grow(-0.4), color)
			draw_rect(Rect2(cell.position, Vector2(cell_size.x * moisture, 2)), Color("#6bbfe8"))
	draw_string(font, Vector2(0, size.y - 3), "Green: plant reserves · blue: soil water", HORIZONTAL_ALIGNMENT_LEFT, -1, 10, BiomeUI.MUTED)
