"""Cinematic color-grade pass to push a GTA-screenshot toward the GTA 6 trailer
look (warm/hazy highlights, teal-leaning shadows, bloom, grain, vignette),
cropped square for use as a channel avatar. This is a color-grade/compositing
pass, not true AI re-rendering - there's no model here that can redraw the
scene in a different engine's art style.
"""
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

SRC = "source_photo.webp"  # a GTA screenshot or similar source photo to grade
OUT = "avatar_photo_graded_1024.png"
OUT_CIRCLE = "avatar_photo_graded_circle_preview.png"

im = Image.open(SRC).convert("RGB")
w, h = im.size

# square crop centered on the character (slightly left-of-center in source)
side = h
cx = 550
x0 = max(0, min(w - side, cx - side // 2))
im = im.crop((x0, 0, x0 + side, side)).resize((1024, 1024), Image.LANCZOS)

arr = np.asarray(im).astype(np.float32) / 255.0

# --- recolor the (mostly neutral-gray concrete) background toward a Vice
# City magenta/purple/pink palette, while mostly leaving the person alone.
# No segmentation model here, so this leans on a color heuristic instead:
# the concrete is low-saturation gray, the subject is skin tone + dark navy
# clothing (both either more saturated or much darker), so a "how gray is
# this pixel" mask does a decent job of targeting the walls/ceiling/floor
# without a real person-vs-background mask.
mx = arr.max(axis=-1)
mn = arr.min(axis=-1)
sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-5), 0.0)
val = mx

gray_mask = np.clip(1.0 - sat * 3.2, 0, 1) ** 1.5           # low-saturation pixels only
dark_gate = np.clip((val - 0.32) / 0.16, 0, 1)               # exclude the (darker) navy clothing/car
bright_gate = np.clip((1.0 - val) / 0.08 + 1.0, 0, 1)        # don't flatten pure white blowout
bg_mask = gray_mask * dark_gate * np.clip(bright_gate, 0, 1)

# dark concrete -> deep indigo, mid concrete -> hot magenta/violet,
# bright concrete (the backlit opening) -> warm sunset pink
stops = [
    (0.00, np.array([0.18, 0.08, 0.34])),
    (0.35, np.array([0.70, 0.28, 0.68])),
    (0.65, np.array([0.95, 0.35, 0.72])),
    (1.00, np.array([1.00, 0.68, 0.58])),
]
vice_color = np.zeros_like(arr)
for i in range(len(stops) - 1):
    p0, c0 = stops[i]
    p1, c1 = stops[i + 1]
    seg = np.clip((val - p0) / (p1 - p0), 0, 1)
    seg_active = (val >= p0) & (val <= p1) if i < len(stops) - 2 else (val >= p0)
    blended = c0[None, None, :] + (c1 - c0)[None, None, :] * seg[..., None]
    vice_color = np.where(seg_active[..., None], blended, vice_color)

strength = 0.7
arr = arr * (1 - bg_mask[..., None] * strength) + vice_color * (bg_mask[..., None] * strength)
arr = np.clip(arr, 0, 1)

# luminance, used to steer the teal-shadow / warm-highlight split-tone
lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])
shadow_w = np.clip(1.0 - lum / 0.55, 0, 1) ** 1.2
highlight_w = np.clip((lum - 0.45) / 0.55, 0, 1) ** 1.2

teal = np.array([-0.14, 0.03, 0.20])
warm = np.array([0.22, 0.09, -0.16])

arr = arr + shadow_w[..., None] * teal + highlight_w[..., None] * warm
arr = np.clip(arr, 0, 1)

# a flat overall warm cast on top - this scene has almost no natural
# highlight/shadow separation (even garage lighting) for the split-tone
# above to grab onto, so most of the "trailer" feel has to come from here
overall_warm = np.array([0.045, 0.015, -0.03])
arr = np.clip(arr + overall_warm, 0, 1)

im = Image.fromarray((arr * 255).astype(np.uint8))

# saturation + contrast push - GTA6 trailers read noticeably punchier than a
# default screenshot
im = ImageEnhance.Color(im).enhance(1.6)
im = ImageEnhance.Contrast(im).enhance(1.22)
im = ImageEnhance.Brightness(im).enhance(1.04)

# bloom: blurred bright-pass, screen-blended back on top
arr = np.asarray(im).astype(np.float32) / 255.0
bright = np.clip((arr - 0.6) / 0.4, 0, 1)
bright_im = Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(20))
bright_arr = np.asarray(bright_im).astype(np.float32) / 255.0
arr = 1 - (1 - arr) * (1 - bright_arr * 0.4)
arr = np.clip(arr, 0, 1)

# vignette
yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)
d = np.sqrt((xx - 512) ** 2 + (yy - 512) ** 2) / (512 * 1.15)
vig = 1.0 - np.clip(d - 0.25, 0, 1) * 0.75
arr = arr * vig[..., None]

# fine film grain
rng = np.random.default_rng(7)
grain = rng.normal(0, 0.02, arr.shape[:2])
arr = arr + grain[..., None]
arr = np.clip(arr, 0, 1)

im = Image.fromarray((arr * 255).astype(np.uint8))
im.save(OUT)
print("saved", OUT)

mask = Image.new("L", (1024, 1024), 0)
from PIL import ImageDraw
ImageDraw.Draw(mask).ellipse([0, 0, 1024, 1024], fill=255)
circ = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
circ.paste(im, (0, 0), mask)
circ.save(OUT_CIRCLE)
print("saved", OUT_CIRCLE)
