extends Node

signal state_updated(state: Dictionary)
signal connection_changed(connected: bool, message: String)
signal command_completed(action: String, ok: bool, message: String)

@export var api := "http://127.0.0.1:8765"
var connected := false
var _busy := false
var _failures := 0
var _timer: Timer
var _request: HTTPRequest
var _command_busy := false

func _ready() -> void:
	_request = HTTPRequest.new()
	_request.timeout = 2.0
	add_child(_request)
	_request.request_completed.connect(_received)
	_timer = Timer.new()
	_timer.one_shot = true
	_timer.timeout.connect(request_state)
	add_child(_timer)

func request_state() -> void:
	if _busy or not is_instance_valid(_request): return
	_busy = true
	if _request.request(api + "/state") != OK:
		_failed("Unable to connect. Start the simulation with vikasa godot.")

func _received(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	_busy = false
	if result != HTTPRequest.RESULT_SUCCESS or code != 200:
		_failed("Simulation offline · Start vikasa godot; reconnecting automatically.")
		return
	var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
	if not parsed is Dictionary or not parsed.get("creatures", null) is Array or not parsed.get("world", null) is Dictionary:
		_failed("Simulation sent an unreadable state. Retrying…")
		return
	_failures = 0
	connected = true
	connection_changed.emit(true, "Connected")
	state_updated.emit(parsed)
	var rate := float(parsed.get("ticks_per_second", 24.0))
	var population := int(parsed.get("population", 0))
	# Presentation updates do not need to match simulation ticks. Polling less
	# often at high speed/population leaves CPU time for both the engine and UI.
	var poll_interval := 0.22
	if rate > 48.0: poll_interval = 0.26
	if population > 250: poll_interval = maxf(poll_interval, 0.42)
	if population > 450: poll_interval = maxf(poll_interval, 0.55)
	_timer.start(poll_interval)

func _failed(message: String) -> void:
	_busy = false
	connected = false
	_failures += 1
	connection_changed.emit(false, message)
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
		if ok: request_state())
	var error := request.request(api + "/command", ["Content-Type: application/json"], HTTPClient.METHOD_POST, JSON.stringify(payload))
	if error != OK:
		_command_busy = false
		request.queue_free()
		command_completed.emit(action, false, "Command could not reach the simulation.")
