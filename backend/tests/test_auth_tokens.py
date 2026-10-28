"""The token checks, run against real RS256-signed tokens (no network, no Azure)."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import AuthError, AuthUnavailable, EntraTokenVerifier

TENANT = "3f5f8e17-f7c3-4938-8fae-5f081b76f39f"
API = "843c3324-8ed5-4039-8a83-bc1a1e22cf3b"
ISSUER = f"https://{TENANT}.ciamlogin.com/{TENANT}/v2.0"

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_token(key=KEY, **overrides):
    claims = {
        "iss": ISSUER,
        "aud": API,
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
        "oid": "user-oid-1",
        "scp": "access_as_user",
        "name": "Faisal",
        "email": "faisal@example.com",
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256")


def verifier(fetch=None):
    return EntraTokenVerifier(
        TENANT,
        "docmindauth",
        API,
        fetch_json=fetch or (lambda url: {"issuer": ISSUER, "jwks_uri": "https://keys"}),
        key_resolver=lambda token: KEY.public_key(),
    )


def test_a_valid_token_gives_the_callers_identity():
    identity = verifier().verify(make_token())
    assert (identity.subject, identity.email, identity.name) == (
        "user-oid-1",
        "faisal@example.com",
        "Faisal",
    )


def test_the_api_uri_form_of_the_audience_is_accepted_too():
    assert verifier().verify(make_token(aud=f"api://{API}")).subject == "user-oid-1"


def test_the_subject_claim_is_used_when_there_is_no_oid():
    assert verifier().verify(make_token(oid=None, sub="sub-9")).subject == "sub-9"


def test_a_missing_email_falls_back_without_failing():
    identity = verifier().verify(make_token(email=None, preferred_username="f@x.com"))
    assert identity.email == "f@x.com"
    bare = verifier().verify(make_token(email=None))
    assert bare.email == "user-oid-1@users.docmind.invalid"


def test_the_metadata_is_asked_for_once_and_remembered():
    calls = []

    def fetch(url):
        calls.append(url)
        return {"issuer": ISSUER, "jwks_uri": "https://keys"}

    v = verifier(fetch)
    v.verify(make_token())
    v.verify(make_token())
    assert calls == [
        f"https://docmindauth.ciamlogin.com/{TENANT}/v2.0/.well-known/openid-configuration"
    ]


@pytest.mark.parametrize(
    "token_kwargs, message",
    [
        ({"exp": int(time.time()) - 60}, "expired"),
        ({"aud": "someone-elses-api"}, "not valid"),
        ({"iss": "https://evil.example/v2.0"}, "not valid"),
        ({"exp": None}, "not valid"),
    ],
)
def test_bad_tokens_are_refused(token_kwargs, message):
    with pytest.raises(AuthError, match=message) as error:
        verifier().verify(make_token(**token_kwargs))
    assert error.value.status_code == 401


def test_a_token_signed_by_someone_else_is_refused():
    with pytest.raises(AuthError, match="not valid"):
        verifier().verify(make_token(key=OTHER_KEY))


def test_garbage_is_refused():
    with pytest.raises(AuthError, match="not valid"):
        verifier().verify("not-a-token")


def test_a_token_without_the_required_scope_is_forbidden():
    with pytest.raises(AuthError) as error:
        verifier().verify(make_token(scp="something_else"))
    assert error.value.status_code == 403
    with pytest.raises(AuthError) as error:
        verifier().verify(make_token(scp=None))  # for example an app-only token
    assert error.value.status_code == 403


def test_an_unreachable_sign_in_service_is_not_reported_as_a_bad_token():
    def fetch(url):
        raise OSError("network down")

    with pytest.raises(AuthUnavailable):
        verifier(fetch).verify(make_token())


def test_metadata_missing_the_issuer_counts_as_unavailable():
    with pytest.raises(AuthUnavailable):
        verifier(lambda url: {"unexpected": True}).verify(make_token())


def test_a_rejected_token_is_explained_in_the_log(caplog):
    with caplog.at_level("WARNING", logger="docmind.auth"):
        with pytest.raises(AuthError):
            verifier().verify(make_token(aud="someone-elses-api"))
    assert "aud=someone-elses-api" in caplog.text
    assert f"iss={ISSUER}" in caplog.text
