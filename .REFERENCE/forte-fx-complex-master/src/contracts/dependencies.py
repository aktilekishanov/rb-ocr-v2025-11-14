from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.service import ContractService
from src.core.database import get_db
from src.core.s3 import S3Client


async def get_s3_client() -> S3Client:
    """Get S3 client instance."""
    return S3Client()


async def get_contract_service(
        session: AsyncSession = Depends(get_db),
        s3_client: S3Client = Depends(get_s3_client),
) -> ContractService:
    """Get contract service with dependencies."""
    return ContractService(session=session, storage_client=s3_client)


ContractServiceDep = Annotated[ContractService, Depends(get_contract_service)]
