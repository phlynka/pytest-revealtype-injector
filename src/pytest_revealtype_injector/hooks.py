from __future__ import annotations

import inspect
import logging

import pytest

from .adapter import mypy_, pyright_
from .main import reveal_type_wrapper

_logger = logging.getLogger(__name__)
_logger.setLevel(logging.INFO)


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> None:
    assert pyfuncitem.module is not None
    for name in dir(pyfuncitem.module):
        if name.startswith("__") or name.startswith("@py"):
            continue

        item = getattr(pyfuncitem.module, name)
        if inspect.isfunction(item):
            if item.__name__ == "reveal_type" and item.__module__ in {
                "typing",
                "typing_extensions",
            }:
                setattr(pyfuncitem.module, name, reveal_type_wrapper)
                _logger.info(
                    f"Replaced {name}() from global import with {reveal_type_wrapper}"
                )
                continue

        if inspect.ismodule(item):
            if item.__name__ not in {"typing", "typing_extensions"}:
                continue
            assert hasattr(item, "reveal_type")
            setattr(item, "reveal_type", reveal_type_wrapper)
            _logger.info(f"Replaced {name}.reveal_type() with {reveal_type_wrapper}")
            continue


def pytest_collection_finish(session: pytest.Session) -> None:
    files = {i.path for i in session.items}
    # TODO Automatic loading of typechecker adapters, and
    # selectively disable them based on pytest config
    for adapter in (pyright_.adapter, mypy_.adapter):
        adapter.run_typechecker_on(files)
