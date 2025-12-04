import os
import json
import glob
import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv
from rapidfuzz import fuzz

from src.common.gpt.gpt_client import GPTClient
from src.common.gpt.prompt_builder import PromptSpec
from src.common.gpt.prompts import system_prompt, general_instructions, main_docs_prompt, chain_of_thought, \
    extra_docs_prompt, reasoning_fields_prompt
from src.common.image_preprocessing.image_preprocessor import ImagePreprocessor
from src.common.ocr.ocr import OCR
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.pipeline import Pipeline

# === Logging setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("tester")

# === Matching config ===
MATCHING_STRATEGIES: Dict[str, str] = {
    "Валютный договор": "exact",
    "Тип договора": "exact",
    "Дата валютного договора": "exact",
    "Дата окончания договора": "exact",
    "Наименование или ФИО контрагента": "fuzzy",
    "Страна контрагента": "exact",
    "Клиент": "fuzzy",
    "Третьи лица": "fuzzy",
    "Грузополучатель": "fuzzy",
    "Грузоотправитель": "fuzzy",
    "Производитель": "fuzzy",
    "Вид суммы договора": "exact",
    "Валюта договора": "exact",
    "Валюта платежа": "exact",
    "Срок репатриации": "exact",
    "Способ расчетов по договору": "exact",
    "Код вида валютного договора": "exact",
    "Категория товара": "exact",
    "БИК/SWIFT": "exact",
    "ТНВЭД код": "exact",
    "Наименование продукта": "ignore",
    "Описание договора": "ignore",
    "Пересечение РК": "fuzzy",
    "Ссылки на документы": "ignore",
    "Сумма договора": "fuzzy",
    "Присвоение УН": "ignore",
    "Тип договора для учетной системы": "ignore",
}

# === Helpers ===
def load_pdf_directory_to_filemap(directory_path: str) -> Dict[str, bytes]:
    """
    Reads all PDF files from the given directory and returns a file_map
    where keys are filenames and values are file bytes.
    """
    file_map: Dict[str, bytes] = {}
    if not os.path.isdir(directory_path):
        return file_map
    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".pdf"):
            full_path = os.path.join(directory_path, filename)
            with open(full_path, "rb") as f:
                file_map[filename] = f.read()
    return file_map


def normalize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(sorted(str(v).strip().lower() for v in value if v is not None))
    return str(value).strip().lower()


def flatten_pipeline_output(output_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for item in output_fields:
        name = item.get("name")
        value = item.get("value")
        if name is None:
            continue
        flat[name] = value
    return flat


def numeric_key(name: str) -> int:
    # Extract numeric prefix for sorting; fallback to 0 if not found
    parts = name.split()
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return 0


def compute_similarities(
    expected: Dict[str, Any],
    output: Dict[str, Any],
    match_config: Dict[str, str],
) -> Tuple[pd.DataFrame, List[Dict[str, Any]], float, float, float]:
    all_keys = list(expected.keys()) + [k for k in output.keys() if k not in expected]

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for key in all_keys:
        expected_val = normalize(expected.get(key))
        output_val = normalize(output.get(key))
        method = match_config.get(key, "fuzzy")

        simple_match = expected_val == output_val
        fuzz_score = fuzz.ratio(expected_val, output_val) / 100 if (expected_val or output_val) else 1.0

        if method == "ignore":
            match = True
        elif method == "exact":
            match = simple_match
        elif method == "fuzzy":
            match = fuzz_score >= 0.60
        else:
            match = False

        if not match and method != "ignore":
            errors.append({
                "Key": key,
                "Expected": expected_val,
                "Actual": output_val,
                "Fuzz Score": round(fuzz_score, 2),
                "Simple Match": simple_match
            })

        results.append({
            "Key": key,
            "Expected": expected_val,
            "Actual": output_val,
            "Matching Strategy": method,
            "Simple Score": round(1.0 if simple_match else 0.0, 2),
            "Fuzz Score": round(fuzz_score, 2),
            "Hybrid Score": round(1.0 if match else 0.0, 2),
            "Match": match
        })

    df = pd.DataFrame(results)
    return (
        df,
        errors,
        round(df["Simple Score"].mean(), 2),
        round(df["Fuzz Score"].mean(), 2),
        round(df["Hybrid Score"].mean(), 2),
    )

# === Tester class with single-case support ===
class Tester:

    def __init__(self, base_dir: str = "testing/data/", config_path: str = "configs/preprocesser_config.json"):

        self.base_dir = base_dir
        self.config_path = config_path

        # Per-run collectors (reset for each _run_cases call)
        self._overall_results: List[Dict[str, Any]] = []
        self._mismatch_counter: Dict[str, int] = {}
        self._mismatch_instances: List[Dict[str, Any]] = []

    # ---------- Public entrypoints ----------
    def run_all_tests(self) -> List[Dict[str, Any]]:
        """Runs all valid case folders under base_dir."""
        case_list = self._discover_case_folders()
        if not case_list:
            logger.error(f"No valid test cases found under {self.base_dir}. Each case must have expected/*.json.")
            return []
        return self._run_cases(case_list)

    def run_single_case(self, case_name: str) -> List[Dict[str, Any]]:
        """
        Runs only a single case by folder name, keeping base_dir pointing to the parent folder.
        Example: tester.run_single_case("19 (вк)")
        """
        case_path = os.path.join(self.base_dir, case_name)
        if not os.path.isdir(case_path):
            raise FileNotFoundError(f"Case folder not found: {case_path}")

        if not self._is_case_folder(case_path):
            raise FileNotFoundError(
                f"Case '{case_name}' is missing expected JSON at {case_path}/expected/*.json"
            )

        return self._run_cases([case_name])

    # ---------- Internal helpers ----------
    def _discover_case_folders(self) -> List[str]:
        candidates = sorted(os.listdir(self.base_dir), key=numeric_key)
        return [c for c in candidates if self._is_case_folder(os.path.join(self.base_dir, c))]

    @staticmethod
    def _is_case_folder(case_path: str) -> bool:
        if not os.path.isdir(case_path):
            return False
        expected_dir = os.path.join(case_path, "expected")
        return bool(glob.glob(os.path.join(expected_dir, "*.json")))

    def _run_cases(self, case_list: List[str]) -> List[Dict[str, Any]]:
        # reset collectors for each run
        self._overall_results = []
        self._mismatch_counter = {}
        self._mismatch_instances = []

        for case in case_list:
            try:
                res = self._run_one_case(case)
                if isinstance(res, dict):
                    self._overall_results.append(res)
            except Exception as e:
                logger.error(f"Test case {case} failed: {e}")

        # Write summaries & print
        self._write_summaries()

        return self._overall_results

    def _run_one_case(self, case: str) -> Optional[Dict[str, Any]]:
        case_path = os.path.join(self.base_dir, case)
        input_main = os.path.join(case_path, "input", "main")
        input_extra = os.path.join(case_path, "input", "extra")
        expected_dir = os.path.join(case_path, "expected")
        expected_files = glob.glob(os.path.join(expected_dir, "*.json"))
        if not expected_files:
            logger.warning(f"Skipping test case {case}: No expected JSON found.")
            return None

        expected_path = expected_files[0]
        try:
            file_map_main = load_pdf_directory_to_filemap(input_main)
            file_map_extra = load_pdf_directory_to_filemap(input_extra)

            prompts = [
                PromptSpec(
                    key="main_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=main_docs_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="main",
                ),
                PromptSpec(
                    key="extra_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=extra_docs_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="both",
                ),
                PromptSpec(
                    key="reasoning_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=reasoning_fields_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="both",
                ),
            ]


            # Dependency injection for Image Preprocessor
            preprocessor = ImagePreprocessAdapter(
                ImagePreprocessor(denoise=False)
            )
            llm = LLMAdapter(
                client=GPTClient(model="gpt-4.1", temperature=0.1)
            )

            ocr = OCRAdapter(ocr = OCR())

            pipeline = Pipeline(
                main_file_dict=file_map_main,
                extra_file_dict=file_map_extra,
                preprocessor_adapter=preprocessor,
                session_id="run001",
                prompts=prompts,
                ocr_adapter=ocr,
                llm_adapter=llm,
                debug_mode=True,
                visualizations_output_dir=os.path.join(case_path, "visualizations"),
                json_output_idr=os.path.join(case_path, "json"),
            )

            logger.info(f"Running test case {case}...")

            raw_response, _, _ = pipeline.run()

            # Parse model output (string or dict)
            if isinstance(raw_response, dict):
                parsed_json = raw_response
            else:
                if not raw_response:
                    raise ValueError("Empty GPT response (None or empty string returned).")
                raw_response = raw_response.strip()
                if raw_response.startswith("```json"):
                    raw_response = raw_response.removeprefix("```json").strip("` \n")
                parsed_json = json.loads(raw_response)

            # Persist raw/actual output for inspection
            with open(os.path.join(case_path, "actual_gpt.json"), "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, ensure_ascii=False, indent=2)

            # Expected JSON (note: here we use raw expected keys directly)
            with open(expected_path, "r", encoding="utf-8") as f:
                raw_expected = json.load(f)

            # If you want Pydantic validation & English-key conversion, uncomment:
            # expected_model = ContractExtractionResult(**raw_expected)
            # expected_english = ContractExtractionConverter.to_english_dict(expected_model)
            # expected_dict = flatten_pipeline_output(expected_english["fields"])
            # But your compute currently expects raw_expected dict of keys->values:
            parsed_response = flatten_pipeline_output(parsed_json["fields"])

            # Compare
            df, errors, simple_acc, fuzz_acc, hybrid_acc = compute_similarities(
                raw_expected, parsed_response, MATCHING_STRATEGIES
            )

            # Track mismatches
            for e in errors:
                self._mismatch_instances.append({"Test Case": case, **e})
                self._mismatch_counter[e["Key"]] = self._mismatch_counter.get(e["Key"], 0) + 1

            # Append summary row to per-case CSV
            summary_row = pd.DataFrame([{
                "Key": "== ACCURACY ==",
                "Expected": "",
                "Actual": "",
                "Matching Strategy": "",
                "Simple Score": simple_acc,
                "Fuzz Score": fuzz_acc,
                "Hybrid Score": hybrid_acc,
                "Match": ""
            }])
            df = pd.concat([df, summary_row], ignore_index=True)
            df.to_csv(os.path.join(case_path, "comparison_table_gpt.csv"), index=False, encoding="utf-8-sig")

            logger.info(f"[{case}] Simple: {simple_acc:.2f}, Fuzz: {fuzz_acc:.2f}, Hybrid: {hybrid_acc:.2f}")

            return {
                "Test Case": case,
                "Simple Accuracy": simple_acc,
                "RapidFuzz Accuracy": fuzz_acc,
                "Hybrid Accuracy": hybrid_acc
            }

        except Exception as e:
            logger.error(f"Test case {case} failed: {e}")
            return None

    def _write_summaries(self) -> None:
        """Writes overall summaries under base_dir and prints to stdout."""
        if not self._overall_results:
            logger.error("No cases completed; nothing to summarize.")
            return

        # Summary CSV
        summary_df = pd.DataFrame(self._overall_results)
        # Be robust to NaNs and missing columns
        simple_mean = pd.to_numeric(summary_df.get("Simple Accuracy"), errors="coerce").mean()
        fuzz_mean = pd.to_numeric(summary_df.get("RapidFuzz Accuracy"), errors="coerce").mean()
        hybrid_mean = pd.to_numeric(summary_df.get("Hybrid Accuracy"), errors="coerce").mean()

        avg_row = {
            "Test Case": "== AVERAGE ==",
            "Simple Accuracy": round(simple_mean, 2) if pd.notna(simple_mean) else None,
            "RapidFuzz Accuracy": round(fuzz_mean, 2) if pd.notna(fuzz_mean) else None,
            "Hybrid Accuracy": round(hybrid_mean, 2) if pd.notna(hybrid_mean) else None
        }
        summary_df = pd.concat([summary_df, pd.DataFrame([avg_row])], ignore_index=True)
        summary_df.to_csv(os.path.join(self.base_dir, "summary_refactored_prompt.csv"), index=False, encoding="utf-8-sig")

        # Mismatch stats
        if self._mismatch_instances:
            pd.DataFrame(self._mismatch_instances).to_csv(
                os.path.join(self.base_dir, "mismatch_instances.csv"), index=False, encoding="utf-8-sig"
            )

        if self._mismatch_counter:
            mismatch_df = pd.DataFrame(
                [{"Key": key, "Mismatch Count": count} for key, count in self._mismatch_counter.items()]
            )
            mismatch_df.to_csv(os.path.join(self.base_dir, "mismatch_stats.csv"), index=False, encoding="utf-8-sig")
        else:
            mismatch_df = pd.DataFrame(columns=["Key", "Mismatch Count"])

        # Print to console
        print("\n=== Final Summary ===")
        print(summary_df.to_string(index=False))
        print("\n=== Most Frequent Mismatches ===")
        if not mismatch_df.empty:
            print(mismatch_df.to_string(index=False))
        else:
            print("(none)")

    # ---------- Run WITHOUT expected/ comparison ----------
    def run_all_cases_no_compare(self) -> List[Dict[str, Any]]:
        """
        Runs every folder under base_dir that looks like a case (has input/main or input/extra),
        without requiring expected/*.json and WITHOUT computing any accuracy.
        """
        case_list = self._discover_case_folders_without_expected()
        if not case_list:
            logger.error(f"No runnable test cases found under {self.base_dir}. "
                         f"Each case must have input/main or input/extra.")
            return []
        return self._run_cases_no_compare(case_list)

    def run_single_case_no_compare(self, case_name: str) -> List[Dict[str, Any]]:
        """
        Runs a single case by folder name, WITHOUT comparison to expected.
        Example: tester.run_single_case_no_compare("19 (вк)")
        """
        case_path = os.path.join(self.base_dir, case_name)
        if not os.path.isdir(case_path):
            raise FileNotFoundError(f"Case folder not found: {case_path}")

        if not self._has_input_payload(case_path):
            raise FileNotFoundError(
                f"Case '{case_name}' is missing input payload at {case_path}/input/main or input/extra"
            )

        return self._run_cases_no_compare([case_name])

    def _discover_case_folders_without_expected(self) -> List[str]:
        """
        Finds runnable cases by presence of input files only (input/main or input/extra).
        Does NOT require expected/*.json.
        """
        candidates = sorted(os.listdir(self.base_dir), key=numeric_key)
        runnable: List[str] = []
        for c in candidates:
            case_path = os.path.join(self.base_dir, c)
            if os.path.isdir(case_path) and self._has_input_payload(case_path):
                runnable.append(c)
        return runnable

    @staticmethod
    def _has_input_payload(case_path: str) -> bool:
        """
        Returns True if the case has at least one of:
          - {case}/input/main/*.pdf
          - {case}/input/extra/*.pdf
        """
        input_main = os.path.join(case_path, "input", "main")
        input_extra = os.path.join(case_path, "input", "extra")
        def has_pdfs(p): return os.path.isdir(p) and any(
            f.lower().endswith(".pdf") for f in os.listdir(p)
        )
        return has_pdfs(input_main) or has_pdfs(input_extra)

    def _run_cases_no_compare(self, case_list: List[str]) -> List[Dict[str, Any]]:
        """
        Internal runner that executes the pipeline and persists output JSON only.
        Returns a list of per-case status dicts.
        """
        results: List[Dict[str, Any]] = []
        for case in case_list:
            try:
                status = self._run_one_case_no_compare(case)
                if isinstance(status, dict):
                    results.append(status)
            except Exception as e:
                logger.error(f"Test case {case} failed (no-compare): {e}")
                results.append({"Test Case": case, "Status": "error", "Error": str(e)})
        return results

    def _run_one_case_no_compare(self, case: str) -> Optional[Dict[str, Any]]:
        """
        Runs a single case WITHOUT loading expected/*.json and WITHOUT comparison.
        Saves parsed JSON to {case}/actual_gpt.json and raw response to {case}/raw_response.txt.
        """
        case_path = os.path.join(self.base_dir, case)
        input_main = os.path.join(case_path, "input", "main")
        input_extra = os.path.join(case_path, "input", "extra")

        try:
            file_map_main = load_pdf_directory_to_filemap(input_main)
            file_map_extra = load_pdf_directory_to_filemap(input_extra)

            # Use same prompts you already defined in _run_one_case
            prompts = [
                PromptSpec(
                    key="main_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=main_docs_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="main",
                ),
                PromptSpec(
                    key="extra_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=extra_docs_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="both",
                ),
                PromptSpec(
                    key="reasoning_docs",
                    system_prompt=system_prompt,
                    general_instructions=general_instructions,
                    docs_prompt=reasoning_fields_prompt,
                    chain_of_thought=chain_of_thought,
                    ocr_sources="both",
                ),
            ]

            preprocessor = ImagePreprocessAdapter(ImagePreprocessor(denoise=False))
            llm = LLMAdapter(client=GPTClient(model="gpt-4.1", temperature=0.1))
            ocr = OCRAdapter(ocr=OCR())

            pipeline = Pipeline(
                main_file_dict=file_map_main,
                extra_file_dict=file_map_extra,
                preprocessor_adapter=preprocessor,
                session_id="run001",
                prompts=prompts,
                ocr_adapter=ocr,
                llm_adapter=llm,
                debug_mode=True,
                visualizations_output_dir=os.path.join(case_path, "visualizations"),
                json_output_idr=os.path.join(case_path, "json"),  # keeping your original param name
            )

            logger.info(f"(no-compare) Running test case {case}...")

            raw_response, _, _ = pipeline.run()

            # Persist raw response text for debugging
            try:
                with open(os.path.join(case_path, "raw_response.txt"), "w", encoding="utf-8") as ftxt:
                    ftxt.write("" if raw_response is None else str(raw_response))
            except Exception as e:
                logger.warning(f"[{case}] Could not save raw_response.txt: {e}")

            # Parse model output to JSON and save
            if isinstance(raw_response, dict):
                parsed_json = raw_response
            else:
                if not raw_response:
                    raise ValueError("Empty GPT response (None or empty string returned).")
                txt = str(raw_response).strip()
                if txt.startswith("```json"):
                    txt = txt.removeprefix("```json").strip("` \n")
                parsed_json = json.loads(txt)

            out_path = os.path.join(case_path, "actual_gpt.json")
            with open(out_path, "w", encoding="utf-8") as fjson:
                json.dump(parsed_json, fjson, ensure_ascii=False, indent=2)

            logger.info(f"(no-compare) [{case}] Output saved to {out_path}")

            return {
                "Test Case": case,
                "Status": "ok",
                "Output Path": out_path,
            }

        except Exception as e:
            logger.error(f"(no-compare) Test case {case} failed: {e}")
            return {"Test Case": case, "Status": "error", "Error": str(e)}

    def run_all_plain_cases_no_compare(self) -> List[Dict[str, Any]]:
        """
        Runs every case folder under self.base_dir where contracts (PDFs) are placed directly
        in the case root (i.e., {case}/*.pdf), WITHOUT requiring expected/*.json and WITHOUT
        computing any accuracy.

        For each qualifying case:
          - Loads PDFs from the case root into main_file_dict
          - Leaves extra_file_dict empty
          - Executes the pipeline
          - Writes:
              * {case}/raw_response.txt
              * {case}/actual_gpt.json

        Returns:
            List[Dict[str, Any]]: Per-case status dicts with keys:
                - "Test Case": case folder name
                - "Status": "ok" | "error"
                - "Output Path": path to actual_gpt.json (when ok)
                - "Error": error message (when error)
        """
        results: List[Dict[str, Any]] = []

        # Discover only folders that have PDFs directly in the case root
        try:
            candidates = sorted(os.listdir(self.base_dir), key=numeric_key)
        except Exception as e:
            logger.error(f"Could not list base_dir '{self.base_dir}': {e}")
            return results

        for case in candidates:
            case_path = os.path.join(self.base_dir, case)
            if not os.path.isdir(case_path):
                continue

            # Check for plain layout: {case}/*.pdf
            try:
                pdf_names = [f for f in os.listdir(case_path) if f.lower().endswith(".pdf")]
            except Exception as e:
                logger.warning(f"Skipping {case_path}: could not list directory ({e})")
                continue

            if not pdf_names:
                # No plain PDFs in the case root; skip
                continue

            try:
                # Load PDFs from the case root as "main" docs; no "extra" docs in plain layout
                file_map_main = load_pdf_directory_to_filemap(case_path)
                file_map_extra: Dict[str, bytes] = {}

                # Prompts (reuse your existing prompt specs)
                prompts = [
                    PromptSpec(
                        key="main_docs",
                        system_prompt=system_prompt,
                        general_instructions=general_instructions,
                        docs_prompt=main_docs_prompt,
                        chain_of_thought=chain_of_thought,
                        ocr_sources="main",
                    ),
                    PromptSpec(
                        key="extra_docs",
                        system_prompt=system_prompt,
                        general_instructions=general_instructions,
                        docs_prompt=extra_docs_prompt,
                        chain_of_thought=chain_of_thought,
                        ocr_sources="both",
                    ),
                    PromptSpec(
                        key="reasoning_docs",
                        system_prompt=system_prompt,
                        general_instructions=general_instructions,
                        docs_prompt=reasoning_fields_prompt,
                        chain_of_thought=chain_of_thought,
                        ocr_sources="both",
                    ),
                ]

                # Adapters / clients (reuse your existing stack)
                preprocessor = ImagePreprocessAdapter(ImagePreprocessor(denoise=False))
                llm = LLMAdapter(client=GPTClient(model="gpt-4.1", temperature=0.1))
                ocr = OCRAdapter(ocr=OCR())

                pipeline = Pipeline(
                    main_file_dict=file_map_main,
                    extra_file_dict=file_map_extra,
                    preprocessor_adapter=preprocessor,
                    session_id="run001",
                    prompts=prompts,
                    ocr_adapter=ocr,
                    llm_adapter=llm,
                    debug_mode=True,
                    visualizations_output_dir=os.path.join(case_path, "visualizations"),
                    json_output_idr=os.path.join(case_path, "json"),  # keep your original param name
                )

                logger.info(f"(no-compare/plain) Running test case {case}...")

                raw_response, _, _ = pipeline.run()

                # Persist raw response text for debugging
                try:
                    with open(os.path.join(case_path, "raw_response.txt"), "w", encoding="utf-8") as ftxt:
                        ftxt.write("" if raw_response is None else str(raw_response))
                except Exception as e:
                    logger.warning(f"[{case}] Could not save raw_response.txt: {e}")

                # Parse model output to JSON and save
                if isinstance(raw_response, dict):
                    parsed_json = raw_response
                else:
                    if not raw_response:
                        raise ValueError("Empty GPT response (None or empty string returned).")
                    txt = str(raw_response).strip()
                    if txt.startswith("```json"):
                        txt = txt.removeprefix("```json").strip("` \n")
                    parsed_json = json.loads(txt)

                out_path = os.path.join(case_path, "actual_gpt.json")
                with open(out_path, "w", encoding="utf-8") as fjson:
                    json.dump(parsed_json, fjson, ensure_ascii=False, indent=2)

                logger.info(f"(no-compare/plain) [{case}] Output saved to {out_path}")

                results.append({
                    "Test Case": case,
                    "Status": "ok",
                    "Output Path": out_path,
                })

            except Exception as e:
                logger.error(f"(no-compare/plain) Test case {case} failed: {e}")
                results.append({
                    "Test Case": case,
                    "Status": "error",
                    "Error": str(e),
                })

        if not results:
            logger.warning("No plain-layout cases were found under base_dir or all were skipped.")

        return results
