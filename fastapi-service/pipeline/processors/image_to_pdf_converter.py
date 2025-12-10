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
    # Determine output path
    if output_path:
        out_dir = os.path.dirname(output_path) or os.path.dirname(image_path)
        os.makedirs(out_dir, exist_ok=True)
        out_pdf = output_path
    else:
        out_dir = output_dir if output_dir else os.path.dirname(image_path)
        os.makedirs(out_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(image_path))[0]
        candidate = os.path.join(out_dir, f"{base}_converted.pdf")
        if overwrite:
            out_pdf = candidate
        else:
            if not os.path.exists(candidate):
                out_pdf = candidate
            else:
                idx = 1
                while True:
                    candidate_i = os.path.join(out_dir, f"{base}_converted({idx}).pdf")
                    if not os.path.exists(candidate_i):
                        out_pdf = candidate_i
                        break
                    idx += 1
    with Image.open(image_path) as image:
        frames = []
        try:
            for frame in ImageSequence.Iterator(image):
                frame_copy = frame.copy()
                try:
                    frame_copy = ImageOps.exif_transpose(frame_copy)
                except Exception:
                    pass
                if frame_copy.mode not in ("RGB", "L"):
                    frame_copy = frame_copy.convert("RGB")
                frames.append(frame_copy)
        except Exception:
            frame_copy = image.copy()
            try:
                frame_copy = ImageOps.exif_transpose(frame_copy)
            except Exception:
                pass
            if frame_copy.mode not in ("RGB", "L"):
                frame_copy = frame_copy.convert("RGB")
            frames = [frame_copy]
        if len(frames) == 1:
            frames[0].save(out_pdf, format="PDF", resolution=300.0)
        else:
            first, rest = frames[0], frames[1:]
            first.save(
                out_pdf,
                format="PDF",
                resolution=300.0,
                save_all=True,
                append_images=rest,
            )
        for frame in frames:
            try:
                frame.close()
            except Exception:
                pass
    return out_pdf
