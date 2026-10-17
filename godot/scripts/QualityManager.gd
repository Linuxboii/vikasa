extends Node
class_name QualityManager
## Keeps the showcase smooth on whatever GPU it lands on. In "auto" it watches
## real frame times and steps quality down quickly when frames are missed and
## back up slowly once there is sustained headroom. Choices persist.

signal changed(settings: Dictionary)

const TIERS := [
	{"name": "battery", "render_scale": 0.72, "msaa": Viewport.MSAA_DISABLED, "glow": false, "shadows": false, "grass": 0.35, "lod": 26.0, "fx": 0.45},
	{"name": "balanced", "render_scale": 0.85, "msaa": Viewport.MSAA_DISABLED, "glow": true, "shadows": true, "grass": 0.6, "lod": 36.0, "fx": 0.75},
	{"name": "high", "render_scale": 1.0, "msaa": Viewport.MSAA_2X, "glow": true, "shadows": true, "grass": 0.85, "lod": 48.0, "fx": 1.0},
	{"name": "ultra", "render_scale": 1.0, "msaa": Viewport.MSAA_4X, "glow": true, "shadows": true, "grass": 1.0, "lod": 72.0, "fx": 1.0},
]
const MODES := ["auto", "battery", "balanced", "high", "ultra"]
const SETTINGS_PATH := "user://settings.cfg"

var mode := "auto"
var tier := 2
var _window: PackedFloat32Array = []
var _headroom_seconds := 0.0
var _cooldown := 8.0
var _bad_windows := 0
## Probes and captures switch this off so experiments never overwrite choices.
var persist := true

func _ready() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) == OK:
		mode = str(config.get_value("quality", "mode", "auto"))
		tier = clampi(int(config.get_value("quality", "tier", 2)), 0, TIERS.size() - 1)
	if mode != "auto": tier = MODES.find(mode) - 1
	apply.call_deferred()

func current() -> Dictionary:
	return TIERS[tier]

func describe() -> String:
	return ("auto → " if mode == "auto" else "") + TIERS[tier].name

func cycle() -> String:
	mode = MODES[(MODES.find(mode) + 1) % MODES.size()]
	if mode != "auto": tier = MODES.find(mode) - 1
	_cooldown = 3.0
	apply()
	return describe()

func apply() -> void:
	if persist:
		var config := ConfigFile.new()
		config.load(SETTINGS_PATH)
		config.set_value("quality", "mode", mode)
		config.set_value("quality", "tier", tier)
		config.save(SETTINGS_PATH)
	changed.emit(TIERS[tier])

func _process(delta: float) -> void:
	if mode != "auto": return
	_cooldown -= delta
	_window.append(delta)
	if _window.size() < 90: return
	var sorted := _window.duplicate()
	sorted.sort()
	var typical := sorted[sorted.size() / 2]
	var slow := sorted[int(sorted.size() * 0.9)]
	_window.clear()
	if _cooldown > 0.0: return
	# Vsync caps us at the refresh rate, so "typical" near 16.7 ms is healthy.
	if slow > 0.0235 and tier > 0:
		# One bad window can be a shader compile or a background task; two in a row is real.
		_bad_windows += 1
		if _bad_windows >= 2:
			tier -= 1
			_bad_windows = 0
			_headroom_seconds = 0.0
			_cooldown = 4.0
			apply()
		return
	_bad_windows = 0
	if typical < 0.0175 and slow < 0.019:
		_headroom_seconds += 1.5
		if _headroom_seconds > 20.0 and tier < TIERS.size() - 2:
			tier += 1
			_headroom_seconds = 0.0
			_cooldown = 6.0
			apply()
	else:
		_headroom_seconds = 0.0
