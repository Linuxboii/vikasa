extends PanelContainer
class_name LegendsPanel
## Hall of legends: who is oldest, most prolific, undefeated, best fed, deepest
## in descent, and which founding mother's line dominates — plus session records.
## Every row is clickable and flies the camera to that animal.

signal focus_requested(creature_id: int)
signal closed

const TITLES := [
	{"key": "age", "title": "Elder", "glyph": "⌛", "unit": "ticks old"},
	{"key": "offspring", "title": "Matriarch / patriarch", "glyph": "✦", "unit": "offspring"},
	{"key": "fights_won", "title": "Champion", "glyph": "⚔", "unit": "clashes won"},
	{"key": "generation", "title": "Deepest descent", "glyph": "⧗", "unit": "generations"},
	{"key": "food_acquired", "title": "Master forager", "glyph": "❀", "unit": "energy eaten"},
]

var rows: VBoxContainer
var records: Label
var peak_population := 0
var peak_generation := 0
var _rows_by_key: Dictionary = {}

func _ready() -> void:
	name = "Legends"
	BiomeUI.panel(self)
	custom_minimum_size = Vector2(372, 0)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	var head := HBoxContainer.new()
	box.add_child(head)
	var title := BiomeUI.label("Hall of legends", 25, BiomeUI.ACCENT)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(title)
	var close := BiomeUI.button("Close", "L or Esc")
	close.pressed.connect(func(): closed.emit())
	head.add_child(close)
	box.add_child(BiomeUI.paragraph("Living record holders. Click a legend to fly to it.", 13))
	rows = VBoxContainer.new()
	rows.add_theme_constant_override("separation", 6)
	box.add_child(rows)
	for spec in TITLES + [{"key": "dynasty", "title": "Greatest dynasty", "glyph": "♛", "unit": "living descendants"}]:
		var button := BiomeUI.button("", "Fly to this animal")
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size.y = 48
		button.add_theme_font_size_override("font_size", 14)
		button.pressed.connect(func(): if button.has_meta("id"): focus_requested.emit(int(button.get_meta("id"))))
		rows.add_child(button)
		_rows_by_key[spec.key] = {"button": button, "spec": spec}
	box.add_child(BiomeUI.label("Session records", 16, BiomeUI.INK))
	records = BiomeUI.paragraph("", 13)
	box.add_child(records)
	visible = false

func set_state(state: Dictionary) -> void:
	var creatures: Array = state.get("creatures", [])
	peak_population = maxi(peak_population, creatures.size())
	for spec in TITLES:
		var best: Dictionary = {}
		for c in creatures:
			if best.is_empty() or float(c.get(spec.key, 0)) > float(best.get(spec.key, 0)): best = c
		_fill(spec.key, best, float(best.get(spec.key, 0)) if not best.is_empty() else 0.0)
		if spec.key == "generation" and not best.is_empty(): peak_generation = maxi(peak_generation, int(best.get("generation", 0)))
	var dynasties: Dictionary = {}
	for c in creatures:
		var founder := int(c.get("founder", c.get("id", -1)))
		dynasties[founder] = dynasties.get(founder, []) + [c]
	var largest := -1
	for founder in dynasties:
		if largest < 0 or dynasties[founder].size() > dynasties[largest].size(): largest = founder
	if largest >= 0:
		var members: Array = dynasties[largest]
		members.sort_custom(func(a, b): return int(a.get("age", 0)) > int(b.get("age", 0)))
		_fill("dynasty", members[0], float(members.size()), "House of #%d" % largest)
	else:
		_fill("dynasty", {}, 0.0)
	records.text = "Peak population %d · deepest generation %d · %d births · %d deaths" % [peak_population, peak_generation, int(state.get("total_births", 0)), int(state.get("total_deaths", 0))]

func _fill(key: String, creature: Dictionary, value: float, name_override: String = "") -> void:
	var row: Dictionary = _rows_by_key[key]
	var button: Button = row.button
	var spec: Dictionary = row.spec
	if creature.is_empty():
		button.text = "%s  %s · —" % [spec.glyph, spec.title]
		button.remove_meta("id")
		button.disabled = true
		return
	button.disabled = false
	button.set_meta("id", int(creature.id))
	var who := name_override if name_override != "" else "#%d" % int(creature.id)
	button.text = "%s  %s · %s\n      %s %s" % [spec.glyph, spec.title, who, _number(value), spec.unit]

func _number(value: float) -> String:
	return str(roundi(value)) if value >= 10.0 or is_equal_approx(value, roundf(value)) else "%.1f" % value

func reset() -> void:
	peak_population = 0
	peak_generation = 0
