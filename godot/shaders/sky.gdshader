shader_type sky;
// Stylised physically-inspired sky: gradient, sun/moon discs, procedural stars,
// drifting cloud bands and storm/lightning response. No textures, no TIME
// (the clock arrives as a uniform), and ambient light comes from a colour, so
// the Compatibility renderer never rebuilds a radiance map for it.

uniform vec3 sun_direction = vec3(0.3, 0.6, 0.2);
uniform float night : hint_range(0.0, 1.0) = 0.0;
uniform float golden : hint_range(0.0, 1.0) = 0.0;
uniform float storm : hint_range(0.0, 1.0) = 0.0;
uniform float flash : hint_range(0.0, 1.0) = 0.0;
uniform float clock = 0.0;
uniform vec3 tint : source_color = vec3(1.0);

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; }
	return v;
}

void sky() {
	vec3 d = normalize(EYEDIR);
	vec3 sun = normalize(sun_direction);
	float up = clamp(d.y, -1.0, 1.0);
	float h = max(up, 0.0);
	vec3 zenith = mix(vec3(0.20, 0.42, 0.72), vec3(0.015, 0.025, 0.07), night);
	vec3 horizon = mix(vec3(0.66, 0.80, 0.90), vec3(0.06, 0.09, 0.17), night);
	horizon = mix(horizon, vec3(1.0, 0.56, 0.30), golden * 0.85);
	zenith = mix(zenith, vec3(0.28, 0.30, 0.52), golden * 0.45);
	vec3 col = mix(horizon, zenith, pow(h, 0.45));
	float toward_sun = max(dot(d, sun), 0.0);
	col += vec3(1.0, 0.55, 0.25) * pow(toward_sun, 6.0) * golden * (1.0 - h) * 0.9;
	col += vec3(1.0, 0.85, 0.6) * pow(toward_sun, 64.0) * (1.0 - night) * 0.6;
	// Sun and moon discs are HDR so the glow pass blooms them.
	float sun_disc = smoothstep(0.9990, 0.9996, dot(d, sun));
	col += vec3(18.0, 14.0, 9.0) * sun_disc * (1.0 - night) * (1.0 - storm);
	vec3 moon = -sun;
	float moon_dot = dot(d, moon);
	float moon_disc = smoothstep(0.9992, 0.9996, moon_dot);
	float crater = noise(d.xz * 900.0) * 0.25;
	col += vec3(2.4, 2.5, 2.8) * (moon_disc - crater * moon_disc) * night * (1.0 - storm);
	col += vec3(0.25, 0.32, 0.5) * pow(max(moon_dot, 0.0), 40.0) * night * 0.6;
	// Stars: sparse hashed cells, twinkling, hidden by cloud and storm.
	vec2 grid = d.xz / (abs(d.y) + 0.35) * 160.0;
	vec2 cell = floor(grid);
	float star = step(0.9965, hash(cell));
	float twinkle = 0.55 + 0.45 * sin(clock * 3.0 + hash(cell + 7.0) * 60.0);
	float sparkle = (1.0 - smoothstep(0.0, 0.42, length(fract(grid) - 0.5)));
	col += vec3(0.9, 0.95, 1.0) * star * sparkle * twinkle * night * smoothstep(0.02, 0.25, up) * 2.2;
	// Milky band.
	float band = exp(-pow(dot(d, normalize(vec3(0.6, 0.3, -0.75))) * 3.2, 2.0));
	col += vec3(0.28, 0.24, 0.38) * band * fbm(d.xz * 6.0) * night * h * 0.7;
	// Clouds.
	vec2 cuv = d.xz / (up + 0.18) * 1.6 + vec2(clock * 0.012, clock * 0.004);
	float cover = mix(0.55, 0.25, storm);
	float c = smoothstep(cover, cover + 0.35, fbm(cuv));
	vec3 cloud_lit = mix(vec3(1.0, 0.97, 0.94), vec3(1.0, 0.62, 0.42), golden);
	cloud_lit = mix(cloud_lit, vec3(0.10, 0.12, 0.18), night);
	cloud_lit = mix(cloud_lit, vec3(0.24, 0.27, 0.32), storm);
	col = mix(col, cloud_lit, c * smoothstep(0.0, 0.15, up) * 0.85);
	col = mix(col, vec3(0.16, 0.19, 0.24) * (1.0 - night * 0.6), storm * 0.65);
	// Below the horizon: dark haze the floating biome hangs over.
	col = mix(col, mix(vec3(0.20, 0.27, 0.30), vec3(0.03, 0.05, 0.08), night), (1.0 - smoothstep(-0.25, 0.0, up)));
	col += vec3(0.75, 0.82, 1.0) * flash * 2.5;
	COLOR = col * tint;
}
