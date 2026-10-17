extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var script = load("res://scripts/LocusChart.gd")
	if script == null:
		push_error("Missing live chromosome chart")
		quit(1)
		return
	var chart = script.new()
	root.add_child(chart)
	chart.size = Vector2(300, 150)
	chart.set_population({"individuals": 2, "allele_frequency": [0.25, 0.75],
		"observed_heterozygosity": [0.5, 0.25]})
	var motion := InputEventMouseMotion.new()
	motion.position = Vector2(90, 70)
	chart._gui_input(motion)
	assert(chart.tooltip_text.contains("Locus 1") and chart.tooltip_text.contains("25.0%"))
	var key := InputEventKey.new()
	key.keycode = KEY_RIGHT
	key.pressed = true
	chart._gui_input(key)
	assert(chart.tooltip_text.contains("Locus 2") and chart.tooltip_text.contains("75.0%"))
	chart.set_population({"individuals": 0, "allele_frequency": null})
	assert(chart.hover_index == -1 and chart.tooltip_text.is_empty())
	chart.queue_free()
	await process_frame
	print("LOCUS CHART SMOKE PASS: hover, keyboard, extinct state")
	quit(0)
