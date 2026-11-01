"""Generate a ClipCityVice profile-picture icon: a synthwave/Vice-City sunset mark.
Square 1024x1024 master (works for YouTube/TikTok/Instagram/Facebook, all of
which crop avatars to a circle), plus a circular-cropped preview so we can see
how it actually reads once platforms mask it.
"""
import math
from PIL import Image, ImageDraw, ImageFilter

W = H = 1024
CX, CY = W // 2, 470   # sun center, slightly above true center so the palm
                        # silhouettes have room to read at the bottom

def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def vertical_gradient(draw, stops, w, h):
    # stops: list of (position 0..1, (r,g,b))
    for y in range(h):
        t = y / (h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= t <= p1:
                local_t = (t - p0) / (p1 - p0) if p1 > p0 else 0
                color = lerp(c0, c1, local_t)
                draw.line([(0, y), (w, y)], fill=color)
                break

img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)

# vice-city sunset backdrop: hot magenta -> violet -> deep indigo
vertical_gradient(draw, [
    (0.0, (255, 45, 120)),
    (0.45, (139, 47, 201)),
    (1.0, (24, 11, 61)),
], W, H)

# --- retro sun: radial-ish blend via concentric rings ---------------------
sun_r = 250
steps = 140
core = (255, 240, 190)
mid = (255, 130, 70)
edge = (255, 45, 140)
for i in range(steps, 0, -1):
    t = i / steps
    r = int(sun_r * t)
    if t > 0.55:
        local = (t - 0.55) / 0.45
        color = lerp(mid, edge, local)
    else:
        local = t / 0.55
        color = lerp(core, mid, local)
    bbox = [CX - r, CY - r, CX + r, CY + r]
    draw.ellipse(bbox, fill=color)

# soft glow around the sun
glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
gdraw = ImageDraw.Draw(glow)
gdraw.ellipse([CX - sun_r - 60, CY - sun_r - 60, CX + sun_r + 60, CY + sun_r + 60],
              fill=(255, 150, 90, 90))
glow = glow.filter(ImageFilter.GaussianBlur(70))
img.paste(Image.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, 0)), glow).convert("RGB"),
          (0, 0), glow.split()[3])

# redraw sun on top of the glow so it stays crisp
for i in range(steps, 0, -1):
    t = i / steps
    r = int(sun_r * t)
    if t > 0.55:
        local = (t - 0.55) / 0.45
        color = lerp(mid, edge, local)
    else:
        local = t / 0.55
        color = lerp(core, mid, local)
    bbox = [CX - r, CY - r, CX + r, CY + r]
    draw.ellipse(bbox, fill=color)

# --- synthwave scanlines cutting across the lower sun ----------------------
overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
odraw = ImageDraw.Draw(overlay)
y = CY - 10
bar_h = 10
gap = 14
while y < CY + sun_r + 40:
    alpha = 235
    odraw.rectangle([CX - sun_r - 20, y, CX + sun_r + 20, y + bar_h],
                     fill=(24, 11, 61, alpha))
    y += bar_h + gap
    bar_h += 2
    gap += 3
img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
draw = ImageDraw.Draw(img)

# --- horizon glow line ------------------------------------------------------
horizon_y = CY + sun_r - 25
draw.line([(0, horizon_y), (W, horizon_y)], fill=(0, 230, 255), width=6)
glow2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
g2draw = ImageDraw.Draw(glow2)
g2draw.line([(0, horizon_y), (W, horizon_y)], fill=(0, 230, 255, 160), width=20)
glow2 = glow2.filter(ImageFilter.GaussianBlur(14))
img = Image.alpha_composite(img.convert("RGBA"), glow2).convert("RGB")
draw = ImageDraw.Draw(img)

# ground band - kept clean/solid so the mark stays legible at avatar sizes
draw.rectangle([0, horizon_y + 3, W, H], fill=(16, 8, 36))

# --- hero silhouette standing against the sun, GTA-cover-art style ---------
# pure black, bold simple shapes only - no interior detail, so it still
# reads as a clean mark once shrunk to a tiny feed avatar
SIL = (6, 4, 10)

# flared long coat / torso (wide shoulders, flares out toward the hem)
draw.polygon([
    (432, 330), (592, 330),   # shoulders
    (636, 742), (388, 742),   # coat hem, flared
], fill=SIL)

# popped collar for a bit of swagger
draw.polygon([(472, 330), (432, 330), (452, 286)], fill=SIL)
draw.polygon([(552, 330), (592, 330), (572, 286)], fill=SIL)

# legs, standing apart in a confident stance
draw.polygon([(404, 742), (500, 742), (472, 962), (402, 962)], fill=SIL)
draw.polygon([(524, 742), (620, 742), (622, 962), (552, 962)], fill=SIL)

# left arm, hanging relaxed at the side
draw.polygon([(432, 332), (462, 332), (448, 566), (416, 566)], fill=SIL)

# right arm, bent up toward the face (classic sunglasses-adjust pose)
draw.line([(592, 335), (646, 272), (566, 232)], fill=SIL, width=46, joint="curve")
draw.ellipse([614, 250, 662, 298], fill=SIL)  # elbow cap, keeps the bend solid

# head
draw.ellipse([460, 196, 564, 300], fill=SIL)

out_path = "clipcityvice_avatar_silhouette_1024.png"
img.save(out_path)
print("saved", out_path)

# circular preview, as platforms will actually crop it
mask = Image.new("L", (W, H), 0)
mdraw = ImageDraw.Draw(mask)
mdraw.ellipse([0, 0, W, H], fill=255)
circ = Image.new("RGBA", (W, H), (0, 0, 0, 0))
circ.paste(img, (0, 0), mask)
circ.save("clipcityvice_avatar_silhouette_circle_preview.png")
print("saved circle preview")
