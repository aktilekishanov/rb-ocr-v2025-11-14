import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import pandas as pd
from rapidfuzz import fuzz

from src.common.gpt.gpt_client import GPTClient
from src.common.image_preprocessing.image_preprocessor import ImagePreprocessor
from src.common.logger.logger_config import get_logger
from src.common.ocr.ocr import OCR
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.pipeline import Pipeline
from src.common.pydantic_models.model_combined_json import FbData

logger = get_logger("FullFieldsTester")

# ---------------- Matching configuration ----------------
#
# Keys can be either raw expected.json field names (e.g. "CLIENT", "CONTRACT_TYPE")
# or their UPPERCASE versions. Anything not listed here defaults to "fuzzy".
#
# Strategies:
#   - "exact": exact string match after normalization
#   - "fuzzy": RapidFuzz similarity >= FUZZY_THRESHOLD
#   - "ignore": field is ignored for accuracy but still saved in CSV
#
MATCHING_STRATEGIES: Dict[str, str] = {
    # ---- Core parties / names (fuzzy) ----
    "CLIENT": "fuzzy",  # ТОО/АО, кавычки, регистр, доп. пояснения
    "COUNTERPARTY_NAME": "fuzzy",
    "CONSIGNEE": "fuzzy",
    "CONSIGNOR": "fuzzy",
    "MANUFACTURER": "fuzzy",
    "THIRD_PARTIES": "fuzzy",

    # ---- Суммы / деньги ----
    "AMOUNT": "fuzzy",  # формат 5 000 000 vs 5000000.00
    "CONTRACT_AMOUNT_TYPE": "exact",  # "общая" / "лимитная" и т.п.
    "REPATRIATION_TERM": "exact",  # "180.00" – как правило нормализуемо

    # ---- Валюта, страны, коды ----
    "CONTRACT_CURRENCY": "exact",  # ISO-коды валют
    "PAYMENT_CURRENCY": "exact",
    "COUNTERPARTY_COUNTRY": "exact",  # "CN", "RU", "KZ" и т.п.
    "PRODUCT_CATEGORY": "exact",  # "0", "1", "2" – категорийные коды
    "UN_CODE": "exact",  # "1", "2" и т.д.
    "CURRENCY_CONTRACT_TYPE_CODE": "exact",  # "1", "2" (тип валютного договора)
    "CONTRACT_TYPE_SYSTEM": "exact",  # "01", "02" – системные коды

    # ---- Тип договора / маршруты / флаги ----
    "CONTRACT_TYPE": "exact",  # "экспорт" / "импорт" – после нормализации
    "ROUTE": "fuzzy",  # "KZ-CN" vs "KZ–CN" vs "Kazakhstan-China"
    "CROSS_BORDER": "exact",  # "1"/"0" – двоичный флаг

    # ---- Даты / номера ----
    "CONTRACT_DATE": "exact",  # уже нормализовано в YYYY-MM-DD
    "CONTRACT_END_DATE": "exact",  # может быть null -> пропускаем
    "CURRENCY_CONTRACT_NUMBER": "fuzzy",  # кавычки, пробелы: "MYG-02" vs MYG-02

    # ---- Коды и реквизиты ----
    "HS_CODE": "exact",  # ТН ВЭД – различия существенны
    "BIK_SWIFT": "exact",  # список кодов, различия важны

    # ---- Описание / текст / ссылки ----
    "PRODUCT_NAME": "ignore",  # длинный текст, не критичен для метрик
    "CONTRACT_DESCRIPTION": "ignore",  # текстовое описание договора
    "DOCUMENT_REFERENCES": "ignore",  # перечень приложений/инвойсов и т.п.

    # ---- Прочие поля ----
    "PAYMENT_METHOD": "exact",  # коды типа "13" – строгое соответствие
}

FUZZY_THRESHOLD = 0.80  # 80% similarity for fuzzy match


@dataclass
class FullFieldsTestCase:
    name: str
    main_path: str
    extra_path: Optional[str]
    expected_fields: Dict[str, Any]
    client_data: Optional[FbData] = None


class FullFieldsTester:
    """
    Generic tester to validate all fields present in expected.json using
    per-field matching strategies (exact/fuzzy/ignore), with:

    - Parallel execution across cases
    - Per-case visualizations directory: <case_folder>/vis
    - Per-case JSON output directory: <case_folder>/json
    """

    def __init__(
            self,
            tests_root: str,
            model_name: str = "gpt-4.1",
            temperature: float = 0.1,
            max_cases: Optional[int] = None,
            focus_field: Optional[str] = None,
            max_workers: Optional[int] = None,
    ) -> None:

        self.tests_root = Path(tests_root)
        self.max_cases = max_cases
        self.max_workers = max_workers
        # If we want to focus on one specific field only:
        self.focus_field = focus_field.upper().strip() if focus_field else None

        preprocessor = ImagePreprocessAdapter(
            preprocessor=ImagePreprocessor(denoise=False, upscale_factor=1.0, contrast=1.0)
        )
        llm = LLMAdapter(
            client=GPTClient(model=model_name, temperature=temperature)
        )
        ocr_adapter = OCRAdapter(
            ocr=OCR()
        )

        self.preprocessor_adapter = preprocessor
        self.llm_adapter = llm
        self.ocr_adapter = ocr_adapter

        # collectors for global summaries
        self._overall_results: List[Dict[str, Any]] = []
        self._mismatch_counter: Dict[str, int] = {}
        self._mismatch_instances: List[Dict[str, Any]] = []

        # lock for thread-safe aggregation
        self._lock = threading.Lock()

    # ------------- Discovery -------------

    def _discover_cases(self) -> List[FullFieldsTestCase]:
        cases: List[FullFieldsTestCase] = []

        for case_dir in self.tests_root.iterdir():
            if not case_dir.is_dir():
                continue

            input_dir = case_dir / "input"
            main_dir = input_dir / "main"
            extra_dir = input_dir / "extra"
            expected_dir = case_dir / "expected"
            expected_path = expected_dir / "expected.json"

            if not main_dir.exists() or not expected_path.exists():
                logger.warning(f"Skipping {case_dir}: no main/ or expected.json")
                continue

            # Load expected.json as a plain dict
            try:
                with expected_path.open("r", encoding="utf-8") as f:
                    expected_raw = json.load(f)

                if not isinstance(expected_raw, dict):
                    raise ValueError("expected.json must be a JSON object {field_name: value, ...}")

            except Exception as e:
                logger.error(f"Invalid expected.json in {case_dir}: {e}")
                continue

            # Optional client/client.json -> FbData
            client_data: Optional[FbData] = None
            client_path = case_dir / "client" / "client.json"
            if client_path.exists():
                try:
                    with client_path.open("r", encoding="utf-8") as cf:
                        client_raw = json.load(cf)
                    client_data = FbData.from_dict(client_raw)
                except Exception as e:
                    logger.error(f"Failed to read/parse client.json in {case_dir}: {e}")

            cases.append(
                FullFieldsTestCase(
                    name=case_dir.name,
                    main_path=str(main_dir),
                    extra_path=str(extra_dir) if extra_dir.exists() else None,
                    expected_fields=expected_raw,
                    client_data=client_data,
                )
            )

        return cases

    # ------------- IO utils -------------

    @staticmethod
    def _load_entries_from_dir(path: str) -> Dict[str, bytes]:
        base = Path(path)
        if not base.exists():
            raise FileNotFoundError(f"Directory not found: {path}")

        entries: Dict[str, bytes] = {}
        allowed_ext = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"}

        for file_path in base.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in allowed_ext:
                logger.debug(f"Skipping unsupported file type: {file_path}")
                continue

            with file_path.open("rb") as f:
                entries[file_path.name] = f.read()

        if not entries:
            logger.warning(f"No suitable files found in directory {path}")

        return entries

    # ------------- Pipeline -------------

    def _run_pipeline_for_case(self, case: FullFieldsTestCase) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Runs Pipeline and returns:
        - eng_bbox_final (structured final JSON with bbox)
        - fb_flat_json (flattened JSON for FB / warehouses)
        Also ensures per-case vis/ and json/ dirs exist and saves JSON outputs.
        """
        main_files = self._load_entries_from_dir(case.main_path)
        extra_files = self._load_entries_from_dir(case.extra_path) if case.extra_path else {}

        case_dir = self.tests_root / case.name
        vis_dir = case_dir / "vis"
        json_dir = case_dir / "json"
        vis_dir.mkdir(parents=True, exist_ok=True)
        json_dir.mkdir(parents=True, exist_ok=True)

        extractor = Pipeline(
            main_file_dict=main_files,
            extra_file_dict=extra_files,
            preprocessor_adapter=self.preprocessor_adapter,
            session_id=case.name,
            llm_adapter=self.llm_adapter,
            ocr_adapter=self.ocr_adapter,
            client_data=case.client_data,  # FbData or None
            debug_mode=True,  # allow pipeline to write debug artifacts if enabled
            visualizations_output_dir=str(vis_dir),  # <case>/vis
            json_output_idr=str(json_dir),  # <case>/json (used by pipeline's _save_json/save_csv_stats if enabled)
        )

        result = extractor.run()
        # Pipeline returns: st.eng_bbox_final, st.fb_flat_json, st.skk_fields
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            raise TypeError(f"Unexpected Pipeline.run() result: {type(result)} {result!r}")

        eng_bbox_final, fb_flat_json = result[0], result[1]

        # Ensure json_dir is not empty even if pipeline didn't save anything
        try:
            eng_path = json_dir / "eng_bbox_final.json"
            with eng_path.open("w", encoding="utf-8") as f:
                json.dump(eng_bbox_final, f, ensure_ascii=False, indent=2)

            fb_path = json_dir / "fb_flat.json"
            with fb_path.open("w", encoding="utf-8") as f:
                json.dump(fb_flat_json, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write JSON outputs for {case.name}: {e}")

        # Optionally drop a small marker into vis_dir so it's never completely empty
        marker_path = vis_dir / "README.txt"
        if not marker_path.exists():
            try:
                with marker_path.open("w", encoding="utf-8") as f:
                    f.write("Visualization outputs from Pipeline (if enabled) will appear in this folder.\n")
            except Exception as e:
                logger.warning(f"Failed to write vis README for {case.name}: {e}")

        return eng_bbox_final, fb_flat_json

    # ------------- Normalization & comparison -------------

    @staticmethod
    def _normalize_key(name: str) -> str:
        return name.strip().upper()

    @staticmethod
    def _normalize_value(value: Any) -> str:
        """
        Simple scalar normalization:
        - str()
        - strip surrounding quotes
        - lower + strip
        """
        if value is None:
            return ""
        s = str(value).strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]
        return s.strip().lower()

    @staticmethod
    def _normalize_for_match(value: Any) -> str:
        """
        Normalization for matching:
        - None -> ""
        - list -> sorted, joined string of normalized elements
        - scalar -> normalized scalar
        """
        if value is None:
            return ""
        if isinstance(value, list):
            parts = [
                FullFieldsTester._normalize_value(v)
                for v in value
                if v is not None
            ]
            return " ".join(sorted(parts))
        return FullFieldsTester._normalize_value(value)

    def _extract_predicted_fields(self, eng_bbox_final: Dict[str, Any], fb_flat_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Converts Pipeline result to {NORMALIZED_FIELD_NAME: raw_value}.

        Case 1: fb_flat_json is already flat:
            { "CLIENT": "...", "CONTRACT_TYPE": "..." }

        Case 2: fb_flat_json["fields"] is a list with name/name_eng/value:
            {
              "fields": [
                { "name_eng": "CLIENT", "value": "..." },
                ...
              ]
            }
        """
        # Case 1: assume flat dict
        if "fields" not in fb_flat_json:
            flat = {}
            for k, v in fb_flat_json.items():
                flat[self._normalize_key(k)] = v
            return flat

        # Case 2: fields array
        flat: Dict[str, Any] = {}
        for field in fb_flat_json.get("fields", []):
            key = field.get("name_eng") or field.get("name")
            if not key:
                continue
            val = field.get("value")
            flat[self._normalize_key(key)] = val

        return flat

    @staticmethod
    def _get_matching_strategy(raw_field_name: str, field_norm: str) -> str:
        """
        Returns matching strategy for field:
        1) Try raw field name as-is.
        2) Try normalized upper-case name.
        3) Default to "fuzzy".
        """
        if raw_field_name in MATCHING_STRATEGIES:
            return MATCHING_STRATEGIES[raw_field_name]
        if field_norm in MATCHING_STRATEGIES:
            return MATCHING_STRATEGIES[field_norm]
        return "fuzzy"

    def _compare_field(
            self,
            raw_field_name: str,
            expected: Any,
            predicted: Any,
    ) -> Dict[str, Any]:
        """
        Performs comparison for a single field and returns a dict with:
          {
            "Key", "Expected", "Actual", "Matching Strategy",
            "Simple Score", "Fuzz Score", "Hybrid Score", "Match"
          }
        Also collects mismatches into self._mismatch_instances (thread-safe via caller).
        """
        field_norm = self._normalize_key(raw_field_name)
        method = self._get_matching_strategy(raw_field_name, field_norm)

        expected_norm = self._normalize_for_match(expected)
        predicted_norm = self._normalize_for_match(predicted)

        simple_match = (expected_norm == predicted_norm)
        simple_score = 1.0 if simple_match else 0.0

        if expected_norm or predicted_norm:
            fuzz_score = fuzz.ratio(expected_norm, predicted_norm) / 100.0
        else:
            fuzz_score = 1.0  # both empty -> perfect

        if method == "ignore":
            match = True
            hybrid_score = 1.0
        elif method == "exact":
            match = simple_match
            hybrid_score = 1.0 if match else 0.0
        elif method == "fuzzy":
            match = fuzz_score >= FUZZY_THRESHOLD
            hybrid_score = 1.0 if match else 0.0
        else:
            # unknown strategy – treat as mismatch but keep data
            match = False
            hybrid_score = 0.0

        return {
            "Key": raw_field_name,
            "Field Norm": field_norm,
            "Expected": expected_norm,
            "Actual": predicted_norm,
            "Matching Strategy": method,
            "Simple Score": round(simple_score, 2),
            "Fuzz Score": round(fuzz_score, 2),
            "Hybrid Score": round(hybrid_score, 2),
            "Match": match,
        }

    # ------------- Per-case processing (for parallel use) -------------

    def _process_single_case(self, case: FullFieldsTestCase) -> Dict[str, Any]:
        """
        Runs pipeline + comparison for one case and returns:
        {
          "case_name": str,
          "overall_result": {...},     # for summary_full_fields.csv
          "mismatches": [ ... ],       # list of mismatch dicts
          "per_field_stats": { field_norm: {"total": int, "correct": int}, ... }
        }
        """
        logger.info(f"=== Test {case.name} ===")
        case_dir = self.tests_root / case.name

        per_field_stats: Dict[str, Dict[str, int]] = {}
        mismatches_this_case: List[Dict[str, Any]] = []
        overall_result: Dict[str, Any] = {}

        try:
            eng_bbox_final, fb_flat_json = self._run_pipeline_for_case(case)
            predicted_fields = self._extract_predicted_fields(eng_bbox_final, fb_flat_json)

            case_rows: List[Dict[str, Any]] = []

            # iterate over all expected fields
            for raw_field_name, expected_value in case.expected_fields.items():
                if expected_value is None:
                    # no GT -> skip completely
                    continue

                field_norm = self._normalize_key(raw_field_name)

                # focus on one field only, if requested
                if self.focus_field and field_norm != self.focus_field:
                    continue

                predicted_value = predicted_fields.get(field_norm)

                row = self._compare_field(
                    raw_field_name=raw_field_name,
                    expected=expected_value,
                    predicted=predicted_value,
                )
                case_rows.append(row)

                method = row["Matching Strategy"]
                if method == "ignore":
                    continue

                # update per-field stats for this case
                per_field_stats.setdefault(field_norm, {"total": 0, "correct": 0})
                per_field_stats[field_norm]["total"] += 1
                if row["Match"]:
                    per_field_stats[field_norm]["correct"] += 1
                else:
                    mismatches_this_case.append(
                        {
                            "Field": raw_field_name,
                            "Field Norm": field_norm,
                            "Expected": row["Expected"],
                            "Actual": row["Actual"],
                            "Fuzz Score": row["Fuzz Score"],
                            "Simple Match": (row["Simple Score"] == 1.0),
                            "Case": case.name,
                        }
                    )

                logger.info(
                    f"[{'OK' if row['Match'] else 'FAIL'}] {case.name} | "
                    f"field={raw_field_name} | "
                    f"expected={row['Expected']!r} | predicted={row['Actual']!r} "
                    f"| strategy={method} | fuzz={row['Fuzz Score']}"
                )

            # Per-case CSV + accuracies
            if case_rows:
                df = pd.DataFrame(case_rows)
                simple_mean = float(df["Simple Score"].mean())
                fuzz_mean = float(df["Fuzz Score"].mean())
                hybrid_mean = float(df["Hybrid Score"].mean())

                summary_row = {
                    "Key": "== ACCURACY ==",
                    "Field Norm": "",
                    "Expected": "",
                    "Actual": "",
                    "Matching Strategy": "",
                    "Simple Score": round(simple_mean, 2),
                    "Fuzz Score": round(fuzz_mean, 2),
                    "Hybrid Score": round(hybrid_mean, 2),
                    "Match": "",
                }
                df = pd.concat([df, pd.DataFrame([summary_row])], ignore_index=True)

                # Save per-case comparison CSV
                out_csv = case_dir / "comparison_full_fields.csv"
                out_csv.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(out_csv, index=False, encoding="utf-8-sig")

                logger.info(
                    f"[{case.name}] Simple: {simple_mean:.2f}, "
                    f"Fuzz: {fuzz_mean:.2f}, Hybrid: {hybrid_mean:.2f}"
                )

                overall_result = {
                    "Test Case": case.name,
                    "Simple Accuracy": round(simple_mean, 2),
                    "RapidFuzz Accuracy": round(fuzz_mean, 2),
                    "Hybrid Accuracy": round(hybrid_mean, 2),
                }
            else:
                overall_result = {
                    "Test Case": case.name,
                    "Simple Accuracy": None,
                    "RapidFuzz Accuracy": None,
                    "Hybrid Accuracy": None,
                }

        except Exception as e:
            logger.exception(f"Error while processing {case.name}: {e}")
            overall_result = {
                "Test Case": case.name,
                "Simple Accuracy": None,
                "RapidFuzz Accuracy": None,
                "Hybrid Accuracy": None,
                "Error": str(e),
            }
            mismatches_this_case.append(
                {
                    "Field": None,
                    "Field Norm": None,
                    "Expected": None,
                    "Actual": None,
                    "Fuzz Score": None,
                    "Simple Match": None,
                    "Error": str(e),
                    "Case": case.name,
                }
            )

        return {
            "case_name": case.name,
            "overall_result": overall_result,
            "mismatches": mismatches_this_case,
            "per_field_stats": per_field_stats,
        }

    # ------------- Main run (parallel) -------------

    def run(self) -> Dict[str, Any]:
        cases = self._discover_cases()
        if not cases:
            logger.warning("No test cases found")
            return {
                "total_cases": 0,
                "total_field_checks": 0,
                "correct_field_checks": 0,
                "accuracy": 0.0,
                "per_field": {},
                "mismatches": [],
            }

        if self.max_cases is not None:
            cases = cases[: self.max_cases]
            logger.info(
                f"Limiting test run to first {len(cases)} cases (max_cases={self.max_cases})"
            )

        total_cases = 0
        total_field_checks = 0
        correct_field_checks = 0

        self._overall_results = []
        self._mismatch_counter = {}
        self._mismatch_instances = []

        per_field_stats: Dict[str, Dict[str, int]] = {}

        # choose number of threads
        if self.max_workers is not None:
            max_workers = self.max_workers
        else:
            max_workers = min(8, len(cases))

        logger.info(f"Running tests in parallel with max_workers={max_workers}")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_case = {
                executor.submit(self._process_single_case, case): case
                for case in cases
            }

            for future in as_completed(future_to_case):
                case = future_to_case[future]
                total_cases += 1

                try:
                    result = future.result()
                except Exception as e:
                    logger.exception(f"Unhandled error in case {case.name}: {e}")
                    continue

                # aggregate results under lock
                with self._lock:
                    self._overall_results.append(result["overall_result"])

                    # mismatches
                    for mm in result["mismatches"]:
                        self._mismatch_instances.append(mm)
                        fname = mm.get("Field Norm")
                        if fname:
                            self._mismatch_counter[fname] = self._mismatch_counter.get(fname, 0) + 1

                    # per-field stats
                    for fname, st in result["per_field_stats"].items():
                        total = st["total"]
                        correct = st["correct"]
                        per_field_stats.setdefault(fname, {"total": 0, "correct": 0})
                        per_field_stats[fname]["total"] += total
                        per_field_stats[fname]["correct"] += correct
                        total_field_checks += total
                        correct_field_checks += correct

        # Global accuracy over all non-ignored field checks
        accuracy = (correct_field_checks / total_field_checks) if total_field_checks else 0.0

        # per-field summary
        per_field_summary = {}
        for fname, st in per_field_stats.items():
            t = st["total"]
            c = st["correct"]
            per_field_summary[fname] = {
                "total": t,
                "correct": c,
                "accuracy": c / t if t else 0.0,
            }

        # Write global CSV summaries
        self._write_summaries()

        logger.info(
            f"=== Final result (Full fields) === "
            f"cases={total_cases}, "
            f"checks={total_field_checks}, "
            f"correct={correct_field_checks}, "
            f"accuracy={accuracy:.3f}"
        )

        return {
            "total_cases": total_cases,
            "total_field_checks": total_field_checks,
            "correct_field_checks": correct_field_checks,
            "accuracy": accuracy,
            "per_field": per_field_summary,
            "mismatches": self._mismatch_instances,
        }

    # ------------- Summary writers -------------

    def _write_summaries(self) -> None:
        """
        Writes overall summaries under tests_root:
          - summary_full_fields.csv
          - mismatch_instances.csv
          - mismatch_stats.csv
        """
        base_dir = str(self.tests_root)

        if not self._overall_results:
            logger.error("No cases completed; nothing to summarize.")
            return

        summary_df = pd.DataFrame(self._overall_results)

        simple_mean = pd.to_numeric(summary_df.get("Simple Accuracy"), errors="coerce").mean()
        fuzz_mean = pd.to_numeric(summary_df.get("RapidFuzz Accuracy"), errors="coerce").mean()
        hybrid_mean = pd.to_numeric(summary_df.get("Hybrid Accuracy"), errors="coerce").mean()

        avg_row = {
            "Test Case": "== AVERAGE ==",
            "Simple Accuracy": round(simple_mean, 2) if pd.notna(simple_mean) else None,
            "RapidFuzz Accuracy": round(fuzz_mean, 2) if pd.notna(fuzz_mean) else None,
            "Hybrid Accuracy": round(hybrid_mean, 2) if pd.notna(hybrid_mean) else None,
        }
        summary_df = pd.concat([summary_df, pd.DataFrame([avg_row])], ignore_index=True)

        summary_path = os.path.join(base_dir, "summary_full_fields.csv")
        summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

        # Mismatch instances
        if self._mismatch_instances:
            mm_df = pd.DataFrame(self._mismatch_instances)
            mm_path = os.path.join(base_dir, "mismatch_instances.csv")
            mm_df.to_csv(mm_path, index=False, encoding="utf-8-sig")

        # Mismatch stats per field
        if self._mismatch_counter:
            mismatch_df = pd.DataFrame(
                [{"Key": key, "Mismatch Count": count} for key, count in self._mismatch_counter.items()]
            )
            mismatch_stats_path = os.path.join(base_dir, "mismatch_stats.csv")
            mismatch_df.to_csv(mismatch_stats_path, index=False, encoding="utf-8-sig")
        else:
            mismatch_df = pd.DataFrame(columns=["Key", "Mismatch Count"])

        # Console printout
        print("\n=== Final Summary (FullFieldsTester) ===")
        print(summary_df.to_string(index=False))
        print("\n=== Most Frequent Mismatches ===")
        if not mismatch_df.empty:
            print(mismatch_df.to_string(index=False))
        else:
            print("(none)")


if __name__ == "__main__":
    tester = FullFieldsTester(
        tests_root=r"/Users/abdiakhmet/Downloads/ocr_train_dataset",
        max_cases=None,  # or an int to limit
        focus_field=None,  # or "CONTRACT_TYPE", "CLIENT", etc.
        max_workers=20,  # tune based on API limits
    )
    summary = tester.run()

    print("Total cases:", summary["total_cases"])
    print("Total field checks:", summary["total_field_checks"])
    print("Correct:", summary["correct_field_checks"])
    print("Accuracy (overall):", round(summary["accuracy"], 3))

    print("\nAccuracy per field:")
    for field, stats in summary["per_field"].items():
        print(
            f"  {field}: {stats['correct']}/{stats['total']} "
            f"({stats['accuracy']:.3f})"
        )

    print("\nMismatches (sample):")
    for mm in summary["mismatches"][:20]:
        print(mm)
