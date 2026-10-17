shader_type spatial;
// Procedural precipitation and airborne life around the habitat. Every particle
// is placed from its INSTANCE_ID and the clock alone: no CPU work per frame.
// mode 0 rain · 1 snow · 2 embers · 3 spores · 4 pollen · 5 dust · 6 fireflies
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform int mode = 0;
uniform float clock = 0.0;
uniform vec3 center = vec3(0.0);
uniform vec2 area = vec2(40.0, 28.0);
uniform float height = 22.0;
uniform float wind = 0.3;
uniform float intensity = 1.0;

varying vec4 tint;
varying vec2 quad;
varying float streak;

float rnd(float n) { return fract(sin(n * 12.9898) * 43758.5453); }

void vertex() {
	float id = float(INSTANCE_ID);
	float r1 = rnd(id + 0.1), r2 = rnd(id + 1.7), r3 = rnd(id + 4.3), r4 = rnd(id + 9.2);
	vec3 right = normalize(INV_VIEW_MATRIX[0].xyz);
	vec3 up = normalize(INV_VIEW_MATRIX[1].xyz);
	vec3 base = center + vec3((r1 * 2.0 - 1.0) * area.x, 0.0, (r2 * 2.0 - 1.0) * area.y);
	vec3 pos = base;
	vec3 color = vec3(1.0);
	float size = 0.1;
	float alpha = 1.0;
	streak = 0.0;
	if (mode == 0) {
		float fall = fract(r3 - clock * (1.4 + r4 * 0.5));
		pos.y = fall * height;
		pos.x += (1.0 - fall) * wind * 4.0;
		vec3 down = normalize(vec3(-wind * 0.35, -1.0, 0.0));
		pos += right * VERTEX.x * 0.035 - down * VERTEX.y * 0.9;
		color = vec3(0.55, 0.68, 0.85) * 0.9;
		streak = 1.0;
		alpha = 0.55;
	} else if (mode == 1) {
		float fall = fract(r3 - clock * (0.06 + r4 * 0.05));
		pos.y = fall * height;
		pos.x += sin(clock * 0.8 + id) * 0.8 + wind * (1.0 - fall) * 6.0;
		pos.z += cos(clock * 0.6 + id * 1.3) * 0.6;
		size = 0.09 + r4 * 0.07;
		color = vec3(0.95, 0.97, 1.0) * 1.3;
	} else if (mode == 2) {
		float rise = fract(r3 + clock * (0.10 + r4 * 0.12));
		pos.y = rise * height * 0.6;
		pos.x += sin(clock * 2.0 + id) * 0.6 + rise * wind * 6.0;
		size = 0.06 + r4 * 0.06;
		color = mix(vec3(1.0, 0.35, 0.05), vec3(1.0, 0.75, 0.25), r1) * (3.0 + 2.0 * sin(clock * 9.0 + id));
		alpha = 1.0 - rise;
	} else if (mode == 3 || mode == 4 || mode == 5) {
		pos.y = 0.4 + r3 * (mode == 5 ? 3.0 : 6.0);
		pos.x += sin(clock * 0.3 + id) * 2.0 + clock * wind * (mode == 5 ? 3.0 : 0.6);
		pos.x = center.x + mod(pos.x - center.x + area.x, area.x * 2.0) - area.x;
		pos.z += cos(clock * 0.27 + id * 0.7) * 2.0;
		size = 0.05 + r4 * 0.06;
		color = mode == 3 ? vec3(0.55, 0.95, 0.45) * 1.6 : (mode == 4 ? vec3(1.0, 0.85, 0.35) * 1.8 : vec3(0.75, 0.62, 0.42) * 0.8);
	} else {
		float t = clock * (0.25 + r4 * 0.2) + id;
		pos.y = 0.5 + r3 * 2.6 + sin(t * 1.7) * 0.4;
		pos.x += sin(t) * 1.8;
		pos.z += cos(t * 1.3) * 1.8;
		float blink = pow(max(sin(clock * (1.2 + r4) + id * 3.1), 0.0), 6.0);
		size = 0.07 + blink * 0.08;
		color = vec3(0.75, 1.0, 0.35) * (0.4 + blink * 6.0);
	}
	if (mode != 0) pos += right * VERTEX.x * size * 2.0 + up * VERTEX.y * size * 2.0;
	float shown = step(r4 * 0.999, intensity);
	tint = vec4(color, alpha * shown);
	quad = VERTEX.xy * 2.0;
	POSITION = PROJECTION_MATRIX * VIEW_MATRIX * vec4(pos, 1.0);
	if (shown < 0.5) POSITION = vec4(2.0, 2.0, 2.0, 1.0);
}

void fragment() {
	float d = streak > 0.5 ? abs(quad.x) : length(quad);
	float core = (1.0 - smoothstep(0.0, 1.0, d));
	ALBEDO = tint.rgb * core * tint.a;
}
