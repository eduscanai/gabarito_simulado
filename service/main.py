from __future__ import annotations

from fastapi import FastAPI

from app.routes import router

app = FastAPI(
    title="OMR Correction Service",
    description=(
        "Serviço stateless de geração/correção de folhas OMR (marcadores, "
        "bolhas e matrícula em blocos), usado pelo EduScanAI."
    ),
    version="0.1.0",
)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
