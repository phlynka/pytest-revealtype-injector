from __future__ import annotations

import inspect
import logging

import pytest

from .adapter import mypy_, pyright_
from .main import revealtype_injector

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
                setattr(pyfuncitem.module, name, revealtype_injector)
                _logger.info(
                    f"Replaced {name}() from global import with {revealtype_injector}"
                )
                continue

        if inspect.ismodule(item):
            if item.__name__ not in {"typing", "typing_extensions"}:
                continue
            assert hasattr(item, "reveal_type")
            setattr(item, "reveal_type", revealtype_injector)
            _logger.info(f"Replaced {name}.reveal_type() with {revealtype_injector}")
            continue


def pytest_collection_finish(session: pytest.Session) -> None:
    files = {i.path for i in session.items}
    # TODO Automatic loading of typechecker adapters, and
    # selectively disable them based on pytest config
    for adapter in {pyright_.adapter, mypy_.adapter}:
        if adapter.enabled:
            adapter.run_typechecker_on(files)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup(
        "revealtype-injector",
        description="Type checker related options for revealtype-injector",
    )
    group.addoption(
        "--revealtype-disable-adapter",
        type=str,
        choices=("mypy", "pyright"),
        default=None,
        help="Disable this type checker when using revealtype-injector plugin",
    )
    group.addoption(
        "--revealtype-mypy-config",
        type=str,
        default=None,
        help="Mypy configuration file, path is relative to pytest rootdir. "
        "If unspecified, use mypy default behavior",
    )
    group.addoption(
        "--revealtype-pyright-config",
        type=str,
        default=None,
        help="Pyright configuration file, path is relative to pytest rootdir. "
        "If unspecified, use pyright default behavior",
    )


def pytest_configure(config: pytest.Config) -> None:
    enabled_adapters = {mypy_.adapter, pyright_.adapter}

    for adp in enabled_adapters:
        if config.option.revealtype_disable_adapter == adp.id:
            adp.enabled = False
        if adp.enabled:
            adp.set_config_file(config)
