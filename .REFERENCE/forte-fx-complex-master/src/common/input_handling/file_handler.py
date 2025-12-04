import io
import logging
from PIL import Image
from pdf2image import convert_from_bytes
from docx import Document
import os

from src.common.logger.logger_config import get_logger

logger = get_logger("file_handler")

class FileHandler:
    SUPPORTED_EXTENSIONS = {"pdf", "docx", "jpg", "jpeg", "png"}

    def __init__(self, session_id: str):
        self.session_id = session_id
        logger.info(f"Initialized in-memory FileHandler. Session id: {self.session_id}")

    def process_files_in_memory(self, file_map: dict[str, bytes]) -> dict[str, bytes | str]:
        """
        Processes a dictionary of files in memory.

        Args:
            file_map: Dictionary where keys are filenames and values are raw bytes.

        Returns:
            Dictionary of output_name → content (bytes for images, str for text).
        """
        outputs = {}

        for fname, file_bytes in file_map.items():
            ext = os.path.splitext(fname)[-1].lower().lstrip(".")
            if ext not in self.SUPPORTED_EXTENSIONS:
                logger.warning(f" Skipping unsupported file: {fname}")
                continue

            try:
                logger.info(f"Processing file: {fname}")
                result = self._normalize(file_bytes, fname, ext)
                base = os.path.splitext(fname)[0]

                if result["type"] == "images":
                    for i, img in enumerate(result["content"]):
                        out_name = f"{base}_page_{i + 1}.png" if ext == "pdf" else f"{base}.png"
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        buf.seek(0)
                        outputs[out_name] = buf.read()

                elif result["type"] == "text":
                    out_name = f"{base}.txt"
                    outputs[out_name] = result["content"]

            except Exception as e:
                logger.error(f"Failed to process {fname}: {e}")

        return outputs

    def _normalize(self, file_bytes: bytes, filename: str, extension: str) -> dict:
        """
        Dispatches file content to the correct handler based on extension.

        Returns:
            Dictionary with type and content for further processing.
        """
        try:
            if extension == "pdf":
                return self._handle_pdf(file_bytes)
            elif extension == "docx":
                return self._handle_docx(file_bytes)
            else:
                return self._handle_image(file_bytes)
        except Exception as e:
            logger.exception(f"Failed to normalize {filename}: {e}")
            raise RuntimeError(f"Normalization failed: {e}")

    def _handle_pdf(self, file_bytes: bytes) -> dict:
        """
        Converts PDF to list of PIL.Image objects.
        """
        try:
            logger.info(f"Converting PDF to images")
            images = convert_from_bytes(file_bytes, dpi=300, grayscale=True)
            return {"type": "images", "content": images}
        except Exception as e:
            logger.exception(f"PDF conversion failed: {e}")
            raise

    def _handle_docx(self, file_bytes: bytes) -> dict:
        """
        Extracts plain text from a DOCX document.
        """
        try:
            logger.info(f"Extracting text from DOCX")
            doc = Document(io.BytesIO(file_bytes))
            text = "\n".join(para.text for para in doc.paragraphs)
            return {"type": "text", "content": text}
        except Exception as e:
            logger.exception(f"DOCX parsing failed: {e}")
            raise

    def _handle_image(self, file_bytes: bytes) -> dict:
        """
        Converts raw image bytes into a PIL image.
        """
        try:
            logger.info(f"Loading image")
            image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            return {"type": "images", "content": [image]}
        except Exception as e:
            logger.exception(f"[{self.session_id}] Image loading failed: {e}")
            raise
