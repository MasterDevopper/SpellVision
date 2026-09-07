"""Fraction of differing pixels between two captures. Used to prove a material change is visible."""
import sys
from PIL import Image, ImageChops

a = Image.open(sys.argv[1]).convert("RGB")
b = Image.open(sys.argv[2]).convert("RGB")
if a.size != b.size:
    print(f"size mismatch {a.size} vs {b.size}")
    sys.exit(2)
diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 8 else 0)
changed = sum(1 for v in diff.getdata() if v)
print(f"{changed / (diff.width * diff.height):.4f}")
