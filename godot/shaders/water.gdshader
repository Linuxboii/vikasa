shader_type spatial;
// Opaque stylised pool: layered sine normals, sky fresnel, sun/moon glints,
// shoreline foam and rain ripples. UV is a unit disc (0.5, 0.5 = centre).
render_mode diffuse_lambert, specular_schlick_ggx;

uniform float clock = 0.0;
uniform float rain = 0.0;
uniform float night = 0.0;
uniform vec3 deep : source_color = vec3(0.05, 0.27, 0.38);
uniform vec3 sun_direction = vec3(0.3, 0.8, 0.2);
uniform vec3 shallow : source_color = vec3(0.18, 0.50, 0.60);
uniform vec3 sky_color : source_color = vec3(0.62, 0.78, 0.88);
uniform float frozen : hint_range(0.0, 1.0) = 0.0;

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void fragment() {
	vec2 p = (UV - 0.5) * 2.0;
	float r = length(p);
	if (r > 1.0) discard;
	vec3 world = (INV_VIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	vec2 w = world.xz;
	vec2 slope = vec2(
		sin(w.x * 1.9 + clock * 1.3) * 0.5 + sin(w.x * 3.7 - w.y * 1.3 + clock * 2.1) * 0.25,
		cos(w.y * 2.3 + clock * 1.1) * 0.5 + cos(w.y * 4.1 + w.x * 1.7 - clock * 1.7) * 0.25);
	// Rain: expanding rings in hashed cells.
	vec2 cell = floor(w * 1.6);
	vec2 local = fract(w * 1.6) - 0.5;
	float phase = fract(clock * 0.9 + hash(cell));
	float ring = (1.0 - smoothstep(0.0, 0.06, abs(length(local) - phase * 0.5))) * (1.0 - phase) * rain;
	slope += normalize(local + 0.0001) * ring * 2.0;
	vec3 n = normalize(vec3(-slope.x * 0.08, 1.0, -slope.y * 0.08));
	NORMAL = normalize((VIEW_MATRIX * vec4(n, 0.0)).xyz);
	float fresnel = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 4.0);
	vec3 body = mix(deep, shallow, smoothstep(0.2, 1.0, r));
	vec3 c = mix(body, sky_color, fresnel * 0.8);
	float foam = smoothstep(0.82, 0.97, r + sin(atan(p.y, p.x) * 9.0 + clock * 0.8) * 0.025);
	c = mix(c, vec3(0.88, 0.94, 0.92), foam * 0.75);
	c = mix(c, vec3(0.80, 0.88, 0.94), frozen * 0.85);
	ALBEDO = c;
	ROUGHNESS = mix(0.06, 0.6, frozen);
	METALLIC = 0.0;
	SPECULAR = 0.9;
	vec3 sun_view = normalize((VIEW_MATRIX * vec4(sun_direction, 0.0)).xyz);
	float glint = pow(max(dot(reflect(-VIEW, NORMAL), sun_view), 0.0), 90.0) * (1.0 - frozen);
	vec3 glint_color = mix(vec3(1.0, 0.92, 0.75), vec3(0.6, 0.7, 1.0), night);
	EMISSION = sky_color * (0.12 + fresnel * 0.35) * (1.0 - night * 0.7) + glint_color * glint * mix(4.0, 1.5, night);
}
