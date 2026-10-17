extends Node3D
class_name Habitat
## Procedural floating biome. Everything that repeats is a MultiMesh with a
## shader doing the animation, so a dense living meadow costs a handful of
## draw calls. Placement is seeded and therefore identical for a given seed.

const GRASS_CAPACITY := 26000
const FLOWER_CAPACITY := 1400

var width := 72.0
var depth := 48.0
var terrain_material: ShaderMaterial
var grass_material: ShaderMaterial
var flower_material: ShaderMaterial
var broadleaf_material: ShaderMaterial
var conifer_material: ShaderMaterial
var water_material: ShaderMaterial
var grass: MultiMeshInstance3D
var flowers: MultiMeshInstance3D
var pools: Array[MeshInstance3D] = []
var _pool_scales: Array[Vector3] = []
var _biomass_texture: ImageTexture
var _materials: Array[ShaderMaterial] = []

func build(world_width: float, world_height: float, scale_factor: float, seed_value: int) -> void:
	width = world_width * scale_factor
	depth = world_height * scale_factor
	terrain_material = _shader_material("terrain")
	terrain_material.set_shader_parameter("world_size", Vector2(width, depth))
	grass_material = _shader_material("grass")
	flower_material = _shader_material("grass")
	flower_material.set_shader_parameter("flowers", true)
	broadleaf_material = _shader_material("foliage")
	conifer_material = _shader_material("foliage")
	conifer_material.set_shader_parameter("evergreen", true)
	water_material = _shader_material("water")
	_build_ground(seed_value)
	_build_cliffs(seed_value)
	_build_water()
	_build_trees(seed_value)
	_build_rocks(seed_value)
	_build_meadow(seed_value)

func _shader_material(shader_name: String) -> ShaderMaterial:
	var material := ShaderMaterial.new()
	material.shader = load("res://shaders/%s.gdshader" % shader_name)
	_materials.append(material)
	return material

## Push one shared atmosphere snapshot into every habitat shader.
func set_conditions(conditions: Dictionary) -> void:
	for material in _materials:
		material.set_shader_parameter("clock", conditions.clock)
		material.set_shader_parameter("wind", conditions.wind)
		material.set_shader_parameter("snow", conditions.snow)
		material.set_shader_parameter("night", conditions.night)
	terrain_material.set_shader_parameter("ground_tint", conditions.ground_tint)
	terrain_material.set_shader_parameter("wet", conditions.wet)
	terrain_material.set_shader_parameter("scorch", conditions.scorch)
	grass_material.set_shader_parameter("tip_tint", conditions.grass_tip)
	grass_material.set_shader_parameter("root_tint", conditions.grass_root)
	grass_material.set_shader_parameter("height_scale", conditions.grass_height)
	flower_material.set_shader_parameter("bloom", conditions.bloom)
	broadleaf_material.set_shader_parameter("season_tint", conditions.canopy_tint)
	broadleaf_material.set_shader_parameter("autumn", conditions.autumn)
	conifer_material.set_shader_parameter("season_tint", Color(0.92, 1.0, 0.95))
	water_material.set_shader_parameter("rain", conditions.rain)
	water_material.set_shader_parameter("sun_direction", conditions.sun_direction)
	water_material.set_shader_parameter("sky_color", conditions.sky_color)
	water_material.set_shader_parameter("frozen", conditions.frozen)
	for i in pools.size():
		pools[i].scale = pools[i].scale.lerp(_pool_scales[i] * conditions.water_level, 0.04)

func set_grass_density(fraction: float) -> void:
	if grass: grass.multimesh.visible_instance_count = int(GRASS_CAPACITY * clampf(fraction, 0.05, 1.0))
	if flowers: flowers.multimesh.visible_instance_count = int(FLOWER_CAPACITY * clampf(fraction, 0.1, 1.0))

## Spatial-ecology runs expose a biomass grid; paint it into the soil colour.
func set_biomass(habitat: Variant) -> void:
	if not habitat is Dictionary or not habitat.get("biomass") is Array:
		terrain_material.set_shader_parameter("biomass_weight", 0.0)
		return
	var rows: Array = habitat.biomass
	if rows.is_empty() or not rows[0] is Array: return
	var capacity := maxf(0.001, float(habitat.get("capacity", 1.0)))
	var image := Image.create(rows[0].size(), rows.size(), false, Image.FORMAT_L8)
	for y in rows.size():
		for x in rows[y].size():
			var v := clampf(float(rows[y][x]) / capacity, 0.0, 1.0)
			image.set_pixel(x, y, Color(v, v, v))
	if _biomass_texture == null or _biomass_texture.get_size() != Vector2(image.get_size()):
		_biomass_texture = ImageTexture.create_from_image(image)
	else:
		_biomass_texture.update(image)
	terrain_material.set_shader_parameter("biomass_map", _biomass_texture)
	terrain_material.set_shader_parameter("biomass_weight", 1.0)

func _pools() -> Array[Vector2]:
	return [Vector2(-width * 0.22, -depth * 0.1), Vector2(width * 0.23, depth * 0.2)]

func in_pool(x: float, z: float, margin: float = 1.0) -> bool:
	for pool in _pools():
		if Vector2((x - pool.x) / (width * 0.058 * margin), (z - pool.y) / (depth * 0.068 * margin)).length() < 1.0:
			return true
	return false

func _build_ground(seed_value: int) -> void:
	var noise := FastNoiseLite.new()
	noise.seed = seed_value
	noise.frequency = 0.046
	noise.fractal_octaves = 3
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	var x_steps := 96
	var z_steps := 64
	for z in range(z_steps):
		for x in range(x_steps):
			var p00 := _terrain_point(x, z, x_steps, z_steps, noise)
			var p10 := _terrain_point(x + 1, z, x_steps, z_steps, noise)
			var p01 := _terrain_point(x, z + 1, x_steps, z_steps, noise)
			var p11 := _terrain_point(x + 1, z + 1, x_steps, z_steps, noise)
			for p in [p00, p01, p10, p10, p01, p11]:
				surface.set_color(_land_color(p))
				surface.add_vertex(p)
	surface.index()
	surface.generate_normals()
	var ground := MeshInstance3D.new()
	ground.name = "LivingTopography"
	ground.mesh = surface.commit()
	ground.material_override = terrain_material
	ground.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ground)

func _terrain_point(x: int, z: int, x_steps: int, z_steps: int, noise: FastNoiseLite) -> Vector3:
	var px := -width * 0.5 + width * float(x) / float(x_steps)
	var pz := -depth * 0.5 + depth * float(z) / float(z_steps)
	var edge: float = minf(1.0, minf((float(x) / float(x_steps)) * 8.0, minf((float(z) / float(z_steps)) * 8.0, minf((float(x_steps - x) / float(x_steps)) * 8.0, (float(z_steps - z) / float(z_steps)) * 8.0))))
	var height: float = -0.16 + (noise.get_noise_2d(px, pz) * 0.14 + noise.get_noise_2d(px * 2.2, pz * 2.2) * 0.04) * edge
	for pool in _pools():
		var elliptical := Vector2((px - pool.x) / (width * 0.052), (pz - pool.y) / (depth * 0.06)).length()
		height -= 0.48 * (1.0 - smoothstep(0.72, 1.25, elliptical))
	return Vector3(px, height, pz)

func _land_color(point: Vector3) -> Color:
	if point.y < -0.4:
		return Color("#3f6f55").lerp(Color("#6d7a52"), clampf((point.y + 0.64) * 3.0, 0.0, 1.0))
	var patch := 0.5 + sin(point.x * 0.14) * cos(point.z * 0.17) * 0.5
	var moisture := 0.5 + sin(point.x * 0.31 + cos(point.z * 0.13) * 2.0) * sin(point.z * 0.22) * 0.5
	return Color("#4d6e4a").lerp(Color("#9aae74"), patch * 0.5 + moisture * 0.25)

func _build_cliffs(seed_value: int) -> void:
	var cliff_material := ShaderMaterial.new()
	cliff_material.shader = load("res://shaders/cliff.gdshader")
	# Open-topped walls: a closed box lid would hide pools and terrain dips.
	var slab := MeshInstance3D.new()
	slab.name = "BiomeCliffs"
	var walls := SurfaceTool.new()
	walls.begin(Mesh.PRIMITIVE_TRIANGLES)
	var hx := width * 0.5 + 0.05
	var hz := depth * 0.5 + 0.05
	var top := -0.15
	var bottom := -3.2
	var corners := [Vector2(-hx, -hz), Vector2(hx, -hz), Vector2(hx, hz), Vector2(-hx, hz)]
	for i in 4:
		var a: Vector2 = corners[i]
		var b: Vector2 = corners[(i + 1) % 4]
		var outward := Vector3(b.y - a.y, 0, a.x - b.x).normalized() * -1.0
		for p in [Vector3(a.x, top, a.y), Vector3(b.x, top, b.y), Vector3(b.x, bottom, b.y), Vector3(a.x, top, a.y), Vector3(b.x, bottom, b.y), Vector3(a.x, bottom, a.y)]:
			walls.set_normal(outward)
			walls.add_vertex(p)
	for p in [Vector3(-hx, bottom, -hz), Vector3(hx, bottom, hz), Vector3(hx, bottom, -hz), Vector3(-hx, bottom, -hz), Vector3(-hx, bottom, hz), Vector3(hx, bottom, hz)]:
		walls.set_normal(Vector3.DOWN)
		walls.add_vertex(p)
	slab.mesh = walls.commit()
	slab.material_override = cliff_material
	slab.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(slab)
	# The rocky root under the floating plate: a jittered, tapering cone.
	var root := CylinderMesh.new()
	root.top_radius = 1.0
	root.bottom_radius = 0.08
	root.height = 1.0
	root.radial_segments = 28
	root.rings = 7
	var arrays := root.get_mesh_arrays()
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var noise := FastNoiseLite.new()
	noise.seed = seed_value + 77
	noise.frequency = 2.2
	for i in points.size():
		var p := points[i]
		var jitter := 1.0 + noise.get_noise_3d(p.x, p.y, p.z) * 0.35
		points[i] = Vector3(p.x * jitter, p.y, p.z * jitter)
	arrays[Mesh.ARRAY_VERTEX] = points
	var tool := SurfaceTool.new()
	tool.create_from_arrays(arrays)
	tool.generate_normals()
	var underside := MeshInstance3D.new()
	underside.name = "FloatingRoot"
	underside.mesh = tool.commit()
	underside.scale = Vector3(width * 0.62, 26.0, depth * 0.66)
	underside.position.y = -3.2 - 13.0
	underside.material_override = cliff_material
	underside.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(underside)

func _build_water() -> void:
	for pool in _pools():
		var pond := MeshInstance3D.new()
		var quad := QuadMesh.new()
		quad.orientation = PlaneMesh.FACE_Y
		quad.size = Vector2(1, 1)
		quad.subdivide_width = 0
		pond.mesh = quad
		var base := Vector3(width * 0.118, 1.0, depth * 0.135)
		pond.scale = base
		pond.position = Vector3(pool.x, -0.26, pool.y)
		pond.material_override = water_material
		pond.name = "SeasonalPool"
		pond.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(pond)
		pools.append(pond)
		_pool_scales.append(base)

func _build_trees(seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 8191
	var trunk := CylinderMesh.new()
	trunk.top_radius = 0.07
	trunk.bottom_radius = 0.17
	trunk.height = 2.2
	trunk.radial_segments = 6
	trunk.rings = 1
	var broadleaf := MeshMerge.merge([
		[MeshMerge.sphere(1.0, 10, 6), Transform3D(Basis.from_scale(Vector3(1.0, 0.82, 1.0)), Vector3(0, 0, 0))],
		[MeshMerge.sphere(0.72, 9, 5), Transform3D(Basis(), Vector3(0.62, -0.18, 0.2))],
		[MeshMerge.sphere(0.66, 9, 5), Transform3D(Basis(), Vector3(-0.55, -0.1, -0.35))],
		[MeshMerge.sphere(0.58, 8, 5), Transform3D(Basis(), Vector3(0.05, 0.42, -0.1))],
	])
	var conifer := MeshMerge.merge([
		[MeshMerge.cone(0.95, 1.4, 9), Transform3D(Basis(), Vector3(0, 0, 0))],
		[MeshMerge.cone(0.75, 1.2, 9), Transform3D(Basis(), Vector3(0, 0.75, 0))],
		[MeshMerge.cone(0.5, 1.0, 8), Transform3D(Basis(), Vector3(0, 1.4, 0))],
	])
	var count := 86
	var trunks := _multimesh(trunk, count, false)
	var crowns_broad := _multimesh(broadleaf, count, true)
	var crowns_pine := _multimesh(conifer, count, true)
	var broad_count := 0
	var pine_count := 0
	var centers := [Vector2(-width * 0.34, -depth * 0.32), Vector2(width * 0.33, -depth * 0.3), Vector2(-width * 0.35, depth * 0.25), Vector2(width * 0.38, depth * 0.3), Vector2(0.0, -depth * 0.42)]
	for i in range(count):
		var center: Vector2 = centers[i % centers.size()]
		var x := clampf(center.x + rng.randfn(0, width * 0.07), -width * 0.47, width * 0.47)
		var z := clampf(center.y + rng.randfn(0, depth * 0.08), -depth * 0.47, depth * 0.47)
		if in_pool(x, z, 1.3): continue
		var s := rng.randf_range(1.0, 1.9)
		var trunk_height := 2.15 * s
		var spin := Basis(Vector3.UP, rng.randf() * TAU)
		trunks.multimesh.set_instance_transform(broad_count + pine_count, Transform3D(Basis.from_scale(Vector3.ONE * s), Vector3(x, trunk_height * 0.5 - 0.2, z)))
		var pine := rng.randf() < 0.32
		if pine:
			crowns_pine.multimesh.set_instance_transform(pine_count, Transform3D(spin.scaled(Vector3(1.1, 1.5, 1.1) * s), Vector3(x, trunk_height * 0.55, z)))
			crowns_pine.multimesh.set_instance_color(pine_count, Color("#2f5a46").lerp(Color("#4f7a52"), rng.randf()))
			pine_count += 1
		else:
			crowns_broad.multimesh.set_instance_transform(broad_count, Transform3D(spin.scaled(Vector3(1.6, 1.35, 1.5) * s), Vector3(x, trunk_height + 0.15 * s, z)))
			crowns_broad.multimesh.set_instance_color(broad_count, Color("#4a7a4f").lerp(Color("#a6bd73"), rng.randf()))
			broad_count += 1
	# Trunks were written densely from index zero; hide the unused tail.
	trunks.multimesh.visible_instance_count = broad_count + pine_count
	crowns_broad.multimesh.visible_instance_count = broad_count
	crowns_pine.multimesh.visible_instance_count = pine_count
	trunks.material_override = _plain(Color("#5e4632"))
	crowns_broad.material_override = broadleaf_material
	crowns_pine.material_override = conifer_material
	for node in [trunks, crowns_broad, crowns_pine]:
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		add_child(node)

func _multimesh(mesh: Mesh, count: int, colors: bool) -> MultiMeshInstance3D:
	var multimesh := MultiMesh.new()
	multimesh.transform_format = MultiMesh.TRANSFORM_3D
	multimesh.use_colors = colors
	multimesh.instance_count = count
	multimesh.mesh = mesh
	var node := MultiMeshInstance3D.new()
	node.multimesh = multimesh
	node.custom_aabb = AABB(Vector3(-width, -4, -depth), Vector3(width * 2, 16, depth * 2))
	return node

func _plain(color: Color) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.95
	return material

func _blade_mesh() -> ArrayMesh:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	var heights := [0.0, 0.3, 0.62, 1.0]
	var widths := [0.032, 0.025, 0.015, 0.0]
	var points: Array[Vector3] = []
	var uvs: Array[Vector2] = []
	for i in heights.size():
		var h: float = heights[i] * 0.42
		var lean: float = heights[i] * heights[i] * 0.12
		points.append(Vector3(-widths[i], h, lean))
		uvs.append(Vector2(0, heights[i]))
		points.append(Vector3(widths[i], h, lean))
		uvs.append(Vector2(1, heights[i]))
	for i in range(heights.size() - 1):
		var a := i * 2
		for k in [a, a + 2, a + 1, a + 1, a + 2, a + 3]:
			tool.set_uv(uvs[k])
			tool.set_normal(Vector3.UP)
			tool.add_vertex(points[k])
	return tool.commit()

func _flower_mesh() -> ArrayMesh:
	var tool := SurfaceTool.new()
	tool.begin(Mesh.PRIMITIVE_TRIANGLES)
	var top := 0.42
	for k in [Vector3(-0.012, 0, 0), Vector3(0.012, 0, 0), Vector3(-0.008, top, 0), Vector3(0.012, 0, 0), Vector3(0.008, top, 0), Vector3(-0.008, top, 0)]:
		tool.set_uv(Vector2(0, k.y / top * 0.98))
		tool.set_normal(Vector3(0, 0, 1))
		tool.add_vertex(k)
	var petals := 6
	for i in range(petals):
		var a0 := TAU * i / petals
		var a1 := TAU * (i + 1) / petals
		for p in [Vector3(0, top + 0.02, 0), Vector3(cos(a0) * 0.085, top, sin(a0) * 0.085), Vector3(cos(a1) * 0.085, top, sin(a1) * 0.085)]:
			tool.set_uv(Vector2(1, 1))
			tool.set_normal(Vector3.UP)
			tool.add_vertex(p)
	return tool.commit()

func _build_meadow(seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 934
	grass = _multimesh(_blade_mesh(), GRASS_CAPACITY, true)
	grass.name = "WindMeadow"
	var placed := 0
	var attempts := 0
	while placed < GRASS_CAPACITY and attempts < GRASS_CAPACITY * 3:
		attempts += 1
		# Clumped distribution: most blades gather around seeded tussock centres.
		var x := rng.randf_range(-width * 0.49, width * 0.49)
		var z := rng.randf_range(-depth * 0.49, depth * 0.49)
		if in_pool(x, z, 0.9): continue
		var s := rng.randf_range(0.6, 1.25)
		var basis := Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3(s, s * rng.randf_range(0.7, 1.25), s))
		grass.multimesh.set_instance_transform(placed, Transform3D(basis, Vector3(x, -0.12, z)))
		var shade := rng.randf()
		grass.multimesh.set_instance_color(placed, Color(shade, shade, shade))
		placed += 1
	grass.material_override = grass_material
	grass.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(grass)
	flowers = _multimesh(_flower_mesh(), FLOWER_CAPACITY, true)
	flowers.name = "Wildflowers"
	var palette := [Color("#f4efe2"), Color("#f2cf4a"), Color("#b98ae8"), Color("#ee8fb3"), Color("#7fb6f0"), Color("#f08a5d")]
	var flower_index := 0
	while flower_index < FLOWER_CAPACITY:
		var cx := rng.randf_range(-width * 0.45, width * 0.45)
		var cz := rng.randf_range(-depth * 0.45, depth * 0.45)
		var hue: Color = palette[rng.randi() % palette.size()]
		for k in range(rng.randi_range(6, 16)):
			if flower_index >= FLOWER_CAPACITY: break
			var x := cx + rng.randfn(0.0, 1.1)
			var z := cz + rng.randfn(0.0, 1.1)
			if in_pool(x, z, 0.95) or absf(x) > width * 0.49 or absf(z) > depth * 0.49: continue
			var s := rng.randf_range(0.8, 1.3)
			flowers.multimesh.set_instance_transform(flower_index, Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(Vector3.ONE * s), Vector3(x, -0.12, z)))
			flowers.multimesh.set_instance_color(flower_index, hue.lerp(Color.WHITE, rng.randf() * 0.2))
			flower_index += 1
	flowers.material_override = flower_material
	flowers.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(flowers)

func _build_rocks(seed_value: int) -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value + 31_337
	var rock_mesh := MeshMerge.merge([
		[MeshMerge.sphere(1.0, 7, 5), Transform3D()],
		[MeshMerge.sphere(0.6, 6, 4), Transform3D(Basis(), Vector3(0.7, -0.15, 0.3))],
	])
	var rocks := _multimesh(rock_mesh, 54, true)
	rocks.name = "Fieldstones"
	for i in range(54):
		var size := Vector3(rng.randf_range(0.18, 0.62), rng.randf_range(0.14, 0.42), rng.randf_range(0.18, 0.52))
		var pos := Vector3(rng.randf_range(-width * 0.49, width * 0.49), -0.1, rng.randf_range(-depth * 0.49, depth * 0.49))
		rocks.multimesh.set_instance_transform(i, Transform3D(Basis(Vector3.UP, rng.randf() * TAU).scaled(size), pos))
		rocks.multimesh.set_instance_color(i, Color("#7d8065").lerp(Color("#a19a84"), rng.randf()))
	var material := _plain(Color.WHITE)
	material.vertex_color_use_as_albedo = true
	rocks.material_override = material
	rocks.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(rocks)
