import argparse
import os
from PIL import Image, ImageDraw, ImageFont

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative-prompt", default="")
    parser.add_argument("--model", default="stub-model")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--cfg", type=float, default=7.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print(f"[worker] starting stub T2I render")
    print(f"[worker] prompt={args.prompt}")
    print(f"[worker] model={args.model}, size={args.width}x{args.height}, steps={args.steps}, cfg={args.cfg}, seed={args.seed}")

    image = Image.new("RGB", (args.width, args.height), color=(28, 28, 34))
    draw = ImageDraw.Draw(image)

    title = "SpellVision Sprint 1"
    prompt_text = f"Prompt: {args.prompt}"
    neg_text = f"Negative: {args.negative_prompt}"
    model_text = f"Model: {args.model}"
    meta_text = f"{args.width}x{args.height} | steps={args.steps} | cfg={args.cfg} | seed={args.seed}"

    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    y = 40
    for line in [title, "", prompt_text, neg_text, model_text, meta_text]:
        draw.text((40, y), line, fill=(220, 220, 235), font=font)
        y += 30

    # decorative shapes
    draw.rectangle((30, 30, args.width - 30, args.height - 30), outline=(90, 140, 255), width=4)
    draw.ellipse((args.width - 260, 60, args.width - 60, 260), outline=(255, 140, 90), width=6)
    draw.rectangle((80, args.height - 220, 380, args.height - 80), outline=(90, 255, 170), width=6)

    image.save(args.output, "PNG")
    print(f"[worker] wrote {args.output}")

if __name__ == "__main__":
    main()