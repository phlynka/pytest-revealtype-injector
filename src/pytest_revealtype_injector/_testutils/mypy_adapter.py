import ast
import json
import re
import typing as _t
from importlib import import_module
from pathlib import Path

import mypy.api

from .common import FilePos, TypeCheckerError, VarType

# {('file.py', 10): (None, '_Element'), ...}
typechecker_result: dict[FilePos, VarType] = {}
_mypy_re = re.compile(r'^Revealed type is "(?P<type>.+?)"$')
id = 'mypy'

# There are "column", "hint" and "code" fields for error
# messages but not in reveal_type output
class _MypyDiagObj(_t.TypedDict):
    file: str
    line: int
    severity: _t.Literal["note", "warning", "error"]
    message: str


def run_typechecker_on(paths: _t.Iterable[Path]) -> None:
    mypy_args = [
        "--output=json",
        "--config-file=rttest-mypy.ini",
    ]
    mypy_args.extend(str(p) for p in paths)
    # Note that mypy UNCONDITIONALLY exits with error when
    # output format is json, there is no point checking
    # exit code for problems
    stdout, _, _ = mypy.api.run(mypy_args)

    # So-called mypy json output is merely a line-by-line
    # transformation of plain text output into json object
    for line in stdout.splitlines():
        if not line.startswith('{'):
            continue
        # If it fails parsing data, json must be containing
        # multiline error hint, just let it KABOOM
        diag: _MypyDiagObj = json.loads(line)
        pos = FilePos(diag['file'], diag['line'])
        if diag['severity'] != 'note':
            raise TypeCheckerError(f"Mypy {diag['severity']} :'{diag['message']}'",
                diag['file'], diag['line'])
        if (m := _mypy_re.match(diag['message'])) is None:
            continue
        # Mypy can insert extra character into expression so that it
        # becomes invalid and unparseable. 0.9x days there
        # was '*', and now '?' (and '=' for typeddict too).
        # Try stripping those character and pray we get something
        # usable for evaluation
        expression = m['type'].translate({ord(c): None for c in '*?='})
        # Unlike pyright, mypy output doesn't contain variable name
        typechecker_result[pos] = VarType(None, _t.ForwardRef(expression))


class NameCollector(ast.NodeTransformer):
    # Preloaded for convenience
    collected: dict[str, _t.Any] = {
        'builtins': import_module('builtins'),
        'typing': import_module('typing'),
    }

    def __init__(
        self,
        globalns: dict[str, _t.Any],
        localns: dict[str, _t.Any],
    ) -> None:
        super().__init__()
        self.globalns = globalns
        self.localns = localns
        self.modified: bool = False

    def visit_Attribute(self, node: ast.Attribute) -> ast.expr:
        prefix = ast.unparse(node.value)
        name = node.attr

        setattr(node.value, 'is_parent', True)
        if not hasattr(node, 'is_parent'):  # Outmost attribute node
            try:
                _ = import_module(prefix)
            except ModuleNotFoundError:
                # Mypy resolve names according to external stub if
                # available. For example, _ElementTree is determined
                # as lxml.etree._element._ElementTree, which doesn't
                # exist in runtime. Try to resolve bare names
                # instead, which rely on runtime tests importing
                # them properly before resolving.
                try:
                    eval(name, self.globalns, self.localns | self.collected)
                except NameError as e:
                    raise NameError(f'Cannot resolve "{prefix}" or "{name}"') from e
                else:
                    self.modified = True
                    return ast.Name(id=name, ctx=node.ctx)

        _ = self.generic_visit(node)
        fullname = ast.unparse(node)
        self.collected[fullname] = getattr(self.collected[prefix], name)
        return node

    # Mypy usually dumps full inferred type with module name,
    # but with a few exceptions (like tuple, Union).
    # visit_Attribute can ultimately recurse into visit_Name
    # as well
    def visit_Name(self, node: ast.Name) -> ast.expr:
        name = node.id
        try:
            eval(name, self.globalns, self.localns | self.collected)
        except NameError:
            pass
        else:
            return node

        try:
            mod = import_module(name)
        except ModuleNotFoundError:
            pass
        else:
            self.collected[name] = mod
            return node

        for n in ('builtins', 'typing'):
            if hasattr(self.collected[n], name):
                self.collected[name] = getattr(self.collected[n], name)
                return node

        raise NameError(f'Cannot resolve "{name}"')
