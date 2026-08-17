"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Servisin ayakta olduğunu doğrulamak için basit health check."""
    return {"status": "ok"}
