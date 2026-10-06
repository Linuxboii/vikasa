extends Node3D

@onready var client = $SimulationClient
@onready var world = $WorldView
@onready var hud = $Interface/HUD
@onready var inspector = $Interface/CreatureInspector
@onready var tools = $Interface/WorldTools
var latest_state: Dictionary = {}
var selected_id := -1
var following := false

func _ready() -> void:
	client.state_updated.connect(_on_state)
	client.connection_changed.connect(_on_connection)
	client.command_completed.connect(_on_command)
	world.creature_clicked.connect(_select)
	world.world_clicked.connect(_on_ground)
	hud.pause_requested.connect(_pause)
	hud.step_requested.connect(func(): client.send_command({"action": "step", "count": 1}))
	hud.speed_requested.connect(func(speed: int): client.send_command({"action": "speed", "ticks_per_second": speed}))
	hud.inspect_requested.connect(func(): inspector.set_open(selected_id >= 0))
	hud.world_tools_requested.connect(func(): inspector.set_open(false); tools.set_open(not tools.visible))
	hud.reset_requested.connect(func(): following = false; world.reset_camera(); hud.set_following(false))
	hud.follow_requested.connect(_toggle_follow)
	hud.restart_requested.connect(func(): _select(-1); client.send_command({"action": "restart"}))
	inspector.closed.connect(func(): inspector.set_open(false))
	tools.command_requested.connect(client.send_command)
	tools.placement_changed.connect(func(active: bool): world.placement_mode = active; hud.set_hint("Click the habitat to place food · Escape cancels" if active else "Right-drag to orbit · Wheel to zoom · Click an animal to observe"))
	client.request_state()

func _on_state(state: Dictionary) -> void:
	latest_state = state
	world.set_state(state)
	hud.set_state(state)
	tools.set_state(state)
	var selected := _selected()
	if selected_id >= 0 and selected.is_empty():
		_select(-1)
		hud.set_notice("The selected animal is no longer alive. Select another animal to observe.")
	else:
		hud.set_selection(selected)
		inspector.set_creature(selected)

func _on_connection(connected: bool, message: String) -> void:
	hud.set_connection(connected, message)
	tools.set_connected(connected)
	if not connected:
		latest_state = {}
		_select(-1)
		world.clear_snapshot()
		hud.set_notice(message, true)

func _on_command(_action: String, ok: bool, message: String) -> void:
	hud.set_notice(message, not ok)
	tools.set_notice(message, not ok)

func _selected() -> Dictionary:
	for creature in latest_state.get("creatures", []):
		if int(creature.get("id", -1)) == selected_id: return creature
	return {}

func _select(id: int) -> void:
	selected_id = id
	if id < 0:
		following = false
		world.set_follow(-1)
		hud.set_following(false)
	world.set_selected(id)
	if following: world.set_follow(id)
	hud.set_selection(_selected())
	inspector.set_creature(_selected())
	tools.set_open(false)
	inspector.set_open(id >= 0)

func _on_ground(position: Vector2) -> void:
	if tools.placing_food:
		tools.place_food(position)
	else:
		_select(-1)

func _pause() -> void:
	client.send_command({"action": "resume" if latest_state.get("paused", false) else "pause"})

func _toggle_follow() -> void:
	following = not following
	world.set_follow(selected_id if following else -1)
	hud.set_following(following)

func _unhandled_key_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode == KEY_ESCAPE:
			tools.cancel_placement()
			tools.set_open(false)
			inspector.set_open(false)
			get_viewport().set_input_as_handled()
		elif event.keycode == KEY_SPACE:
			_pause()
			get_viewport().set_input_as_handled()
