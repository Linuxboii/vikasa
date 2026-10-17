shader_type spatial;
// Glowberry clusters. CUSTOM = (spawn time on a 64 s wrapping clock, or < -50
// once fully grown; energy 0..1; seed; 0). Small wrapped values keep the
// half-precision custom channel exact enough. Clusters sprout when they
// appear, sway gently and become faintly bioluminescent at night.
render_mode diffuse_burley;

uniform float clock = 0.0;
uniform float night = 0.0;

varying float ripe;
varying float seed;

void vertex() {
	float born = INSTANCE_CUSTOM.x;
	float wrapped = mod(clock, 64.0);
	float grow = born < -50.0 ? 1.0 : clamp(mod(wrapped - born + 64.0, 64.0) / 0.7, 0.0, 1.0);
	grow = 1.0 - pow(1.0 - grow, 3.0);
	ripe = INSTANCE_CUSTOM.y;
	seed = INSTANCE_CUSTOM.z;
	VERTEX *= grow * (0.92 + 0.08 * sin(clock * 2.0 + seed * 10.0));
	VERTEX.x += sin(clock * 1.3 + seed * 6.0) * 0.03 * VERTEX.y;
}

void fragment() {
	vec3 berry = mix(vec3(0.55, 0.12, 0.30), vec3(0.95, 0.55, 0.20), ripe);
	berry = mix(berry, vec3(0.62, 0.30, 0.85), fract(seed * 3.0) * 0.35);
	ALBEDO = berry;
	ROUGHNESS = 0.32;
	SPECULAR = 0.6;
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 2.0);
	EMISSION = mix(vec3(0.25, 0.95, 0.85), berry, 0.35) * night * (0.55 + rim * 1.6) + berry * rim * 0.15;
}
