import os

try:
    from PIL import Image, ImageOps, ImageSequence
except Exception:
    Image = None
    ImageSequence = None
    ImageOps = None


def convert_image_to_pdf(
    image_path: str,
    output_dir: str | None = None,
    output_path: str | None = None,
    overwrite: bool = False,
) -> str:
    if Image is None:
        raise RuntimeError("Pillow is required for image to PDF conversion")
    if not os.path.isfile(image_path):
        raise FileNotFoundError(image_path)

    # --- Resolve output path ---
    if output_path:
        out_pdf = output_path
        out_dir = os.path.dirname(output_path) or os.path.dirname(image_path)
    else:
        out_dir = output_dir or os.path.dirname(image_path)
        base = os.path.splitext(os.path.basename(image_path))[0]
        candidate = os.path.join(out_dir, f"{base}_converted.pdf")

        if overwrite or not os.path.exists(candidate):
            out_pdf = candidate
        else:
            idx = 1
            while True:
                alt = os.path.join(out_dir, f"{base}_converted({idx}).pdf")
                if not os.path.exists(alt):
                    out_pdf = alt
                    break
                idx += 1

    os.makedirs(out_dir, exist_ok=True)

    # --- Frame preparation helper ---
    def _prepare_frame(frame):
        try:
            frame = ImageOps.exif_transpose(frame)
        except Exception:
            pass
        if frame.mode not in ("RGB", "L"):
            frame = frame.convert("RGB")
        return frame

    # --- Read frames ---
    with Image.open(image_path) as image:
        frames = []
        try:
            for frame in ImageSequence.Iterator(image):
                frames.append(_prepare_frame(frame.copy()))
        except Exception:
            # Fallback: single frame
            frames = [_prepare_frame(image.copy())]

        # --- Save PDF ---
        if len(frames) == 1:
            frames[0].save(out_pdf, format="PDF", resolution=300.0)
        else:
            frames[0].save(
                out_pdf,
                format="PDF",
                resolution=300.0,
                save_all=True,
                append_images=frames[1:],
            )

        # Explicit close (kept, though unnecessary)
        for f in frames:
            try:
                f.close()
            except Exception:
                pass

    return out_pdf
