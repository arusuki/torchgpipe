from typing import Callable

import pytest

from torchgpipe.distributed.context import (distributed, get_backward, get_forward, put_backward,
                                            put_forward, worker)


@pytest.fixture
def data():
    return {
        3: "456",
        17: "91011",
        29: "0721"
    }


def _test_kv(name: str, data, put: Callable, get: Callable):
    for k, v in data.items():
        put(name, k, v)
    for k, v in data.items():
        vv = get(name, k)
        assert v == vv


@pytest.mark.timeout(10)
@pytest.mark.parametrize('put,get', [
    [put_forward, get_forward],
    [put_backward, get_backward]
])
def test_put_get(data, put: Callable, get: Callable):
    name = "worker0"
    with worker(name, 32):
        _test_kv(name, data, put, get)


@pytest.mark.parametrize('put', [
    put_forward,
    put_backward
])
def test_illegal(put: Callable):
    try:
        put("Unstarted worker", 0, None)
        pytest.fail("allow put on unkown context")
    except KeyError:
        return


def test_restart():
    name = "redundant"
    try:
        with worker(name, 32):
            with worker(name, 32):
                pytest.fail("allow restart worker context")
    except RuntimeError:
        return


@distributed("worker1", 32)
def _test_single_decorator(data, put, get):
    _test_kv("worker1", data, put, get)


@distributed("worker2", 32)
@distributed("worker3", 32)
@distributed("worker4", 32)
def _test_double_decorator(data, put, get):
    _test_kv("worker2", data, put, get)
    _test_kv("worker3", data, put, get)
    _test_kv("worker4", data, put, get)


@pytest.mark.parametrize("put,get", [[put_forward, get_forward], [put_backward, get_backward]])
def test_decorator(data, put, get):
    _test_single_decorator(data, put, get)
    _test_double_decorator(data, put, get)
