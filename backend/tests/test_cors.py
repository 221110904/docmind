PREFLIGHT = {
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type, authorization",
}


def test_the_dev_frontend_is_allowed_to_call_the_api(client):
    response = client.options(
        "/ask", headers={"Origin": "http://localhost:5173", **PREFLIGHT}
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_the_browser_may_send_its_sign_in_token(client):
    response = client.options(
        "/ask", headers={"Origin": "http://localhost:5173", **PREFLIGHT}
    )
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_other_websites_are_not(client):
    response = client.options(
        "/ask", headers={"Origin": "https://evil.example", **PREFLIGHT}
    )
    assert "access-control-allow-origin" not in response.headers
