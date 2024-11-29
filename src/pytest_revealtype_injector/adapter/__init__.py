from __future__ import annotations

from ..models import TypeCheckerAdapter
from . import mypy_, pyright_


# Hardcode will do for now, it's not like we're going to have more
# adapters soon. Pyre and PyType are not there yet.
def discovery() -> set[TypeCheckerAdapter]:
    return {
        pyright_.adapter,
        mypy_.adapter,
    }
