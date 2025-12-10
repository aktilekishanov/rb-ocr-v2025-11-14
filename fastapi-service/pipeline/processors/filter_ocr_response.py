from pipeline.core.config import OCR_FILTERED
from pipeline.utils.io_utils import write_json


def _parse_ocr_response(obj: dict) -> list[dict]:
    """Parse OCR response into normalized page format.
    
    Handles multiple OCR response formats:
    - {data: {pages: [...]}} format
    - Textract-like {Blocks: [...]} format
    - Fallback for unrecognized formats
    
    Returns:
        List of dicts with 'page_number' and 'text' keys
    """
    pages = []
    
    # Prefer {data: {pages: [...]}} if present
    data = obj.get("data", {}) if isinstance(obj, dict) else {}
    if isinstance(data, dict) and isinstance(data.get("pages"), list):
        for page_data in data["pages"]:
            if isinstance(page_data, dict):
                page_number = page_data.get("page_number")
                try:
                    page_number = int(page_number) if page_number is not None else None
                except Exception:
                    page_number = None
                pages.append(
                    {
                        "page_number": page_number,
                        "text": page_data.get("text", "") or "",
                    }
                )
        if all(isinstance(x.get("page_number"), int) for x in pages):
            pages.sort(key=lambda x: x["page_number"])
    
    # Else, derive from Textract-like Blocks if present
    elif isinstance(obj, dict) and isinstance(obj.get("Blocks"), list):
        from collections import defaultdict

        blocks = obj["Blocks"]
        pages_map = defaultdict(list)
        has_line = any(
            isinstance(b, dict) and b.get("BlockType") == "LINE" for b in blocks
        )
        if has_line:
            for b in blocks:
                if isinstance(b, dict) and b.get("BlockType") == "LINE":
                    page_no = b.get("Page")
                    txt = b.get("Text", "")
                    if txt:
                        pages_map[page_no].append(txt)
        else:
            for b in blocks:
                if isinstance(b, dict) and b.get("Text"):
                    pages_map[b.get("Page")].append(b.get("Text"))
        
        for page_number in sorted(k for k in pages_map.keys() if isinstance(k, int)):
            pages.append(
                {
                    "page_number": page_number,
                    "text": "\n".join(pages_map[page_number]).strip(),
                }
            )
        if None in pages_map:
            pages.append(
                {
                    "page_number": None,
                    "text": "\n".join(pages_map[None]).strip(),
                }
            )
    else:
        # Fallback: nothing recognizable
        pages = [{"page_number": None, "text": ""}]
    
    return pages


def filter_ocr_response(
    obj: dict, output_dir: str, filename: str = OCR_FILTERED
) -> str:
    """Build per-page text and save to JSON file.
    
    Parses OCR response into normalized format and writes to file.
    
    Args:
        obj: OCR response dict (various formats supported)
        output_dir: Directory to write output file
        filename: Name of output file
        
    Returns:
        Full path to the saved file
    """
    import os
    
    pages = _parse_ocr_response(obj)
    out_path = os.path.join(output_dir, filename)
    write_json(out_path, {"pages": pages})
    return out_path
