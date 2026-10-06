extends RefCounted
class_name BehaviorPresentation

const DRIVES := {
	"survival": {"label": "Survival", "description": "Preserving energy and recovering from injury.", "color": Color("#d6a780")},
	"foraging": {"label": "Foraging", "description": "Finding food within sensing range.", "color": Color("#d7c080")},
	"mating": {"label": "Mating", "description": "Seeking an eligible nearby partner.", "color": Color("#c2add0")},
	"offspring_care": {"label": "Offspring care", "description": "Staying near and supporting dependent young.", "color": Color("#b4cfa8")},
	"danger_avoidance": {"label": "Danger avoidance", "description": "Moving away from threats or hazardous weather.", "color": Color("#ddad91")},
	"territory": {"label": "Territory", "description": "Returning to or defending the home range.", "color": Color("#9fbfc5")}
}
const ACTIONS := {"explore": "Exploring nearby", "forage": "Seeking food", "rest": "Resting and recovering", "seek_mate": "Seeking a mate", "care": "Tending young", "flee": "Avoiding danger", "patrol": "Patrolling home range", "challenge": "Defending territory"}

static func ratio(data: Dictionary, key: String) -> Variant:
	var value: Variant = data.get(key)
	if not (value is float or value is int) or not is_finite(float(value)): return null
	return clampf(float(value), 0.0, 1.0)

static func percent(value: Variant) -> String:
	return "Unknown" if value == null else BiomeUI.percent(value)

static func urgency(value: Variant) -> String:
	if value == null: return "Unknown"
	if float(value) >= 0.75: return "Urgent"
	if float(value) >= 0.45: return "Rising"
	return "Low"

static func dominant(data: Dictionary) -> String:
	var key := ""
	var strongest := -1.0
	for candidate in DRIVES:
		var value: Variant = ratio(data, candidate)
		if value != null and float(value) > strongest:
			strongest = float(value)
			key = candidate
	return key

static func action(data: Dictionary) -> String:
	return str(ACTIONS.get(str(data.get("behavior", "explore")), "Exploring nearby"))

static func reason(data: Dictionary) -> String:
	var value: Variant = data.get("behavior_reason")
	return str(value) if value is String and not str(value).strip_edges().is_empty() else "Exploring nearby"

static func meter(bar: ProgressBar, value: Variant, color: Color) -> void:
	bar.value = 0.0 if value == null else float(value)
	bar.modulate = Color("#758078") if value == null else Color.WHITE
	var fill := bar.get_theme_stylebox("fill").duplicate() as StyleBoxFlat
	fill.bg_color = color
	bar.add_theme_stylebox_override("fill", fill)
	bar.tooltip_text = "No current measurement" if value == null else "0–44% low · 45–74% rising · 75–100% urgent"
