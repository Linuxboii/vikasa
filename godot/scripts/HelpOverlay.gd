extends PanelContainer
class_name HelpOverlay
## Keyboard and mouse reference (F1 / ?).

const KEYS := [
	["Space", "Pause / resume"], ["1 · 2 · 3", "Observe · Present · Accelerate"], ["Right-drag", "Orbit camera"],
	["Middle-drag / WASD", "Pan camera"], ["Q · E", "Rotate camera"], ["Wheel", "Zoom"],
	["Click animal", "Select & explain"], ["Double-click", "Fly to & follow"], ["Tab", "Select next animal"],
	["F", "Follow selected"], ["C", "Director (cinematic camera)"], ["V", "Cycle lens: coat, action, energy, dynasty…"],
	["N", "Daylight: cycle · day · golden · night"], ["L", "Hall of legends"], ["G", "Graphs"],
	["T", "World tools"], ["M", "Radar"], ["H", "Hide interface"], ["P", "Photo mode"], ["F12", "Save screenshot"],
	["F3", "Performance overlay"], ["F4", "Quality: auto · battery · balanced · high · ultra"], ["Esc", "Close panels / exit modes"],
]

func _ready() -> void:
	name = "Help"
	set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	grow_horizontal = Control.GROW_DIRECTION_BOTH
	grow_vertical = Control.GROW_DIRECTION_BOTH
	BiomeUI.panel(self, 0.94)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 12)
	add_child(box)
	box.add_child(BiomeUI.label("Field guide", 30, BiomeUI.ACCENT))
	box.add_child(BiomeUI.paragraph("Every animal decides for itself from inherited genes, temperament and changing needs. Nothing you see is scripted.", 14))
	var grid := GridContainer.new()
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 22)
	grid.add_theme_constant_override("v_separation", 7)
	box.add_child(grid)
	for pair in KEYS:
		var key := BiomeUI.chip(pair[0], BiomeUI.TEAL, 13)
		key.size_flags_horizontal = Control.SIZE_SHRINK_END
		grid.add_child(key)
		grid.add_child(BiomeUI.label(pair[1], 14, BiomeUI.INK))
	box.add_child(BiomeUI.label("Press F1 or Esc to close", 12, BiomeUI.MUTED))
	visible = false
