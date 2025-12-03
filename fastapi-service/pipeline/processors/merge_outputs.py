import json
import os
from typing import Any

from pipeline.core.config import MERGED_FILENAME


def merge_extractor_and_doc_type(
    extractor_filtered_path: str,
    doc_type_filtered_path: str,
    output_dir: str,
    filename: str = MERGED_FILENAME,
) -> str:
    """
    Merge two JSON objects from given file paths and save to output_dir/filename.
    - extractor_filtered_path: file with extractor result (dict) with keys: fio, doc_date
    - doc_type_filtered_path: file with doc-type check result (dict) with keys: detected_doc_types, single_doc_type, doc_type_known
    The curated merged.json will contain only: fio, doc_date, single_doc_type, doc_type, doc_type_known
    """
    with open(extractor_filtered_path, encoding="utf-8") as ef:
        extractor_obj: dict[str, Any] = json.load(ef)
    with open(doc_type_filtered_path, encoding="utf-8") as df:
        doc_type_obj: dict[str, Any] = json.load(df)

    merged: dict[str, Any] = {}

    # Extractor fields
    if isinstance(extractor_obj, dict):
        fio = extractor_obj.get("fio")
        doc_date = extractor_obj.get("doc_date")
        merged["fio"] = fio if (fio is None or isinstance(fio, str)) else None
        merged["doc_date"] = doc_date if (doc_date is None or isinstance(doc_date, str)) else None

    # Doc-type checker curated fields
    single_doc_type_val = None
    doc_type_known_val = None
    top_doc_type: Any = None
    if isinstance(doc_type_obj, dict):
        sdt = doc_type_obj.get("single_doc_type")
        if isinstance(sdt, bool):
            single_doc_type_val = sdt
        dtk = doc_type_obj.get("doc_type_known")
        if isinstance(dtk, bool):
            doc_type_known_val = dtk
        detected = doc_type_obj.get("detected_doc_types")
        if isinstance(detected, list) and detected:
            cand = detected[0]
            if isinstance(cand, str):
                top_doc_type = cand

    merged["single_doc_type"] = single_doc_type_val
    merged["doc_type_known"] = doc_type_known_val
    merged["doc_type"] = top_doc_type if isinstance(top_doc_type, str) else None

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as mf:
        json.dump(merged, mf, ensure_ascii=False, indent=2)
    return out_path
