extends Node3D
class_name Atmos
## Light, sky and mood. Daylight is a presentation clock (the model has seasons
## but no diurnal cycle); seasons and weather come from the simulation frame.
## Produces one `conditions` dictionary that every visual system reads.

const DAYLIGHT_MODES := ["cycle", "day", "golden", "night"]
const SEASONS := [
	{"name": "spring", "grass_tip": Color("#a8d66a"), "grass_root": Color("#2e5a2e"), "canopy": Color(1.04, 1.1, 0.96), "ground": Color(1.0, 1.05, 0.95), "autumn": 0.0, "snow": 0.0, "bloom": 1.0, "grass_height": 1.0},
	{"name": "summer", "grass_tip": Color("#cfc86a"), "grass_root": Color("#4a6430"), "canopy": Color(1.0, 1.0, 0.86), "ground": Color(1.08, 1.03, 0.86), "autumn": 0.0, "snow": 0.0, "bloom": 0.55, "grass_height": 1.1},
	{"name": "autumn", "grass_tip": Color("#cf9e50"), "grass_root": Color("#5b5230"), "canopy": Color(1.0, 0.95, 0.85), "ground": Color(1.06, 0.95, 0.80), "autumn": 0.45, "snow": 0.0, "bloom": 0.12, "grass_height": 0.95},
	{"name": "winter", "grass_tip": Color("#aab4a2"), "grass_root": Color("#46524a"), "canopy": Color(0.9, 0.95, 1.0), "ground": Color(0.95, 0.99, 1.04), "autumn": 0.2, "snow": 0.28, "bloom": 0.0, "grass_height": 0.7},
]

var environment: Environment
var sun: DirectionalLight3D
var sky_material: ShaderMaterial
var day_phase := 0.30
var daylight_mode := "cycle"
## Real seconds per full day at "Present" speed (48 ticks/s).
var day_seconds := 150.0
var season_phase := 0.0
var weather := ""
var intensity := 0.0
var night := 0.0
var golden := 0.0
var flash := 0.0
var storminess := 0.0
var conditions: Dictionary = {}
var clock := 0.0
var glow_allowed := true
var _target_season := 0.0
var _weather_blend: Dictionary = {}

func _ready() -> void:
	name = "Atmosphere"
	sky_material = ShaderMaterial.new()
	sky_material.shader = load("res://shaders/sky.gdshader")
	var sky := Sky.new()
	sky.sky_material = sky_material
	sky.radiance_size = Sky.RADIANCE_SIZE_32
	sky.process_mode = Sky.PROCESS_MODE_QUALITY
	environment = Environment.new()
	environment.background_mode = Environment.BG_SKY
	environment.sky = sky
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	environment.tonemap_mode = Environment.TONE_MAPPER_ACES
	environment.tonemap_exposure = 1.0
	environment.tonemap_white = 8.0
	environment.glow_enabled = true
	environment.glow_intensity = 0.55
	environment.glow_strength = 0.9
	environment.glow_bloom = 0.04
	environment.glow_hdr_threshold = 1.05
	environment.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	environment.fog_enabled = true
	environment.fog_density = 0.0035
	environment.fog_sky_affect = 0.25
	environment.fog_aerial_perspective = 0.0
	environment.adjustment_enabled = true
	environment.adjustment_saturation = 1.14
	environment.adjustment_contrast = 1.07
	var world := WorldEnvironment.new()
	world.environment = environment
	add_child(world)
	sun = DirectionalLight3D.new()
	sun.name = "SunAndMoon"
	sun.shadow_enabled = true
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_ORTHOGONAL
	sun.directional_shadow_max_distance = 150.0
	sun.shadow_blur = 1.5
	sun.shadow_bias = 0.08
	sun.shadow_normal_bias = 2.5
	add_child(sun)
	_compute(0.0)

func cycle_daylight() -> String:
	daylight_mode = DAYLIGHT_MODES[(DAYLIGHT_MODES.find(daylight_mode) + 1) % DAYLIGHT_MODES.size()]
	return daylight_mode

func set_frame(frame: Dictionary) -> void:
	_target_season = float(frame.get("season_phase", 0.0))
	weather = str(frame.get("weather", ""))
	intensity = float(frame.get("weather_intensity", 0.0))

func strike() -> void:
	flash = 1.0

func update(delta: float, running: bool, speed_scale: float) -> void:
	clock += delta
	if running and daylight_mode == "cycle":
		day_phase = fposmod(day_phase + delta * clampf(speed_scale, 0.3, 2.5) / day_seconds, 1.0)
	var goal_phase: float = {"cycle": day_phase, "day": 0.27, "golden": 0.46, "night": 0.77}[daylight_mode]
	if daylight_mode != "cycle":
		day_phase = fposmod(day_phase + _cyclic_delta(day_phase, goal_phase) * minf(1.0, delta * 1.5), 1.0)
	season_phase = fposmod(season_phase + _cyclic_delta(season_phase / 4.0, _target_season / 4.0) * 4.0 * minf(1.0, delta * 0.8), 4.0)
	flash = move_toward(flash, 0.0, delta * 3.2)
	_compute(delta)

func _cyclic_delta(from: float, to: float) -> float:
	var d := fposmod(to - from, 1.0)
	return d - 1.0 if d > 0.5 else d

func _season_value(key: String) -> Variant:
	var index := int(floorf(season_phase)) % 4
	var within := season_phase - floorf(season_phase)
	var blend := smoothstep(0.0, 1.0, within)
	var a: Variant = SEASONS[index][key]
	var b: Variant = SEASONS[(index + 1) % 4][key]
	if a is Color: return (a as Color).lerp(b, blend)
	return lerpf(float(a), float(b), blend)

func _weather_amount(kinds: Array, delta: float) -> float:
	var key := ",".join(kinds)
	var goal := clampf(0.4 + intensity * 0.45, 0.0, 1.0) if weather in kinds else 0.0
	var current: float = _weather_blend.get(key, 0.0)
	current = move_toward(current, goal, delta * 0.6) if delta > 0.0 else goal
	_weather_blend[key] = current
	return current

func _compute(delta: float) -> void:
	var angle := day_phase * TAU
	var elevation := sin(angle)
	var to_sun := Vector3(cos(angle) * 0.82, elevation, 0.42 + cos(angle) * 0.12).normalized()
	night = smoothstep(0.06, -0.20, elevation)
	golden = (1.0 - smoothstep(0.04, 0.42, elevation)) * (1.0 - night)
	var storm := _weather_amount(["storm", "flood"], delta)
	var cold := _weather_amount(["cold"], delta)
	var fire := _weather_amount(["wildfire"], delta)
	var dry := _weather_amount(["drought", "heat"], delta)
	var sick := _weather_amount(["disease"], delta)
	var bloom_boost := _weather_amount(["abundance"], delta)
	storminess = storm
	var light_dir := to_sun if night < 0.5 else -to_sun
	if light_dir.y < 0.12: light_dir = Vector3(light_dir.x, 0.12, light_dir.z).normalized()
	var up := Vector3.UP if absf(light_dir.dot(Vector3.UP)) < 0.98 else Vector3.FORWARD
	sun.transform = Transform3D(Basis.looking_at(-light_dir, up), Vector3.ZERO)
	var day_energy := lerpf(0.3, 1.75, smoothstep(-0.05, 0.45, elevation))
	var sun_color := Color(1.0, 0.95, 0.86).lerp(Color(1.0, 0.62, 0.34), golden)
	var moon_color := Color(0.55, 0.66, 1.0)
	var light_energy := lerpf(day_energy, 0.48, night) * (1.0 - storm * 0.55)
	sun.light_color = sun_color.lerp(moon_color, night)
	sun.light_energy = light_energy + flash * 2.6
	var ambient := Color(0.64, 0.72, 0.80).lerp(Color(0.95, 0.70, 0.55), golden * 0.5).lerp(Color(0.24, 0.32, 0.56), night)
	ambient = ambient.lerp(Color(0.42, 0.45, 0.52), storm * 0.6)
	environment.ambient_light_color = ambient
	environment.ambient_light_energy = lerpf(0.44, 0.5, night) + flash * 0.8
	var horizon := Color(0.66, 0.78, 0.86).lerp(Color(0.95, 0.62, 0.42), golden * 0.7).lerp(Color(0.07, 0.10, 0.18), night)
	horizon = horizon.lerp(Color(0.30, 0.33, 0.38), storm * 0.7).lerp(Color(0.62, 0.40, 0.25), fire * 0.6).lerp(Color(0.50, 0.62, 0.40), sick * 0.5)
	environment.fog_light_color = horizon
	environment.fog_density = 0.0028 + storm * 0.006 + fire * 0.006 + sick * 0.004 + dry * 0.002 + night * 0.0015
	environment.glow_enabled = glow_allowed
	environment.glow_intensity = lerpf(0.45, 0.85, night)
	environment.tonemap_exposure = lerpf(1.0, 1.25, night)
	sky_material.set_shader_parameter("sun_direction", to_sun)
	sky_material.set_shader_parameter("night", night)
	sky_material.set_shader_parameter("golden", golden)
	sky_material.set_shader_parameter("storm", storm)
	sky_material.set_shader_parameter("flash", flash)
	sky_material.set_shader_parameter("clock", clock)
	sky_material.set_shader_parameter("tint", Color(1, 1, 1).lerp(Color(1.0, 0.78, 0.6), fire * 0.6).lerp(Color(0.85, 1.0, 0.8), sick * 0.3))
	var snow := clampf(float(_season_value("snow")) + cold * 0.75, 0.0, 1.0)
	var grass_tip: Color = _season_value("grass_tip")
	grass_tip = grass_tip.lerp(Color("#cdb46e"), dry * 0.7)
	conditions = {
		"clock": clock, "night": night, "golden": golden, "sun_direction": light_dir,
		"wind": 0.25 + storm * 0.9 + cold * 0.3 + fire * 0.4,
		"snow": snow, "wet": clampf(storm * 1.1, 0.0, 1.0), "scorch": fire * 0.8,
		"rain": storm, "frozen": clampf(cold * 1.2 + snow * 0.3 - 0.2, 0.0, 1.0),
		"ground_tint": (_season_value("ground") as Color).lerp(Color(1.12, 1.0, 0.78), dry * 0.6),
		"grass_tip": grass_tip, "grass_root": _season_value("grass_root"),
		"grass_height": float(_season_value("grass_height")) * (1.0 - dry * 0.35),
		"bloom": clampf(float(_season_value("bloom")) + bloom_boost * 0.8 - dry * 0.6, 0.0, 1.0),
		"canopy_tint": _season_value("canopy"), "autumn": float(_season_value("autumn")),
		"sky_color": horizon.lerp(Color(0.40, 0.55, 0.70), 0.4),
		"water_level": clampf(1.0 + storm * 0.35 - dry * 0.35, 0.55, 1.4),
		"weather": weather, "intensity": intensity,
		"season": SEASONS[int(floorf(season_phase)) % 4].name,
	}

func clock_label() -> String:
	var hours := fposmod(day_phase * 24.0 + 6.0, 24.0)
	return "%02d:%02d" % [int(hours), int(fposmod(hours * 60.0, 60.0))]
