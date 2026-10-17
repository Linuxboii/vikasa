extends Control
class_name CinematicLayer
## Film-language overlays: animated letterbox, lower-third captions for the
## director camera, the opening title card and transient centre toasts.

var _bars := 0.0
var _bars_goal := 0.0
var caption_title: Label
var caption_body: Label
var caption_box: VBoxContainer
var title_box: VBoxContainer
var toast: Label
var _toast_time := 0.0
var _title_time := -1.0

func _ready() -> void:
	name = "Cinematic"
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	caption_box = VBoxContainer.new()
	caption_box.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	caption_box.offset_left = 64
	caption_box.offset_top = -190
	caption_box.offset_bottom = -110
	caption_box.offset_right = 900
	caption_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	caption_box.modulate.a = 0.0
	add_child(caption_box)
	caption_title = BiomeUI.label("", 34, BiomeUI.INK)
	caption_title.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	caption_title.add_theme_constant_override("shadow_offset_y", 2)
	caption_box.add_child(caption_title)
	caption_body = BiomeUI.label("", 17, BiomeUI.ACCENT)
	caption_body.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.6))
	caption_box.add_child(caption_body)
	title_box = VBoxContainer.new()
	title_box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	title_box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	title_box.grow_vertical = Control.GROW_DIRECTION_BOTH
	title_box.alignment = BoxContainer.ALIGNMENT_CENTER
	title_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title_box.modulate.a = 0.0
	add_child(title_box)
	var big := BiomeUI.label("V I K A S A", 92, Color("#f6e7c4"))
	big.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	big.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.45))
	big.add_theme_constant_override("shadow_offset_y", 4)
	big.add_theme_constant_override("shadow_outline_size", 8)
	title_box.add_child(big)
	var sub := BiomeUI.label("a living biome  ·  every life is an experiment", 20, Color("#cfe3dc"))
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.5))
	title_box.add_child(sub)
	toast = BiomeUI.label("", 18, BiomeUI.INK)
	toast.set_anchors_and_offsets_preset(Control.PRESET_CENTER_TOP)
	toast.grow_horizontal = Control.GROW_DIRECTION_BOTH
	toast.offset_top = 104
	toast.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	toast.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	toast.add_theme_constant_override("shadow_outline_size", 6)
	toast.modulate.a = 0.0
	add_child(toast)

func set_letterbox(on: bool) -> void:
	_bars_goal = 1.0 if on else 0.0
	if not on: caption_box.modulate.a = 0.0

func caption(title: String, body: String) -> void:
	caption_title.text = title
	caption_body.text = body
	caption_box.modulate.a = 0.0
	create_tween().tween_property(caption_box, "modulate:a", 1.0, 0.8)

func show_title() -> void:
	_title_time = 0.0

func flash(message: String) -> void:
	toast.text = message
	_toast_time = 2.6

func _process(delta: float) -> void:
	var before := _bars
	_bars = move_toward(_bars, _bars_goal, delta * 1.6)
	if _title_time >= 0.0:
		_title_time += delta
		var t := _title_time
		title_box.modulate.a = clampf(t / 1.2, 0.0, 1.0) * clampf((5.2 - t) / 1.2, 0.0, 1.0)
		title_box.scale = Vector2.ONE * (1.0 + t * 0.012)
		title_box.pivot_offset = title_box.size * 0.5
		if t > 5.4: _title_time = -1.0
	if _toast_time > 0.0:
		_toast_time -= delta
		toast.modulate.a = clampf(_toast_time / 0.5, 0.0, 1.0)
	if before != _bars or _bars > 0.0: queue_redraw()

func _draw() -> void:
	if _bars <= 0.0: return
	var eased := _bars * _bars * (3.0 - 2.0 * _bars)
	var bar := size.y * 0.1 * eased
	draw_rect(Rect2(0, 0, size.x, bar), Color(0, 0, 0, 0.92))
	draw_rect(Rect2(0, size.y - bar, size.x, bar), Color(0, 0, 0, 0.92))
