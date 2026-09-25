def test_health_needs_no_session(anon):
    res = anon.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_create_app_initialises_database(app, settings):
    assert settings.db_path.exists()
