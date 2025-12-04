import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

from src.common.gpt.dmz_client import DMZClient
from src.common.image_preprocessing.image_preprocessor import ImagePreprocessor
from src.common.logger.logger_config import get_logger
from src.common.ocr.ocr import OCR
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.pipeline import Pipeline
from src.common.pydantic_models.model_combined_json import IndependentFields

logger = get_logger("IndependentFieldsTester")


@dataclass
class IndependentFieldsTestCase:
    name: str
    main_path: str
    extra_path: Optional[str]
    expected: Dict[str, Any]
    client_data: Optional[Dict[str, Any]] = None


class IndependentFieldsTester:
    """
    Tester for IndependentFields extraction.

    Expected structure per case:

        case_XXXXX/
          input/
            main/      <-- contract files
            extra/     <-- optional extra files
          expected/
            expected.json   <-- contains all IndependentFields values
          client/
            client.json     <-- optional client data (passed into Pipeline)
    """

    def __init__(
            self,
            tests_root: str,
            model_name: str = "gpt-4.1-nano",
            temperature: float = 0.1,
            max_cases: Optional[int] = None,
    ) -> None:
        self.tests_root = Path(tests_root)
        self.max_cases = max_cases

        preprocessor = ImagePreprocessAdapter(
            preprocessor=ImagePreprocessor(denoise=False, upscale_factor=1.0, contrast=1.0)
        )
        llm = LLMAdapter(
            client=DMZClient(model=model_name, temperature=temperature)
        )
        ocr_adapter = OCRAdapter(
            ocr=OCR()
        )

        self.preprocessor_adapter = preprocessor
        self.llm_adapter = llm
        self.ocr_adapter = ocr_adapter

    # --- helpers ---

    def _discover_cases(self) -> List[IndependentFieldsTestCase]:
        cases: List[IndependentFieldsTestCase] = []

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

            # Load expected json
            try:
                with expected_path.open("r", encoding="utf-8") as f:
                    expected_raw = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load expected.json in {case_dir}: {e}")
                continue

            # Load client/client.json if present
            client_data: Optional[Dict[str, Any]] = None
            client_path = case_dir / "client" / "client.json"
            if client_path.exists():
                try:
                    with client_path.open("r", encoding="utf-8") as cf:
                        client_data = json.load(cf)
                except Exception as e:
                    logger.error(f"Failed to read client.json in {case_dir}: {e}")

            cases.append(
                IndependentFieldsTestCase(
                    name=case_dir.name,
                    main_path=str(main_dir),
                    extra_path=str(extra_dir) if extra_dir.exists() else None,
                    expected=expected_raw,
                    client_data=client_data,
                )
            )

        return cases

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

    def _run_pipeline_for_case(self, case: IndependentFieldsTestCase) -> IndependentFields:
        main_files = self._load_entries_from_dir(case.main_path)
        extra_files = self._load_entries_from_dir(case.extra_path) if case.extra_path else {}

        extractor = Pipeline(
            main_file_dict=main_files,
            extra_file_dict=extra_files,
            preprocessor_adapter=self.preprocessor_adapter,
            session_id=case.name,
            llm_adapter=self.llm_adapter,
            ocr_adapter=self.ocr_adapter,
            client_data=case.client_data,
        )

        result = extractor.run()

        if isinstance(result, IndependentFields):
            return result

        if isinstance(result, dict):
            return IndependentFields(**result)

        raise TypeError(f"Unexpected Pipeline.run() result type: {type(result)}")

    def _normalize_value(self, value: Any) -> Any:
        """Normalize values for comparison"""
        if value is None:
            return None

        # Handle Pydantic models
        if hasattr(value, 'model_dump'):
            return value.model_dump()

        # Handle dict
        if isinstance(value, dict):
            return {k: self._normalize_value(v) for k, v in value.items()}

        # Handle list
        if isinstance(value, list):
            return [self._normalize_value(v) for v in value]

        # Handle strings - strip and normalize
        if isinstance(value, str):
            return value.strip()

        return value

    def _compare_fields(self, expected: Any, predicted: Any, field_path: str = "") -> List[str]:
        """
        Recursively compare expected and predicted values.
        Returns list of mismatch descriptions.
        """
        mismatches = []

        expected_norm = self._normalize_value(expected)
        predicted_norm = self._normalize_value(predicted)

        if type(expected_norm) != type(predicted_norm):
            mismatches.append(
                f"{field_path}: type mismatch - expected {type(expected_norm).__name__}, "
                f"got {type(predicted_norm).__name__}"
            )
            return mismatches

        if isinstance(expected_norm, dict):
            all_keys = set(expected_norm.keys()) | set(predicted_norm.keys())
            for key in all_keys:
                new_path = f"{field_path}.{key}" if field_path else key

                if key not in expected_norm:
                    mismatches.append(f"{new_path}: unexpected key in prediction")
                elif key not in predicted_norm:
                    mismatches.append(f"{new_path}: missing in prediction")
                else:
                    mismatches.extend(
                        self._compare_fields(expected_norm[key], predicted_norm[key], new_path)
                    )

        elif isinstance(expected_norm, list):
            if len(expected_norm) != len(predicted_norm):
                mismatches.append(
                    f"{field_path}: list length mismatch - expected {len(expected_norm)}, "
                    f"got {len(predicted_norm)}"
                )
            else:
                for idx, (exp_item, pred_item) in enumerate(zip(expected_norm, predicted_norm)):
                    new_path = f"{field_path}[{idx}]"
                    mismatches.extend(self._compare_fields(exp_item, pred_item, new_path))

        else:
            if expected_norm != predicted_norm:
                mismatches.append(
                    f"{field_path}: value mismatch - expected '{expected_norm}', got '{predicted_norm}'"
                )

        return mismatches

    # --- main ---

    def run(self) -> Dict[str, Any]:
        cases = self._discover_cases()
        if not cases:
            logger.warning("No test cases found")
            return {
                "total": 0,
                "correct": 0,
                "accuracy": 0.0,
                "field_accuracy": {},
                "mismatches": []
            }

        # Apply limiter
        if self.max_cases is not None:
            cases = cases[: self.max_cases]
            logger.info(
                f"Limiting test run to first {len(cases)} cases (max_cases={self.max_cases})"
            )

        total = 0
        correct = 0
        field_stats: Dict[str, Dict[str, int]] = {}  # field -> {correct, total}
        mismatches = []

        for case in cases:
            total += 1
            logger.info(f"=== Test {case.name} ===")

            try:
                predicted = self._run_pipeline_for_case(case)
                predicted_dict = predicted.model_dump()

                # Compare all fields
                field_mismatches = self._compare_fields(case.expected, predicted_dict)

                if not field_mismatches:
                    correct += 1
                    logger.info(f"[OK] {case.name}: all fields match")
                    status = "OK"
                else:
                    logger.info(f"[FAIL] {case.name}: {len(field_mismatches)} field(s) mismatch")
                    for mismatch in field_mismatches:
                        logger.info(f"  - {mismatch}")

                    mismatches.append(
                        {
                            "name": case.name,
                            "field_mismatches": field_mismatches,
                            "error": None,
                        }
                    )
                    status = "FAIL"

                # Track per-field accuracy
                for field_name in case.expected.keys():
                    if field_name not in field_stats:
                        field_stats[field_name] = {"correct": 0, "total": 0}

                    field_stats[field_name]["total"] += 1

                    # Check if this specific field has any mismatches
                    field_has_error = any(
                        mismatch.startswith(field_name) for mismatch in field_mismatches
                    )

                    if not field_has_error:
                        field_stats[field_name]["correct"] += 1

            except Exception as e:
                logger.exception(f"Error while processing {case.name}: {e}")
                mismatches.append(
                    {
                        "name": case.name,
                        "field_mismatches": [],
                        "error": str(e),
                    }
                )
                status = "FAIL"

            # Running cumulative accuracy
            current_accuracy = correct / total if total else 0.0
            logger.info(
                f"[{status}] accuracy: {current_accuracy * 100:.0f}%, {correct}/{total} passed"
            )

        accuracy = correct / total if total else 0.0

        # Calculate per-field accuracy
        field_accuracy = {}
        for field_name, stats in field_stats.items():
            field_accuracy[field_name] = {
                "accuracy": stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0,
                "correct": stats["correct"],
                "total": stats["total"],
            }

        summary = {
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
            "field_accuracy": field_accuracy,
            "mismatches": mismatches,
        }

        logger.info(
            f"=== Final result (IndependentFields) === "
            f"correct={correct}/{total}, accuracy={accuracy:.3f}"
        )

        if field_accuracy:
            logger.info("=== Per-field accuracy ===")
            for field_name, stats in sorted(field_accuracy.items(), key=lambda x: x[1]["accuracy"]):
                logger.info(
                    f"  {field_name}: {stats['accuracy']:.3f} "
                    f"({stats['correct']}/{stats['total']})"
                )

        if mismatches:
            logger.info(f"=== {len(mismatches)} Cases with errors ===")
            for mm in mismatches:
                logger.info(f"  - {mm['name']}: {len(mm['field_mismatches'])} field(s) failed")
                if mm.get('error'):
                    logger.info(f"    Error: {mm['error']}")

        return summary


if __name__ == "__main__":
    tester = IndependentFieldsTester(
        tests_root=r"C:\Users\YOrazayev\Downloads\ocr_train_dataset",
        max_cases=None,  # set to e.g. 20 to limit
    )
    summary = tester.run()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tests: {summary['total']}")
    print(f"Correct: {summary['correct']}")
    print(f"Overall accuracy: {summary['accuracy']:.3f}")

    print("\n" + "=" * 60)
    print("PER-FIELD ACCURACY")
    print("=" * 60)
    for field_name, stats in sorted(
            summary['field_accuracy'].items(),
            key=lambda x: x[1]['accuracy'],
            reverse=True
    ):
        print(f"{field_name:40s}: {stats['accuracy']:.3f} ({stats['correct']}/{stats['total']})")

    if summary['mismatches']:
        print("\n" + "=" * 60)
        print("FAILED CASES")
        print("=" * 60)
        for mm in summary['mismatches']:
            print(f"\n{mm['name']}:")
            if mm.get('error'):
                print(f"  ERROR: {mm['error']}")
            else:
                for mismatch in mm['field_mismatches'][:5]:  # Show first 5 mismatches
                    print(f"  - {mismatch}")
                if len(mm['field_mismatches']) > 5:
                    print(f"  ... and {len(mm['field_mismatches']) - 5} more")
