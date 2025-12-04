import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed

import numpy as np
import pytesseract
from pytesseract import Output
import cv2
from collections import defaultdict
from typing import Dict, Tuple
from src.common.logger.logger_config import get_logger
import re
from typing import Dict

logger = get_logger("OCR")


class OCR:
    def __init__(self, model="tesseract"):
        """
        Initialize OCR engine with Tesseract backend.
        """
        self.model = model.lower()
        self.lang = 'eng+kaz+rus'
        logger.info(f"OCR initialized with model: {self.model}, language: {self.lang}")

    def run_ocr_with_indexes_bytes(self, image_bytes: bytes, scale_divisor: float = 1.0) -> Tuple[
        list[dict], dict[int, list[float]]]:
        """
        Run Tesseract OCR on an image and return:
        - a list of line-level OCR results with index, text, and confidence
        - a mapping from index → scaled bounding box coordinates

        :param image_bytes: Image in bytes format
        :param scale_divisor: Factor to divide all coordinates by (e.g., for DPI normalization)
        :return: (indexed_output, bbox_map)
        """
        try:
            # Decode image from bytes using OpenCV
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Failed to decode image from bytes")

            # Run OCR with Tesseract, return word-level data
            data = pytesseract.image_to_data(image, output_type=Output.DICT, lang=self.lang)
            lines = defaultdict(list)
            n = len(data['text'])

            # Group words into lines
            for i in range(n):
                text = data['text'][i].strip()
                if text:
                    conf_value = data['conf'][i]
                    if isinstance(conf_value, str):
                        conf = int(conf_value) if conf_value.isdigit() else -1
                    elif isinstance(conf_value, (int, float)):
                        conf = int(conf_value)
                    else:
                        conf = -1

                    key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
                    lines[key].append({
                        "text": text,
                        "left": data['left'][i],
                        "top": data['top'][i],
                        "width": data['width'][i],
                        "height": data['height'][i],
                        "conf": conf
                    })

            indexed_output = []
            bbox_map = {}
            index = 0

            for key, words in lines.items():
                line_text = " ".join(w["text"] for w in words)
                x1 = min(w["left"] for w in words)
                y1 = min(w["top"] for w in words)
                x2 = max(w["left"] + w["width"] for w in words)
                y2 = max(w["top"] + w["height"] for w in words)

                # Scale coordinates
                x1 /= scale_divisor
                y1 /= scale_divisor
                x2 /= scale_divisor
                y2 /= scale_divisor

                conf_scores = [w["conf"] for w in words if w["conf"] >= 0]
                avg_conf = sum(conf_scores) / len(conf_scores) if conf_scores else -1
                avg_conf /= 100  # Normalize to 0–1

                indexed_output.append({
                    "index": index,
                    "text": line_text,
                    "confidence": round(avg_conf, 2)
                })

                bbox_map[index] = [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]
                index += 1

            return indexed_output, bbox_map

        except Exception as e:
            logger.error(f"run_ocr_with_indexes_bytes() failed: {e}")
            return [], {}

    def run_ocr_on_dict(
            self,
            image_dict: Dict[str, bytes],
            scale_divisor: float = 1.0,
            workers: int | None = None,
    ) -> Dict[str, Dict[str, object]]:
        """
        Parallel OCR over PNG images in `image_dict`.
        """
        # (Optional but recommended) Avoid oversubscription when running many Tesseracts in parallel.
        os.environ.setdefault("OMP_THREAD_LIMIT", "1")
        # If OpenCV starts multiple threads for decode, you can also cap it:
        try:
            import cv2 as _cv2
            _cv2.setNumThreads(1)
        except Exception:
            pass

        files = [name for name in image_dict if name.lower().endswith(".png")]
        if not files:
            return {}

        # How many threads to spawn
        if workers is None:
            workers = 12

        logger.info(f"Running OCR on {len(files)} PNG files with {workers} workers")

        def _one(name: str) -> tuple[str, Dict[str, object]]:
            try:
                indexed, bbox_map = self.run_ocr_with_indexes_bytes(image_dict[name], scale_divisor)
                match = re.search(r"_page_(\d+)", name)
                page_number = int(match.group(1)) if match else None
                return name, {"page": page_number, "indexed": indexed, "bbox_map": bbox_map}
            except Exception as e:
                logger.error(f"OCR failed for {name}: {e}")
                return name, {"page": None, "indexed": [], "bbox_map": {}}

        results: Dict[str, Dict[str, object]] = {}
        # Run tasks concurrently; completion order doesn’t matter for the dict.
        with ThreadPoolExecutor(max_workers=workers) as ex:
            future_map = {ex.submit(_one, name): name for name in files}
            for fut in as_completed(future_map):
                name, data = fut.result()
                results[name] = data
                match = re.search(r"_page_(\d+)", name)
                page_number = int(match.group(1)) if match else None
                logger.info(f"completed OCR on {page_number}")

        return results

    @staticmethod
    def to_gpt_text(ocr_result: Dict[str, Dict]) -> str:
        """
        Formats OCR output into a readable string for GPT input.
        Results are ordered by 'page' number first, then filename.
        """

        def page_key(item):
            fname, data = item
            p = data.get("page")
            return (p if isinstance(p, int) else float("inf"), fname)

        # Reorder dict by page number before stringifying
        ordered_items = sorted(ocr_result.items(), key=page_key)

        lines = []
        for filename, data in ordered_items:
            page = data.get("page", "?")
            lines.append(f"{filename}: page {page}")
            for entry in data.get("indexed", []):
                lines.append(f"[{entry['index']}][{entry['confidence']}] {entry['text']}")
            lines.append("")  # spacer
        return "\n".join(lines)