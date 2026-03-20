import pytest

from app.infrastructure.external.sandbox.docker_sandbox import DockerSandbox


class _FakeContainer:
    def __init__(self):
        self.removed_force: bool | None = None

    def remove(self, force: bool = False):
        self.removed_force = force


class _FakeContainers:
    def __init__(self, container: _FakeContainer):
        self._container = container
        self.last_get_name: str | None = None

    def get(self, name: str) -> _FakeContainer:
        self.last_get_name = name
        return self._container


class _FakeDockerClient:
    def __init__(self, container: _FakeContainer):
        self.containers = _FakeContainers(container)


@pytest.mark.asyncio
async def test_destroy_uses_internal_container_name(monkeypatch):
    sandbox = DockerSandbox(ip="127.0.0.1", container_name="sandbox-123")
    fake_container = _FakeContainer()
    fake_client = _FakeDockerClient(fake_container)

    import app.infrastructure.external.sandbox.docker_sandbox as module

    monkeypatch.setattr(module.docker, "from_env", lambda: fake_client)

    destroyed = await sandbox.destroy()

    assert destroyed is True
    assert fake_client.containers.last_get_name == "sandbox-123"
    assert fake_container.removed_force is True


@pytest.mark.asyncio
async def test_destroy_skips_container_delete_when_name_missing(monkeypatch):
    sandbox = DockerSandbox(ip="127.0.0.1", container_name=None)

    import app.infrastructure.external.sandbox.docker_sandbox as module

    class _Sentinel:
        called = False

    sentinel = _Sentinel()

    def _from_env():
        sentinel.called = True
        raise AssertionError("docker.from_env should not be called when container name is missing")

    monkeypatch.setattr(module.docker, "from_env", _from_env)

    destroyed = await sandbox.destroy()

    assert destroyed is True
    assert sentinel.called is False
