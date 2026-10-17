shader_type spatial;
// Soft elliptical ground contact under each animal. Replaces per-animal shadow
// maps: one transparent quad per instance, no shadow pass at all.
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

void fragment() {
	vec2 d = (UV - 0.5) * 2.0;
	float r = dot(d, d);
	float a = (1.0 - smoothstep(0.0, 1.0, r));
	ALBEDO = vec3(0.02, 0.04, 0.03);
	ALPHA = a * a * COLOR.a;
}
