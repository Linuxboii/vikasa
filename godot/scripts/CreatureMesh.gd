extends RefCounted
class_name CreatureMesh
## Bakes the procedural quadruped into ONE ArrayMesh so the whole population can
## be drawn as a single GPU-instanced MultiMesh. Every vertex carries UV2 =
## (part, region): the creature shader animates parts (legs, head, tail) and
## shades regions (hide, underside, eyes…) without any per-animal nodes.

enum Part { TORSO, HEAD, NECK, TAIL, LEG0, LEG1, LEG2, LEG3, EAR, RIDGE, CROWN, WOUND, MARK }
enum Region { HIDE, UNDER, DARK, ACCENT, EYE, BLACK, GOLD, WOUND, MARK }

const BASE_Y := 0.70
const HIP_X := 0.84
const HIP_Z := 0.34
const HIP_Y := BASE_Y - 0.12
const TAIL_ROOT := Vector3(-1.11, BASE_Y + 0.03, 0.0)
const NECK_PIVOT := Vector3(0.86, BASE_Y + 0.10, 0.0)

static var _cache: Dictionary = {}

var _vertices := PackedVector3Array()
var _normals := PackedVector3Array()
var _parts := PackedVector2Array()
var _indices := PackedInt32Array()

static func build(detailed: bool) -> ArrayMesh:
	if _cache.has(detailed): return _cache[detailed]
	var maker := CreatureMesh.new()
	maker._assemble(detailed)
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = maker._vertices
	arrays[Mesh.ARRAY_NORMAL] = maker._normals
	arrays[Mesh.ARRAY_TEX_UV2] = maker._parts
	arrays[Mesh.ARRAY_INDEX] = maker._indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_cache[detailed] = mesh
	return mesh

func _assemble(detailed: bool) -> void:
	var hi := 14 if detailed else 9
	var mid := 10 if detailed else 7
	var lo := 7 if detailed else 5
	var y := BASE_Y
	_ellipsoid(Vector3(-0.02, y, 0), Vector3(1.46, 0.37, 0.51), Part.TORSO, Region.HIDE, hi, hi * 2 / 3)
	if detailed:
		_ellipsoid(Vector3(0.0, y - 0.23, 0), Vector3(0.88, 0.22, 0.42), Part.TORSO, Region.UNDER, mid, 6)
		_ellipsoid(Vector3(0.70, y + 0.01, 0), Vector3(0.44, 0.37, 0.43), Part.TORSO, Region.HIDE, mid, 7, Vector3(0, 0, -0.10))
		_ellipsoid(Vector3(-0.79, y - 0.01, 0), Vector3(0.49, 0.39, 0.45), Part.TORSO, Region.HIDE, mid, 7, Vector3(0, 0, 0.08))
		_ellipsoid(Vector3(0.91, y + 0.09, 0), Vector3(0.39, 0.28, 0.31), Part.NECK, Region.HIDE, mid, 7)
	_ellipsoid(Vector3(1.20, y + 0.19, 0), Vector3(0.31, 0.25, 0.30), Part.HEAD, Region.HIDE, mid, 7)
	_ellipsoid(Vector3(1.50, y + 0.08, 0), Vector3(0.41, 0.14, 0.21), Part.HEAD, Region.UNDER, mid, 6)
	if detailed:
		_ellipsoid(Vector3(1.43, y - 0.01, 0), Vector3(0.32, 0.105, 0.18), Part.HEAD, Region.DARK, lo, 5)
		_ellipsoid(Vector3(1.84, y + 0.10, 0), Vector3(0.10, 0.085, 0.15), Part.HEAD, Region.BLACK, lo, 5)
	for side in [-1.0, 1.0]:
		_ellipsoid(Vector3(1.29, y + 0.25, side * 0.245), Vector3(0.058, 0.07, 0.045), Part.HEAD, Region.EYE, lo, 5)
		_cone(Vector3(1.03, y + 0.39, side * 0.19), 0.13, 0.32, Part.EAR, Region.DARK, lo, Vector3(side * 0.35, 0, -0.42))
		if detailed:
			for mark in range(4):
				_ellipsoid(Vector3(-0.76 + mark * 0.25, y + 0.15, side * 0.485), Vector3(0.11, 0.075, 0.03), Part.MARK, Region.MARK, lo, 4, Vector3(0, 0, 0.18))
	for leg in range(4):
		var fore := leg < 2
		var side := -1.0 if leg % 2 == 0 else 1.0
		var hip := Vector3(HIP_X if fore else -HIP_X, HIP_Y, side * HIP_Z)
		var part: int = Part.LEG0 + leg
		if detailed:
			_capsule(hip + Vector3(0, -0.16, 0), 0.125, 0.43, part, Region.DARK, Vector3(0, 0, 0.10 if fore else -0.16))
			_ellipsoid(hip + Vector3(0.015, -0.30, 0), Vector3(0.13, 0.13, 0.125), part, Region.DARK, lo, 5)
			_capsule(hip + Vector3(0.025, -0.31, 0), 0.085, 0.34, part, Region.DARK, Vector3(0, 0, -0.06 if fore else 0.12))
			_ellipsoid(hip + Vector3(0.12, -0.41, 0), Vector3(0.26, 0.095, 0.17), part, Region.BLACK, lo, 5)
		else:
			_capsule(hip + Vector3(0, -0.22, 0), 0.12, 0.68, part, Region.DARK, Vector3.ZERO)
	var tail_length := 0.67
	_ellipsoid(TAIL_ROOT + Vector3(-tail_length * 0.62, -0.07, 0), Vector3(tail_length, 0.105, 0.12), Part.TAIL, Region.DARK, mid, 6, Vector3(0, 0, -0.12))
	if detailed:
		_ellipsoid(TAIL_ROOT + Vector3(-tail_length * 1.18, -0.12, 0), Vector3(0.20, 0.085, 0.10), Part.TAIL, Region.ACCENT, lo, 5, Vector3(0, 0, -0.25))
		for i in range(5):
			_ellipsoid(Vector3(-0.42 + i * 0.20, y + 0.31, 0), Vector3(0.105, 0.16, 0.15), Part.RIDGE, Region.ACCENT, lo, 4, Vector3(0, 0, -0.15))
		_ellipsoid(Vector3(0.26, y + 0.22, 0.40), Vector3(0.25, 0.04, 0.09), Part.WOUND, Region.WOUND, lo, 4)
	# The alpha crest is a raised gold mantle that also glows: readable from afar.
	_ellipsoid(Vector3(-0.05, y + 0.36, 0), Vector3(0.62, 0.035, 0.09), Part.CROWN, Region.GOLD, mid, 5)

func _append(arrays: Array, transform: Transform3D, part: int, region: int) -> void:
	var start := _vertices.size()
	var normal_basis := transform.basis.inverse().transposed()
	var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
	var tag := Vector2(part, region)
	for i in points.size():
		_vertices.append(transform * points[i])
		_normals.append((normal_basis * normals[i]).normalized())
		_parts.append(tag)
	for index in arrays[Mesh.ARRAY_INDEX]:
		_indices.append(start + index)

func _ellipsoid(at: Vector3, dimensions: Vector3, part: int, region: int, radial: int, rings: int, euler: Vector3 = Vector3.ZERO) -> void:
	var sphere := SphereMesh.new()
	sphere.radius = 1.0
	sphere.height = 2.0
	sphere.radial_segments = radial
	sphere.rings = maxi(3, rings)
	_append(sphere.get_mesh_arrays(), Transform3D(Basis.from_euler(euler) * Basis.from_scale(dimensions), at), part, region)

func _capsule(at: Vector3, radius: float, height: float, part: int, region: int, euler: Vector3) -> void:
	var capsule := CapsuleMesh.new()
	capsule.radius = radius
	capsule.height = maxf(height, radius * 2.0)
	capsule.radial_segments = 7
	capsule.rings = 2
	_append(capsule.get_mesh_arrays(), Transform3D(Basis.from_euler(euler), at), part, region)

func _cone(at: Vector3, radius: float, height: float, part: int, region: int, radial: int, euler: Vector3) -> void:
	var cone := CylinderMesh.new()
	cone.top_radius = 0.0
	cone.bottom_radius = radius
	cone.height = height
	cone.radial_segments = radial
	cone.rings = 1
	cone.cap_bottom = false
	_append(cone.get_mesh_arrays(), Transform3D(Basis.from_euler(euler), at), part, region)
