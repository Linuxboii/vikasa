extends Node

const VIEW = preload("res://scripts/CreatureView.gd")

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var root := Node3D.new()
	add_child(root)
	var floor := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(18.0, 8.0)
	floor.mesh = plane
	var earth := StandardMaterial3D.new()
	earth.albedo_color = Color("#53624c")
	earth.roughness = 1.0
	floor.material_override = earth
	root.add_child(floor)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-42, -25, 0)
	sun.light_energy = 1.5
	root.add_child(sun)
	var camera := Camera3D.new()
	camera.position = Vector3(0, 5.4, 12.5)
	camera.current = true
	root.add_child(camera)
	camera.look_at(Vector3(0, 0.7, 0))
	var specimens := [
		{"id": 1, "size": 2.5, "aggression": 0.05, "energy_ratio": 0.82, "behavior": "forage", "position": [20.0, 24.0], "velocity": [0.5, 0.1]},
		{"id": 2, "size": 4.0, "aggression": 0.45, "energy_ratio": 0.48, "behavior": "rest", "position": [30.0, 24.0], "velocity": [0.0, 0.0], "alpha": true},
		{"id": 3, "size": 6.5, "aggression": 0.92, "energy_ratio": 0.19, "behavior": "challenge", "position": [40.0, 24.0], "velocity": [1.2, 0.1], "injury": 0.31, "perception": 3.7, "resilience": 0.9, "sociability": 0.1}
	]
	var gallery: Array[CreatureView] = []
	for specimen in specimens:
		var view: CreatureView = VIEW.new()
		root.add_child(view)
		gallery.append(view)
		view.configure(specimen, 0.1, 120, 80)
		view.position = Vector3((specimens.find(specimen) - 1) * 4.2, 0, 0)
		assert(view.legs.size() == 4, "four articulated legs required")
		var feet := view.find_children("Foot", "MeshInstance3D", true, false)
		assert(feet.size() == 4, "four visible feet required")
		for foot in feet:
			assert(foot.global_position.y < view.body.global_position.y, "feet below body center")
			assert(foot.global_position.y - 0.11 >= 0.0, "foot geometry remains above the habitat floor")
		view.update_state({"position": [41.0, 24.0], "velocity": [1.4, 0.0], "behavior": "flee", "injury": 0.4}, 0.2)
		view.update_state({"position": [42.0, 24.0], "velocity": [0.2, 0.0], "behavior": "rest"}, 0.2)
		view.set_selected(true)
		assert(view.selected_ring.visible, "selection state must show ground ring")
		assert(view.find_child("InjuryMark", true, false) != null)
		assert(view.find_child("AlphaMark", true, false) != null)
	for index in gallery.size():
		gallery[index].position = Vector3((index - 1) * 4.2, 0, 0)
	# Let a live viewport render the gallery for visual inspection/movie capture.
	await get_tree().create_timer(1.0).timeout
	print("CreatureView harness passed: three phenotypes, four legs/feet, missing optional keys, action transitions and selection.")
	get_tree().quit(0)
