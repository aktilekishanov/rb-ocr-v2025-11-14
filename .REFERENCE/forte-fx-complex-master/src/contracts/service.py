import logging
from io import BytesIO

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.transactions import transactional
from src.contracts import constants
from src.contracts.exceptions import (
    DocumentNotFoundError,
    FileKeyNotFoundError,
    FieldNotFoundError,
)
from src.contracts.models import Contract, FieldCorrection
from src.contracts.schemas import DocumentContent
from src.core.s3 import S3Client

logger = logging.getLogger(__name__)


class ContractService:
    def __init__(
            self,
            session: AsyncSession,
            storage_client: S3Client,
    ):
        self.session = session
        self.storage = storage_client

    async def _get_contract(self, document_id: str) -> Contract:
        """Get contract by document_id. Raises DocumentNotFoundError if not found."""
        stmt = select(Contract).where(Contract.document_id == document_id)
        result = await self.session.execute(stmt)
        contract = result.scalar_one_or_none()

        if not contract:
            raise DocumentNotFoundError(f"Document {document_id} not found")
        return contract

    @transactional
    async def save_document(self, payload: DocumentContent) -> None:
        """Save document data only."""
        logger.info(f"Saving document {payload.document_id}")

        # Transform payload data
        data = {
            d.AttributeName: (None if d.Value == "None" else d.Value)
            for d in payload.data
        }

        # Transform payload documents
        docs = {
            "DocumentBasic": [f.model_dump() for f in payload.document_basic],
            "ApplicationDocument": [f.model_dump() for f in payload.application_document],
        }

        try:
            contract = await self._get_contract(payload.document_id)

            # Check if data has actually changed
            data_changed = contract.data_json != data
            docs_changed = contract.docs_json != docs

            if data_changed or docs_changed:
                # Only update DB if something changed
                contract.docs_json = docs
                contract.data_json = data
                contract.status = constants.ContractStatus.UPLOADED
                await self.session.flush()
                logger.info(
                    f"Updated contract for document {payload.document_id} "
                    f"(data_changed={data_changed}, docs_changed={docs_changed})"
                )
            else:
                logger.info(
                    f"No changes detected for document {payload.document_id} - skipping DB update"
                )

        except DocumentNotFoundError:
            contract = Contract(
                document_id=payload.document_id,
                docs_json=docs,
                data_json=data,
                status=constants.ContractStatus.UPLOADED,
            )
            self.session.add(contract)
            await self.session.flush()
            logger.info(f"Created new contract for document {payload.document_id}")

    async def get_status(self, document_id: str) -> str:
        """Get document status."""
        contract = await self._get_contract(document_id)
        return contract.status

    async def get_result(self, document_id: str) -> dict:
        """Get flat result."""
        contract = await self._get_contract(document_id)
        return contract.flat_result_json

    async def get_fb_data(self, document_id: str) -> dict:
        """Get FB data."""
        contract = await self._get_contract(document_id)
        return contract.data_json

    async def get_cross_check_result(self, document_id: str) -> list:
        """Get cross-check result."""
        contract = await self._get_contract(document_id)
        return contract.cross_check_json

    async def get_compliance_check_result(self, document_id: str) -> dict:
        """Get compliance check result."""
        contract = await self._get_contract(document_id)
        return contract.compliance_check_json

    async def get_docs(self, document_id: str) -> dict:
        """Get documents metadata."""
        contract = await self._get_contract(document_id)
        return contract.docs_json

    async def get_coordinates(self, document_id: str) -> list:
        """Get field coordinates."""
        contract = await self._get_contract(document_id)
        return (contract.result_json or {}).get("fields", [])

    async def download_file(self, document_id: str, key: str) -> tuple[str, BytesIO]:
        """Download file by key."""
        contract = await self._get_contract(document_id)

        # Search for file in documents
        for section in ("DocumentBasic", "ApplicationDocument"):
            for entry in (contract.docs_json or {}).get(section, []):
                if entry.get("Document") == key:
                    data = self.storage.download_bytes(key)
                    if data is None:
                        raise FileKeyNotFoundError(f"File '{key}' not found in storage")

                    buf = BytesIO(data)
                    buf.seek(0)
                    return entry["Truename"], buf

        raise FileKeyNotFoundError(f"File key '{key}' not found in document {document_id}")

    @transactional
    async def save_document_results(
            self,
            document_id: str,
            result_json: dict | None = None,
            flat_result_json: dict | None = None,
            cross_check_json: list | None = None,
            error: str | None = None,
    ) -> None:
        """Save document processing results."""
        status = (
            constants.ContractStatus.DONE
            if error is None
            else constants.ContractStatus.FAILED
        )

        await self.session.execute(
            update(Contract)
            .where(Contract.document_id == document_id)
            .values(
                result_json=result_json,
                flat_result_json=flat_result_json,
                cross_check_json=cross_check_json,
                error_message=error,
                status=status,
            )
        )

        logger.info(
            f"Saved results for document {document_id} with status {status}"
            + (f" (error: {error})" if error else "")
        )

    @transactional
    async def save_compliance_check(
            self,
            document_id: str,
            compliance_check_result: dict,
    ) -> None:
        """Save compliance check result for a document."""
        contract = await self._get_contract(document_id)
        contract.compliance_check_json = compliance_check_result
        await self.session.flush()

        logger.info(f"Saved compliance check for document {document_id}")

    @transactional
    async def save_field_correction(
            self,
            document_id: str,
            field_name: str,
            correct_value: str,
    ) -> FieldCorrection:
        """Save a field correction."""
        contract = await self._get_contract(document_id)

        flat_result = contract.flat_result_json or {}
        if not isinstance(flat_result, dict) or field_name not in flat_result:
            raise FieldNotFoundError(
                f"Field '{field_name}' not found in document {document_id}"
            )

        current_value = flat_result.get(field_name)
        correction = FieldCorrection(
            document_id=document_id,
            field_name=field_name,
            current_value=current_value,
            correct_value=correct_value,
        )

        self.session.add(correction)
        await self.session.flush()

        logger.info(
            f"Saved correction for field '{field_name}' in document {document_id}"
        )
        return correction
