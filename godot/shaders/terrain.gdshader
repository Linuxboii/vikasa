shader_type spatial;
// Vertex-coloured topography tinted live by season, rain, snow and (when the
// spatial ecology profile is active) the measured plant biomass field.
render_mode diffuse_burley, specular_disabled, cull_disabled;

uniform vec3 ground_tint : source_color = vec3(1.0);
uniform float snow : hint_range(0.0, 1.0) = 0.0;
uniform float wet : hint_range(0.0, 1.0) = 0.0;
uniform float scorch : hint_range(0.0, 1.0) = 0.0;
uniform sampler2D biomass_map : filter_linear, repeat_disable;
uniform float biomass_weight = 0.0;
uniform vec2 world_size = vec2(72.0, 48.0);

varying vec3 world_pos;

float hash(vec2 p) { return fract(sin(dot(p, vec2(41.3, 289.1))) * 15731.743); }
float noise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec3 base = COLOR.rgb * ground_tint;
	float grain = noise(world_pos.xz * 1.7) * 0.5 + noise(world_pos.xz * 6.0) * 0.25;
	base *= 0.86 + grain * 0.28;
	if (biomass_weight > 0.0) {
		vec2 uv = world_pos.xz / world_size + 0.5;
		float plants = texture(biomass_map, uv).r;
		vec3 lush = vec3(0.22, 0.46, 0.20);
		vec3 bare = vec3(0.50, 0.42, 0.28);
		base = mix(base, mix(bare, lush, plants), biomass_weight * 0.7);
	}
	base = mix(base, vec3(0.20, 0.17, 0.12), scorch * smoothstep(0.3, 0.7, grain));
	float flat_ground = smoothstep(0.55, 0.95, NORMAL.y);
	float snow_mask = smoothstep(0.35, 0.65, snow + grain * 0.35 - 0.15) * mix(0.6, 1.0, flat_ground);
	base = mix(base, vec3(0.90, 0.93, 0.97), snow_mask * snow);
	base *= 1.0 - wet * 0.28;
	ALBEDO = base;
	ROUGHNESS = mix(0.95, 0.35, wet * 0.8);
	SPECULAR = wet * 0.5;
}
