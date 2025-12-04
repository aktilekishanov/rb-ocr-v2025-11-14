import logging

from fastapi import APIRouter, Query, status, HTTPException
from fastapi.responses import StreamingResponse

from src.common.http import make_content_disposition
from src.contracts import constants
from src.contracts.dependencies import ContractServiceDep
from src.contracts.exceptions import (
    DocumentNotFoundError,
    FileKeyNotFoundError,
    FieldNotFoundError,
)
from src.contracts.schemas import (
    CoordinatesResponse,
    CorrectionCreate,
    CorrectionResponse,
    DocumentPayload,
    FileInfo,
    FilesOnlyResponse,
    StatusResponse,
)
from src.core.celery_app import celery_app

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/contracts",
    tags=["contracts"],
)


@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive and enqueue business document for processing",
)
async def submit_document(
        payload: DocumentPayload,
        service: ContractServiceDep,
) -> dict:
    """Accept document for processing."""
    document_id = payload.document.document_id
    logger.info(f"Received document for processing: {document_id}")

    try:
        # Step 1: Save document
        await service.save_document(payload.document)

        # Step 2: Enqueue processing task
        docs = {
            "DocumentBasic": [f.model_dump() for f in payload.document.document_basic],
            "ApplicationDocument": [f.model_dump() for f in payload.document.application_document],
        }

        celery_app.send_task(
            "src.contracts.tasks.process_document_task",
            args=(document_id, docs["DocumentBasic"], docs["ApplicationDocument"]),
            queue="contracts",
        )

        logger.info(f"Successfully enqueued processing task for document: {document_id}")

        return {
            "message": "Document accepted for processing",
            "document_id": document_id,
        }
    except Exception as e:
        logger.error(f"Failed to process document {document_id}: {str(e)}", exc_info=True)
        raise


@router.get(
    "/{document_id}/files",
    response_model=FilesOnlyResponse,
    summary="Fetch DocumentBasic & ApplicationDocument arrays",
)
async def get_docs(
        document_id: str,
        service: ContractServiceDep,
) -> FilesOnlyResponse:
    """Get document file references."""
    logger.debug(f"Fetching files for document: {document_id}")

    try:
        docs = await service.get_docs(document_id)
        return FilesOnlyResponse(
            DocumentBasic=[FileInfo(**f) for f in docs.get("DocumentBasic", [])],
            ApplicationDocument=[FileInfo(**f) for f in docs.get("ApplicationDocument", [])],
        )
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/coordinates",
    response_model=CoordinatesResponse,
    summary="Get field coordinates",
)
async def get_coordinates(
        document_id: str,
        service: ContractServiceDep,
) -> CoordinatesResponse:
    """Get field coordinates from extraction results."""
    logger.debug(f"Fetching coordinates for document: {document_id}")

    try:
        fields = await service.get_coordinates(document_id)
        return CoordinatesResponse(fields=fields)
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/status",
    response_model=StatusResponse,
    summary="Get document processing status",
)
async def get_status(
        document_id: str,
        service: ContractServiceDep,
) -> StatusResponse:
    """Get document status."""
    logger.debug(f"Fetching status for document: {document_id}")

    try:
        status_value = await service.get_status(document_id)
        return StatusResponse(status=status_value)
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/result",
    summary="Get extraction results",
)
async def get_result(
        document_id: str,
        service: ContractServiceDep,
) -> dict:
    """Get document processing results."""
    logger.debug(f"Fetching result for document: {document_id}")

    try:
        result = await service.get_result(document_id)
        if not result:
            logger.warning(f"Result not ready for document: {document_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": constants.ErrorCode.RESULT_NOT_READY,
                    "message": "Result not ready or not found",
                },
            )
        return result
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/cross-check",
    summary="Get cross-check results",
)
async def get_cross_check(
        document_id: str,
        service: ContractServiceDep,
) -> list:
    """Get cross-check validation results."""
    logger.debug(f"Fetching cross-check for document: {document_id}")

    try:
        result = await service.get_cross_check_result(document_id)
        if not result:
            logger.warning(f"Cross-check not ready for document: {document_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": constants.ErrorCode.RESULT_NOT_READY,
                    "message": "Cross Check Result not ready or not found",
                },
            )
        return result
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/fb-data",
    summary="Get FB data",
)
async def get_fb_data(
        document_id: str,
        service: ContractServiceDep,
) -> dict:
    """Get FB source data."""
    logger.debug(f"Fetching FB data for document: {document_id}")

    try:
        return await service.get_fb_data(document_id)
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/compliance-check",
    summary="Get compliance check",
)
async def get_compliance_check(
        document_id: str,
        service: ContractServiceDep,
) -> dict:
    """Get compliance check results."""
    logger.debug(f"Fetching compliance check for document: {document_id}")

    try:
        result = await service.get_compliance_check_result(document_id)
        if not result:
            logger.warning(f"Compliance Check not ready for document: {document_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error_code": constants.ErrorCode.RESULT_NOT_READY,
                    "message": "Compliance Check not ready or not found",
                },
            )
        return result
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )


@router.get(
    "/{document_id}/download",
    summary="Download file",
)
async def download_file(
        document_id: str,
        service: ContractServiceDep,
        document: str = Query(..., description="S3 object key"),
) -> StreamingResponse:
    """Download a file from S3."""
    logger.info(f"Download request for document {document_id}, key: {document}")

    try:
        filename, buffer = await service.download_file(document_id, document)
        logger.info(f"Successfully prepared download for {filename} (document: {document_id})")

        return StreamingResponse(
            buffer,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{make_content_disposition(filename)}"'
            },
        )
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )
    except FileKeyNotFoundError as e:
        logger.warning(f"File key not found for document {document_id}: {document}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.FILE_KEY_NOT_FOUND,
                "message": str(e),
            },
        )


@router.post(
    "/{document_id}/corrections",
    response_model=CorrectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a correction for a specific field",
)
async def submit_correction(
        document_id: str,
        payload: CorrectionCreate,
        service: ContractServiceDep,
) -> CorrectionResponse:
    """Submit a field correction."""
    logger.info(f"Correction submission for document {document_id}, field: {payload.field_name}")

    try:
        correction = await service.save_field_correction(
            document_id=document_id,
            field_name=payload.field_name,
            correct_value=payload.correct_value,
        )
        logger.info(f"Successfully saved correction for {payload.field_name} in document {document_id}")
        return CorrectionResponse.model_validate(correction)
    except DocumentNotFoundError:
        logger.warning(f"Document not found: {document_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.DOCUMENT_NOT_FOUND,
                "message": f"Document {document_id} not found",
            },
        )
    except FieldNotFoundError as e:
        logger.warning(f"Field not found in document {document_id}: {payload.field_name}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": constants.ErrorCode.FIELD_NOT_FOUND,
                "message": str(e),
            },
        )