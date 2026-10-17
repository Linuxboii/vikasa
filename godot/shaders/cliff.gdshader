shader_type spatial;
// Sides of the floating biome: layered sediment strata fading into shadow.
render_mode diffuse_burley, specular_disabled, cull_disabled;

varying vec3 world_pos;

float hash(vec2 p) { return fract(sin(dot(p, vec2(17.1, 113.7))) * 43758.5453); }
float noise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
}

void vertex() { world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz; }

void fragment() {
	float along = world_pos.x + world_pos.z;
	float wobble = noise(vec2(along * 0.35, world_pos.y * 2.0)) * 0.35;
	float strata = fract(world_pos.y * 1.6 + wobble);
	vec3 a = vec3(0.36, 0.30, 0.24);
	vec3 b = vec3(0.24, 0.20, 0.17);
	vec3 c = mix(a, b, smoothstep(0.3, 0.7, strata));
	c *= 0.75 + noise(vec2(along * 2.0, world_pos.y * 6.0)) * 0.35;
	float depth = clamp(-world_pos.y / 6.0, 0.0, 1.0);
	c = mix(c, vec3(0.05, 0.07, 0.08), depth * 0.85);
	float lip = smoothstep(-0.55, -0.15, world_pos.y);
	c = mix(c, vec3(0.24, 0.38, 0.22), lip);
	ALBEDO = c;
	ROUGHNESS = 1.0;
}
