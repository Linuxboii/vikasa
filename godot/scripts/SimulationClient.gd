extends Node

signal state_updated(state: Dictionary)
signal frame_updated(frame: Dictionary)
signal connection_changed(connected: bool, message: String)
signal command_completed(action: String, ok: bool, message: String)

const FRAME_VERSION := 2.0
const FRAME_HEADER := 24
const WEATHER := ["drought", "abundance", "heat", "cold", "storm", "flood", "wildfire", "disease", "redistribute"]

@export var api := "http://127.0.0.1:8765"
## Fallback motion sample rate when the push stream is unavailable.
@export var frame_rate := 24.0
var connected := false
## Animal whose full explanation should ride along with the slim state document.
var focus_id := -1
## Append-only series merged locally; the bridge sends only rows past these cursors.
var history: Array = []
var birth_history: Array = []
var _last_state_tick := -1
var streaming := true
var last_frame: Dictionary = {}
var frame_latency_ms := 0.0
var frames_per_second := 0.0
var state_latency_ms := 0.0
var transport := "connecting"
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
# Push stream: one long-lived socket the bridge writes length-prefixed frames to.
# Polled without blocking once per rendered frame — no request per frame and no
# helper threads (threaded HTTPRequest busy-waits and steals CPU from rendering).
var _stream: StreamPeerTCP
var _stream_buffer := PackedByteArray()
var _stream_headers_done := false
var _stream_failures := 0
var _stream_retry := 0.0
var _last_frame_usec := 0
var _stream_requested := false

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
	_close_stream()
	_busy = false
	_frame_busy = false

func request_state() -> void:
	if _busy or not is_instance_valid(_request): return
	_busy = true
	_state_sent = Time.get_ticks_usec()
	var cursors := [_last_tick_of(history), _last_tick_of(birth_history)]
	if _request.request(api + "/state?lite=1&focus=%d&hs=%d&bs=%d" % [focus_id, cursors[0], cursors[1]]) != OK:
		_failed("Unable to connect. Start the simulation with vikasa godot.")

## Start motion: the push stream when possible, polling as a fallback.
func request_frame() -> void:
	if not streaming: return
	if _stream_failures < 3:
		if _stream == null: _open_stream()
		return
	if _frame_busy or not is_instance_valid(_frame_request): return
	_frame_busy = true
	transport = "polling"
	_frame_sent = Time.get_ticks_usec()
	if _frame_request.request(api + "/frame") != OK:
		_frame_busy = false
		_frame_timer.start(0.5)

func _open_stream() -> void:
	var address := api.trim_prefix("http://").split("/")[0]
	var host := address.get_slice(":", 0)
	var port := int(address.get_slice(":", 1)) if address.contains(":") else 80
	_stream = StreamPeerTCP.new()
	_stream_buffer.clear()
	_stream_headers_done = false
	if _stream.connect_to_host(host, port) != OK:
		_stream_lost()
		return
	transport = "stream"

func _close_stream() -> void:
	if _stream: _stream.disconnect_from_host()
	_stream = null
	_stream_buffer.clear()
	_stream_headers_done = false
	_stream_requested = false

func _stream_lost() -> void:
	_close_stream()
	_stream_failures += 1
	_stream_retry = 0.6
	if _stream_failures >= 3: request_frame()

func _process(delta: float) -> void:
	if not streaming: return
	if _stream == null:
		if connected and _stream_failures < 3 and _stream_retry > 0.0:
			_stream_retry -= delta
			if _stream_retry <= 0.0: _open_stream()
		return
	_stream.poll()
	var status := _stream.get_status()
	if status == StreamPeerTCP.STATUS_CONNECTING: return
	if status != StreamPeerTCP.STATUS_CONNECTED:
		_stream_lost()
		return
	if not _stream_requested:
		_stream_requested = true
		_stream.set_no_delay(true)
		_stream.put_data("GET /stream HTTP/1.1\r\nHost: localhost\r\n\r\n".to_ascii_buffer())
	var available := _stream.get_available_bytes()
	if available > 0:
		var chunk: Array = _stream.get_partial_data(available)
		if chunk[0] != OK:
			_stream_lost()
			return
		_stream_buffer.append_array(chunk[1])
	if not _stream_headers_done:
		var head := _stream_buffer.slice(0, mini(_stream_buffer.size(), 512)).get_string_from_ascii()
		var end := head.find("\r\n\r\n")
		if end < 0: return
		if not head.begins_with("HTTP/1.0 200") and not head.begins_with("HTTP/1.1 200"):
			_stream_lost()
			return
		_stream_headers_done = true

		_stream_failures = 0
		_stream_buffer = _stream_buffer.slice(end + 4)
	# Several frames may have queued during a slow frame; render only the newest.
	var newest := PackedByteArray()
	var cursor := 0
	while _stream_buffer.size() - cursor >= 4:
		var size := _stream_buffer.decode_u32(cursor)
		if _stream_buffer.size() - cursor < 4 + size: break
		newest = _stream_buffer.slice(cursor + 4, cursor + 4 + size)
		cursor += 4 + size
	if cursor > 0: _stream_buffer = _stream_buffer.slice(cursor)
	if newest.is_empty(): return
	var frame := decode(newest)
	if frame.is_empty(): return
	var now := Time.get_ticks_usec()
	if _last_frame_usec > 0:
		frames_per_second = lerpf(frames_per_second, 1_000_000.0 / maxf(1.0, now - _last_frame_usec), 0.1)
	_last_frame_usec = now
	frame_latency_ms = 0.0
	last_frame = frame
	frame_updated.emit(frame)

func _received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_busy = false
		_failed("Simulation offline · Start vikasa godot; reconnecting automatically.")
		return
	# Parse on a worker so a large document can never stall a rendered frame.
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
	var tick := int(parsed.get("tick", 0))
	var restarted := tick < _last_state_tick
	_last_state_tick = tick
	if restarted:
		# A restarted biome begins new series; fetch them whole on the next poll.
		history.clear()
		birth_history.clear()
	elif parsed.has("history_since"):
		_merge(history, parsed.get("history", []), 240)
		_merge(birth_history, parsed.get("birth_history", []), 180)
		parsed.history = history
		parsed.birth_history = birth_history
	_failures = 0
	var was_connected := connected
	connected = true
	if not was_connected:
		connection_changed.emit(true, "Connected")
		_stream_failures = 0
		request_frame()
	state_updated.emit(parsed)
	if not streaming: return
	var population := int(parsed.get("population", 0))
	_timer.start(0.4 if population < 300 else 0.8)

static func _last_tick_of(rows: Array) -> int:
	return int(rows[-1].get("tick", -1)) if not rows.is_empty() and rows[-1] is Dictionary else -1

static func _merge(into: Array, rows: Variant, limit: int) -> void:
	if not rows is Array: return
	var last := _last_tick_of(into)
	for row in rows:
		if row is Dictionary and int(row.get("tick", -1)) > last:
			into.append(row)
	if into.size() > limit:
		var excess := into.size() - limit
		for i in excess: into.pop_front()

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
	_close_stream()
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
			if transport == "polling": request_frame())
	var error := request.request(api + "/command", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_command_busy = false
		request.queue_free()
		command_completed.emit(action, false, "Command could not reach the simulation.")
