extends Node3D
class_name Habitat

func build(world_width: float, world_height: float, scale_factor: float, seed_value: int) -> void:
	var width := world_width * scale_factor
	var depth := world_height * scale_factor
	_build_ground(width, depth, seed_value)
	_build_trees(width, depth, seed_value)
	_build_water(width, depth)
	_build_rocks(width, depth, seed_value)

func _build_ground(width: float, depth: float, seed_value: int) -> void:
	var noise := FastNoiseLite.new()
	noise.seed = seed_value
	noise.frequency = 0.046
	noise.fractal_octaves = 3
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var x_steps := 72
	var z_steps := 52
	for z in range(z_steps):
		for x in range(x_steps):
			var p00 := _terrain_point(x, z, x_steps, z_steps, width, depth, noise)
			var p10 := _terrain_point(x + 1, z, x_steps, z_steps, width, depth, noise)
			var p01 := _terrain_point(x, z + 1, x_steps, z_steps, width, depth, noise)
			var p11 := _terrain_point(x + 1, z + 1, x_steps, z_steps, width, depth, noise)
			_add_land_vertex(surface, p00)
			_add_land_vertex(surface, p01)
			_add_land_vertex(surface, p10)
			_add_land_vertex(surface, p10)
			_add_land_vertex(surface, p01)
			_add_land_vertex(surface, p11)
	surface.generate_normals()
	var mesh := surface.commit()
	var ground := MeshInstance3D.new()
	ground.name = "LivingTopography"
	ground.mesh = mesh
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.vertex_color_is_srgb = true
	material.roughness = 0.96
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	ground.material_override = material
	ground.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ground)
	var underlay := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(width, depth)
	underlay.mesh = plane
	var underlay_material := StandardMaterial3D.new()
	underlay_material.albedo_color = Color("#254737")
	underlay_material.roughness = 1.0
	underlay.material_override = underlay_material
	underlay.position.y = -0.26
	add_child(underlay)

func _terrain_point(x: int, z: int, x_steps: int, z_steps: int, width: float, depth: float, noise: FastNoiseLite) -> Vector3:
	var px := -width * 0.5 + width * float(x) / float(x_steps)
	var pz := -depth * 0.5 + depth * float(z) / float(z_steps)
	var edge: float = minf(1.0, minf((float(x) / float(x_steps)) * 8.0, minf((float(z) / float(z_steps)) * 8.0, minf((float(x_steps - x) / float(x_steps)) * 8.0, (float(z_steps - z) / float(z_steps)) * 8.0))))
	var height: float = (noise.get_noise_2d(px, pz) * 1.25 + noise.get_noise_2d(px * 2.2, pz * 2.2) * 0.34) * edge
	return Vector3(px, height, pz)

func _add_land_vertex(surface: SurfaceTool, point: Vector3) -> void:
	var color := Color("#688b50")
	if point.y > 0.6:
		color = Color("#77775a").lerp(Color("#95a16a"), clampf(point.y * 0.12, 0.0, 0.5))
	elif point.y < -0.7:
		color = Color("#376d52").lerp(Color("#4c8053"), clampf((point.y + 2.0) * 0.15, 0.0, 0.5))
	else:
		color = Color("#416b45").lerp(Color("#7c9b56"), clampf((point.y + 1.0) * 0.42, 0.0, 0.78))
	surface.set_color(color)
	surface.add_vertex(point)

func _build_trees(width: float, depth: float, seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 8191
	var trunk_mm := MultiMesh.new()
	trunk_mm.transform_format = MultiMesh.TRANSFORM_3D
	var trunk_mesh := CylinderMesh.new()
	trunk_mesh.top_radius = 0.08
	trunk_mesh.bottom_radius = 0.16
	trunk_mesh.height = 2.2
	trunk_mesh.radial_segments = 7
	trunk_mm.mesh = trunk_mesh
	var canopy_mm := MultiMesh.new()
	canopy_mm.transform_format = MultiMesh.TRANSFORM_3D
	var canopy_mesh := SphereMesh.new()
	canopy_mesh.radial_segments = 8
	canopy_mesh.rings = 6
	canopy_mm.mesh = canopy_mesh
	var tree_count := 92
	trunk_mm.instance_count = tree_count
	canopy_mm.instance_count = tree_count
	for i in range(tree_count):
		var x := rng.randf_range(-width * 0.48, width * 0.48)
		var z := rng.randf_range(-depth * 0.48, depth * 0.48)
		var scale := rng.randf_range(0.7, 1.6)
		var height := 2.15 * scale
		var transform := Transform3D(Basis().scaled(Vector3.ONE * scale), Vector3(x, height * 0.5, z))
		trunk_mm.set_instance_transform(i, transform)
		var canopy_basis := Basis().scaled(Vector3(0.8, 1.0, 0.8) * scale)
		canopy_mm.set_instance_transform(i, Transform3D(canopy_basis, Vector3(x, height + 0.45 * scale, z)))
	var trunks := MultiMeshInstance3D.new()
	trunks.name = "CanopyTrunks"
	trunks.multimesh = trunk_mm
	trunks.material_override = _mat(Color("#6d5236"), 0.92)
	add_child(trunks)
	var canopies := MultiMeshInstance3D.new()
	canopies.name = "CanopyCrowns"
	canopies.multimesh = canopy_mm
	canopies.material_override = _mat(Color("#72a257"), 0.82)
	add_child(canopies)

func _build_water(width: float, depth: float) -> void:
	var placements := [Vector3(-width * 0.22, -0.62, -depth * 0.1), Vector3(width * 0.27, -0.68, depth * 0.2), Vector3(-width * 0.02, -0.6, depth * 0.34)]
	var sizes := [Vector3(5.5, 0.16, 3.1), Vector3(4.2, 0.14, 2.3), Vector3(3.2, 0.12, 1.7)]
	for i in range(placements.size()):
		var pond := MeshInstance3D.new()
		var mesh := SphereMesh.new()
		mesh.radial_segments = 24
		mesh.rings = 12
		pond.mesh = mesh
		pond.scale = sizes[i]
		pond.position = placements[i]
		pond.material_override = _mat(Color("#3e9a91"), 0.18, Color("#72cbbb"), 0.12)
		pond.name = "SeasonalPool"
		add_child(pond)

func _build_rocks(width: float, depth: float, seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 31_337
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	var rock_mesh := SphereMesh.new()
	rock_mesh.radial_segments = 7
	rock_mesh.rings = 5
	multimesh.mesh = rock_mesh
	multimesh.instance_count = 48
	for i in range(multimesh.instance_count):
		var scale := Vector3(rng.randf_range(0.18, 0.54), rng.randf_range(0.14, 0.4), rng.randf_range(0.18, 0.48))
		var pos := Vector3(rng.randf_range(-width * 0.49, width * 0.49), -0.08, rng.randf_range(-depth * 0.49, depth * 0.49))
		multimesh.set_instance_transform(i, Transform3D(Basis().scaled(scale), pos))
	var rocks := MultiMeshInstance3D.new()
	rocks.name = "Fieldstones"
	rocks.multimesh = multimesh
	rocks.material_override = _mat(Color("#858a67"), 0.94)
	add_child(rocks)

func _mat(color: Color, roughness: float, emission: Color = Color.BLACK, power: float = 0.0) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	if power > 0.0:
		material.emission_enabled = true
		material.emission = emission
		material.emission_energy_multiplier = power
	return material
