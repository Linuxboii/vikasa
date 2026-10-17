extends RefCounted
class_name MeshMerge
## Bakes several primitive meshes (each with its own transform) into one
## ArrayMesh surface, so compound props cost a single draw per MultiMesh.

static func merge(pieces: Array) -> ArrayMesh:
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	for piece in pieces:
		var mesh: PrimitiveMesh = piece[0]
		var transform: Transform3D = piece[1]
		var arrays := mesh.get_mesh_arrays()
		var start := vertices.size()
		var normal_basis := transform.basis.inverse().transposed()
		var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		var source_normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
		var source_uvs: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
		for i in points.size():
			vertices.append(transform * points[i])
			normals.append((normal_basis * source_normals[i]).normalized())
			uvs.append(source_uvs[i] if i < source_uvs.size() else Vector2.ZERO)
		for index in arrays[Mesh.ARRAY_INDEX]:
			indices.append(start + index)
	var out := []
	out.resize(Mesh.ARRAY_MAX)
	out[Mesh.ARRAY_VERTEX] = vertices
	out[Mesh.ARRAY_NORMAL] = normals
	out[Mesh.ARRAY_TEX_UV] = uvs
	out[Mesh.ARRAY_INDEX] = indices
	var result := ArrayMesh.new()
	result.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, out)
	return result

static func sphere(radius: float, radial: int, rings: int) -> SphereMesh:
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	mesh.radial_segments = radial
	mesh.rings = rings
	return mesh

static func cone(radius: float, height: float, radial: int) -> CylinderMesh:
	var mesh := CylinderMesh.new()
	mesh.top_radius = 0.0
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = radial
	mesh.rings = 1
	return mesh
