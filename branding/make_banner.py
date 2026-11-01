"""ClipCityVice YouTube banner, 2560x1440, same Vice City synthwave look as the
avatar and the shorts' own on-brand purple. YouTube crops this per device -
only a centered 1546x423 "safe area" is guaranteed visible everywhere, so the
wordmark/tagline stay inside that box; the sun/horizon can bleed off-canvas.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 2560, 1440
CX = W // 2
SAFE_W, SAFE_H = 1546, 423
SAFE_TOP = (H - SAFE_H) // 2       # 508
SAFE_BOTTOM = SAFE_TOP + SAFE_H     # 931

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def vgrad(draw, stops, w, h):
    for y in range(h):
        t = y / (h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                lt = (t - p0) / (p1 - p0) if p1 > p0 else 0
                draw.line([(0, y), (w, y)], fill=lerp(c0, c1, lt))
                break

img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)
vgrad(draw, [
    (0.0, (255, 45, 120)),
    (0.45, (139, 47, 201)),
    (1.0, (24, 11, 61)),
], W, H)

# retro sun, mostly above the safe area so it reads on ultrawide/TV without
# fighting the wordmark; its lower rim still bleeds into frame on all crops
sun_cx, sun_r, sun_cy = CX, 300, 170
core, mid, edge = (255, 240, 190), (255, 130, 70), (255, 45, 140)
for i in range(140, 0, -1):
    t = i / 140
    r = int(sun_r * t)
    color = lerp(mid, edge, (t - 0.55) / 0.45) if t > 0.55 else lerp(core, mid, t / 0.55)
    draw.ellipse([sun_cx - r, sun_cy - r, sun_cx + r, sun_cy + r], fill=color)

overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
odraw = ImageDraw.Draw(overlay)
y = sun_cy - 10
bar_h, gap = 10, 12
while y < sun_cy + sun_r + 20:
    odraw.rectangle([sun_cx - sun_r - 20, y, sun_cx + sun_r + 20, y + bar_h], fill=(24, 11, 61, 235))
    y += bar_h + gap
    bar_h += 1
    gap += 2
img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
draw = ImageDraw.Draw(img)

# cyan horizon line, sitting just above the safe area
horizon_y = SAFE_TOP - 40
draw.line([(0, horizon_y), (W, horizon_y)], fill=(0, 230, 255), width=5)
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(glow)
gdraw.line([(0, horizon_y), (W, horizon_y)], fill=(0, 230, 255, 150), width=22)
glow = glow.filter(ImageFilter.GaussianBlur(16))
img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
draw = ImageDraw.Draw(img)

# ground band below the horizon
draw.rectangle([0, horizon_y + 3, W, H], fill=(16, 8, 36))
# redraw a soft reflection of the sun on the "ground" for depth
refl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
rdraw = ImageDraw.Draw(refl)
rdraw.ellipse([sun_cx - sun_r, horizon_y, sun_cx + sun_r, horizon_y + 90], fill=(255, 90, 160, 70))
refl = refl.filter(ImageFilter.GaussianBlur(30))
img = Image.alpha_composite(img.convert("RGBA"), refl).convert("RGB")
draw = ImageDraw.Draw(img)

# --- wordmark + tagline, centered inside the 1546x423 safe area -----------
brand_purple = (123, 104, 238)   # the same 7B68EE used as hook-text color in the shorts
title_font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 150)
tagline_font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 46)
handle_font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 34)

def draw_outlined(draw, xy, text, font, fill, outline, outline_w, anchor):
    x, y = xy
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((x + dx, y + dy), text, font=font, fill=outline, anchor=anchor)
    draw.text((x, y), text, font=font, fill=fill, anchor=anchor)

title = "CLIPCITYVICE"
tagline = "GAME BREAKDOWNS  \u00b7  THEORIES  \u00b7  CULTURE"
handle = "@clipcityvice  \u2014  new shorts daily"

safe_mid_y = (SAFE_TOP + SAFE_BOTTOM) // 2
draw_outlined(draw, (CX, safe_mid_y - 60), title, title_font, brand_purple, (0, 0, 0), 8, "mm")
draw_outlined(draw, (CX, safe_mid_y + 60), tagline, tagline_font, (255, 255, 255), (0, 0, 0), 4, "mm")
draw_outlined(draw, (CX, safe_mid_y + 125), handle, handle_font, (210, 210, 230), (0, 0, 0), 3, "mm")

out = "clipcityvice_banner_2560x1440.png"
img.save(out)
print("saved", out)

# a guide copy with the safe-area box drawn on, so we can check framing
guide = img.copy()
gd = ImageDraw.Draw(guide)
gd.rectangle([CX - SAFE_W // 2, SAFE_TOP, CX + SAFE_W // 2, SAFE_BOTTOM], outline=(0, 255, 0), width=4)
guide.save("clipcityvice_banner_safearea_guide.png")
print("saved guide")
