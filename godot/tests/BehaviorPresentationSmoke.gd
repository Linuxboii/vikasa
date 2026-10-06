extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var inspector = load("res://scenes/CreatureInspector.tscn").instantiate()
	root.add_child(inspector)
	await process_frame
	var drives := {}
	var index := 0
	for key in BehaviorPresentation.DRIVES:
		drives[key] = 0.1 * (index + 1)
		index += 1
	inspector.set_creature({"id": 1, "drives": drives, "behavior_scores": {"forage": 0.8, "rest": 0.5, "patrol": 0.2}})
	for key in drives:
		assert(is_equal_approx(inspector.drive_bars[key].value, drives[key]), "Drive value mapping: " + key)
		assert(inspector.drive_labels[key].text.begins_with(BehaviorPresentation.DRIVES[key].label), "Drive label mapping: " + key)
		assert(inspector.drive_bars[key].get_theme_stylebox("fill").bg_color == BehaviorPresentation.DRIVES[key].color, "Drive color mapping: " + key)
	assert(inspector.scores_label.text.contains("Seeking food · 0.80") and not inspector.scores_label.text.contains("Patrolling"))
	inspector.set_creature({"id": 1, "drives": {"survival": null, "foraging": "missing"}})
	for key in BehaviorPresentation.DRIVES: assert(inspector.drive_labels[key].text.contains("Unknown"))
	assert(inspector.action_label.text.contains("Exploring nearby"))
	inspector.set_creature({"id": 1, "drives": null, "behavior_scores": null})
	assert(inspector.drive_labels.survival.text.contains("Unknown"))
	assert(BehaviorPresentation.ratio({"energy": NAN}, "energy") == null)
	assert(BehaviorPresentation.dominant({"mating": 0.9, "survival": 0.2}) == "mating")
	print("BEHAVIOR PRESENTATION PASS: six labels/values/colors, unknown optional data, top-two real scores and reason fallback")
	inspector.queue_free()
	await process_frame
	quit()
