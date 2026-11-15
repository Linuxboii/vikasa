extends Control
class_name DemoPilot
## Presentation autopilot for `vikasa demo` / `vikasa godot --demo`.
##
## Runs a narrated, looping tour of the Living Biome: director camera, lenses,
## night, a storm, a food bloom and a fast-forward burst. Any key or click hands
## control back to the presenter and restores normal settings.

signal finished

const LOOP_FROM := 30.0
const LOOP_AT := 250.0
## Each step fires once per loop at `t` seconds after the first animals appear.
const STEPS := [
	{"t": 9.0, "director": true, "title": "Vikasa · Living Biome", "body": "Every animal decides for itself from inherited genes, temperament and changing needs."},
	{"t": 34.0, "title": "Bodies from genes", "body": "Size, ears, ridges and tails are drawn from each animal's own genome."},
	{"t": 52.0, "lens": "dynasty", "title": "Dynasty lens", "body": "Families share a colour. Watch some lineages spread while others vanish."},
	{"t": 72.0, "lens": "generation", "title": "Generation lens", "body": "Brighter animals are more generations removed from the founders."},
	{"t": 90.0, "lens": "natural", "daylight": "night", "title": "Night falls", "body": "Eyeshine, fireflies and glowing food after dark. The simulation never pauses."},
	{"t": 116.0, "daylight": "golden", "weather": {"kind": "storm", "intensity": 1.4, "duration": 160}, "title": "A storm rolls in", "body": "Rain and wind injure exposed animals. Energy reserves decide who survives."},
	{"t": 150.0, "daylight": "cycle", "title": "Selection at work", "body": "The vulnerable die first; survivors pass their genes to the next generation."},
	{"t": 175.0, "weather": {"kind": "abundance", "intensity": 1.5, "duration": 220}, "title": "Food bloom", "body": "Abundance returns and the population rebuilds from the survivors."},
	{"t": 200.0, "speed": 120, "title": "Fast-forward", "body": "Generations pass in seconds. Evolution is slow; simulation lets us watch it."},
	{"t": 226.0, "speed": 48, "title": "Your turn", "body": "Press any key to explore. C restarts the director's cut, F1 lists every control."},
]

var main: Node
var elapsed := 0.0
var active := false
var _next := 0
var _banner: Label
var _panel: PanelContainer
var _title: Label
var _body: Label
var _progress: ProgressBar
var _panel_time := 0.0

func setup(owner_main: Node) -> void:
	main = owner_main

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_banner = BiomeUI.label("●  DEMO AUTOPILOT  ·  press any key or click to take control", 14, BiomeUI.ACCENT)
	_banner.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	_banner.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_banner.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_banner.offset_top = 92
	_banner.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.8))
	_banner.add_theme_constant_override("shadow_outline_size", 5)
	add_child(_banner)
	_panel = PanelContainer.new()
	BiomeUI.panel(_panel)
	_panel.custom_minimum_size = Vector2(640, 0)
	_panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP, Control.PRESET_MODE_MINSIZE)
	_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_panel.offset_top = 140
	_panel.offset_bottom = 140
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 4)
	_title = BiomeUI.label("", 24, BiomeUI.INK)
	_title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_body = BiomeUI.label("", 16, BiomeUI.MUTED)
	_body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_progress = BiomeUI.meter(BiomeUI.ACCENT)
	_progress.custom_minimum_size = Vector2(0, 4)
	_progress.max_value = LOOP_AT
	box.add_child(_title)
	box.add_child(_body)
	box.add_child(_progress)
	_panel.add_child(box)
	_panel.modulate.a = 0.0
	add_child(_panel)
	active = true

func _process(delta: float) -> void:
	if not active or main == null:
		return
	# The tour clock starts once the opening flight has something to show.
	if not bool(main.get("_intro_played")):
		return
	elapsed += delta
	_progress.value = elapsed
	while _next < STEPS.size() and elapsed >= float(STEPS[_next].t):
		_apply(STEPS[_next])
		_next += 1
	if elapsed >= LOOP_AT:
		elapsed = LOOP_FROM
		_next = 0
		while _next < STEPS.size() and float(STEPS[_next].t) < LOOP_FROM:
			_next += 1
	_panel_time -= delta
	var target := 1.0 if _panel_time > 0.0 else 0.0
	_panel.modulate.a = move_toward(_panel.modulate.a, target, delta * 1.6)
	_banner.modulate.a = 0.55 + 0.45 * absf(sin(Time.get_ticks_msec() / 700.0))

func _apply(step: Dictionary) -> void:
	if step.has("director") and not bool(main.get("director")):
		main.call("set_director", true)
	if step.has("lens"):
		main.call("set_view_mode", str(step.lens))
	if step.has("daylight"):
		set_daylight(str(step.daylight))
	if step.has("weather"):
		var weather: Dictionary = step.weather
		main.client.send_command({"action": "weather", "kind": weather.kind, "intensity": weather.intensity, "duration": int(weather.duration)})
	if step.has("speed"):
		main.client.send_command({"action": "speed", "ticks_per_second": int(step.speed)})
	narrate(str(step.get("title", "")), str(step.get("body", "")))

func narrate(title: String, body: String) -> void:
	if title == "" and body == "":
		return
	_title.text = title
	_body.text = body
	_panel_time = 11.0

func set_daylight(mode: String) -> void:
	var atmos = main.world.atmos
	for i in 4:
		if atmos.daylight_mode == mode:
			break
		atmos.cycle_daylight()
	main.hud.set_daylight(atmos.daylight_mode)

func _input(event: InputEvent) -> void:
	if not active:
		return
	var key: bool = event is InputEventKey and event.pressed and not event.echo
	var click: bool = event is InputEventMouseButton and event.pressed
	if key or click:
		stop()

func stop() -> void:
	if not active:
		return
	active = false
	if main != null:
		if bool(main.get("director")):
			main.call("set_director", false)
		main.client.send_command({"action": "speed", "ticks_per_second": 48})
		set_daylight("cycle")
		if str(main.get("view_mode")) != "natural":
			main.call("set_view_mode", "natural")
		main.hud.cinematic.flash("Autopilot off · you have the controls · F1 shows every shortcut")
	var tween := create_tween()
	tween.tween_property(self, "modulate:a", 0.0, 0.6)
	tween.tween_callback(func(): finished.emit(); queue_free())
