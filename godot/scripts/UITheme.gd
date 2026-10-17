extends RefCounted
class_name BiomeUI

const INK := Color("#eef4ef")
const MUTED := Color("#9db9b8")
const ACCENT := Color("#f0cd8a")
const TEAL := Color("#7be0c2")
const ROSE := Color("#f1a07c")
const GLASS := Color("#0b1820d9")
const EDGE := Color("#7be0c233")

static var _font: SystemFont
static var _display: SystemFont

static func font() -> SystemFont:
	if _font == null:
		_font = SystemFont.new()
		_font.font_names = PackedStringArray(["Bahnschrift", "Segoe UI Variable Text", "Aptos", "DejaVu Sans", "Arial"])
		_font.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
		_font.subpixel_positioning = TextServer.SUBPIXEL_POSITIONING_DISABLED
	return _font

static func display_font() -> SystemFont:
	if _display == null:
		_display = SystemFont.new()
		_display.font_names = PackedStringArray(["Bahnschrift SemiLight", "Bahnschrift", "Segoe UI Variable Display", "Arial"])
		_display.font_weight = 300
	return _display

static func panel(control: PanelContainer, alpha: float = -1.0) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = GLASS if alpha < 0.0 else Color(GLASS.r, GLASS.g, GLASS.b, alpha)
	style.border_color = EDGE
	style.set_border_width_all(1)
	style.border_width_top = 1
	style.set_corner_radius_all(14)
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	style.shadow_color = Color("#02080c88")
	style.shadow_size = 6
	style.shadow_offset = Vector2(0, 3)
	style.anti_aliasing = true
	control.add_theme_stylebox_override("panel", style)

static func label(text: String, size: int = 16, color: Color = INK) -> Label:
	var item := Label.new()
	item.text = text
	item.add_theme_font_size_override("font_size", size)
	item.add_theme_font_override("font", display_font() if size >= 26 else font())
	item.add_theme_color_override("font_color", color)
	return item

static func paragraph(text: String, size: int = 16, color: Color = MUTED) -> Label:
	var item := label(text, size, color)
	item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	item.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return item

static func button(text: String, tip: String = "") -> Button:
	var item := Button.new()
	item.text = text
	item.tooltip_text = tip
	item.custom_minimum_size.y = 38
	item.focus_mode = Control.FOCUS_NONE
	item.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	item.add_theme_font_size_override("font_size", 15)
	item.add_theme_font_override("font", font())
	item.add_theme_color_override("font_color", INK)
	item.add_theme_color_override("font_hover_color", Color.WHITE)
	item.add_theme_color_override("font_pressed_color", ACCENT)
	item.add_theme_color_override("font_disabled_color", Color("#6f807a"))
	for kind in ["normal", "hover", "pressed", "disabled", "focus", "hover_pressed"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("#16303acc")
		if kind == "hover": style.bg_color = Color("#22495499")
		if kind in ["pressed", "hover_pressed"]: style.bg_color = Color("#2a5a52dd")
		if kind == "disabled": style.bg_color = Color("#11222a99")
		if kind == "focus": style.bg_color = Color.TRANSPARENT
		style.border_color = ACCENT if kind in ["hover", "pressed", "hover_pressed"] else Color("#7be0c222")
		if kind == "focus": style.border_color = Color("#f0cd8a88")
		style.set_border_width_all(1)
		style.set_corner_radius_all(9)
		style.content_margin_left = 13
		style.content_margin_right = 13
		style.anti_aliasing = true
		if kind in ["pressed", "hover_pressed"]:
			style.shadow_color = Color("#f0cd8a33")
			style.shadow_size = 6
		item.add_theme_stylebox_override(kind, style)
	return item

static func meter(color: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.max_value = 1.0
	bar.show_percentage = false
	bar.custom_minimum_size.y = 8
	var fill := StyleBoxFlat.new()
	fill.bg_color = color
	fill.set_corner_radius_all(4)
	bar.add_theme_stylebox_override("fill", fill)
	var track := StyleBoxFlat.new()
	track.bg_color = Color("#22363c")
	track.set_corner_radius_all(4)
	bar.add_theme_stylebox_override("background", track)
	return bar

static func chip(text: String, color: Color, size: int = 13) -> PanelContainer:
	var holder := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(color.r, color.g, color.b, 0.16)
	style.border_color = Color(color.r, color.g, color.b, 0.55)
	style.set_border_width_all(1)
	style.set_corner_radius_all(20)
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 3
	style.content_margin_bottom = 3
	holder.add_theme_stylebox_override("panel", style)
	var text_label := label(text, size, color.lightened(0.25))
	text_label.name = "Text"
	holder.add_child(text_label)
	return holder

static func percent(value: Variant) -> String:
	return "%d%%" % roundi(clampf(float(value), 0.0, 1.0) * 100.0)
