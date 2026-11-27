from typing import Any, Callable, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.config import Settings, get_settings
from backend.app.database import LocalDevSQLiteRepository, SupabaseRepository, get_repository
from backend.app.utils.security import decode_dev_access_token, decode_supabase_jwt

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> Dict[str, Any]:
    """Authenticate Bearer JWT and resolve the authoritative user profile from the database."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    token = credentials.credentials
    repo = get_repository(settings)
    profile: Dict[str, Any] | None = None

    if isinstance(repo, SupabaseRepository):
        claims = decode_supabase_jwt(token, settings)
        if claims and claims.get("sub"):
            profile = repo.get_profile_by_auth_user_id(str(claims["sub"]))
        else:
            profile = repo.get_user_from_jwt(token)
    elif isinstance(repo, LocalDevSQLiteRepository) and settings.dev_auth_mode:
        claims = decode_dev_access_token(token, settings)
        if claims and claims.get("profile_id"):
            profile = repo.get_profile_by_id(str(claims["profile_id"]))

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token.",
        )

    if profile.get("account_status") != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is suspended or inactive.",
        )

    return profile


def require_roles(*allowed_roles: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    """Dependency enforcing backend role-based authorization."""

    def _checker(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this resource.",
            )
        return current_user

    return _checker
