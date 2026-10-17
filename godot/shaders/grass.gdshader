shader_type spatial;
// Instanced grass blades and wildflowers that bend in the wind. Blade UV.y is
// 0 at the root and 1 at the tip; only the tip moves, so roots stay planted.
render_mode cull_disabled, diffuse_lambert_wrap, specular_disabled;

uniform float clock = 0.0;
uniform float wind = 0.35;
uniform vec3 tip_tint : source_color = vec3(0.78, 0.86, 0.48);
uniform vec3 root_tint : source_color = vec3(0.20, 0.34, 0.20);
uniform float snow : hint_range(0.0, 1.0) = 0.0;
uniform float height_scale = 1.0;
uniform bool flowers = false;
uniform float bloom : hint_range(0.0, 1.0) = 1.0;
uniform float night = 0.0;

varying float tip;
varying vec3 variation;

void vertex() {
	vec3 world = (MODEL_MATRIX * vec4(0.0, 0.0, 0.0, 1.0)).xyz;
	tip = UV.y;
	variation = COLOR.rgb;
	float h = UV.y * UV.y;
	VERTEX.y *= height_scale * (flowers ? bloom : 1.0);
	float gust = sin(clock * (1.3 + wind) + world.x * 0.35 + world.z * 0.22) * 0.6
		+ sin(clock * 2.7 + world.x * 0.9) * 0.25;
	vec3 bend = vec3(gust * (0.18 + wind * 0.55), 0.0, cos(clock * 1.7 + world.z * 0.4) * 0.12 * (0.3 + wind));
	VERTEX += (inverse(mat3(MODEL_MATRIX)) * bend) * h;
	VERTEX.y -= h * wind * wind * 0.12;
}

void fragment() {
	vec3 c;
	if (flowers) {
		c = variation;
		EMISSION = variation * night * 0.35;
	} else {
		c = mix(root_tint, tip_tint, tip) * (0.75 + variation * 0.5);
	}
	c = mix(c, vec3(0.88, 0.92, 0.96), snow * smoothstep(0.3, 1.0, tip));
	ALBEDO = c;
	BACKLIGHT = vec3(0.25, 0.32, 0.10) * tip;
	ROUGHNESS = 0.9;
}
