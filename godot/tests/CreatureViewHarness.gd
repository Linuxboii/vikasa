extends Node

const VIEW = preload("res://scripts/CreatureView.gd")

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	var root := Node3D.new()
	add_child(root)
	var floor := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(22.0, 12.0)
	floor.mesh = plane
	var earth := StandardMaterial3D.new()
	earth.albedo_color = Color("#5d5a41")
	earth.roughness = 1.0
	floor.material_override = earth
	root.add_child(floor)
	var environment := WorldEnvironment.new()
	var lighting := Environment.new()
	lighting.background_mode = Environment.BG_COLOR
	lighting.background_color = Color("#aab394")
	lighting.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	lighting.ambient_light_color = Color("#e8dabc")
	lighting.ambient_light_energy = 0.58
	lighting.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.environment = lighting
	root.add_child(environment)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-38, -28, 0)
	sun.light_color = Color("#ffe5b8")
	sun.light_energy = 1.05
	root.add_child(sun)
	var fill := OmniLight3D.new()
	fill.position = Vector3(-3, 3.5, 3)
	fill.light_color = Color("#b8d7a1")
	fill.light_energy = 0.55
	fill.omni_range = 18.0
	root.add_child(fill)
	var camera := Camera3D.new()
	var close_up := "--close-up" in OS.get_cmdline_user_args()
	camera.position = Vector3(0, 2.2, 4.8) if close_up else Vector3(0, 3.6, 8.8)
	camera.current = true
	root.add_child(camera)
	camera.look_at(Vector3(0, 0.58, 0))
	# A few soft forms at the rear edge ground the gallery without distracting from anatomy.
	for shrub_position in [Vector3(-8.0, 0.35, -2.8), Vector3(8.0, 0.42, -3.2), Vector3(6.2, 0.25, 2.8)]:
		for offset in [Vector3(-0.25, 0, 0), Vector3(0.15, 0.12, 0.18), Vector3(0.35, 0, -0.12)]:
			var shrub := MeshInstance3D.new()
			var bush_mesh := SphereMesh.new()
			bush_mesh.radial_segments = 10
			bush_mesh.rings = 6
			shrub.mesh = bush_mesh
			shrub.position = shrub_position + offset
			shrub.scale = Vector3(0.45, 0.38, 0.50)
			var leaf := StandardMaterial3D.new()
			leaf.albedo_color = Color("#4e6945")
			leaf.roughness = 1.0
			shrub.material_override = leaf
			root.add_child(shrub)
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
		assert(view.body.scale.x > view.body.scale.y * 2.0, "spine/body silhouette must be elongated and low")
		var feet := view.find_children("Foot", "MeshInstance3D", true, false)
		assert(feet.size() == 4, "four visible feet required")
		var claw_count := 0
		for leg in view.legs:
			for child in leg.get_children():
				if child is MeshInstance3D and child.mesh is CylinderMesh:
					claw_count += 1
		assert(claw_count == 12, "each foot needs three claws: found %d" % claw_count)
		assert(view.find_child("Jaw", true, false) != null and view.find_child("Nose", true, false) != null, "muzzle anatomy requires jaw and nose")
		for foot in feet:
			assert(foot.global_position.y < view.body.global_position.y, "feet below body center")
			assert(foot.global_position.y - 0.11 >= 0.0, "foot geometry remains above the habitat floor")
		if int(specimen.id) == 2:
			assert(view.alpha_mark.visible, "alpha should use a distinct visual mark")
		var standing_head_y := view.head.position.y
		view.update_state({"position": [41.0, 24.0], "velocity": [1.4, 0.0], "behavior": "flee", "injury": 0.4}, 0.2)
		assert(view.injury_mark.visible, "injury state should add a visible mark")
		assert(view.head.position.y != standing_head_y, "action transition should alter animal posture")
		view.update_state({"position": [42.0, 24.0], "velocity": [0.2, 0.0], "behavior": "rest"}, 0.2)
		view.set_selected(true)
		assert(view.selected_ring.visible, "selection state must show ground ring")
		assert(view.find_child("InjuryMark", true, false) != null)
		assert(view.find_child("AlphaMark", true, false) != null)
	for index in gallery.size():
		gallery[index].position = Vector3((index - 1) * 4.2, 0, 0)
	if close_up:
		gallery[0].visible = false
		gallery[2].visible = false
		camera.position = Vector3(0.9, 2.0, 4.0)
		camera.look_at(Vector3(0, 0.68, 0))
	# Let a live viewport render the gallery for visual inspection/movie capture.
	await get_tree().create_timer(1.0).timeout
	print("CreatureView harness passed: three phenotypes, four legs/feet, missing optional keys, action transitions and selection.")
	get_tree().quit(0)
