import logging
import os

from dotenv import load_dotenv

from src.common.gpt.dmz_client import DMZClient
from src.common.image_preprocessing.image_preprocessor import ImagePreprocessor
from src.common.ocr.ocr import OCR
from src.common.pipeline.adapters.image_preprocessor_adapter import ImagePreprocessAdapter
from src.common.pipeline.adapters.llm_adapter import LLMAdapter
from src.common.pipeline.adapters.ocr_adapter import OCRAdapter
from src.common.pipeline.pipeline import Pipeline
from src.common.pydantic_models.model_combined_json import FbData

# from src.common.gpt.gpt_client import GPTClient

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("main")

BASE_DIR = os.path.dirname(__file__)
TEST_DATA_DIR = os.path.join("/Users/abdiakhmet/Downloads/ocr_train_dataset")


def load_pdf_directory_to_filemap(directory_path: str) -> dict:
    """
    Reads all PDF files from the given directory and returns a file_map
    where keys are filenames and values are file bytes.
    """
    file_map = {}

    for filename in os.listdir(directory_path):
        if filename.lower().endswith(".pdf"):
            full_path = os.path.join(directory_path, filename)
            with open(full_path, "rb") as f:
                file_map[filename] = f.read()

    return file_map


def main():
    # Load an image file from disk
    input_dir_main = "/Users/abdiakhmet/Downloads/test_repatriation/input"
    # input_dir_extra = os.path.join(TEST_DATA_DIR, "case_146994653_checked", "input", "extra")

    file_map_main = load_pdf_directory_to_filemap(input_dir_main)
    file_map_extra = {}

    # Dependency injection for Image Preprocessor
    preprocessor = ImagePreprocessAdapter(
        preprocessor=ImagePreprocessor(denoise=False)
    )
    llm = LLMAdapter(
        client=DMZClient(model="gpt-4.1", temperature=0)
    )

    ocr_adapter = OCRAdapter(OCR())

    client_data = FbData(CLIENT="ТОО \"Network Solutions (Нетворк Солушнс)\"")

    pipeline = Pipeline(
        main_file_dict=file_map_main,
        extra_file_dict=file_map_extra,
        preprocessor_adapter=preprocessor,
        session_id="1",
        llm_adapter=llm,
        debug_mode=True,
        ocr_adapter=ocr_adapter,
        client_data=client_data,
        visualizations_output_dir="/Users/abdiakhmet/Downloads/test_repatriation/vis",
    )

    bbox_json, flat_json, skk_json = pipeline.run()


if __name__ == "__main__":
    main()

    # tester = Tester(base_dir="testing/Контракты на тест октябрь 2025")
    # results = tester.run_all_plain_cases_no_compare()
    #
    # for result in results:
    #     print("\n=== Test Case:", result["Test Case"], "===")
    #     print(f"Accuracy: {result['Hybrid Accuracy']:.2f}")
