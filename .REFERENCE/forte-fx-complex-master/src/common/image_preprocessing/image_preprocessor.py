import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageEnhance
from typing import Optional

from src.common.logger.logger_config import get_logger

logger = get_logger("preprocessor")


class ImagePreprocessor:
    def __init__(self,
                 contrast: float = 1.5,
                 denoise: bool = True,
                 denoise_strength: int = 13,
                 denoise_template_window_size: int = 7,
                 deskew: bool = False,
                 upscale_factor: Optional[float] = 2.5):
        self.contrast = contrast
        self.denoise = denoise
        self.denoise_strength = denoise_strength
        self.denoise_template_window_size = denoise_template_window_size
        self.deskew = deskew
        self.upscale_factor = upscale_factor

    def _enhance_contrast(self, pil_image: Image.Image) -> Image.Image:
        if self.contrast != 1.0:
            enhancer = ImageEnhance.Contrast(pil_image)
            return enhancer.enhance(self.contrast)
        return pil_image

    def _apply_denoise(self, image: np.ndarray) -> np.ndarray:
        return cv2.fastNlMeansDenoising(
            image,
            h=self.denoise_strength,
            templateWindowSize=self.denoise_template_window_size
        )

    def _upscale(self, image: np.ndarray) -> np.ndarray:
        """Upscale image using OpenCV resize with pixel limit check."""
        if self.upscale_factor and self.upscale_factor > 1.0:
            orig_height, orig_width = image.shape[:2]
            new_width = int(orig_width * self.upscale_factor)
            new_height = int(orig_height * self.upscale_factor)
            new_pixel_count = new_width * new_height

            MAX_PIXELS = 150_000_000  # PIL's default

            if new_pixel_count > MAX_PIXELS:
                logger.warning(
                    f"Skipping upscale: target size [{new_width}x{new_height}] exceeds max safe pixel count ({MAX_PIXELS})."
                )
                self.upscale_factor = 1.0
                return image
            return cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        return image

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )

        kernel = np.ones((3, 3), np.uint8)
        thresh = cv2.dilate(thresh, kernel, iterations=1)

        height, width = thresh.shape
        coords = np.column_stack(np.where(thresh > 0))

        if len(coords) < 10:
            logger.warning("Insufficient contours for deskew, skipping rotation")
            return image

        angles = np.arange(-10, 10, 0.1)
        max_score = 0.0
        best_angle = 0.0

        for angle in angles:
            M = cv2.getRotationMatrix2D((width // 2, height // 2), angle, 1.0)
            rotated = cv2.warpAffine(thresh, M, (width, height), flags=cv2.INTER_NEAREST)
            proj = np.sum(rotated, axis=1)
            score = float(np.sum(proj ** 2))
            if score > max_score:
                max_score = score
                best_angle = angle

        if abs(best_angle) < 0.5:
            return image

        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, best_angle, 1.0)
        image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return image

    def preprocess_image_bytes(self, image_bytes: bytes) -> bytes:
        """
        Preprocess an image given as raw bytes.
        Returns preprocessed image as PNG bytes.

        No timing or per-step logging; only warnings and exceptions.
        """
        try:
            # Load
            pil_image = Image.open(io.BytesIO(image_bytes))

            # Enhance contrast
            pil_image = self._enhance_contrast(pil_image)

            # PIL -> NumPy
            image = np.array(pil_image)

            # Upscale
            image = self._upscale(image)

            # Denoise (optional)
            if self.denoise:
                if image.dtype != np.uint8:
                    image = image.astype(np.uint8)
                image = self._apply_denoise(image)

            # Deskew (optional)
            if self.deskew:
                image = self._deskew(image)

            # Encode PNG
            result_buf = io.BytesIO()
            Image.fromarray(image).save(
                result_buf, 'PNG', compress_level=1, dpi=(300, 300), optimize=False
            )
            return result_buf.getvalue()

        except Exception:
            logger.exception("Failed to preprocess image")
            # On any error, return original bytes without emitting timings
            return image_bytes
