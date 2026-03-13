import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

APP_API_KEY = os.getenv("APP_API_KEY", "")
_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(key: str = Security(_header)):
    """봇 제어 엔드포인트 보호용 API Key 인증.
    APP_API_KEY 환경변수가 비어있으면 개발 모드로 인증 생략.
    """
    if not APP_API_KEY:
        return  # dev mode
    if key != APP_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key (X-API-Key header)",
        )
