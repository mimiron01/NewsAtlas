import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit import log_event
from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _invite_code_is_valid(provided: str) -> bool:
    expected = get_settings().signup_invite_code
    if not expected:
        return False
    return hmac.compare_digest(provided, expected)


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/hour")
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if not _invite_code_is_valid(payload.invite_code):
        log_event("signup_rejected_invalid_invite_code", request=request, email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Signup is invite-only. Check your invite code and try again.",
        )

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing is not None:
        log_event("signup_rejected_duplicate_email", request=request, email=payload.email)
        # Deliberately generic: avoids explicitly confirming the email is registered.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Unable to create an account with the provided details.",
        )

    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        name=payload.name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_event("signup_succeeded", request=request, email=payload.email, user_id=str(user.id))
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        log_event("login_failed", request=request, email=payload.email)
        raise invalid

    log_event("login_succeeded", request=request, email=payload.email, user_id=str(user.id))
    token = create_access_token(subject=str(user.id), token_version=user.token_version)
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Revokes every outstanding token for this user (all devices/sessions at once) by
    bumping token_version — any token minted before this no longer matches and is
    rejected by get_current_user. A fresh login immediately after logout works
    correctly because it reads the post-increment version when minting its token.
    """
    current_user.token_version += 1
    db.commit()
    log_event("logout", request=request, user_id=str(current_user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
