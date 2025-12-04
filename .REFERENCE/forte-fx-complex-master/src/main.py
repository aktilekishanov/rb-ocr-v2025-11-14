from fastapi import FastAPI
from src.contracts.router import router as contracts_router

app = FastAPI(
    title="Exchange Control API",
    description="Валютный контроль",
    version="0.1.0",
)

app.include_router(contracts_router, prefix="/api/v1")
