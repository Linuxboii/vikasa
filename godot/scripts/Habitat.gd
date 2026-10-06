extends Node3D
class_name Habitat

func build(world_width: float, world_height: float, scale_factor: float, seed_value: int) -> void:
	var width := world_width * scale_factor
	var depth := world_height * scale_factor
	_build_ground(width, depth, seed_value)
	_build_trees(width, depth, seed_value)
	_build_water(width, depth)
	_build_rocks(width, depth, seed_value)
	_build_meadow(width, depth, seed_value)
	var plinth := MeshInstance3D.new()
	plinth.name = "BiomePlinth"
	var base := BoxMesh.new()
	base.size = Vector3(width + 1.2, 1.3, depth + 1.2)
	plinth.mesh = base
	plinth.position.y = -1.05
	plinth.material_override = _mat(Color("#1c3d38"), 0.95)
	add_child(plinth)

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
	# Always below the minimum terrain height; never clips through the field.
	underlay.position.y = -2.0
	add_child(underlay)

func _terrain_point(x: int, z: int, x_steps: int, z_steps: int, width: float, depth: float, noise: FastNoiseLite) -> Vector3:
	var px := -width * 0.5 + width * float(x) / float(x_steps)
	var pz := -depth * 0.5 + depth * float(z) / float(z_steps)
	var edge: float = minf(1.0, minf((float(x) / float(x_steps)) * 8.0, minf((float(z) / float(z_steps)) * 8.0, minf((float(x_steps - x) / float(x_steps)) * 8.0, (float(z_steps - z) / float(z_steps)) * 8.0))))
	var height: float = -0.16 + (noise.get_noise_2d(px, pz) * 0.14 + noise.get_noise_2d(px * 2.2, pz * 2.2) * 0.04) * edge
	# Recess scenic pools into the same terrain mesh so their surfaces stay visible.
	for pool in _pools(width, depth):
		var elliptical := Vector2((px - pool.x) / (width * 0.052), (pz - pool.y) / (depth * 0.06)).length()
		height -= 0.48 * (1.0 - smoothstep(0.72, 1.25, elliptical))
	return Vector3(px, height, pz)

func _add_land_vertex(surface: SurfaceTool, point: Vector3) -> void:
	var color := Color("#6c7d52")
	if point.y > 0.6:
		color = Color("#77775a").lerp(Color("#95a16a"), clampf(point.y * 0.12, 0.0, 0.5))
	elif point.y < -0.7:
		color = Color("#376d52").lerp(Color("#4c8053"), clampf((point.y + 2.0) * 0.15, 0.0, 0.5))
	else:
		var patch := 0.5 + sin(point.x * 0.14) * cos(point.z * 0.17) * 0.5
		var moisture := 0.5 + sin(point.x * 0.31 + cos(point.z * 0.13) * 2.0) * sin(point.z * 0.22) * 0.5
		color = Color("#476651").lerp(Color("#92a878"), patch * 0.5 + moisture * 0.25)
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
	canopy_mm.use_colors = true
	var canopy_mesh := SphereMesh.new()
	canopy_mesh.radial_segments = 8
	canopy_mesh.rings = 6
	canopy_mm.mesh = canopy_mesh
	var tree_count := 74
	trunk_mm.instance_count = tree_count
	canopy_mm.instance_count = tree_count
	for i in range(tree_count):
		# Keep the center readable; group cover into small groves along the edges.
		var centers := [Vector2(-width * 0.34, -depth * 0.32), Vector2(width * 0.33, -depth * 0.3), Vector2(-width * 0.35, depth * 0.25), Vector2(width * 0.38, depth * 0.3)]
		var center: Vector2 = centers[i % centers.size()]
		var x := clampf(center.x + rng.randfn(0, width * 0.07), -width * 0.47, width * 0.47)
		var z := clampf(center.y + rng.randfn(0, depth * 0.08), -depth * 0.47, depth * 0.47)
		var scale := rng.randf_range(1.2, 2.1)
		var height := 2.15 * scale
		var transform := Transform3D(Basis().scaled(Vector3.ONE * scale), Vector3(x, height * 0.5, z))
		trunk_mm.set_instance_transform(i, transform)
		var canopy_basis := Basis().scaled(Vector3(2.3, 1.7, 2.0) * scale)
		canopy_mm.set_instance_transform(i, Transform3D(canopy_basis, Vector3(x, height + 0.3 * scale, z)))
		canopy_mm.set_instance_color(i, Color("#476d59").lerp(Color("#a0b877"), rng.randf()))
	var trunks := MultiMeshInstance3D.new()
	trunks.name = "CanopyTrunks"
	trunks.multimesh = trunk_mm
	trunks.material_override = _mat(Color("#6d5236"), 0.92)
	add_child(trunks)
	var canopies := MultiMeshInstance3D.new()
	canopies.name = "CanopyCrowns"
	canopies.multimesh = canopy_mm
	var leaves := _mat(Color.WHITE, 0.92)
	leaves.vertex_color_use_as_albedo = true
	canopies.material_override = leaves
	add_child(canopies)

func _build_water(width: float, depth: float) -> void:
	var placements := _pools(width, depth)
	for i in range(placements.size()):
		var pond := MeshInstance3D.new()
		var mesh := SphereMesh.new()
		mesh.radial_segments = 24
		mesh.rings = 12
		pond.mesh = mesh
		pond.scale = Vector3(width * 0.095, 0.045, depth * 0.11)
		pond.position = Vector3(placements[i].x, -0.23, placements[i].y)
		pond.material_override = _mat(Color("#63a0a7"), 0.22)
		pond.name = "SeasonalPool"
		add_child(pond)

func _pools(width: float, depth: float) -> Array[Vector2]:
	return [Vector2(-width * 0.22, -depth * 0.1), Vector2(width * 0.23, depth * 0.2)]

func _build_meadow(width: float, depth: float, seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 934
	var meadow := MultiMesh.new()
	meadow.transform_format = MultiMesh.TRANSFORM_3D
	meadow.use_colors = true
	var tuft := CylinderMesh.new()
	tuft.top_radius = 0.0
	tuft.bottom_radius = 0.16
	tuft.height = 0.48
	tuft.radial_segments = 3
	meadow.mesh = tuft
	meadow.instance_count = 480
	for i in range(meadow.instance_count):
		var x := rng.randf_range(-width * 0.48, width * 0.48)
		var z := rng.randf_range(-depth * 0.48, depth * 0.48)
		var size := rng.randf_range(0.6, 1.3)
		meadow.set_instance_transform(i, Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * size), Vector3(x, 0.1, z)))
		meadow.set_instance_color(i, Color("#83a168").lerp(Color("#cfbd82"), rng.randf() * 0.65))
	var field := MultiMeshInstance3D.new()
	field.multimesh = meadow
	var material := _mat(Color.WHITE, 1)
	material.vertex_color_use_as_albedo = true
	field.material_override = material
	field.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(field)

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
