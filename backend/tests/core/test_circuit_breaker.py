import pytest
from src.core.errors import CircuitBreakerError
from src.core.resilience.circuit_breaker import CircuitBreaker, CircuitState


@pytest.mark.asyncio
async def test_closed_by_default():
    cb = CircuitBreaker("test")
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_opens_after_threshold():
    cb = CircuitBreaker("test", failure_threshold=2)

    async def failing():
        raise ValueError("fail")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.execute(failing)

    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_open_raises_circuit_breaker_error():
    cb = CircuitBreaker("test", failure_threshold=1)

    async def failing():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        await cb.execute(failing)

    with pytest.raises(CircuitBreakerError):
        await cb.execute(failing)


@pytest.mark.asyncio
async def test_reset():
    cb = CircuitBreaker("test", failure_threshold=1)

    async def failing():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        await cb.execute(failing)

    cb.reset()
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_success_resets_failures():
    cb = CircuitBreaker("test", failure_threshold=3)

    async def success():
        return 42

    result = await cb.execute(success)
    assert result == 42
    assert cb._failures == 0
