import pytest

from app.contexts.user.jobs.login_succeeded import LoginSucceededJob
from app.infrastructure.queue.errors import QueueConfigurationError
from app.infrastructure.queue.job import encode_job
from app.interfaces.worker.resolver import JobResolver


def test_resolver_dynamically_loads_and_caches_queue_job() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver()

    binding = resolver.resolve(encoded.job_type, encoded.version)

    assert binding is resolver.resolve(encoded.job_type, encoded.version)
    assert binding.policy == LoginSucceededJob.policy


def test_resolver_rejects_unknown_version_and_external_module() -> None:
    encoded = encode_job(LoginSucceededJob())
    resolver = JobResolver()

    with pytest.raises(KeyError):
        resolver.resolve(encoded.job_type, encoded.version + 1)
    with pytest.raises(KeyError):
        resolver.resolve("tests.queue.fakes:Job", 1)


@pytest.mark.parametrize("allowed_packages", [(), ("",)])
def test_resolver_rejects_invalid_allowed_packages(allowed_packages: tuple[str, ...]) -> None:
    with pytest.raises(QueueConfigurationError):
        JobResolver(allowed_packages)
