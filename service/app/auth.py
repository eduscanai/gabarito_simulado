from __future__ import annotations

from fastapi import Header, HTTPException

from .config import SERVICE_TOKEN


async def verificar_token(authorization: str = Header(default="")) -> None:
    """Shared-secret check between EduScanAI (Nitro) and this service.

    If OMR_SERVICE_TOKEN is not set, the check is skipped — useful for local
    development only. Always set it in any deployed environment.
    """
    if not SERVICE_TOKEN:
        return

    esperado = f"Bearer {SERVICE_TOKEN}"
    if authorization != esperado:
        raise HTTPException(status_code=401, detail="Token de serviço inválido.")
