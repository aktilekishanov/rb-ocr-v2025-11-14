import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, Optional, List

import yaml

from src.common.extra_fields.DocTypeAssigner import DocTypeAssigner
from src.common.extra_fields.UNAssigner import UNAssigner
from src.common.input_handling.file_handler import FileHandler
from src.common.json_converter.fb_converter import FBConverter
from src.common.json_converter.filepage_remover import FilePageRemover
from src.common.json_converter.final_json_to_eng_converter import ContractExtractionConverter
from src.common.json_converter.indextobboxconverter import IndexToBboxConverter
from src.common.json_converter.repatriation_term_converter import RepatriationTermConverter
from src.common.logger.logger_config import get_logger
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.utils.pipeline_state import PipelineState
from src.common.pipeline.utils.timings import _timed, _count_pages
from src.common.pydantic_models.model_combined_json import IndependentFields, CombinedExtractionModel, CombinedResult, \
    FbData, TradeClientFields, TradeTypeEnum, DependentFields
from src.common.pydantic_models.model_final_json import ContractExtractionResult
from src.contracts.exceptions import PipelineError

logger = get_logger("Pipeline")

with open(
        Path('src/common/gpt/prompts.yml'),
        'r',
        encoding='utf-8',
) as file:
    instructions = yaml.safe_load(file)


class ParsingResultsMapper:
    """
    Maps ParsingResults and ParsingResultsReasoning model to CombinedExtractionModel format.
    """

    # Mapping field names to FieldName enum values
    FIELD_MAPPING = {
        'contract_id': 'Валютный договор',
        'trade_type': 'Тип договора',
        'contract_start_date': 'Дата валютного договора',
        'contract_end_date': 'Дата окончания договора',
        'foreign_party_name': 'Наименование или ФИО контрагента',
        'foreign_party_country': 'Страна контрагента',
        'kazakhstan_party_name': 'Клиент',
        'amount_type': 'Вид суммы договора',
        'contract_currency': 'Валюта договора',
        'contract_summary': 'Описание договора',
        'contract_amount': 'Сумма договора',
        'additional_parties': 'Третьи лица',
        'consignee': 'Грузополучатель',
        'consignor': 'Грузоотправитель',
        'product_manufacturer': 'Производитель',
        'payment_currency': 'Валюта платежа',
        'product_category_code': 'Категория товара',
        'bic_swift': 'БИК/SWIFT',
        'hs_code': 'ТНВЭД код',
        'subject_name': 'Наименование продукта',
        'document_references': 'Ссылки на документы',
        'counterparty_bank_name': 'Наименование банка контрагента',
        'correspondent_bank_name': 'Наименование банка корреспондента',
        'names': 'ФИО',
        'route': 'Маршрут',
        'repatriation_term': 'Срок репатриации',
        'payment_method': 'Способ расчетов по договору',
        'contract_type_code': 'Код вида валютного договора',
        'border_crossing': 'Пересечение РК',
    }

    @staticmethod
    def _convert_occurrences(occurrences) -> Optional[List[dict]]:
        """Convert Occurrence objects to IndexOccurrence format."""
        if not occurrences:
            return None
        return [
            {
                'page': occ.page,
                'index': occ.index
            }
            for occ in occurrences
        ]

    @staticmethod
    def _convert_reference(ref_obj) -> Optional[List[dict]]:
        """Convert Reference object to IndexReference format."""
        if not ref_obj or not hasattr(ref_obj, 'filename'):
            return []  # was: return None

        occurrences = ParsingResultsMapper._convert_occurrences(
            getattr(ref_obj, 'occurrences', None)
        )

        if not occurrences:
            return []  # was: return None

        return [{
            'filename': ref_obj.filename,
            'occurrences': occurrences
        }]

    @classmethod
    def map_to_combined_extraction(
            cls,
            trade_client_fields: TradeClientFields,
            independent_fields: IndependentFields,
            dependent_fields: DependentFields,
    ) -> CombinedExtractionModel:

        fields = []
        combined_result = CombinedResult(
            **trade_client_fields.model_dump(),
            **independent_fields.model_dump(),
            **dependent_fields.model_dump(),
        )
        for field_name, mapped_name in cls.FIELD_MAPPING.items():
            field_obj = getattr(combined_result, field_name, None)

            if field_obj is None:
                fields.append(
                    {
                        'name': mapped_name,
                        'value': None,
                        'confidence': None,
                        'references': [],  # <- use empty list, not None
                    }
                )
                continue

            value = getattr(field_obj, 'value', None)
            if value is not None:
                if field_name in (
                        'payment_method',
                        'payment_currency',
                        'additional_parties',
                        'consignee',
                        'consignor',
                        'product_manufacturer',
                ):
                    value = str(field_obj)

            confidence = getattr(field_obj, 'confidence', None)
            references = cls._convert_reference(field_obj) or []  # <- always a list

            fields.append(
                {
                    'name': mapped_name,
                    'value': value,
                    'confidence': confidence,
                    'references': references,
                }
            )

        result = CombinedExtractionModel(fields=fields)
        return result


class Pipeline:
    def __init__(
            self,
            main_file_dict: dict,
            extra_file_dict: dict,
            session_id: str,
            client_data: FbData,
            llm_adapter: LLMAdapter = None,
            ocr_adapter: OCRAdapter = None,
            preprocessor_adapter: ImagePreprocessAdapter = None,
            visualizations_output_dir: str = None,
            json_output_idr: str = None,
            debug_mode: bool = False,
    ):
        self.main_file_dict = main_file_dict
        self.extra_file_dict = extra_file_dict

        self.llm_adapter = llm_adapter
        self.ocr_adapter = ocr_adapter
        self.preprocessor = preprocessor_adapter

        self.client_data = client_data
        self.session_id = session_id
        self.upscale_factor = preprocessor_adapter.preprocessor.upscale_factor
        self.file_handler = FileHandler(session_id=self.session_id)
        self.visualizations_output_dir = visualizations_output_dir
        self.json_output_idr = json_output_idr
        self.logger = get_logger("pipeline")
        self.debug_mode = debug_mode
        self.fb_converter = FBConverter()
        self.page_remover = FilePageRemover()

    def extract_images(self, file_map):
        return self.file_handler.process_files_in_memory(file_map)

    def preprocess_images(self, outputs):
        return self.preprocessor.preprocess_image_dict(outputs)

    def run_ocr(self, processed_outputs):
        return self.ocr_adapter.run_ocr_on_dict(processed_outputs, self.upscale_factor)

    def to_gpt_text(self, ocr_result):
        return self.ocr_adapter.to_gpt_text(ocr_result)

    def _save_json(self, data, filename):
        """Helper to save JSON to self.json_output_idr"""
        if not self.json_output_idr:
            self.logger.warning("No json_output_idr set, skipping save for %s", filename)
            return
        Path(self.json_output_idr).mkdir(parents=True, exist_ok=True)
        path = os.path.join(self.json_output_idr, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.logger.info("Saved JSON to %s", path)

    def save_csv_stats(self, stats: Dict, filename: str = "run_stats.csv"):
        """Append run stats as a row in a CSV file, keyed by session_id."""
        if not self.json_output_idr:
            self.logger.warning("No json_output_idr set, skipping CSV save")
            return

        Path(self.json_output_idr).mkdir(parents=True, exist_ok=True)
        path = os.path.join(self.json_output_idr, filename)

        # Flatten nested dicts for CSV
        flat = {
            "session_id": stats.get("session_id"),
            "main_files": stats.get("inputs", {}).get("main_files", 0),
            "extra_files": stats.get("inputs", {}).get("extra_files", 0),
            "total_images": stats.get("ocr_counts", {}).get("total_images", 0),
            "total_unique_pages": stats.get("ocr_counts", {}).get("total_unique_pages", 0),
            "extract_s": round(stats.get("extract_s", 0.0), 3),
            "preprocess_s": round(stats.get("preprocess_s", 0.0), 3),
            "ocr_s": round(stats.get("ocr_s", 0.0), 3),
            "gpt_s": round(stats.get("gpt_s", 0.0), 3),
            "total_s": round(stats.get("total_s", 0.0), 3),
        }

        file_exists = os.path.isfile(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(flat.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(flat)

        self.logger.info("Appended run stats to %s", path)

    @staticmethod
    def parse_and_convert(json_output, ocr_result):
        converter = IndexToBboxConverter(ocr_result)
        return converter.convert(json_output)

    @staticmethod
    def merge_and_sort_fields(json1: Dict, json2: Dict) -> Dict:
        """Merge two dicts with structure { "fields": [...] } and sort by 'name'."""
        combined_fields = json1.get("fields", []) + json2.get("fields", [])
        sorted_fields = sorted(combined_fields, key=lambda x: x.get("name", ""))
        return {"fields": sorted_fields}

    @staticmethod
    def merge_ocr_results(result1: Dict, result2: Dict) -> Dict:
        merged = result1.copy()
        for k, v in result2.items():
            if k in merged and isinstance(v, dict) and isinstance(merged[k], dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged

    def run(self):

        try:

            if self.json_output_idr:
                Path(self.json_output_idr).mkdir(parents=True, exist_ok=True)

            st = PipelineState(
                session_id=self.session_id,
                file_map_main=self.main_file_dict,
                file_map_extra=self.extra_file_dict,
            )

            self.logger.info(f"Main files: {list(st.file_map_main.keys())}")
            self.logger.info(f"Extra files: {list(st.file_map_extra.keys())}")

            stats: Dict[str, object] = {
                "session_id": self.session_id,
                "inputs": {
                    "main_files": len(st.file_map_main or {}),
                    "extra_files": len(st.file_map_extra or {}),
                }
            }

            t_total = time.time()

            # 1) extract
            with _timed(stats, "extract_s"):
                st.outputs_main = self.extract_images(st.file_map_main)
                st.outputs_extra = self.extract_images(st.file_map_extra)

            # 2) preprocess
            with _timed(stats, "preprocess_s"):
                st.processed_main = self.preprocess_images(st.outputs_main)
                st.processed_extra = self.preprocess_images(st.outputs_extra)

            # 3) OCR
            with _timed(stats, "ocr_s"):
                ocr_result_main = self.run_ocr(st.processed_main)
                ocr_text_main = self.to_gpt_text(ocr_result_main)
                ocr_result_extra = self.run_ocr(st.processed_extra)
                ocr_text_extra = self.to_gpt_text(ocr_result_extra)

            st.ocr_result_main, st.ocr_result_extra = ocr_result_main, ocr_result_extra
            st.ocr_texts = ocr_text_main + "\n\n" + ocr_text_extra

            # Counts after OCR
            main_counts = _count_pages(ocr_result_main)
            extra_counts = _count_pages(ocr_result_extra)
            stats["ocr_counts"] = {
                "main": main_counts,
                "extra": extra_counts,
                "total_images": main_counts["total_images"] + extra_counts["total_images"],
                "total_unique_pages": main_counts["unique_pages"] + extra_counts["unique_pages"],
            }

            # 4) ========= LLM calls with structured output (retries handled by DMZClient) =======

            # Dependent fields (Dependent on Trade Type)
            def _parse_dependent_fields():
                # Trade type + Kazakhstan Party prompt call
                with _timed(stats, "gpt_contract_type_and_client_s"):
                    # Inject client value from client data
                    client_gt = self.client_data.CLIENT
                    logger.info(f"Injected client {client_gt}")
                    # Init prompts
                    system_prompt = instructions["dependent_fields"]["contract_type"]
                    user_prompt = st.ocr_texts + f"\n\n\n Determine if this client is exporting or importing in above contract: {client_gt}. Then determine the correctness of the client: {client_gt}"
                    trade_type_client = self.llm_adapter.send(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=TradeClientFields,
                        model='gpt-4.1',
                        temperature=0.0,
                    )
                with _timed(stats, "gpt_dependent_s"):
                    if trade_type_client.trade_type.value == TradeTypeEnum.EXPORT:
                        system_prompt = instructions["dependent_fields"]["dependent_fields_export"]
                        logger.info("Dependent prompt sent. Export prompt used")
                    else:
                        system_prompt = instructions["dependent_fields"]["dependent_fields_import"]
                        logger.info("Dependent prompt sent. Import prompt used")

                    user_prompt = st.ocr_texts + f"\n\n CLIENT: {client_gt}"
                    dependent_fields =  self.llm_adapter.send(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=DependentFields,
                        model='gpt-4.1',
                        temperature=0.0,
                    )
                return trade_type_client, dependent_fields

            def _parse_independent_fields():
                with _timed(stats, "gpt_independent_s"):
                    contract_number_gt = self.client_data.CURRENCY_CONTRACT_NUMBER
                    logger.info(f"Independent contract sent. Injected contract number {contract_number_gt}")

                    system_prompt = instructions["independent_fields"]["system_prompt"]
                    user_prompt = st.ocr_texts + f"\n\n USER_CONTRACT_ID: {contract_number_gt}"
                    return self.llm_adapter.send(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_model=IndependentFields,
                    )

            with _timed(stats, "gpt_fields_parallel"):
                with ThreadPoolExecutor(max_workers=2) as executor:
                    dependent_future = executor.submit(_parse_dependent_fields)
                    independent_future = executor.submit(_parse_independent_fields)

                    trade_type_client, dependent_fields = dependent_future.result()
                    independent_fields = independent_future.result()

            # logger.info("Independent fields JSON:\n%s", json.dumps(independent_fields.model_dump(mode="json"), indent=2, ensure_ascii=False))

            # 6) Merge OCR (for bbox mapping)
            st.ocr_bbox_data = self.merge_ocr_results(st.ocr_result_main, st.ocr_result_extra)

            # 7) Merge 3 Prompt results into one dict
            validated = ParsingResultsMapper.map_to_combined_extraction(
                trade_client_fields=trade_type_client,
                independent_fields=independent_fields,
                dependent_fields=dependent_fields,
            ).model_dump(mode="json")

            # logger.info("Validated JSON:\n%s", json.dumps(validated, indent=2, ensure_ascii=False))

            # 7.1) clipping: enforce value length limit (250 chars)
            for field in validated.get("fields", []):
                val = field.get("value")
                if isinstance(val, str):
                    field["value"] = val[:250]
                elif isinstance(val, list):
                    field["value"] = [
                        v[:250] if isinstance(v, str) else v
                        for v in val
                    ]
                # if None → leave untouched

            # 7.2) Final combined + clipped output
            st.combined_json_output = validated

            # 8) Index → bbox
            st.bbox_final_json = self.parse_and_convert(st.combined_json_output, st.ocr_bbox_data)

            # 9) Extra fields
            try:
                st.bbox_final_json = UNAssigner.assign_account_number(st.bbox_final_json)
                st.bbox_final_json = DocTypeAssigner.assign_doc_type(st.bbox_final_json)
            except Exception as e:
                logger.warning(f"Failed to assign UN and DocType: {e}")

            # 10) Final validation
            st.bbox_final_json = ContractExtractionResult.model_validate(st.bbox_final_json).model_dump()

            # logger.info("Bbox JSON:\n%s", json.dumps(st.bbox_final_json, indent=2, ensure_ascii=False))

            # 11) Convert Repatriation term to correct format
            repatriation_converter = RepatriationTermConverter()
            st.bbox_final_json = repatriation_converter.process(st.bbox_final_json)

            # ------- No more modification of values -----------

            # 12) FB flatten
            st.fb_flat_json = self.fb_converter.flatten_and_translate(st.bbox_final_json)

            # Totals
            stats["total_s"] = time.time() - t_total

            # # 13) Debug / visualize
            # if self.debug_mode:
            #     self._save_json(st.ocr_bbox_data, "ocr_bbox_data.json")
            #     self._save_json(st.combined_json_output, "combined_gpt_output.json")
            #     self._save_json(st.fb_flat_json, "fb_flat.json")
            #     self._save_json(stats, "run_stats.json")
            #     visualize_bboxes_per_field(
            #         st.bbox_final_json,
            #         {**(st.outputs_extra or {}), **(st.outputs_main or {})},
            #         self.visualizations_output_dir
            #     )
            # self.save_csv_stats(stats)

            # 14) Post-process remove filenames
            st.bbox_final_json = self.page_remover.remove_page_suffixes(st.bbox_final_json)

            # 15) ENG view
            st.eng_bbox_final = ContractExtractionConverter.to_eng_bbox_final(st.bbox_final_json)

            # if self.debug_mode:
            #     self._save_json(st.eng_bbox_final, "eng_bbox_final.json")

            # Pretty log
            self.logger.info(
                "\nRun stats "
                "\n├── total: %.2fs "
                "\n├── preprocess: %.2fs "
                "\n├── ocr: %.2fs "
                "\n├── gpt-contract-type-and-client: %.2fs "
                "\n├── gpt-dependent-fields: %.2fs "
                "\n├── gpt-independent-fields: %.2fs "
                "\n├── gpt-fields-parallel: %.2fs "
                "\n└── images: %d, pages: %d",
                stats.get("total_s", 0.0),
                stats.get("preprocess_s", 0.0),
                stats.get("ocr_s", 0.0),
                stats.get("gpt_contract_type_and_client_s", 0.0),
                stats.get("gpt_dependent_s", 0.0),
                stats.get("gpt_independent_s", 0.0),
                stats.get("gpt_fields_parallel", 0.0),
                stats["ocr_counts"]["total_images"],
                stats["ocr_counts"]["total_unique_pages"],
            )

            # Return stats as a 3rd value
            return st.eng_bbox_final, st.fb_flat_json, st.skk_fields


        except Exception as e:
            logger.error(f"PipelineError: {e}", exc_info=True)
            raise PipelineError(e)
