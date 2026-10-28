"""Who is calling? Checks the Microsoft Entra External ID token and finds the user's workspace.

AUTH_BACKEND=none skips all of this and treats every request as one local developer, so
local work and the test suite need no login. AUTH_BACKEND=entra requires a valid token.
"""

import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User, Workspace

log = logging.getLogger("docmind.auth")


class AuthError(Exception):
    """The caller's token is missing, invalid or not allowed."""

    def __init__(self, message: str, status_code: int = 401):
        super().__init__(message)
        self.status_code = status_code


class AuthUnavailable(Exception):
    """The sign-in service could not be reached, so the token could not be checked."""


@dataclass(frozen=True)
class Identity:
    subject: str  # the user's stable id in Entra
    email: str
    name: str | None


DEV_IDENTITY = Identity("dev-user", "dev@localhost", "Local developer")


class TokenVerifier(ABC):
    @abstractmethod
    def verify(self, token: str) -> Identity: ...


def _fetch_json(url: str) -> dict:
    # The URL is built from settings and is always https
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.load(response)


class EntraTokenVerifier(TokenVerifier):
    """Checks tokens issued by a Microsoft Entra External ID tenant for the DocMind API.

    The issuer and the signing keys come from the tenant's own published metadata, so
    nothing about the token format is hard-coded here.
    """

    def __init__(
        self,
        tenant_id: str,
        subdomain: str,
        client_id: str,
        required_scope: str = "access_as_user",
        fetch_json: Callable[[str], dict] = _fetch_json,
        key_resolver: Callable[[str], Any] | None = None,
    ):
        self._metadata_url = (
            f"https://{subdomain}.ciamlogin.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        )
        self._audiences = [client_id, f"api://{client_id}"]
        self._scope = required_scope
        self._fetch_json = fetch_json
        self._key_resolver = key_resolver
        self._issuer: str | None = None
        self._jwks_uri: str | None = None
        self._jwk_client: jwt.PyJWKClient | None = None

    def _load_metadata(self) -> str:
        if self._issuer is None:
            try:
                data = self._fetch_json(self._metadata_url)
                self._issuer, self._jwks_uri = data["issuer"], data["jwks_uri"]
            except Exception as exc:
                log.error("Could not load sign-in metadata from %s: %s", self._metadata_url, exc)
                raise AuthUnavailable("The sign-in service could not be reached.") from exc
        return self._issuer

    def _signing_key(self, token: str) -> Any:
        if self._key_resolver is not None:
            return self._key_resolver(token)
        if self._jwk_client is None:
            self._jwk_client = jwt.PyJWKClient(self._jwks_uri)
        return self._jwk_client.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> Identity:
        issuer = self._load_metadata()
        try:
            claims = jwt.decode(
                token,
                self._signing_key(token),
                algorithms=["RS256"],
                audience=self._audiences,
                issuer=issuer,
                options={"require": ["exp", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise AuthError("Your session has expired. Sign in again.") from exc
        except jwt.PyJWKClientConnectionError as exc:
            raise AuthUnavailable("The sign-in service could not be reached.") from exc
        except jwt.PyJWTError as exc:
            self._log_rejection(token, exc, issuer)
            raise AuthError("The sign-in token is not valid.") from exc

        if self._scope not in str(claims.get("scp", "")).split():
            raise AuthError("This token does not allow access to DocMind.", status_code=403)

        subject = str(claims.get("oid") or claims.get("sub") or "")
        if not subject:
            raise AuthError("The sign-in token does not say who you are.")
        emails = claims.get("emails")
        email = (
            claims.get("email")
            or (emails[0] if isinstance(emails, list) and emails else None)
            or claims.get("preferred_username")
            or _placeholder_email(subject)
        )
        name = claims.get("name")
        return Identity(
            subject=subject[:64],
            email=str(email)[:255],
            name=str(name)[:255] if name else None,
        )

    def _log_rejection(self, token: str, exc: Exception, expected_issuer: str) -> None:
        """Say why a token was refused, so a mismatch is easy to diagnose from the log."""
        try:
            seen = jwt.decode(token, options={"verify_signature": False})
            details = f"iss={seen.get('iss')} aud={seen.get('aud')} ver={seen.get('ver')}"
        except jwt.PyJWTError:
            details = "unreadable token"
        log.warning(
            "Token refused (%s: %s). %s. Expected iss=%s aud=%s",
            type(exc).__name__, exc, details, expected_issuer, self._audiences,
        )


def _placeholder_email(subject: str) -> str:
    return f"{subject}@users.docmind.invalid"


@lru_cache
def get_token_verifier() -> TokenVerifier | None:
    if settings.auth_backend != "entra":
        return None
    missing = [
        name
        for name, value in (
            ("ENTRA_TENANT_ID", settings.entra_tenant_id),
            ("ENTRA_TENANT_SUBDOMAIN", settings.entra_tenant_subdomain),
            ("ENTRA_API_CLIENT_ID", settings.entra_api_client_id),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"AUTH_BACKEND=entra but {', '.join(missing)} is empty")
    return EntraTokenVerifier(
        settings.entra_tenant_id,
        settings.entra_tenant_subdomain,
        settings.entra_api_client_id,
        settings.entra_required_scope,
    )


@dataclass
class Caller:
    user: User
    workspace: Workspace


def _find_or_create_user(db: Session, identity: Identity) -> User:
    user = db.scalar(select(User).where(User.external_id == identity.subject))
    if user is not None:
        return user
    role = db.scalar(select(Role).where(Role.name == "viewer"))
    if role is None:
        raise HTTPException(status_code=500, detail="Roles are not set up.")
    email = identity.email
    if db.scalar(select(User).where(User.email == email)) is not None:
        email = _placeholder_email(identity.subject)  # emails are unique
    user = User(
        external_id=identity.subject, email=email, display_name=identity.name, role_id=role.id
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Two first requests arrived together and the other one created the user
        db.rollback()
        user = db.scalar(select(User).where(User.external_id == identity.subject))
        if user is None:
            raise
    return user


def _find_or_create_workspace(db: Session, user: User) -> Workspace:
    workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
    if workspace is not None:
        return workspace
    label = user.display_name or user.email
    workspace = Workspace(name=f"{label}'s documents"[:100], owner_id=user.id)
    db.add(workspace)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        workspace = db.scalar(select(Workspace).where(Workspace.owner_id == user.id))
        if workspace is None:
            raise
    return workspace


def provision(db: Session, identity: Identity) -> Caller:
    """Find this person's user and private workspace, creating them on first sign-in."""
    user = _find_or_create_user(db, identity)
    return Caller(user=user, workspace=_find_or_create_workspace(db, user))


_bearer = HTTPBearer(auto_error=False)


def get_caller(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    verifier: TokenVerifier | None = Depends(get_token_verifier),
    db: Session = Depends(get_db),
) -> Caller:
    if verifier is None:
        identity = DEV_IDENTITY
    else:
        if credentials is None or not credentials.credentials:
            raise HTTPException(
                status_code=401,
                detail="Sign in to use DocMind.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            identity = verifier.verify(credentials.credentials)
        except AuthUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except AuthError as exc:
            headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
            raise HTTPException(
                status_code=exc.status_code, detail=str(exc), headers=headers
            ) from exc
    return provision(db, identity)
