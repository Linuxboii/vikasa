extends VBoxContainer
class_name EventFeed
## Live chronicle of the biome as fading toasts. Births, deaths, clashes,
## traditions and milestones arrive from the bridge's sequenced feed (none are
## lost between polls); clicking a toast focuses the animal involved.

signal focus_requested(creature_id: int)
signal event_arrived(item: Dictionary)

const STYLE := {
	"birth": {"glyph": "✦", "color": Color("#f6d27a"), "title": "Birth"},
	"death": {"glyph": "✝", "color": Color("#a9c6e8"), "title": "Death"},
	"fight": {"glyph": "⚔", "color": Color("#f08a5d"), "title": "Clash"},
	"food": {"glyph": "❀", "color": Color("#8fdc9a"), "title": "Food"},
	"weather": {"glyph": "☁", "color": Color("#9fc3d6"), "title": "Weather"},
	"founded": {"glyph": "◈", "color": Color("#c9a6f0"), "title": "Tradition"},
	"ritual": {"glyph": "◌", "color": Color("#c9a6f0"), "title": "Ritual"},
	"restart": {"glyph": "↺", "color": Color("#7be0c2"), "title": "Restart"},
	"milestone": {"glyph": "★", "color": Color("#ffd36e"), "title": "Milestone"},
}
const MAX_TOASTS := 6
const LIFETIME := 7.0

var last_seq := 0
var muted_kinds := {"food": true}
var _toasts: Array = []
var enabled := true

func _ready() -> void:
	name = "EventFeed"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_theme_constant_override("separation", 6)
	alignment = BoxContainer.ALIGNMENT_BEGIN

func ingest(feed: Array) -> void:
	if feed.is_empty(): return
	var newest := int(feed[-1].get("seq", 0))
	if last_seq == 0 or newest < last_seq:
		# First contact or a restarted bridge: start from now, don't replay history.
		last_seq = newest
		return
	var fresh: Array = feed.filter(func(item): return int(item.get("seq", 0)) > last_seq)
	last_seq = newest
	for item in fresh: event_arrived.emit(item)
	# Births and deaths can come in bursts; summarise rather than flood.
	var births := fresh.filter(func(item): return item.kind == "birth")
	var deaths := fresh.filter(func(item): return item.kind == "death")
	for item in fresh:
		var kind := str(item.get("kind", ""))
		if muted_kinds.has(kind): continue
		if kind == "birth" and births.size() > 2: continue
		if kind == "death" and deaths.size() > 2: continue
		push(kind, str(item.get("text", "")), int(item.get("creature_id", -1)) if item.get("creature_id") != null else -1)
	if births.size() > 2: push("birth", "%d animals were born." % births.size(), int(births[-1].get("creature_id", -1)))
	if deaths.size() > 2: push("death", "%d animals died." % deaths.size(), -1)

func push(kind: String, text: String, creature_id: int = -1) -> void:
	if not enabled: return
	var style: Dictionary = STYLE.get(kind, {"glyph": "•", "color": BiomeUI.MUTED, "title": kind.capitalize()})
	var toast := PanelContainer.new()
	var box := StyleBoxFlat.new()
	var color: Color = style.color
	box.bg_color = Color("#0b1820cc")
	box.border_color = Color(color.r, color.g, color.b, 0.45)
	box.border_width_left = 3
	box.set_corner_radius_all(10)
	box.content_margin_left = 12
	box.content_margin_right = 12
	box.content_margin_top = 7
	box.content_margin_bottom = 7
	if kind == "milestone":
		box.shadow_color = Color(color.r, color.g, color.b, 0.35)
		box.shadow_size = 10
	toast.add_theme_stylebox_override("panel", box)
	toast.custom_minimum_size.x = 300
	toast.mouse_filter = Control.MOUSE_FILTER_STOP if creature_id >= 0 else Control.MOUSE_FILTER_IGNORE
	if creature_id >= 0:
		toast.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
		toast.tooltip_text = "Click to fly to animal #%d" % creature_id
		toast.gui_input.connect(func(event: InputEvent):
			if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
				focus_requested.emit(creature_id))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	toast.add_child(row)
	var glyph := BiomeUI.label(str(style.glyph), 18, color)
	glyph.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(glyph)
	var words := BiomeUI.paragraph(_tidy(text), 13, BiomeUI.INK)
	words.custom_minimum_size.x = 240
	words.mouse_filter = Control.MOUSE_FILTER_IGNORE
	row.add_child(words)
	add_child(toast)
	move_child(toast, 0)
	toast.modulate.a = 0.0
	toast.position.x += 40
	var tween := create_tween().set_parallel(true)
	tween.tween_property(toast, "modulate:a", 1.0, 0.35)
	_toasts.push_front({"node": toast, "age": 0.0})
	while _toasts.size() > MAX_TOASTS:
		var old: Dictionary = _toasts.pop_back()
		old.node.queue_free()

static var _creature_id := RegEx.create_from_string("\\b[Cc]reature (\\d+)")
static var _parents := RegEx.create_from_string("born to (\\d+) and (\\d+)")

func _tidy(text: String) -> String:
	text = text.replace("A new creature", "A new animal")
	text = _parents.sub(text, "born to #$1 and #$2")
	return _creature_id.sub(text, "#$1", true)

func _process(delta: float) -> void:
	for i in range(_toasts.size() - 1, -1, -1):
		var toast: Dictionary = _toasts[i]
		toast.age += delta
		var node: Control = toast.node
		if toast.age > LIFETIME - 0.8:
			node.modulate.a = clampf((LIFETIME - toast.age) / 0.8, 0.0, 1.0)
		if toast.age >= LIFETIME:
			node.queue_free()
			_toasts.remove_at(i)

func clear() -> void:
	for toast in _toasts: toast.node.queue_free()
	_toasts.clear()
	last_seq = 0
