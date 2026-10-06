extends PanelContainer

signal closed
var name_label: Label
var action_label: Label
var summary: Label
var sections: Dictionary = {}
var drive_bars: Dictionary = {}
var drive_labels: Dictionary = {}
var drive_descriptions: Dictionary = {}
var scores_label: Label

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
	for title in ["Instincts", "Action choices", "Genome", "Encounters", "Lineage"]:
		var toggle := BiomeUI.button(title + "  +", "Show " + title.to_lower() + " details")
		toggle.toggle_mode = true
		content.add_child(toggle)
		var detail := VBoxContainer.new()
		detail.add_theme_constant_override("separation", 8)
		detail.hide()
		content.add_child(detail)
		toggle.toggled.connect(func(open: bool): detail.visible = open; toggle.text = title + ("  −" if open else "  +"))
		if title == "Instincts":
			detail.add_child(BiomeUI.paragraph("0–44% low · 45–74% rising · 75–100% urgent. Pressures compete; a high need does not guarantee an action.", 14))
			for key in BehaviorPresentation.DRIVES:
				var caption := BiomeUI.label(BehaviorPresentation.DRIVES[key].label, 15, BiomeUI.INK)
				detail.add_child(caption)
				drive_labels[key] = caption
				var bar := BiomeUI.meter(BehaviorPresentation.DRIVES[key].color)
				detail.add_child(bar)
				drive_bars[key] = bar
				var description := BiomeUI.paragraph(BehaviorPresentation.DRIVES[key].description, 13)
				detail.add_child(description)
				drive_descriptions[key] = description
		elif title == "Action choices":
			scores_label = BiomeUI.paragraph("No action scores available.", 15)
			detail.add_child(scores_label)
		else:
			var text := BiomeUI.paragraph("", 15)
			detail.add_child(text)
			sections[title] = text
	hide()
	get_viewport().size_changed.connect(_resize)
	_resize()

func _resize() -> void:
	var narrow := get_viewport_rect().size.x < 1150
	offset_left = -minf(390, get_viewport_rect().size.x - 32)
	offset_right = -16
	offset_top = 82
	offset_bottom = -256 if narrow else -212

func set_open(open: bool) -> void:
	visible = open

func _process(_delta: float) -> void:
	var dock := get_parent().get_node_or_null("HUD/ObservationDock") as Control
	if dock: offset_bottom = dock.offset_top - 12

func set_creature(data: Dictionary) -> void:
	if data.is_empty():
		name_label.text = "No animal selected"
		action_label.text = "Click an animal in the habitat."
		summary.text = ""
		return
	name_label.text = "Animal #%d" % int(data.get("id", -1))
	action_label.text = BehaviorPresentation.action(data) + "\n" + BehaviorPresentation.reason(data)
	summary.text = "Energy %s · Hunger %s\nInjury %s · Age %s ticks\nNearby dependent young: %d" % [
		BehaviorPresentation.percent(BehaviorPresentation.ratio(data, "energy_ratio")),
		BehaviorPresentation.percent(BehaviorPresentation.ratio(data, "hunger")),
		BehaviorPresentation.percent(BehaviorPresentation.ratio(data, "injury")),
		str(int(data.get("age", 0))), data.get("dependent_ids", []).size()]
	var raw_drives: Variant = data.get("drives", {})
	var drives: Dictionary = raw_drives if raw_drives is Dictionary else {}
	for key in drive_bars:
		var value: Variant = BehaviorPresentation.ratio(drives, key)
		BehaviorPresentation.meter(drive_bars[key], value, BehaviorPresentation.DRIVES[key].color)
		drive_labels[key].text = str(BehaviorPresentation.DRIVES[key].label) + " · " + BehaviorPresentation.percent(value) + " · " + BehaviorPresentation.urgency(value)
		drive_labels[key].add_theme_color_override("font_color", BehaviorPresentation.DRIVES[key].color if value != null and float(value) >= 0.75 else BiomeUI.INK)
	var raw_scores: Variant = data.get("behavior_scores", {})
	_update_scores(raw_scores if raw_scores is Dictionary else {})
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

func _update_scores(scores: Dictionary) -> void:
	var candidates: Array = []
	for key in scores:
		var value: Variant = scores[key]
		if (value is int or value is float) and is_finite(float(value)):
			candidates.append({"name": str(key), "value": float(value)})
	candidates.sort_custom(func(a: Dictionary, b: Dictionary): return a.value > b.value if a.value != b.value else a.name < b.name)
	var lines: PackedStringArray = []
	for candidate in candidates.slice(0, 2):
		lines.append("%s · %.2f" % [BehaviorPresentation.ACTIONS.get(candidate.name, candidate.name.capitalize()), candidate.value])
	scores_label.text = ("No action scores available." if lines.is_empty() else "Top perceived choices\n" + "\n".join(lines)) + "\nScores compare reward, effort and risk. An urgent need or a persistent action can override the highest score."
