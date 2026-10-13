import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

_security = HTTPBasic()


def require_admin(credentials: HTTPBasicCredentials = Depends(_security)) -> str:
    """Single shared admin login, per CLAUDE.md (no per-admin accounts).

    If ADMIN_USERNAME/ADMIN_PASSWORD aren't configured, the dashboard is
    unreachable rather than silently open.
    """
    if not settings.admin_username or not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin dashboard is not configured")

    valid_username = secrets.compare_digest(credentials.username, settings.admin_username)
    valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
