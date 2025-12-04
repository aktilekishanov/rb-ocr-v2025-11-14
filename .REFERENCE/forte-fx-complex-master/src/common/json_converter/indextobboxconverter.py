from typing import Dict, List, Any, Tuple, Optional
from sklearn.cluster import DBSCAN
import numpy as np
from src.common.logger.logger_config import get_logger

logger = get_logger("IndexToBboxConverter")


class IndexToBboxConverter:
    def __init__(self, bbox_data: Dict[str, Dict[str, Any]], distance_threshold: float = 400.0):
        """
        :param bbox_data: OCR bbox data, typically merged from main/extra.
            Expected per filename one of these shapes:

            A) {
                 "page": 1,
                 "bbox_map": { 0: [x1,y1,x2,y2], 1: [...] }
               }

            B) {
                 "pages": {
                   1: { "bbox_map": { 0: [...], ... } },
                   "2": { "bbox_map": { ... } }
                 }
               }

            C) direct map:
               { 0: [x1,y1,x2,y2], 1: [...] }

        :param distance_threshold: Max distance between bbox centers to be grouped.
        """
        self.bbox_data = bbox_data
        self.distance_threshold = distance_threshold

    def convert(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert index-based references in `extracted["fields"][...]["references"]`
        into bbox-based references.

        Input example (per field):

            {
              "name": "Валютный договор",
              "value": "35",
              "confidence": 0.94,
              "references": [
                {
                  "filename": "file_page_1.png",
                  "occurrences": [
                    { "page": 1, "index": [0, 1] }
                  ]
                }
              ]
            }

        Output example (per field):

            {
              "name": "Валютный договор",
              "value": "35",
              "confidence": 0.94,
              "references": [
                {
                  "filename": "file_page_1.png",
                  "occurrences": [
                    { "page": 1, "bbox": [x1, y1, x2, y2] }
                  ]
                }
              ]
            }
        """
        fields = extracted.get("fields")
        if not isinstance(fields, list):
            raise ValueError("Input must be a dict with a 'fields' list")

        updated_fields = [self._convert_field(field) for field in fields]
        return {"fields": updated_fields}

    def _convert_field(self, field: Dict[str, Any]) -> Dict[str, Any]:
        new_field = field.copy()
        refs = field.get("references") or []
        new_field["references"] = self._build_references(refs)
        return new_field

    def _resolve_bbox_map(
            self,
            filename: str,
            page: Optional[int],
    ) -> Dict[Any, List[float]]:
        """
        Try to resolve a bbox_map for given filename and (optionally) page
        from self.bbox_data. Handles several typical shapes.
        """
        if filename not in self.bbox_data:
            logger.debug(f"[IndexToBboxConverter] filename not in bbox_data: {filename}")
            return {}

        entry = self.bbox_data[filename]

        # Case A: direct map {idx: bbox}
        if all(isinstance(k, (int, str)) and isinstance(v, (list, tuple)) and len(v) == 4
               for k, v in entry.items()):
            return entry

        # Case B: { "bbox_map": {...} }
        if isinstance(entry, dict) and "bbox_map" in entry:
            return entry["bbox_map"] or {}

        # Case C: { "pages": { page: { "bbox_map": {...} } } }
        if isinstance(entry, dict) and "pages" in entry and page is not None:
            pages = entry["pages"]
            page_key = page
            if page_key not in pages and str(page_key) in pages:
                page_key = str(page_key)
            page_entry = pages.get(page_key)
            if isinstance(page_entry, dict) and "bbox_map" in page_entry:
                return page_entry["bbox_map"] or {}

        logger.debug(f"[IndexToBboxConverter] No bbox_map resolved for {filename}, page={page}")
        return {}

    def _build_references(self, references: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped_bboxes: Dict[Tuple[str, int], List[List[float]]] = {}

        for ref in references:
            filename = ref.get("filename")
            occurrences = ref.get("occurrences", [])

            if not filename:
                continue

            for occ in occurrences:
                page = occ.get("page")
                indices = occ.get("index", [])

                bbox_map = self._resolve_bbox_map(filename, page)
                if not bbox_map:
                    continue

                page_bboxes: List[List[float]] = []

                for idx in indices:
                    # support both int and str keys in bbox_map
                    if idx in bbox_map:
                        page_bboxes.append(bbox_map[idx])
                    elif str(idx) in bbox_map:
                        page_bboxes.append(bbox_map[str(idx)])
                    else:
                        logger.debug(
                            f"[IndexToBboxConverter] index {idx} not found in bbox_map "
                            f"for {filename}, page={page}"
                        )

                if not page_bboxes:
                    continue

                grouped_bboxes.setdefault((filename, page), []).extend(page_bboxes)

        final_references: List[Dict[str, Any]] = []

        for (filename, page), bboxes in grouped_bboxes.items():
            clustered = self._cluster_and_merge_bboxes(bboxes)

            for merged_bbox in clustered:
                final_references.append(
                    {
                        "filename": filename,
                        "occurrences": [
                            {
                                "page": page,
                                "bbox": merged_bbox,
                            }
                        ],
                    }
                )

        return final_references

    def _cluster_and_merge_bboxes(self, bboxes: List[List[float]]) -> List[List[int]]:
        """
        Cluster close bboxes using DBSCAN and merge them into enclosing boxes.
        """
        if not bboxes:
            return []

        centers = np.array([self._bbox_center(b) for b in bboxes], dtype=float)
        clustering = DBSCAN(eps=self.distance_threshold, min_samples=1).fit(centers)
        labels = clustering.labels_

        clusters: Dict[int, List[List[float]]] = {}
        for label, bbox in zip(labels, bboxes):
            clusters.setdefault(label, []).append(bbox)

        return [self._merge_bboxes(cluster) for cluster in clusters.values()]

    @staticmethod
    def _bbox_center(bbox: List[float]) -> Tuple[float, float]:
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    @staticmethod
    def _merge_bboxes(bboxes: List[List[float]]) -> List[int]:
        x1 = min(b[0] for b in bboxes)
        y1 = min(b[1] for b in bboxes)
        x2 = max(b[2] for b in bboxes)
        y2 = max(b[3] for b in bboxes)
        return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]
