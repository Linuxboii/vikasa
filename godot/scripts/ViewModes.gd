extends RefCounted
class_name ViewModes
## Lenses on the same population. Each mode is a colouring rule evaluated on the
## compact frame row, so switching lens costs nothing and never touches the model.

const MODES := ["natural", "behavior", "energy", "dynasty", "generation", "temperament"]
const LABELS := {
	"natural": "Natural coat",
	"behavior": "Current action",
	"energy": "Energy reserve",
	"dynasty": "Dynasty (maternal line)",
	"generation": "Generation depth",
	"temperament": "Temperament",
}
const DESCRIPTIONS := {
	"natural": "Coat colour is inherited: body size, resilience and aggression shape hue and tone.",
	"behavior": "Every animal is tinted by what it is doing right now.",
	"energy": "Red animals are close to starvation; green animals carry full reserves.",
	"dynasty": "Animals sharing a colour descend from the same founding mother.",
	"generation": "Darker violet = founders; brighter gold = deeper descendant generations.",
	"temperament": "Red leans aggressive, blue leans sociable, pale animals are balanced.",
}
const BEHAVIOR_NAMES := ["explore", "forage", "rest", "seek_mate", "care", "flee", "patrol", "challenge"]
const BEHAVIOR_COLORS := [
	Color("#8fb8d8"), Color("#e2c35e"), Color("#7f8fa6"), Color("#e48fc0"),
	Color("#8fdc9a"), Color("#f08a5d"), Color("#5fc4c9"), Color("#e2534b"),
]
const BEHAVIOR_LABELS := ["Exploring", "Foraging", "Resting", "Courting", "Tending young", "Fleeing", "Patrolling", "Challenging"]

static func next(mode: String) -> String:
	return MODES[(MODES.find(mode) + 1) % MODES.size()]

static func coat(mode: String, row: Dictionary) -> Color:
	var energy: float = row.energy
	match mode:
		"behavior":
			return BEHAVIOR_COLORS[clampi(row.behavior, 0, 7)]
		"energy":
			if energy < 0.5: return Color("#d9483b").lerp(Color("#e8b84a"), energy * 2.0)
			return Color("#e8b84a").lerp(Color("#5fd47f"), (energy - 0.5) * 2.0)
		"dynasty":
			var hue := fposmod(float(row.founder) * 0.618034 + 0.05, 1.0)
			return Color.from_hsv(hue, 0.62, 0.86)
		"generation":
			var depth := clampf(float(row.generation) / 14.0, 0.0, 1.0)
			return Color("#4b2a7a").lerp(Color("#2f8f8a"), minf(1.0, depth * 2.0)).lerp(Color("#f2d35b"), maxf(0.0, depth * 2.0 - 1.0))
		"temperament":
			var aggression: float = row.aggression
			var sociability: float = row.sociability
			return Color("#e9e3d4").lerp(Color("#e0533f"), clampf(aggression - sociability * 0.5, 0.0, 1.0)).lerp(Color("#4f8fe0"), clampf(sociability - aggression * 0.5, 0.0, 1.0))
	# Natural: heritable coat, dulled by low reserves. Hues stay earthy.
	var size_norm := clampf((float(row.size) - 2.5) / 5.5, 0.0, 1.0)
	var hue := fposmod(0.035 + size_norm * 0.085 + float(row.resilience) * 0.05, 1.0)
	var hide := Color.from_hsv(hue, 0.46 + float(row.aggression) * 0.22, 0.46 + float(row.resilience) * 0.16)
	return hide.lerp(Color("#5a5850"), (1.0 - energy) * 0.32)
