shader_type spatial;
// GPU-animated life events. Each instance is one particle of a burst:
//   origin = burst centre, basis.x.x = start clock (float32 transform data),
//   CUSTOM = (unused, kind, seed, scale)  — custom data may be half precision.
// kind 0 birth · 1 death · 2 clash · 3 food · 4 alpha crowned
// The whole pool is a single additive draw call; expired particles collapse.
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform float clock = 0.0;

varying vec4 tint;
varying vec2 quad;

float rnd(float n) { return fract(sin(n * 91.3458) * 47453.5453); }

void vertex() {
	float start = MODEL_MATRIX[0].x;
	int kind = int(INSTANCE_CUSTOM.y + 0.5);
	float seed = INSTANCE_CUSTOM.z;
	float scale = INSTANCE_CUSTOM.w;
	float age = clock - start;
	float life = kind == 0 ? 1.8 : (kind == 1 ? 3.0 : (kind == 2 ? 0.8 : (kind == 3 ? 1.4 : 2.4)));
	float t = age / life;
	float a = rnd(seed) * 6.2831;
	float b = rnd(seed + 3.1);
	float c = rnd(seed + 7.7);
	vec3 offset = vec3(0.0);
	float size = 0.16;
	vec3 color = vec3(1.0);
	float ease = 1.0 - pow(1.0 - clamp(t, 0.0, 1.0), 3.0);
	if (kind == 0) {
		float radius = 0.4 + ease * (1.2 + b * 0.8);
		offset = vec3(cos(a) * radius, 0.3 + ease * (1.6 + c * 1.4), sin(a) * radius);
		color = mix(vec3(1.0, 0.86, 0.45), vec3(1.0, 0.55, 0.7), b) * 3.2;
		size = 0.20 * (1.0 - t * 0.6);
	} else if (kind == 1) {
		float spin = a + age * (1.2 + b);
		float radius = (0.3 + b * 0.7) * (1.0 - t * 0.7);
		offset = vec3(cos(spin) * radius, 0.4 + t * (3.6 + c * 2.4), sin(spin) * radius);
		color = mix(vec3(0.55, 0.80, 1.0), vec3(0.92, 0.95, 1.0), c) * 2.4;
		size = 0.26 * (1.0 - t * 0.5);
	} else if (kind == 2) {
		vec3 dir = normalize(vec3(cos(a), 0.6 + b, sin(a)));
		offset = dir * age * (4.0 + c * 4.0) + vec3(0.0, 0.9 - 6.0 * age * age, 0.0);
		color = mix(vec3(1.0, 0.45, 0.12), vec3(1.0, 0.85, 0.35), b) * 4.0;
		size = 0.12 * (1.0 - t);
	} else if (kind == 3) {
		float radius = (0.2 + b * 1.4);
		offset = vec3(cos(a) * radius, 0.2 + ease * (0.8 + c), sin(a) * radius);
		color = mix(vec3(0.55, 1.0, 0.55), vec3(1.0, 0.95, 0.5), c) * 2.6;
		size = 0.14 * (1.0 - t);
	} else {
		float spin = a + age * 2.4;
		float radius = 1.1 + sin(t * 3.14159) * 0.6;
		offset = vec3(cos(spin) * radius, 0.4 + t * 2.8 + b * 0.5, sin(spin) * radius);
		color = vec3(1.0, 0.78, 0.30) * 4.0;
		size = 0.18;
	}
	float alive = step(0.0, age) * step(t, 1.0);
	float fade = smoothstep(0.0, 0.08, t) * (1.0 - smoothstep(0.65, 1.0, t));
	tint = vec4(color, fade * alive);
	quad = VERTEX.xy * 2.0;
	vec3 center = MODEL_MATRIX[3].xyz + offset * scale;
	vec3 view_center = (VIEW_MATRIX * vec4(center, 1.0)).xyz;
	vec3 view_pos = view_center + vec3(VERTEX.xy * size * scale * alive, 0.0);
	POSITION = PROJECTION_MATRIX * vec4(view_pos, 1.0);
}

void fragment() {
	float d = length(quad);
	float core = (1.0 - smoothstep(0.0, 1.0, d));
	ALBEDO = tint.rgb * core * core * tint.a;
	ALPHA = 1.0;
}
