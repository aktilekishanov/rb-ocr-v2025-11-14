"""
Streamlit UI for the RB loan deferment IDP (main-dev).

Provides a single-page interface for uploading a document, collecting
contextual metadata (FIO), invoking the
pipeline orchestrator, and rendering results, diagnostics, and timings.
"""

import json
import os
import re
import tempfile
from pathlib import Path

import streamlit as st

from pipeline.core.config import STAMP_ENABLED
from pipeline.core.errors import message_for
from pipeline.orchestrator import run_pipeline
from pipeline.core.settings import RUNS_DIR

# --- Page setup ---
st.set_page_config(page_title="[DEV] RB Loan Deferment IDP", layout="centered")

st.write("")
st.title("[DEV] RB Loan Deferment IDP")
st.write("Загрузите один файл для распознавания (OCR (Tesseract async, Dev-OCR) & LLM (DMZ))")

# --- Basic paths ---
RUNS_DIR.mkdir(parents=True, exist_ok=True)

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


def _safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-\.\s]", "_", name.strip())
    name = re.sub(r"\s+", "_", name)
    return name or "file"


def _count_pdf_pages(path: str):
    try:
        if _pypdf is not None:
            reader = _pypdf.PdfReader(path)
            return len(reader.pages)
    except Exception:
        pass
    try:
        if _pypdf2 is not None:
            reader = _pypdf2.PdfReader(path)
            return len(reader.pages)
    except Exception:
        pass
    try:
        with open(path, "rb") as f:
            data = f.read()
        return len(re.findall(rb"/Type\s*/Page\b", data)) or None
    except Exception:
        return None


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
        # Save uploaded file to a temporary location (auto-cleaned) and call orchestrator once
        with tempfile.TemporaryDirectory(prefix="upload_") as tmp_dir:
            tmp_path = Path(tmp_dir) / _safe_filename(uploaded_file.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("Обрабатываем документ..."):
                result = run_pipeline(
                    fio=fio or None,
                    source_file_path=str(tmp_path),
                    original_filename=uploaded_file.name,
                    content_type=getattr(uploaded_file, "type", None),
                    runs_root=RUNS_DIR,
                )

        st.subheader("Результат проверки")
        verdict = bool(result.get("verdict", False))
        errors = result.get("errors", []) or []

        if verdict:
            st.success("Вердикт: True — документ прошел проверку")
        else:
            st.error("Вердикт: False — документ не прошел проверку")

        if errors:
            st.markdown("**Ошибки**")
            for e in errors:
                code = e.get("code")
                msg = message_for(code) or e.get("message") or str(code)
                st.write(f"- {msg}")

        # Diagnostics: show final_result.json for full context
        final_result_path = result.get("final_result_path")
        if isinstance(final_result_path, str) and os.path.exists(final_result_path):
            try:
                with open(final_result_path, encoding="utf-8") as ff:
                    final_obj = json.load(ff)
                with st.expander("Диагностика: final_result.json"):
                    st.json(final_obj)
            except Exception:
                pass

        # Side-by-side comparison (if available)
        if isinstance(final_result_path, str):
            sbs_path = os.path.join(os.path.dirname(final_result_path), "side_by_side.json")
            if os.path.exists(sbs_path):
                try:
                    with open(sbs_path, encoding="utf-8") as sbf:
                        side_by_side = json.load(sbf)
                    with st.expander("Сравнение: side_by_side.json"):
                        # Compact table for quick review
                        rows = []
                        try:
                            rows = [
                                {
                                    "Поле": "ФИО (заявка)",
                                    "Значение": str(side_by_side.get("fio", {}).get("meta")),
                                },
                                {
                                    "Поле": "ФИО (из документа)",
                                    "Значение": str(side_by_side.get("fio", {}).get("extracted")),
                                },
                                {
                                    "Поле": "Тип документа (из документа)",
                                    "Значение": str(
                                        side_by_side.get("doc_type", {}).get("extracted")
                                    ),
                                },
                                {
                                    "Поле": "Дата (заявки)",
                                    "Значение": str(side_by_side.get("request_created_at")),
                                },
                                {
                                    "Поле": "Дата (из документа)",
                                    "Значение": str(
                                        side_by_side.get("doc_date", {}).get("extracted")
                                    ),
                                },
                                {
                                    "Поле": "Действителен до",
                                    "Значение": str(
                                        side_by_side.get("doc_date", {}).get("valid_until")
                                    ),
                                },
                                {
                                    "Поле": "Один тип документа",
                                    "Значение": str(
                                        side_by_side.get("single_doc_type", {}).get("extracted")
                                    ),
                                },
                                {
                                    "Поле": "Тип документа имеется в справочнике",
                                    "Значение": str(
                                        side_by_side.get("doc_type_known", {}).get("extracted")
                                    ),
                                },
                            ]
                            if STAMP_ENABLED:
                                rows.append(
                                    {
                                        "Поле": "Печать обнаружена",
                                        "Значение": str(
                                            side_by_side.get("stamp_present", {}).get("extracted")
                                        ),
                                    }
                                )
                        except Exception:
                            rows = []
                        if rows:
                            st.table(rows)
                except Exception:
                    pass

        # Preview visualization of stamp detector (if available)
        if STAMP_ENABLED and isinstance(final_result_path, str):
            try:
                meta_dir = os.path.dirname(final_result_path)
                run_base = os.path.dirname(meta_dir)
                input_original_dir = os.path.join(run_base, "input", "original")
                vis_path = None
                if os.path.isdir(input_original_dir):
                    for name in os.listdir(input_original_dir):
                        lower = name.lower()
                        if (
                            lower.endswith("_with_boxes.jpg")
                            or lower.endswith("_with_boxes.jpeg")
                            or lower.endswith("_with_boxes.png")
                        ):
                            vis_path = os.path.join(input_original_dir, name)
                            break
                if vis_path and os.path.exists(vis_path):
                    with st.expander("Превью документа с печатью"):
                        st.image(vis_path, use_container_width=True)
            except Exception:
                pass

        # SLA & timings (displayed at the end) from manifest.timing
        if isinstance(final_result_path, str) and os.path.exists(final_result_path):
            try:
                meta_dir = os.path.dirname(final_result_path)
                manifest_path = os.path.join(meta_dir, "manifest.json")
                if os.path.exists(manifest_path):
                    with open(manifest_path, encoding="utf-8") as mf:
                        manifest = json.load(mf)
                    timing = manifest.get("timing", {}) if isinstance(manifest, dict) else {}
                    if isinstance(timing, dict):
                        dur = timing.get("duration_seconds")
                        stamp_t = timing.get("stamp_seconds")
                        ocr_t = timing.get("ocr_seconds")
                        llm_t = timing.get("llm_seconds")
                        with st.expander("SLA и тайминги выполнения"):
                            if STAMP_ENABLED:
                                cols = st.columns(4)
                                cols[0].metric(
                                    "Всего (сек)",
                                    f"{dur:.2f}" if isinstance(dur, (int, float)) else "-",
                                )
                                cols[1].metric(
                                    "Печать (сек)",
                                    f"{stamp_t:.2f}" if isinstance(stamp_t, (int, float)) else "-",
                                )
                                cols[2].metric(
                                    "OCR (сек)",
                                    f"{ocr_t:.2f}" if isinstance(ocr_t, (int, float)) else "-",
                                )
                                cols[3].metric(
                                    "LLM (сек)",
                                    f"{llm_t:.2f}" if isinstance(llm_t, (int, float)) else "-",
                                )
                            else:
                                cols = st.columns(3)
                                cols[0].metric(
                                    "Всего (сек)",
                                    f"{dur:.2f}" if isinstance(dur, (int, float)) else "-",
                                )
                                cols[1].metric(
                                    "OCR (сек)",
                                    f"{ocr_t:.2f}" if isinstance(ocr_t, (int, float)) else "-",
                                )
                                cols[2].metric(
                                    "LLM (сек)",
                                    f"{llm_t:.2f}" if isinstance(llm_t, (int, float)) else "-",
                                )
            except Exception:
                pass
