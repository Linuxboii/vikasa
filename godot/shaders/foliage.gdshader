shader_type spatial;
// Tree crowns: seasonal colour per instance, wind sway weighted by height,
// snow settling on upward faces in winter.
render_mode diffuse_lambert_wrap, specular_disabled;

uniform float clock = 0.0;
uniform float wind = 0.35;
uniform vec3 season_tint : source_color = vec3(1.0);
uniform float autumn : hint_range(0.0, 1.0) = 0.0;
uniform float snow : hint_range(0.0, 1.0) = 0.0;
uniform bool evergreen = false;

varying vec3 variation;
varying float upness;

void vertex() {
	vec3 world = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	variation = COLOR.rgb;
	float sway = sin(clock * (0.9 + wind) + world.x * 0.21 + world.z * 0.17) * (0.04 + wind * 0.10);
	VERTEX.x += sway * (VERTEX.y + 1.0);
	VERTEX.z += cos(clock * 1.1 + world.z * 0.3) * (0.02 + wind * 0.05) * (VERTEX.y + 1.0);
	upness = NORMAL.y;
}

void fragment() {
	vec3 leaf = variation * season_tint;
	if (!evergreen) {
		vec3 fall = mix(vec3(0.86, 0.42, 0.12), vec3(0.78, 0.18, 0.10), variation.g);
		leaf = mix(leaf, fall * (0.8 + variation.r * 0.4), autumn);
	}
	float settle = smoothstep(0.2, 0.75, upness) * snow;
	leaf = mix(leaf, vec3(0.92, 0.95, 0.98), settle * (evergreen ? 0.85 : 0.6));
	ALBEDO = leaf;
	BACKLIGHT = vec3(0.18, 0.22, 0.06);
	ROUGHNESS = 0.92;
}
