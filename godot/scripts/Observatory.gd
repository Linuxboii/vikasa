extends PanelContainer
const Chart := preload("res://scripts/LiveChart.gd")
var graphs: Array = []
var tab := 0
var tabs: Array[Button] = []
var vitality: Label
var pressure: Label
var events_label: Label
var sample_label: Label
var latest: Dictionary = {}
var stats: Dictionary = {}
var development_heading: Label
var habitat_map: Control

func _ready() -> void:
	name = "Observatory"
	anchor_bottom = 1
	offset_left = 16
	offset_right = 330
	offset_top = 96
	offset_bottom = -205
	BiomeUI.panel(self)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 12)
	scroll.add_child(content)
	content.add_child(BiomeUI.label("THE OBSERVATORY", 12, BiomeUI.ACCENT))
	development_heading = BiomeUI.label("A world in motion", 24)
	content.add_child(development_heading)
	var counts := HBoxContainer.new()
	counts.add_theme_constant_override("separation", 18)
	content.add_child(counts)
	for spec in [{"key": "total_births", "name": "Births", "color": Color("#7be0c2")}, {"key": "total_deaths", "name": "Deaths", "color": Color("#f1a07c")}, {"key": "food_count", "name": "Food", "color": BiomeUI.ACCENT}]:
		var box := VBoxContainer.new()
		box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		counts.add_child(box)
		stats[spec.key] = BiomeUI.label("0", 28, spec.color)
		box.add_child(stats[spec.key])
		box.add_child(BiomeUI.label(spec.name, 12, BiomeUI.MUTED))
	var tab_row := GridContainer.new()
	tab_row.columns = 2
	tab_row.add_theme_constant_override("separation", 4)
	content.add_child(tab_row)
	for i in range(5):
		var button := BiomeUI.button(["Population", "Survival", "Genetics", "Evolution", "Ecology"][i])
		button.add_theme_font_size_override("font_size", 12)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.toggle_mode = true
		button.pressed.connect(func(): tab = i; _configure(); set_state(latest))
		tab_row.add_child(button)
		tabs.append(button)
	for i in range(3):
		var graph = Chart.new()
		content.add_child(graph)
		graphs.append(graph)
	habitat_map = preload("res://scripts/HabitatMap.gd").new()
	content.add_child(habitat_map)
	pressure = BiomeUI.paragraph("Seasonal conditions", 13, BiomeUI.ACCENT)
	content.add_child(pressure)
	vitality = BiomeUI.paragraph("", 12)
	content.add_child(vitality)
	events_label = BiomeUI.paragraph("Observe births, adaptation and competition as time advances.", 12)
	content.add_child(events_label)
	sample_label = BiomeUI.label("Real simulation data · Hover a graph to inspect", 10, BiomeUI.MUTED)
	content.add_child(sample_label)
	_configure()
	get_viewport().size_changed.connect(_resize)
	_resize()

func _resize() -> void:
	var small := get_viewport_rect().size.y < 750
	offset_right = 302 if get_viewport_rect().size.x < 1150 else 330
	for graph in graphs: graph.custom_minimum_size.y = 90 if small else 112

func _process(_delta: float) -> void:
	var dock := get_parent().get_node_or_null("ObservationDock") as Control
	if dock: offset_bottom = dock.offset_top - 12

func _configure() -> void:
	habitat_map.visible = tab == 4
	for i in tabs.size(): tabs[i].set_pressed_no_signal(i == tab)
	var mint := Color("#7be0c2")
	var gold := Color("#e9c786")
	var coral := Color("#f1a07c")
	if tab == 0:
		graphs[0].configure("Population & food", [{"key": "population", "label": "Animals", "color": mint}, {"key": "food", "label": "Food", "color": gold}])
		graphs[1].configure("Life & loss · cumulative", [{"key": "total_births", "label": "Births", "color": mint}, {"key": "total_deaths", "label": "Deaths", "color": coral}])
		graphs[2].configure("Energy & injury · %", [{"key": "mean_energy_ratio", "label": "Energy", "color": gold}, {"key": "mean_injury", "label": "Injury", "color": coral}], true)
	elif tab == 1:
		graphs[0].configure("Reserves & exposure · %", [{"key": "mean_energy_ratio", "label": "Energy", "color": mint}, {"key": "mean_injury", "label": "Injury", "color": coral}], true)
		graphs[1].configure("Temperature & rainfall · %", [{"key": "temperature", "label": "Heat", "color": coral}, {"key": "rainfall", "label": "Rain", "color": mint}], true)
		graphs[2].configure("Food & metabolic pressure", [{"key": "food_multiplier", "label": "Food ×", "color": mint}, {"key": "metabolic_multiplier", "label": "Cost ×", "color": coral}])
	elif tab == 2:
		graphs[0].configure("Inherited size & speed · means", [{"key": "size_mean", "label": "Size", "color": gold}, {"key": "speed_mean", "label": "Speed", "color": mint}])
		graphs[1].configure("Generational development", [{"key": "max_generation", "label": "Deepest", "color": gold}, {"key": "mean_generation", "label": "Mean", "color": mint}])
		graphs[2].configure("Genetic diversity · normalized", [{"key": "diversity", "label": "Diversity", "color": gold}], true)
	elif tab == 3:
		graphs[0].configure("Generational development", [{"key": "max_generation", "label": "Deepest", "color": gold}, {"key": "mean_generation", "label": "Mean", "color": mint}])
		graphs[1].configure("Size · birth-cohort Price equation", [{"key": "size_selection", "label": "Selection", "color": mint}, {"key": "size_transmission", "label": "Transmission", "color": coral}], false, true)
		graphs[2].configure("Population renewal · %", [{"key": "founder_fraction", "label": "Founders", "color": gold}, {"key": "juvenile_fraction", "label": "Young", "color": mint}], true)
	else:
		graphs[0].configure("Living habitat · %", [{"key": "biomass_fraction", "label": "Plants", "color": mint}, {"key": "mean_water", "label": "Water", "color": gold}], true)
		graphs[1].configure("Finite plant-energy reservoir", [{"key": "plant_energy", "label": "Energy", "color": mint}])
		graphs[2].configure("Plant budget · cumulative energy", [{"key": "grown_energy", "label": "Growth", "color": mint}, {"key": "harvested_energy", "label": "Food", "color": gold}, {"key": "weather_loss", "label": "Loss", "color": coral}])

func set_state(state: Dictionary) -> void:
	latest = state
	habitat_map.set_habitat(state.get("habitat"))
	for key in stats: stats[key].text = str(int(state.get(key, 0)))
	for graph in graphs: graph.set_samples(state.get("history", []))
	if tab == 3:
		graphs[1].set_samples(state.get("birth_history", []))
		sample_label.text = "Birth-event identity · not a causal estimate of adaptation"
	else:
		sample_label.text = "Real simulation data · Hover a graph to inspect"
	var env: Dictionary = state.get("environment", {})
	var active: Array = env.get("active_events", [])
	pressure.text = "%s · productivity %.2f× · cost %.2f×" % [str(active[0].kind).capitalize() if not active.is_empty() else "Seasonal cycle", float(env.get("food_pressure", 1)), float(env.get("metabolic_pressure", 1))]
	vitality.text = "%d starving · %d alphas · %d fights won" % [int(state.get("starving_count", 0)), int(state.get("alpha_count", 0)), int(state.get("fight_count", 0))]
	var development: Dictionary = state.get("development", {})
	development_heading.text = "Generation %d" % int(development.get("max_generation", 0)) if not development.is_empty() else "A world in motion"
	if not development.is_empty():
		vitality.text += "\nGeneration %d · mean %.1f · founders %.0f%%" % [int(development.get("max_generation", 0)), float(development.get("mean_generation", 0)), float(development.get("founder_fraction", 0)) * 100]
		vitality.text += "\nYoung %.0f%% · mean age %.0f ticks" % [float(development.get("juvenile_fraction", 0)) * 100, float(development.get("mean_age", 0))]
	if tab == 4:
		var habitat = state.get("habitat")
		if habitat is Dictionary:
			var balance: Dictionary = habitat.get("summary", {})
			vitality.text += "\nPlant energy %.0f · soil water %.0f%%" % [float(balance.get("plant_energy", 0)), float(balance.get("mean_water", 0)) * 100]
			vitality.text += "\nExternal food %.0f energy · recorded interventions" % float(state.get("external_food_energy", 0))
			sample_label.text = "Finite reservoir · energy-balance residual %.8f" % float(balance.get("biomass_balance_residual", 0))
		else:
			sample_label.text = "Legacy patch model · select config/spatial-biome.json for soil and plant dynamics"
	var causes: Dictionary = state.get("death_causes", {})
	var loss: Array[String] = []
	for cause in causes: loss.append("%s %d" % [str(cause).capitalize(), int(causes[cause])])
	events_label.text = " · ".join(loss) if not loss.is_empty() else "No deaths yet · watch reserves, hazards and age."
	if not active.is_empty():
		events_label.text += "\nHazard: %.0f%% · shaded chart periods show exposure." % (float(env.get("health_pressure", 0)) * 100)
