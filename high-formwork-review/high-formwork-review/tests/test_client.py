from app.mineru_client import MinerUClient


def test_system_proxy_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("MINERU_USE_SYSTEM_PROXY", raising=False)
    client = MinerUClient()
    try:
        assert client.session.trust_env is False
    finally:
        client.session.close()


def test_system_proxy_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("MINERU_USE_SYSTEM_PROXY", "true")
    client = MinerUClient()
    try:
        assert client.session.trust_env is True
    finally:
        client.session.close()
