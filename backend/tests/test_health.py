FAKE_TEST_KEY = "TEST-not-a-real-key"


def test_health_reports_ok_and_database(make_client):
    response = make_client(RIOT_API_KEY=FAKE_TEST_KEY).get("/api/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["schema_version"] == "1"
    assert body["riot_api_key_configured"] is True


def test_health_never_leaks_the_key(make_client):
    response = make_client(RIOT_API_KEY=FAKE_TEST_KEY).get("/api/health")

    assert FAKE_TEST_KEY not in response.get_data(as_text=True)


def test_health_reports_missing_key(make_client):
    body = make_client(RIOT_API_KEY="").get("/api/health").get_json()

    assert body["riot_api_key_configured"] is False
