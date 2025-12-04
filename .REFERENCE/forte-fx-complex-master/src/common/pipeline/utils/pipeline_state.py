from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class PipelineState:
    session_id: str
    file_map_main: Dict[str, bytes]
    file_map_extra: Dict[str, bytes]

    # extraction → preprocess → OCR
    outputs_main: Optional[Dict[str, bytes]] = None
    outputs_extra: Optional[Dict[str, bytes]] = None
    processed_main: Optional[Dict[str, bytes]] = None
    processed_extra: Optional[Dict[str, bytes]] = None
    ocr_result_main: Optional[Dict] = None
    ocr_result_extra: Optional[Dict] = None
    ocr_texts: Optional[str] = None

    # LLM
    raw_outputs: Dict[str, str] = field(default_factory=dict)
    parsed_jsons: Dict[str, Dict] = field(default_factory=dict)

    # merge/convert/assign/flatten
    combined_json_output: Optional[Dict] = None
    ocr_bbox_data: Optional[Dict] = None
    bbox_final_json: Optional[Dict] = None
    fb_flat_json: Optional[Dict] = None
    eng_bbox_final: Optional[Dict] = None
    skk_fields: Optional[Dict] = None

    def drop(self, *attrs: str) -> None:
        """Free big intermediates to save RAM."""
        for a in attrs:
            setattr(self, a, None)
