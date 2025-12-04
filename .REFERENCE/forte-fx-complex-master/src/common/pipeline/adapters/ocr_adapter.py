class OCRAdapter:
    def __init__(self, ocr):
        self.ocr = ocr

    def run_ocr_on_dict(self, processed_outputs, upscale_factor):
        return self.ocr.run_ocr_on_dict(processed_outputs, upscale_factor)

    def to_gpt_text(self, ocr_result):
        return self.ocr.to_gpt_text(ocr_result)