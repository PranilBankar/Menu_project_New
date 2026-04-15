"""
Authentication — Supabase JWT verification.

Usage in any endpoint:

    from app.core.auth import get_current_user

    @router.post("/")
    def create_something(current_user: uuid.UUID = Depends(get_current_user)):
        # current_user is the authenticated user's UUID (from auth.users)
        ...

The JWT is issued by Supabase Auth and sent by the frontend as:
    Authorization: Bearer <access_token>
"""
import uuid
import jwt  # PyJWT
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import settings

# Scheme that extracts the token from "Authorization: Bearer <token>"
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> uuid.UUID:
    """
    Decode a Supabase JWT and return the user's UUID.

    Raises 401 if:
    - No token is provided
    - Token is expired
    - Token is malformed or signature doesn't match
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — send Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        # Initialize JWKS client using Supabase URL
        if not settings.SUPABASE_URL:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_URL is not configured for JWKS verification"
            )
            
        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/keys"
        jwks_client = jwt.PyJWKClient(jwks_url)
        
        # Get signing key from the token header (kid)
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except jwt.PyJWKClientError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unable to fetch signing key: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "ES384", "RS384", "RS512", "ES512"], # Allow ECC and RSA
            audience="authenticated",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The "sub" claim is the user's UUID in Supabase
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
        )

    try:
        return uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid user ID in token",
        )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> uuid.UUID | None:
    """
    Same as get_current_user but returns None instead of 401 if no token.
    Useful for endpoints that behave differently for logged-in vs anonymous users.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None
