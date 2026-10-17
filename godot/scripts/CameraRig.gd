extends Camera3D
class_name CameraRig
## Critically-damped orbit camera. Input changes *goals*; the camera eases
## toward them every frame, so every move — orbit, zoom, follow, director
## cut, intro flight — is smooth by construction.

var target := Vector3.ZERO
var yaw := 0.24
var pitch := 0.82
var distance := 90.0
var goal_target := Vector3.ZERO
var goal_yaw := 0.24
var goal_pitch := 0.82
var goal_distance := 90.0
var stiffness := 5.0
var min_distance := 7.0
var max_distance := 210.0
var auto_orbit := 0.0
var _shake := 0.0
var _shake_clock := 0.0

func _ready() -> void:
	fov = 46.0
	near = 0.2
	far = 700.0
	current = true

func snap() -> void:
	target = goal_target
	yaw = goal_yaw
	pitch = goal_pitch
	distance = goal_distance
	_apply()

func orbit(dx: float, dy: float) -> void:
	goal_yaw -= dx * 0.006
	goal_pitch = clampf(goal_pitch - dy * 0.004, 0.12, 1.42)

func zoom(steps: float) -> void:
	goal_distance = clampf(goal_distance * pow(1.12, steps), min_distance, max_distance)

func pan(local: Vector2) -> void:
	var forward := Vector3(-sin(goal_yaw), 0, -cos(goal_yaw))
	var right := Vector3(cos(goal_yaw), 0, -sin(goal_yaw))
	goal_target += (right * local.x + forward * local.y) * goal_distance * 0.0016

func shake(amount: float) -> void:
	_shake = maxf(_shake, amount)

func update(delta: float) -> void:
	goal_yaw += auto_orbit * delta
	var k := 1.0 - exp(-stiffness * delta)
	target = target.lerp(goal_target, k)
	yaw = lerp_angle(yaw, goal_yaw, k)
	pitch = lerpf(pitch, goal_pitch, k)
	distance = lerpf(distance, goal_distance, k)
	_shake = move_toward(_shake, 0.0, delta * 2.5)
	_shake_clock += delta
	_apply()

func _apply() -> void:
	var horizontal := distance * cos(pitch)
	var jitter := Vector3(sin(_shake_clock * 47.0), sin(_shake_clock * 59.0), cos(_shake_clock * 41.0)) * _shake * 0.35
	position = target + Vector3(sin(yaw) * horizontal, distance * sin(pitch), cos(yaw) * horizontal) + jitter
	look_at(target + Vector3(0, 1.0 if distance < 40.0 else 0.0, 0), Vector3.UP)

func ground_point(screen: Vector2) -> Vector3:
	var origin := project_ray_origin(screen)
	var ray := project_ray_normal(screen)
	if absf(ray.y) < 0.0001: return Vector3.INF
	var along := -origin.y / ray.y
	return origin + ray * along if along > 0.0 else Vector3.INF
