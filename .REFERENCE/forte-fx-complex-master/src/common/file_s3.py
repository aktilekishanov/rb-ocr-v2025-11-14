from typing import Dict, List
from src.core.s3 import S3Client

def load_entries_from_s3(entries: List[Dict[str, str]]) -> Dict[str, bytes]:
    """
    Given a list of {"Truename": str, "Document": object_key},
    download each object from S3 and return a dict: filename -> bytes.
    """
    s3 = S3Client()
    file_map: Dict[str, bytes] = {}

    for entry in entries:
        key      = entry["Document"]  # your S3 object key
        filename = entry["Document"]  # desired filename
        content  = s3.download_bytes(key)
        file_map[filename] = content

    return file_map
