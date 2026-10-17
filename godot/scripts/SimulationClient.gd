extends Node

signal state_updated(state: Dictionary)
signal frame_updated(frame: Dictionary)
signal connection_changed(connected: bool, message: String)
signal command_completed(action: String, ok: bool, message: String)

const FRAME_VERSION := 2.0
const FRAME_HEADER := 24
const WEATHER := ["drought", "abundance", "heat", "cold", "storm", "flood", "wildfire", "disease", "redistribute"]

@export var api := "http://127.0.0.1:8765"
## Motion samples per second requested from /frame. Explanations (/state) poll
## separately and slower; nothing in the render path ever parses JSON.
@export var frame_rate := 24.0
var connected := false
var streaming := true
var last_frame: Dictionary = {}
var frame_latency_ms := 0.0
var state_latency_ms := 0.0
var _busy := false
var _failures := 0
var _timer: Timer
var _request: HTTPRequest
var _frame_request: HTTPRequest
var _frame_timer: Timer
var _frame_busy := false
var _frame_sent := 0
var _state_sent := 0
var _command_busy := false

func _ready() -> void:
	_request = HTTPRequest.new()
	_request.timeout = 2.5
	add_child(_request)
	_request.request_completed.connect(_received)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.timeout.connect(request_state)
	add_child(_timer)
	_frame_request = HTTPRequest.new()
	_frame_request.timeout = 1.5
	add_child(_frame_request)
	_frame_request.request_completed.connect(_frame_received)
	_frame_timer = Timer.new()
	_frame_timer.one_shot = true
	_frame_timer.timeout.connect(request_frame)
	add_child(_frame_timer)

func stop_polling() -> void:
	streaming = false
	_timer.stop()
	_frame_timer.stop()
	_request.cancel_request()
	_frame_request.cancel_request()
	_busy = false
	_frame_busy = false

func request_state() -> void:
	if _busy or not is_instance_valid(_request): return
	_busy = true
	_state_sent = Time.get_ticks_usec()
	if _request.request(api + "/state") != OK:
		_failed("Unable to connect. Start the simulation with vikasa godot.")

func request_frame() -> void:
	if _frame_busy or not streaming or not is_instance_valid(_frame_request): return
	_frame_busy = true
	_frame_sent = Time.get_ticks_usec()
	if _frame_request.request(api + "/frame") != OK:
		_frame_busy = false
		_frame_timer.start(0.5)

func _received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_busy = false
		_failed("Simulation offline · Start vikasa godot; reconnecting automatically.")
		return
	# The explanatory document is ~100–200 KB; parsing it on the main thread
	# caused visible hitches. Parse on a worker and hand back the result.
	WorkerThreadPool.add_task(func():
		var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
		_parsed.call_deferred(parsed))

func _parsed(parsed: Variant) -> void:
	_busy = false
	if not is_inside_tree(): return
	if not parsed is Dictionary or not parsed.get("creatures", null) is Array or not parsed.get("world", null) is Dictionary:
		_failed("Simulation sent an unreadable state. Retrying…")
		return
	state_latency_ms = (Time.get_ticks_usec() - _state_sent) / 1000.0
	_failures = 0
	var was_connected := connected
	connected = true
	if not was_connected:
		connection_changed.emit(true, "Connected")
		request_frame()
	state_updated.emit(parsed)
	if not streaming: return
	var population := int(parsed.get("population", 0))
	# The explanatory document is heavy; at large populations read it less often.
	_timer.start(0.45 if population < 300 else 0.8)

func _frame_received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_frame_busy = false
	if not streaming: return
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_frame_timer.start(0.5)
		return
	var frame := decode(body)
	if frame.is_empty():
		_frame_timer.start(0.5)
		return
	frame_latency_ms = (Time.get_ticks_usec() - _frame_sent) / 1000.0
	last_frame = frame
	frame_updated.emit(frame)
	var period := 1.0 / maxf(1.0, frame_rate)
	_frame_timer.start(maxf(0.004, period - frame_latency_ms / 1000.0))

static func decode(body: PackedByteArray) -> Dictionary:
	var data := body.to_float32_array()
	if data.size() < FRAME_HEADER or not is_equal_approx(data[0], FRAME_VERSION): return {}
	var count := int(data[2])
	var resources := int(data[3])
	var stride := int(data[4])
	var resource_stride := int(data[5])
	if data.size() != FRAME_HEADER + count * stride + resources * resource_stride: return {}
	var weather_code := int(data[12])
	return {
		"tick": int(data[1]), "count": count, "resource_count": resources,
		"stride": stride, "resource_stride": resource_stride, "paused": data[6] > 0.5,
		"ticks_per_second": data[7], "actual_ticks_per_second": data[8],
		"season_phase": data[9], "temperature": data[10], "rainfall": data[11],
		"weather": WEATHER[weather_code] if weather_code >= 0 and weather_code < WEATHER.size() else "",
		"weather_intensity": data[13], "weather_remaining": data[14],
		"width": data[15], "height": data[16], "total_births": int(data[17]),
		"total_deaths": int(data[18]), "feed_seq": int(data[19]), "food_pressure": data[20],
		"health_pressure": data[21], "maximum_energy": data[22],
		"offset": FRAME_HEADER, "resource_offset": FRAME_HEADER + count * stride, "data": data,
	}

func _failed(message: String) -> void:
	_busy = false
	var was_connected := connected
	connected = false
	_failures += 1
	if was_connected or _failures <= 1 or _failures % 4 == 0:
		connection_changed.emit(false, message)
	if streaming:
		_timer.start(minf(4.0, 0.4 * pow(2.0, mini(_failures, 4))))

func send_command(payload: Dictionary) -> void:
	var action := str(payload.get("action", "command"))
	if not connected:
		command_completed.emit(action, false, "Connect the simulation before changing the world.")
		return
	if _command_busy:
		command_completed.emit(action, false, "A command is still being applied. Try again in a moment.")
		return
	var request := HTTPRequest.new()
	request.timeout = 3.0
	add_child(request)
	_command_busy = true
	request.request_completed.connect(func(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray):
		_command_busy = false
		var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
		var ok := result == HTTPRequest.RESULT_SUCCESS and code >= 200 and code < 300
		var message := "Applied: " + action.capitalize() if ok else "Command could not be applied."
		if parsed is Dictionary and not ok: message = str(parsed.get("error", message))
		command_completed.emit(action, ok, message)
		request.queue_free()
		if ok:
			request_state()
			request_frame())
	var error := request.request(api + "/command", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_command_busy = false
		request.queue_free()
		command_completed.emit(action, false, "Command could not reach the simulation.")
