extends Node
class_name Soundscape
## Procedural audio with no asset files. Every sound is synthesised once, on a
## worker thread at startup, into small looping or one-shot AudioStreamWAVs;
## at runtime the engine only mixes them. Ambience follows wind, rain, night
## and weather; life events add rate-limited chimes, tones and thumps.

const RATE := 22050
var enabled := true
var ready_to_play := false
var _wind: AudioStreamPlayer
var _rain: AudioStreamPlayer
var _crickets: AudioStreamPlayer
var _oneshots: Array[AudioStreamPlayer] = []
var _streams: Dictionary = {}
var _cooldowns: Dictionary = {}
var _bird_timer := 3.0
var _rng := RandomNumberGenerator.new()

func _ready() -> void:
	name = "Soundscape"
	_rng.seed = 2026
	_wind = _player(-60.0)
	_rain = _player(-60.0)
	_crickets = _player(-60.0)
	for i in 6: _oneshots.append(_player(-12.0))
	WorkerThreadPool.add_task(_synthesise)

func _player(volume: float) -> AudioStreamPlayer:
	var player := AudioStreamPlayer.new()
	player.volume_db = volume
	add_child(player)
	return player

func _synthesise() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 77
	var made := {
		"wind": _loop(_wind_samples(rng, 6.0), 0.5),
		"rain": _loop(_rain_samples(rng, 4.0), 0.4),
		"crickets": _loop(_cricket_samples(rng, 5.0), 0.3),
		"thunder": _wav(_thunder_samples(rng, 3.6)),
		"birth": _wav(_bell([880.0, 1318.5, 1760.0], 0.9)),
		"death": _wav(_glide(330.0, 196.0, 1.4)),
		"clash": _wav(_thump(rng)),
	}
	for i in 4: made["bird%d" % i] = _wav(_bird_phrase(rng))
	_installed.call_deferred(made)

func _installed(made: Dictionary) -> void:
	_streams = made
	_wind.stream = made.wind
	_rain.stream = made.rain
	_crickets.stream = made.crickets
	for player in [_wind, _rain, _crickets]: player.play()
	ready_to_play = true

## conditions from Atmos: wind, rain, night, weather.
func update(delta: float, conditions: Dictionary, running: bool) -> void:
	if not ready_to_play: return
	for key in _cooldowns.keys(): _cooldowns[key] = maxf(0.0, _cooldowns[key] - delta)
	var mute := not enabled
	var wind := float(conditions.get("wind", 0.3))
	var rain := float(conditions.get("rain", 0.0))
	var night := float(conditions.get("night", 0.0))
	_fade(_wind, -60.0 if mute else lerpf(-30.0, -12.0, clampf(wind, 0.0, 1.2)), delta)
	_fade(_rain, -60.0 if mute or rain < 0.05 else lerpf(-30.0, -9.0, rain), delta)
	var calm := str(conditions.get("weather", "")) not in ["storm", "flood", "wildfire", "cold"]
	_fade(_crickets, -60.0 if mute or not calm else lerpf(-60.0, -20.0, clampf((night - 0.3) * 1.6, 0.0, 1.0)), delta)
	if not mute and running and calm and night < 0.4:
		_bird_timer -= delta
		if _bird_timer <= 0.0:
			_bird_timer = _rng.randf_range(2.5, 7.0)
			play("bird%d" % _rng.randi_range(0, 3), _rng.randf_range(-22.0, -14.0), _rng.randf_range(0.9, 1.15))

func _fade(player: AudioStreamPlayer, target: float, delta: float) -> void:
	player.volume_db = move_toward(player.volume_db, target, delta * 30.0)

func play(key: String, volume: float = -12.0, pitch: float = 1.0, cooldown: float = 0.0) -> void:
	if not enabled or not ready_to_play or not _streams.has(key): return
	if _cooldowns.get(key, 0.0) > 0.0: return
	_cooldowns[key] = cooldown
	for player in _oneshots:
		if not player.playing:
			player.stream = _streams[key]
			player.volume_db = volume
			player.pitch_scale = pitch
			player.play()
			return

func birth() -> void: play("birth", -20.0, _rng.randf_range(0.94, 1.12), 0.5)
func death() -> void: play("death", -24.0, _rng.randf_range(0.9, 1.05), 0.7)
func clash() -> void: play("clash", -16.0, _rng.randf_range(0.85, 1.15), 0.25)
func thunder(distance: float) -> void:
	var delay := clampf(distance / 60.0, 0.05, 1.6)
	get_tree().create_timer(delay).timeout.connect(func(): play("thunder", lerpf(-4.0, -16.0, clampf(distance / 90.0, 0.0, 1.0)), _rng.randf_range(0.85, 1.1)))

# --- synthesis ---------------------------------------------------------------

func _wav(samples: PackedFloat32Array, loop: bool = false) -> AudioStreamWAV:
	var bytes := PackedByteArray()
	bytes.resize(samples.size() * 2)
	for i in samples.size():
		bytes.encode_s16(i * 2, int(clampf(samples[i], -1.0, 1.0) * 32000.0))
	var wav := AudioStreamWAV.new()
	wav.format = AudioStreamWAV.FORMAT_16_BITS
	wav.mix_rate = RATE
	wav.stereo = false
	wav.data = bytes
	if loop:
		wav.loop_mode = AudioStreamWAV.LOOP_FORWARD
		wav.loop_begin = 0
		wav.loop_end = samples.size()
	return wav

func _loop(samples: PackedFloat32Array, crossfade_seconds: float) -> AudioStreamWAV:
	# Fold the tail into the head so the loop point is inaudible.
	var fade := int(crossfade_seconds * RATE)
	var body := samples.slice(0, samples.size() - fade)
	for i in fade:
		var t := float(i) / fade
		body[i] = body[i] * sqrt(t) + samples[samples.size() - fade + i] * sqrt(1.0 - t)
	return _wav(body, true)

func _wind_samples(rng: RandomNumberGenerator, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	var brown := 0.0
	var smooth := 0.0
	for i in out.size():
		brown = (brown + 0.02 * rng.randf_range(-1.0, 1.0)) / 1.02
		smooth += (brown - smooth) * 0.08
		var t := float(i) / RATE
		var gust := 0.55 + 0.3 * sin(t * 0.9) + 0.15 * sin(t * 2.3 + 1.0)
		out[i] = smooth * 9.0 * gust
	return out

func _rain_samples(rng: RandomNumberGenerator, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	var low := 0.0
	var drop := 0.0
	for i in out.size():
		var white := rng.randf_range(-1.0, 1.0)
		low += (white - low) * 0.35
		if rng.randf() < 0.0018: drop = rng.randf_range(0.3, 0.8)
		drop *= 0.985
		out[i] = low * 0.32 + drop * rng.randf_range(-1.0, 1.0) * 0.5
	return out

func _cricket_samples(rng: RandomNumberGenerator, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	for voice in 3:
		var pitch := rng.randf_range(3900.0, 4700.0)
		var period := rng.randf_range(0.42, 0.7)
		var offset := rng.randf() * period
		for i in out.size():
			var t := float(i) / RATE
			var phase := fmod(t + offset, period)
			if phase < 0.13:
				var gate := 1.0 if fmod(phase, 0.033) < 0.018 else 0.0
				out[i] += sin(TAU * pitch * t) * gate * sin(PI * phase / 0.13) * 0.16
	return out

func _thunder_samples(rng: RandomNumberGenerator, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	var brown := 0.0
	for i in out.size():
		var t := float(i) / RATE
		brown = (brown + 0.04 * rng.randf_range(-1.0, 1.0)) / 1.01
		var crack := rng.randf_range(-1.0, 1.0) * exp(-t * 18.0) * 0.6
		var rumble := brown * 3.0 * exp(-t / 1.1) * (0.7 + 0.3 * sin(t * 7.0))
		out[i] = crack + rumble
	return out

func _bell(partials: Array, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	for i in out.size():
		var t := float(i) / RATE
		var v := 0.0
		for k in partials.size():
			v += sin(TAU * float(partials[k]) * t) * exp(-t * (3.0 + k * 2.5)) / (1.0 + k)
		out[i] = v * 0.35 * minf(1.0, t * 400.0)
	return out

func _glide(from: float, to: float, seconds: float) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(seconds * RATE))
	var phase := 0.0
	for i in out.size():
		var t := float(i) / RATE
		phase += TAU * lerpf(from, to, t / seconds) / RATE
		out[i] = (sin(phase) + 0.3 * sin(phase * 2.0)) * exp(-t * 2.2) * minf(1.0, t * 60.0) * 0.3
	return out

func _thump(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(0.35 * RATE))
	var phase := 0.0
	for i in out.size():
		var t := float(i) / RATE
		phase += TAU * lerpf(140.0, 60.0, t / 0.35) / RATE
		out[i] = sin(phase) * exp(-t * 14.0) * 0.7 + rng.randf_range(-1.0, 1.0) * exp(-t * 40.0) * 0.35
	return out

func _bird_phrase(rng: RandomNumberGenerator) -> PackedFloat32Array:
	var out := PackedFloat32Array()
	out.resize(int(1.6 * RATE))
	var cursor := 0.0
	var base := rng.randf_range(2200.0, 3600.0)
	for n in rng.randi_range(3, 6):
		var length := rng.randf_range(0.06, 0.16)
		var sweep := rng.randf_range(-900.0, 1400.0)
		var phase := 0.0
		var start := int(cursor * RATE)
		for i in int(length * RATE):
			if start + i >= out.size(): break
			var t := float(i) / RATE
			var f := base + sweep * (t / length) + sin(t * 180.0) * 120.0
			phase += TAU * f / RATE
			out[start + i] += sin(phase) * pow(sin(PI * t / length), 2.0) * 0.28
		cursor += length + rng.randf_range(0.03, 0.12)
	return out
