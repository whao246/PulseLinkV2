from app.workers import main as worker_main


def test_start_worker_runs_rq_worker_from_environment(monkeypatch):
    calls = {}

    class FakeRedis:
        @classmethod
        def from_url(cls, url):
            calls["redis_url"] = url
            return "redis-connection"

    class FakeQueue:
        def __init__(self, name, connection):
            self.name = name
            calls["queue_name"] = name
            calls["queue_connection"] = connection

    class FakeWorker:
        def __init__(self, queues, connection):
            calls["worker_queues"] = queues
            calls["worker_connection"] = connection

        def work(self, *, burst=False):
            calls["burst"] = burst
            return True

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("QUEUE_NAME", "pulselink-debug")
    monkeypatch.setattr(worker_main, "Redis", FakeRedis, raising=False)
    monkeypatch.setattr(worker_main, "Queue", FakeQueue, raising=False)
    monkeypatch.setattr(worker_main, "Worker", FakeWorker, raising=False)

    assert worker_main.start_worker(burst=True) is True
    assert calls["redis_url"] == "redis://127.0.0.1:6379/0"
    assert calls["queue_name"] == "pulselink-debug"
    assert calls["queue_connection"] == "redis-connection"
    assert calls["worker_connection"] == "redis-connection"
    assert calls["burst"] is True
    assert calls["worker_queues"][0].name == "pulselink-debug"


def test_start_worker_can_use_simple_worker_for_debug(monkeypatch):
    calls = {}

    class FakeRedis:
        @classmethod
        def from_url(cls, url):
            return "redis-connection"

    class FakeQueue:
        def __init__(self, name, connection):
            self.name = name

    class FakeWorker:
        def __init__(self, queues, connection):
            calls["worker_class"] = "worker"

        def work(self, *, burst=False):
            return True

    class FakeSimpleWorker:
        def __init__(self, queues, connection):
            calls["worker_class"] = "simple"

        def work(self, *, burst=False):
            calls["burst"] = burst
            return True

    monkeypatch.setenv("RQ_WORKER_CLASS", "simple")
    monkeypatch.setattr(worker_main, "Redis", FakeRedis, raising=False)
    monkeypatch.setattr(worker_main, "Queue", FakeQueue, raising=False)
    monkeypatch.setattr(worker_main, "Worker", FakeWorker, raising=False)
    monkeypatch.setattr(worker_main, "SimpleWorker", FakeSimpleWorker, raising=False)

    assert worker_main.start_worker(burst=True) is True
    assert calls == {"worker_class": "simple", "burst": True}
