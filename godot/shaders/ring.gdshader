shader_type spatial;
// Ground-projected ring on a unit quad: selection halo, sensing radius and home
// range. Optional dashes rotate so the overlay reads as "live" rather than paint.
render_mode unshaded, blend_add, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled;

uniform vec4 color : source_color = vec4(1.0, 0.85, 0.45, 1.0);
uniform float width = 0.06;
uniform float dashes = 0.0;
uniform float speed = 0.4;
uniform float clock = 0.0;
uniform float fill = 0.0;
uniform float energy = 1.6;

void fragment() {
	vec2 p = (UV - 0.5) * 2.0;
	float r = length(p);
	float band = (1.0 - smoothstep(0.0, width, abs(r - (1.0 - width))));
	if (dashes > 0.5) {
		float ang = atan(p.y, p.x) / 6.2831853 + 0.5;
		band *= step(0.45, fract(ang * dashes + clock * speed));
	}
	float inner = fill * (1.0 - smoothstep(0.0, 1.0, r)) * 0.25;
	ALBEDO = color.rgb * (band + inner) * color.a * energy;
}
