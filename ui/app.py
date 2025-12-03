"""
Streamlit UI for the RB loan deferment IDP (main-dev).

Provides a single-page interface for uploading a document, collecting
contextual metadata (FIO), invoking the FastAPI service, and rendering results.
"""

import json
import os
import requests
import streamlit as st
from typing import Optional

# --- Configuration ---
# Use the Nginx domain URL for production/dev environment
DEFAULT_API_URL = "http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api"
API_URL = os.getenv("FASTAPI_SERVICE_URL", DEFAULT_API_URL)
VERIFY_ENDPOINT = f"{API_URL}/v1/verify"

# --- Page setup ---
st.set_page_config(page_title="[DEV] RB Loan Deferment IDP", layout="centered")

st.write("")
st.title("[DEV] RB Loan Deferment IDP")
st.write("Загрузите один файл для распознавания (OCR (Tesseract async, Dev-OCR) & LLM (DMZ))")

# --- Simple CSS tweaks ---
st.markdown(
    """
<style>
.block-container{max-width:980px;padding-top:1.25rem;}
.meta{color:#6b7280;font-size:0.92rem;margin:0.25rem 0 1rem 0;}
.meta code{background:#f3f4f6;border:1px solid #e5e7eb;padding:2px 6px;border-radius:6px;}
.card{border:1px solid #e5e7eb;border-radius:14px;background:#ffffff;box-shadow:0 2px 8px rgba(0,0,0,.04);}
.card.pad{padding:22px;}
.result-card{border:1px solid #e5e7eb;border-radius:14px;padding:16px;background:#fafafa;}
.stButton>button{border-radius:10px;padding:.65rem 1rem;font-weight:600;}
.stDownloadButton>button{border-radius:10px;}
</style>
""",
    unsafe_allow_html=True,
)

# --- Inputs outside form for dynamic selects ---
fio = st.text_input("ФИО", placeholder="Иванов Иван Иванович")


def call_verify_api(file_bytes: bytes, filename: str, fio: Optional[str]) -> dict:
    """
    Call the FastAPI /v1/verify endpoint.
    
    Args:
        file_bytes: Content of the uploaded file
        filename: Original filename
        fio: Full name (optional)
    
    Returns:
        dict: API response with run_id, verdict, errors, processing_time_seconds
    
    Raises:
        requests.HTTPError: If API call fails
        requests.ConnectionError: If cannot connect to API
    """
    files = {"file": (filename, file_bytes, "application/octet-stream")}
    data = {"fio": fio or ""}
    
    try:
        response = requests.post(
            VERIFY_ENDPOINT,
            files=files,
            data=data,
            timeout=120  # 2 minutes timeout for OCR processing
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        raise Exception(f"Не удалось подключиться к API по адресу {VERIFY_ENDPOINT}. Проверьте, запущен ли сервис.")
    except requests.exceptions.Timeout:
        raise Exception("Превышено время ожидания ответа от API (120 сек). Сервис перегружен или документ слишком большой.")
    except requests.exceptions.HTTPError as e:
        error_detail = "Unknown error"
        try:
            error_detail = e.response.json().get('detail', e.response.text)
        except Exception:
            error_detail = e.response.text
        raise Exception(f"Ошибка API ({e.response.status_code}): {error_detail}")


# --- Upload form ---
with st.form("upload_form", clear_on_submit=False):
    uploaded_file = st.file_uploader(
        "Выберите документ",
        type=["pdf", "jpg", "png", "jpeg"],
        accept_multiple_files=False,
        help="Поддержка: PDF, JPEG",
    )
    submitted = st.form_submit_button("Загрузить и распознать", type="primary")

if submitted:
    if not uploaded_file:
        st.warning("Пожалуйста, прикрепите файл")
    else:
        # Call API
        with st.spinner("Обрабатываем документ через API..."):
            try:
                result = call_verify_api(
                    file_bytes=uploaded_file.getvalue(),
                    filename=uploaded_file.name,
                    fio=fio or None
                )
            except Exception as e:
                st.error(f"❌ Ошибка при обработке документа: {str(e)}")
                st.stop()

        # Display Results
        st.subheader("Результат проверки")
        
        run_id = result.get("run_id", "N/A")
        verdict = bool(result.get("verdict", False))
        errors = result.get("errors", []) or []
        processing_time = result.get("processing_time_seconds")

        # Display Run ID and Time
        col1, col2 = st.columns(2)
        with col1:
            st.caption(f"Run ID: {run_id}")
        with col2:
            if processing_time:
                st.caption(f"Время обработки: {processing_time:.2f} сек")

        if verdict:
            st.success("Вердикт: True — документ прошел проверку")
        else:
            st.error("Вердикт: False — документ не прошел проверку")

        # Error Code Mapping
        ERROR_MESSAGES = {
            "DOC_DATE_TOO_OLD": "Документ просрочен",
            "DOC_TYPE_UNKNOWN": "Неизвестный тип документа",
            "MULTIPLE_DOC_TYPES": "Обнаружено несколько типов документов",
            "FIO_MISMATCH": "ФИО в документе не совпадает с заявкой",
            "OCR_FAILED": "Ошибка распознавания текста",
            "LLM_FAILED": "Ошибка обработки LLM",
            "NO_FILE": "Файл не загружен",
            "INVALID_FILE": "Некорректный формат файла"
        }

        if errors:
            st.markdown("**Ошибки**")
            for e in errors:
                # Handle both string errors and dict errors
                if isinstance(e, dict):
                    code = e.get("code")
                    # Use mapped message if available, otherwise use API message or code
                    msg = ERROR_MESSAGES.get(code) or e.get("message") or str(code)
                    st.write(f"- {msg}")
                else:
                    st.write(f"- {str(e)}")

