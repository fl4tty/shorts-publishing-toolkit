"""Same Vice City cinematic color-grade pass as grade_avatar.py, applied to
the second source photo (already square, 300x300 - upscaled to 1024x1024).
"""
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw

SRC = "source_photo2.jpg"  # a second source photo to grade
OUT = "avatar2_graded_1024.png"
OUT_CIRCLE = "avatar2_graded_circle_preview.png"

im = Image.open(SRC).convert("RGB")
side = min(im.size)
im = im.crop((0, 0, side, side)).resize((1024, 1024), Image.LANCZOS)

arr = np.asarray(im).astype(np.float32) / 255.0

# --- recolor the background toward Vice City magenta/purple/pink.
# Unlike photo 1's neutral-gray concrete, the jacket here sits in almost the
# same value/saturation range as the walls - there's no clean color-based
# split. So: protect the person with a rough body-shaped region instead, and
# let the recolor apply to everything else regardless of its own brightness
# (including the bright ceiling-light streak, which otherwise stays an
# unrelated leftover green/teal against the new magenta scheme).
val = arr.max(axis=-1)

yy_grid, xx_grid = np.mgrid[0:1024, 0:1024].astype(np.float32)
person_oval = ((((xx_grid - 560) / 195) ** 2 + ((yy_grid - 500) / 485) ** 2) <= 1.0).astype(np.float32)
person_oval = np.asarray(Image.fromarray((person_oval * 255).astype(np.uint8))
                          .filter(ImageFilter.GaussianBlur(18))).astype(np.float32) / 255.0

low_gate = np.clip((val - 0.03) / 0.05, 0, 1)   # exclude only crushed-black noise
bg_mask = low_gate * (1 - person_oval)

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

strength = 0.65
arr = arr * (1 - bg_mask[..., None] * strength) + vice_color * (bg_mask[..., None] * strength)
arr = np.clip(arr, 0, 1)

lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2])
shadow_w = np.clip(1.0 - lum / 0.55, 0, 1) ** 1.2
highlight_w = np.clip((lum - 0.45) / 0.55, 0, 1) ** 1.2

teal = np.array([-0.12, 0.02, 0.18])
warm = np.array([0.18, 0.07, -0.13])
arr = arr + shadow_w[..., None] * teal + highlight_w[..., None] * warm
arr = np.clip(arr, 0, 1)

overall_warm = np.array([0.035, 0.012, -0.025])
arr = np.clip(arr + overall_warm, 0, 1)

im = Image.fromarray((arr * 255).astype(np.uint8))
im = ImageEnhance.Color(im).enhance(1.4)
im = ImageEnhance.Contrast(im).enhance(1.08)
im = ImageEnhance.Brightness(im).enhance(1.22)

# bloom - kept tight and only on the very brightest pixels, since the white
# jacket sleeves already sit near pure white and would otherwise balloon
# into a big washed-out glow
arr = np.asarray(im).astype(np.float32) / 255.0
bright = np.clip((arr - 0.88) / 0.12, 0, 1)
bright_im = Image.fromarray((bright * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(9))
bright_arr = np.asarray(bright_im).astype(np.float32) / 255.0
arr = 1 - (1 - arr) * (1 - bright_arr * 0.18)
arr = np.clip(arr, 0, 1)

yy, xx = np.mgrid[0:1024, 0:1024].astype(np.float32)
d = np.sqrt((xx - 512) ** 2 + (yy - 512) ** 2) / (512 * 1.15)
vig = 1.0 - np.clip(d - 0.25, 0, 1) * 0.7
arr = arr * vig[..., None]

rng = np.random.default_rng(7)
grain = rng.normal(0, 0.018, arr.shape[:2])
arr = arr + grain[..., None]
arr = np.clip(arr, 0, 1)

im = Image.fromarray((arr * 255).astype(np.uint8))
im.save(OUT)
print("saved", OUT)

mask = Image.new("L", (1024, 1024), 0)
ImageDraw.Draw(mask).ellipse([0, 0, 1024, 1024], fill=255)
circ = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
circ.paste(im, (0, 0), mask)
circ.save(OUT_CIRCLE)
print("saved", OUT_CIRCLE)
