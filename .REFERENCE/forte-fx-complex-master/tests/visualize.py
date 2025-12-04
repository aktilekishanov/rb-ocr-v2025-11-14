import os
import io
import re
import shutil
from collections import defaultdict
from typing import Any, Dict

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def sanitize_filename(text: str) -> str:
    return re.sub(r"[^\w\-_.]", "_", text)


def get_color_from_confidence(conf: Any) -> str:
    """
    Map confidence to color.
    - None or invalid -> gray
    """
    if conf is None:
        return "gray"

    try:
        c = float(conf)
    except (TypeError, ValueError):
        return "gray"

    if c >= 0.8:
        return "green"
    elif c > 0.5:
        return "yellow"
    else:
        return "red"


def get_font(font_size: int = 50):
    path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    return ImageFont.truetype(path, font_size)


def load_image(image_data):
    """Convert bytes, ndarray, or PIL.Image to PIL.Image"""
    if isinstance(image_data, bytes):
        return Image.open(io.BytesIO(image_data)).convert("RGB")
    elif isinstance(image_data, np.ndarray):
        return Image.fromarray(image_data)
    elif isinstance(image_data, Image.Image):
        return image_data.copy()
    else:
        raise TypeError(f"Unsupported image type: {type(image_data)}")


def visualize_bboxes_per_field(fields_json: dict, images_dict: Dict[str, Any], output_dir: str):
    # 🔄 Always recreate the output folder
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"[debug] images_dict keys: {list(images_dict.keys())}")

    font = get_font(50)

    # Group occurrences by (field, filename, page)
    grouped = defaultdict(list)

    for field_idx, field in enumerate(fields_json.get("fields", [])):
        field_name = field.get("name", f"field_{field_idx}")
        field_value = field.get("value", "")
        confidence = field.get("confidence", None)

        # Safe color and safe confidence display
        color = get_color_from_confidence(confidence)
        if isinstance(confidence, (int, float)):
            conf_display = f"{float(confidence):.2f}"
        else:
            conf_display = "n/a"

        label_text = f"{field_name}: {field_value} ({conf_display})"

        for ref in field.get("references", []):
            filename = ref.get("filename")
            for occ in ref.get("occurrences", []):
                page = occ.get("page")
                bbox = occ.get("bbox")
                if not bbox:
                    continue
                key = (field_name, filename, page)
                grouped[key].append((bbox, color, label_text))

    # Also index by basename for robustness
    images_by_basename = {os.path.basename(k): v for k, v in images_dict.items()}
    print(f"[debug] images_by_basename keys: {list(images_by_basename.keys())}")

    # Render each field's boxes per page
    for (field_name, filename, page), boxes in grouped.items():
        if not filename:
            continue

        img_data = images_dict.get(filename)
        if img_data is None:
            # Try by basename (in case paths got stripped)
            basename = os.path.basename(filename)
            img_data = images_by_basename.get(basename)

        if img_data is None:
            print(
                f"[warning] Image '{filename}' not found in images_dict "
                f"(original: '{filename}')"
            )
            continue

        image = load_image(img_data)
        draw = ImageDraw.Draw(image)

        for bbox, color, label_text in boxes:
            draw.rectangle(bbox, outline=color, width=4)
            # offset label slightly above bbox
            text_x = bbox[0]
            text_y = max(0, bbox[1] - 50)
            draw.text((text_x, text_y), label_text, fill="black", font=font)

        safe_field_name = sanitize_filename(field_name)
        out_name = f"{safe_field_name}_page{page}.png"
        out_path = os.path.join(output_dir, out_name)
        image.save(out_path)

    print(f"✅ Saved visualizations to: {output_dir}")
