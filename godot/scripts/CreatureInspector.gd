extends PanelContainer

signal closed
var name_label: Label
var action_label: Label
var summary: Label
var sections: Dictionary = {}
var drive_bars: Dictionary = {}
var drive_labels: Dictionary = {}

func _ready() -> void:
	anchor_left = 1
	anchor_right = 1
	anchor_top = 0
	anchor_bottom = 1
	offset_left = -396
	offset_right = -24
	offset_top = 104
	offset_bottom = -240
	BiomeUI.panel(self)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 14)
	scroll.add_child(content)
	var row := HBoxContainer.new()
	content.add_child(row)
	name_label = BiomeUI.label("Animal", 25, BiomeUI.ACCENT)
	name_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name_label)
	var close := BiomeUI.button("Close", "Escape · Close the inspector")
	close.pressed.connect(func(): closed.emit())
	row.add_child(close)
	action_label = BiomeUI.paragraph("", 18, BiomeUI.INK)
	content.add_child(action_label)
	summary = BiomeUI.paragraph("", 16)
	content.add_child(summary)
	for title in ["Instincts", "Genome", "Encounters", "Lineage"]:
		var toggle := BiomeUI.button(title + "  +", "Show " + title.to_lower() + " details")
		toggle.toggle_mode = true
		content.add_child(toggle)
		var detail := VBoxContainer.new()
		detail.add_theme_constant_override("separation", 8)
		detail.hide()
		content.add_child(detail)
		toggle.toggled.connect(func(open: bool): detail.visible = open; toggle.text = title + ("  −" if open else "  +"))
		if title == "Instincts":
			for key in ["survival", "foraging", "mating", "offspring_care", "danger_avoidance", "territory"]:
				var caption := BiomeUI.label(key.replace("_", " ").capitalize(), 15, BiomeUI.MUTED)
				detail.add_child(caption)
				drive_labels[key] = caption
				var bar := BiomeUI.meter(Color("#b8bc88"))
				detail.add_child(bar)
				drive_bars[key] = bar
			detail.add_child(BiomeUI.paragraph("These pressures compete for attention; a high drive does not guarantee an action.", 14))
		else:
			var text := BiomeUI.paragraph("", 15)
			detail.add_child(text)
			sections[title] = text
	hide()
	get_viewport().size_changed.connect(_resize)
	_resize()

func _resize() -> void:
	offset_left = -minf(396, get_viewport_rect().size.x * 0.43)
	offset_bottom = -278 if get_viewport_rect().size.x < 1150 else -240

func set_open(open: bool) -> void:
	visible = open

func set_creature(data: Dictionary) -> void:
	if data.is_empty():
		name_label.text = "No animal selected"
		action_label.text = "Click an animal in the habitat."
		summary.text = ""
		return
	name_label.text = "Animal #%d" % int(data.get("id", -1))
	action_label.text = str(data.get("behavior", "explore")).replace("_", " ").capitalize() + "\n" + str(data.get("behavior_reason", ""))
	summary.text = "Energy %s · Hunger %s\nInjury %s · Age %s ticks\nNearby dependent young: %d" % [
		BiomeUI.percent(data.get("energy_ratio", 0)),
		BiomeUI.percent(data.get("hunger", 0)),
		BiomeUI.percent(data.get("injury", 0)),
		str(int(data.get("age", 0))), data.get("dependent_ids", []).size()]
	var drives: Dictionary = data.get("drives", {})
	for key in drive_bars:
		var value := clampf(float(drives.get(key, 0)), 0, 1)
		drive_bars[key].value = value
		drive_labels[key].text = key.replace("_", " ").capitalize() + " · " + BiomeUI.percent(value)
	sections["Genome"].text = "Size %.2f · Speed %.2f\nPerception %.2f · Metabolism %.2f\nAggression %s · Resilience %s\nSociability %s" % [
		float(data.get("size", 0)), float(data.get("speed", 0)), float(data.get("perception", 0)),
		float(data.get("metabolism", 0)),
		BiomeUI.percent(data.get("aggression", 0)), BiomeUI.percent(data.get("resilience", 0)), BiomeUI.percent(data.get("sociability", 0))]
	sections["Encounters"].text = "Wins %s · Losses %s\n%s\nFood acquired %s · Satisfaction %s\nHealthy or hungry animals may avoid a contest even after a win." % [
		str(int(data.get("fights_won", 0))), str(int(data.get("fights_lost", 0))), "Established alpha" if data.get("alpha", false) else "No alpha status",
		str(data.get("food_acquired", 0)), BiomeUI.percent(data.get("satisfaction", 0))]
	var parents: Array = data.get("parents", [])
	sections["Lineage"].text = ("Founder" if parents.is_empty() else "Parents: " + _ids(parents)) + "\nOffspring: " + str(int(data.get("offspring", 0))) + "\nDependent IDs: " + _ids(data.get("dependent_ids", []))

func _ids(values: Array) -> String:
	var labels: PackedStringArray = []
	for id in values: labels.append("#%d" % int(id))
	return ", ".join(labels) if not labels.is_empty() else "None"
