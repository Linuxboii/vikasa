shader_type spatial;
// One draw call for the whole population. Per-instance data (CreatureSwarm.gd):
//   COLOR.rgb  coat colour, already shaded for energy and view mode
//   COLOR.a    head dip, (dip + 0.25) / 0.5   (feeding lowers, display raises)
//   CUSTOM.x   gait phase (radians)      CUSTOM.y  locomotion * stride
//   CUSTOM.z   rest blend (lying down)   CUSTOM.w  integer flag bits (< 2048):
//     1 selected · 2 alpha · 4 injured · 8 display · 16/32 ear · 64/128 tail
//     256/512 ridge · 1024 excited (tail wag)
// Every value fits half-float precision used by the Compatibility renderer.
render_mode cull_back, diffuse_burley, specular_schlick_ggx;

uniform float night = 0.0;
uniform float clock = 0.0;
uniform vec3 rim_tint : source_color = vec3(0.75, 0.86, 0.95);

const float BASE_Y = 0.70;
const float HIP_X = 0.84;
const float HIP_Y = 0.58;
const vec3 TAIL_ROOT = vec3(-1.11, 0.73, 0.0);
const vec3 NECK = vec3(0.86, 0.80, 0.0);

varying flat float v_region;
varying flat float v_flags;
varying float v_pulse;

vec3 rot_z(vec3 p, vec3 pivot, float a) {
	vec3 d = p - pivot;
	float c = cos(a), s = sin(a);
	return pivot + vec3(d.x * c - d.y * s, d.x * s + d.y * c, d.z);
}

vec3 rot_y(vec3 p, vec3 pivot, float a) {
	vec3 d = p - pivot;
	float c = cos(a), s = sin(a);
	return pivot + vec3(d.x * c + d.z * s, d.y, -d.x * s + d.z * c);
}

int bits(int value, int shift, int mask) { return (value >> shift) & mask; }

void vertex() {
	int part = int(UV2.x + 0.5);
	float gait = INSTANCE_CUSTOM.x;
	float loco = INSTANCE_CUSTOM.y;
	float rest = INSTANCE_CUSTOM.z;
	int flags = int(INSTANCE_CUSTOM.w + 0.5);
	float dip = COLOR.a * 0.5 - 0.25;
	float seed = float(INSTANCE_ID) * 1.618;
	bool excited = bits(flags, 10, 1) == 1;
	vec3 p = VERTEX;
	vec3 n = NORMAL;

	if (part >= 4 && part <= 7) {
		int leg = part - 4;
		float offset = (leg == 1 || leg == 2) ? 3.14159 : 0.0;
		float swing = sin(gait + offset) * 0.45 * loco;
		float hip_x = leg < 2 ? HIP_X : -HIP_X;
		vec3 hip = vec3(hip_x, HIP_Y, p.z);
		// Lying down folds the legs under the body.
		p.y = mix(p.y, HIP_Y + (p.y - HIP_Y) * 0.35, rest);
		p = rot_z(p, hip, swing);
		n = rot_z(n, vec3(0.0), swing);
	} else if (part == 3) {
		int tail_level = bits(flags, 6, 3);
		p.x = TAIL_ROOT.x + (p.x - TAIL_ROOT.x) * (0.8 + 0.2 * float(tail_level));
		float wag = excited ? sin(clock * 9.0 + seed) * 0.35 : 0.0;
		p = rot_z(p, TAIL_ROOT, sin(gait * 0.5) * 0.11 + float(bits(flags, 3, 1)) * 0.25);
		p = rot_y(p, TAIL_ROOT, wag);
	} else if (part == 1 || part == 2 || part == 8) {
		float amount = part == 2 ? 0.55 : 1.0;
		// Idle animals look around; moving animals look ahead.
		float glance = sin(clock * 0.7 + seed) * 0.32 * (1.0 - clamp(loco, 0.0, 1.0)) * (1.0 - rest);
		if (part == 8) {
			int ear_level = bits(flags, 4, 3);
			vec3 base = vec3(1.03, BASE_Y + 0.27, sign(p.z) * 0.19);
			p = base + (p - base) * (0.75 + 0.25 * float(ear_level));
			p = rot_z(p, base, sin(clock * 3.0 + seed) * 0.06);
		}
		p = rot_y(p, NECK, glance * amount);
		n = rot_y(n, vec3(0.0), glance * amount);
		p.y += dip * amount;
	} else if (part == 9) {
		int ridge = bits(flags, 8, 3);
		p.y = BASE_Y + 0.2 + (p.y - BASE_Y - 0.2) * float(ridge) * 0.5;
	} else if (part == 10) {
		p = mix(vec3(-0.19, BASE_Y + 0.3, 0.0), p, float(bits(flags, 1, 1)));
	} else if (part == 11) {
		p = mix(vec3(0.26, BASE_Y + 0.22, 0.38), p, float(bits(flags, 2, 1)));
	}
	if (part != 4 && part != 5 && part != 6 && part != 7) {
		float breath = sin(clock * 2.2 + seed) * 0.018;
		float bob = abs(sin(gait * 2.0)) * 0.05 * clamp(loco, 0.0, 1.0);
		p.y += breath + bob - 0.24 * rest;
	}
	VERTEX = p;
	NORMAL = normalize(n);
	v_region = UV2.y;
	v_flags = float(flags);
	v_pulse = 0.5 + 0.5 * sin(clock * 4.0);
}

void fragment() {
	int region = int(v_region + 0.5);
	int flags = int(v_flags + 0.5);
	vec3 coat = COLOR.rgb;
	vec3 albedo = coat;
	float rough = 0.86;
	vec3 glow = vec3(0.0);
	if (region == 1) albedo = mix(coat, vec3(0.93, 0.88, 0.78), 0.32);
	else if (region == 2) albedo = coat * 0.62;
	else if (region == 3) albedo = mix(coat.gbr, coat, 0.55) * 1.12;
	else if (region == 4) {
		albedo = vec3(0.02, 0.025, 0.02);
		rough = 0.18;
		// Tapetum lucidum: animal eyes return light at night.
		float facing = clamp(dot(NORMAL, VIEW), 0.0, 1.0);
		glow = vec3(0.95, 0.82, 0.35) * night * (0.6 + 2.6 * facing * facing);
	}
	else if (region == 5) albedo = vec3(0.07, 0.06, 0.05);
	else if (region == 6) { albedo = vec3(0.86, 0.66, 0.30); glow = vec3(1.0, 0.68, 0.22) * (0.08 + 0.9 * night); rough = 0.35; }
	else if (region == 7) albedo = vec3(0.62, 0.22, 0.18);
	else if (region == 8) albedo = coat * 0.72 + 0.06;
	float rim = pow(1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0), 3.0);
	glow += rim_tint * rim * 0.16 * (1.0 - 0.5 * night);
	if ((flags & 1) == 1) glow += vec3(1.0, 0.82, 0.42) * rim * (0.7 + 0.5 * v_pulse);
	ALBEDO = albedo;
	ROUGHNESS = rough;
	SPECULAR = 0.35;
	EMISSION = glow;
}
