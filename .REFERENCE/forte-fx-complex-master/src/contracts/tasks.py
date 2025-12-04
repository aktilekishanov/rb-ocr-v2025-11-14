import asyncio
import logging

from src.common.callback import send_callback
from src.common.compliance_control import get_compliance_data
from src.common.file_s3 import load_entries_from_s3
from src.common.gpt.dmz_client import DMZClient
from src.common.image_preprocessing.image_preprocessor import ImagePreprocessor
from src.common.ocr.ocr import OCR
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.pipeline import Pipeline
from src.common.pydantic_models.model_combined_json import FbData
from src.common.similarity_check.similarity_checker import SimilarityChecker
from src.contracts.service import ContractService
from src.core.celery_app import celery_app
from src.core.database import SessionLocal
from src.core.s3 import S3Client

logger = logging.getLogger(__name__)


@celery_app.task(queue="contracts")
def process_document_task(document_id: str, main_path: list, optional_paths: list):
    logger.info(f"[{document_id}] Начата обработка документа")

    async def _worker():
        async with SessionLocal() as session:
            service = ContractService(session, storage_client=S3Client())

            try:
                fb_data_raw = await service.get_fb_data(document_id)
                fb_data = FbData.from_dict(fb_data_raw)
                fb_data_for_compare = fb_data.as_dict()

                preprocessor = ImagePreprocessAdapter(
                    preprocessor=ImagePreprocessor(denoise=False, upscale_factor=1.2, contrast=1.2)
                )
                llm = LLMAdapter(
                    client=DMZClient(model="gpt-4.1", temperature=0.1)
                )
                ocr_adapter = OCRAdapter(
                    ocr=OCR()
                )
                # Run your OCR→GPT pipeline
                extractor = Pipeline(
                    main_file_dict=load_entries_from_s3(main_path),
                    extra_file_dict=load_entries_from_s3(optional_paths),
                    preprocessor_adapter=preprocessor,
                    session_id=document_id,
                    llm_adapter=llm,
                    ocr_adapter=ocr_adapter,
                    client_data=fb_data,
                )
                raw, fb_json, skk_json = extractor.run()

                cross_check_json = SimilarityChecker().compare(fb_data_for_compare, fb_json)
                # Persist a result and mark ready
                await service.save_document_results(document_id=document_id, result_json=raw, flat_result_json=fb_json,
                                                    cross_check_json=cross_check_json)
                # await service.update_status(document_id, "ready")
                logger.info(f"[{document_id}] Документ успешно обработан, status=ready")

                # Notify service
                compliance_data = get_compliance_data(document_id, fb_json)
                await service.save_compliance_check(document_id, compliance_data)
                send_callback(document_id, fb_json)

                logger.info(f"[{document_id}] Callback отправлен: ready")

            except Exception as e:
                err_msg = str(e)
                logger.exception(f"[{document_id}] Ошибка обработки: {err_msg}")

                # Persist empty result + error, mark error
                await service.save_document_results(document_id, {}, error=err_msg)

    # run the coroutine to completion so Celery sees a normal return
    asyncio.get_event_loop().run_until_complete(_worker())
    return None
