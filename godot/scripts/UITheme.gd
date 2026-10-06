extends RefCounted
class_name BiomeUI

const INK := Color("#eef4ef")
const MUTED := Color("#9db9b8")
const ACCENT := Color("#e9c786")

static func font() -> SystemFont:
	var face := SystemFont.new()
	face.font_names = PackedStringArray(["Bahnschrift", "Aptos", "DejaVu Sans", "Arial"])
	return face

static func panel(control: PanelContainer) -> void:
	var style := StyleBoxFlat.new()
	style.bg_color = Color("#101f28f5")
	style.border_color = Color("#7be0c244")
	style.set_border_width_all(1)
	style.set_corner_radius_all(10)
	style.content_margin_left = 20
	style.content_margin_right = 20
	style.content_margin_top = 14
	style.content_margin_bottom = 14
	style.shadow_color = Color("#06121a90")
	style.shadow_size = 12
	control.add_theme_stylebox_override("panel", style)

static func label(text: String, size: int = 16, color: Color = INK) -> Label:
	var item := Label.new()
	item.text = text
	item.add_theme_font_size_override("font_size", size)
	item.add_theme_font_override("font", font())
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
	item.add_theme_font_size_override("font_size", 15)
	item.add_theme_font_override("font", font())
	item.add_theme_color_override("font_color", INK)
	item.add_theme_color_override("font_disabled_color", Color("#8e9d8e"))
	for kind in ["normal", "hover", "pressed", "disabled", "focus"]:
		var style := StyleBoxFlat.new()
		style.bg_color = Color("#223942") if kind == "normal" else Color("#355864")
		if kind == "pressed": style.bg_color = Color("#386159")
		if kind == "disabled": style.bg_color = Color("#1c2b34")
		if kind == "focus": style.bg_color = Color.TRANSPARENT
		style.border_color = ACCENT if kind in ["hover", "focus", "pressed"] else Color("#76927555")
		style.set_border_width_all(2 if kind == "focus" else 1)
		style.set_corner_radius_all(6)
		style.content_margin_left = 12
		style.content_margin_right = 12
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
	track.bg_color = Color("#405345")
	track.set_corner_radius_all(4)
	bar.add_theme_stylebox_override("background", track)
	return bar

static func percent(value: Variant) -> String:
	return "%d%%" % roundi(clampf(float(value), 0.0, 1.0) * 100.0)
