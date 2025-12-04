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
from src.common.pydantic_models.model_combined_json import TradeTypeEnum, TradeType

logger = get_logger("Tester")


@dataclass
class TradeTypeTestCase:
    name: str
    main_path: str
    extra_path: Optional[str]
    expected: TradeTypeEnum
    client_data: Optional[Dict[str, Any]] = None


class TradeTypeTester:
    """
    Tester for 'Тип договора' (экспорт/импорт).

    Expected structure per case:

        case_XXXXX/
          input/
            main/      <-- contract files
            extra/     <-- optional extra files
          expected/
            expected.json   <-- contains CONTRACT_TYPE / TRADE_TYPE
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

    def _discover_cases(self) -> List[TradeTypeTestCase]:
        cases: List[TradeTypeTestCase] = []

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
            with expected_path.open("r", encoding="utf-8") as f:
                expected_raw = json.load(f)

            try:
                # Find key for contract type in a case-insensitive way
                type_key = None
                for k in expected_raw.keys():
                    k_norm = k.strip().upper()
                    if k_norm in ("TRADE_TYPE", "CONTRACT_TYPE"):
                        type_key = k
                        break

                if type_key is None:
                    raise KeyError("No 'trade_type' or 'CONTRACT_TYPE' in expected.json")

                raw_value = expected_raw[type_key]

                if raw_value is None:
                    raise ValueError("CONTRACT_TYPE / trade_type = None")

                # Normalize and strip quotes
                norm = str(raw_value).strip()
                if (norm.startswith('"') and norm.endswith('"')) or (norm.startswith("'") and norm.endswith("'")):
                    norm = norm[1:-1]
                norm = norm.strip().lower()

                if norm in ("экспорт", "export"):
                    expected_enum = TradeTypeEnum.EXPORT
                elif norm in ("импорт", "import"):
                    expected_enum = TradeTypeEnum.IMPORT
                else:
                    raise ValueError(
                        f"Unknown CONTRACT_TYPE / trade_type after normalization: "
                        f"{raw_value!r} -> {norm!r}"
                    )

            except Exception as e:
                logger.error(f"Invalid expected.json in {case_dir}: {e}")
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
                TradeTypeTestCase(
                    name=case_dir.name,
                    main_path=str(main_dir),
                    extra_path=str(extra_dir) if extra_dir.exists() else None,
                    expected=expected_enum,
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

    def _run_pipeline_for_case(self, case: TradeTypeTestCase) -> TradeType:
        main_files = self._load_entries_from_dir(case.main_path)
        extra_files = self._load_entries_from_dir(case.extra_path) if case.extra_path else {}

        extractor = Pipeline(
            main_file_dict=main_files,
            extra_file_dict=extra_files,
            preprocessor_adapter=self.preprocessor_adapter,
            session_id=case.name,
            llm_adapter=self.llm_adapter,
            ocr_adapter=self.ocr_adapter,
            client_data=case.client_data,  # passed into pipeline
        )

        result = extractor.run()

        if isinstance(result, TradeType):
            return result

        if isinstance(result, dict):
            return TradeType(**result)

        raise TypeError(f"Unexpected Pipeline.run() result type: {type(result)}")

    # --- main ---

    def run(self) -> Dict[str, Any]:
        cases = self._discover_cases()
        if not cases:
            logger.warning("No test cases found")
            return {"total": 0, "correct": 0, "accuracy": 0.0, "mismatches": []}

        # Apply limiter
        if self.max_cases is not None:
            cases = cases[: self.max_cases]
            logger.info(
                f"Limiting test run to first {len(cases)} cases (max_cases={self.max_cases})"
            )

        total = 0
        correct = 0
        mismatches = []

        for case in cases:
            total += 1
            logger.info(f"=== Test {case.name} ===")

            try:
                predicted_tt = self._run_pipeline_for_case(case)
                predicted_value = predicted_tt.trade_type

                if predicted_value == case.expected:
                    correct += 1
                    logger.info(f"[OK] {case.name}: {predicted_value.value}")
                    status = "OK"
                else:
                    logger.info(
                        f"[FAIL] {case.name}: expected={case.expected.value}, "
                        f"predicted={predicted_value.value}"
                    )
                    mismatches.append(
                        {
                            "name": case.name,
                            "expected": case.expected.value,
                            "predicted": predicted_value.value,
                            "error": None,
                        }
                    )
                    status = "FAIL"

            except Exception as e:
                logger.exception(f"Error while processing {case.name}: {e}")
                mismatches.append(
                    {
                        "name": case.name,
                        "expected": case.expected.value,
                        "predicted": None,
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

        summary = {
            "total": total,
            "correct": correct,
            "accuracy": accuracy,
            "mismatches": mismatches,
        }

        logger.info(
            f"=== Final result (Тип договора) === "
            f"correct={correct}/{total}, accuracy={accuracy:.3f}"
        )

        if mismatches:
            logger.info("Mismatches:")
            for mm in mismatches:
                logger.info(
                    f"  - {mm['name']}: expected={mm['expected']}, "
                    f"predicted={mm.get('predicted')}, "
                    f"error={mm.get('error')}"
                )

        return summary


if __name__ == "__main__":
    tester = TradeTypeTester(
        tests_root=r"C:\Users\YOrazayev\Downloads\ocr_train_dataset",
        max_cases=None,  # set to e.g. 20 to limit
    )
    summary = tester.run()
    print("Всего тестов:", summary["total"])
    print("Верных:", summary["correct"])
    print("Accuracy:", round(summary["accuracy"], 3))
    for mm in summary["mismatches"]:
        print(mm)
