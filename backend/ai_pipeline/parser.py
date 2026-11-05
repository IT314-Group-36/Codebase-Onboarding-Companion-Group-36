"""Tree-sitter based extraction of symbols, imports and calls.

Supports Python, JavaScript/JSX, TypeScript and TSX. Other files are chunked as plain text.
Call extraction is syntactic (names, not types), so downstream graphs are approximations.
"""
import threading
from dataclasses import dataclass, field
from pathlib import PurePosixPath

LANG_BY_EXT = {".py": "python", ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
               ".cjs": "javascript", ".ts": "typescript", ".tsx": "tsx"}

_local = threading.local()          # tree-sitter parsers are not thread-safe: one per thread


def _get_parser(lang: str):
    cache = getattr(_local, "parsers", None)
    if cache is None:
        cache = _local.parsers = {}
    if lang not in cache:
        from tree_sitter import Language, Parser
        if lang == "python":
            import tree_sitter_python as mod
            handle = mod.language()
        elif lang == "javascript":
            import tree_sitter_javascript as mod
            handle = mod.language()
        else:
            import tree_sitter_typescript as mod
            handle = mod.language_tsx() if lang == "tsx" else mod.language_typescript()
        cache[lang] = Parser(Language(handle))
    return cache[lang]


@dataclass
class Symbol:
    uid: str                    # "<path>::<qualname>", unique per repo
    name: str
    qualname: str
    kind: str                   # function | method | class
    path: str
    start_line: int             # 1-based, inclusive
    end_line: int
    signature: str
    parent: str | None = None   # uid of enclosing symbol
    calls: set = field(default_factory=set)   # {(called_name, qualifier)}; qualifier None = plain call, "?" = unknown receiver


@dataclass
class ParsedFile:
    path: str
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)          # module specifiers as written
    bindings: dict = field(default_factory=dict)              # local name -> (module spec, original name)
    parse_error: bool = False


class _Base:
    def __init__(self, path: str, lang: str, src: bytes):
        self.path, self.lang, self.src = path, lang, src
        self.symbols: list[Symbol] = []
        self.imports: list[str] = []
        self.bindings: dict = {}
        self.module_calls: set = set()
        self._uids: dict[str, int] = {}

    def text(self, node) -> str:
        return self.src[node.start_byte:node.end_byte].decode("utf-8", "replace")

    def add_symbol(self, name: str, kind: str, range_node, scope: list[Symbol]) -> Symbol:
        qual = f"{scope[-1].qualname}.{name}" if scope else name
        uid = f"{self.path}::{qual}"
        n = self._uids.get(uid, 0) + 1
        self._uids[uid] = n
        if n > 1:
            uid = f"{uid}#{n}"
        start = range_node.start_point.row + 1
        end = range_node.end_point.row + (1 if range_node.end_point.column > 0 else 0)
        sig = self.text(range_node).split("\n", 1)[0].strip()[:200]
        sym = Symbol(uid, name, qual, kind, self.path, start, max(start, end), sig,
                     scope[-1].uid if scope else None)
        self.symbols.append(sym)
        return sym

    def record_call(self, scope, name: str, obj):
        (scope[-1].calls if scope else self.module_calls).add((name, obj))

    def visit(self, node, scope: list[Symbol]):
        if self.handle(node, scope):
            return
        for child in node.children:
            self.visit(child, scope)

    def visit_children(self, node, scope):
        if node is not None:
            for child in node.children:
                self.visit(child, scope)

    def handle(self, node, scope) -> bool:      # True = children already handled
        raise NotImplementedError


class _Py(_Base):
    def handle(self, node, scope):
        t = node.type
        if t == "decorated_definition":
            d = node.child_by_field_name("definition")
            if d is not None:
                self._def(d, scope, node)
            return True
        if t in ("function_definition", "class_definition"):
            self._def(node, scope, node)
            return True
        if t == "import_statement":
            for n in node.children_by_field_name("name"):
                if n.type == "aliased_import":
                    spec, local = self.text(n.child_by_field_name("name")), self.text(n.child_by_field_name("alias"))
                else:
                    spec = local = self.text(n)
                self.imports.append(spec)
                self.bindings[local] = (spec, "*")
            return True
        if t == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            if mod is None:
                return True
            spec = self.text(mod)
            self.imports.append(spec)
            for n in node.children_by_field_name("name"):
                if n.type == "aliased_import":
                    orig, local = self.text(n.child_by_field_name("name")), self.text(n.child_by_field_name("alias"))
                else:
                    orig = local = self.text(n)
                self.imports.append(spec + orig if spec.endswith(".") else f"{spec}.{orig}")  # maybe a submodule
                self.bindings[local] = (spec, orig)
            return True
        if t == "call":
            fn = node.child_by_field_name("function")
            if fn is not None and fn.type == "identifier":
                self.record_call(scope, self.text(fn), None)
            elif fn is not None and fn.type == "attribute":
                obj = fn.child_by_field_name("object")
                attr = fn.child_by_field_name("attribute")
                self.record_call(scope, self.text(attr),
                                 self.text(obj) if obj is not None and obj.type == "identifier" else "?")
        return False

    def _def(self, node, scope, range_node):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return
        if node.type == "class_definition":
            kind = "class"
        else:
            kind = "method" if scope and scope[-1].kind == "class" else "function"
        sym = self.add_symbol(self.text(name_node), kind, range_node, scope)
        self.visit_children(node.child_by_field_name("body"), scope + [sym])


_JS_FUNC_VALUES = {"arrow_function", "function_expression", "function", "generator_function"}


class _Js(_Base):
    def handle(self, node, scope):
        t = node.type
        if t in ("function_declaration", "generator_function_declaration"):
            return self._def(node, "function", scope)
        if t in ("class_declaration", "abstract_class_declaration"):
            return self._def(node, "class", scope)
        if t == "method_definition":
            return self._def(node, "method", scope)
        if t == "variable_declarator":
            return self._declarator(node, scope)
        if t == "import_statement":
            self._import(node)
            return True
        if t == "export_statement":
            src = node.child_by_field_name("source")
            if src is not None:
                self.imports.append(self._str(src))
                return True
            return False
        if t == "call_expression":
            return self._call(node, scope)
        if t == "new_expression":
            ctor = node.child_by_field_name("constructor")
            if ctor is not None and ctor.type == "identifier":
                self.record_call(scope, self.text(ctor), None)
            return False
        if t in ("jsx_self_closing_element", "jsx_opening_element"):
            name = node.child_by_field_name("name")
            if name is not None and name.type == "identifier" and self.text(name)[:1].isupper():
                self.record_call(scope, self.text(name), None)      # <Component /> counts as a use
            return False
        return False

    def _str(self, node) -> str:
        frag = next((c for c in node.children if c.type == "string_fragment"), None)
        return self.text(frag) if frag is not None else self.text(node).strip("'\"`")

    def _require_spec(self, call):
        fn, args = call.child_by_field_name("function"), call.child_by_field_name("arguments")
        if fn is not None and fn.type == "identifier" and self.text(fn) == "require" and args is not None:
            first = next((c for c in args.children if c.type == "string"), None)
            return self._str(first) if first is not None else None
        return None

    def _def(self, node, kind, scope) -> bool:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return False
        range_node = node
        if node.parent is not None and node.parent.type == "export_statement":
            range_node = node.parent
        sym = self.add_symbol(self.text(name_node), kind, range_node, scope)
        self.visit_children(node.child_by_field_name("body"), scope + [sym])
        return True

    def _declarator(self, node, scope) -> bool:
        name, value = node.child_by_field_name("name"), node.child_by_field_name("value")
        if name is None or value is None or name.type != "identifier":
            return False
        if value.type in _JS_FUNC_VALUES:
            outer, p = node, node.parent
            if p is not None and p.type in ("lexical_declaration", "variable_declaration"):
                outer, p = p, p.parent
            if p is not None and p.type == "export_statement":
                outer = p
            sym = self.add_symbol(self.text(name), "function", outer, scope)
            body = value.child_by_field_name("body")
            if body is not None:
                self.visit(body, scope + [sym])
            return True
        if value.type == "call_expression":
            spec = self._require_spec(value)
            if spec:
                self.imports.append(spec)
                self.bindings[self.text(name)] = (spec, "*")
                return True
        return False

    def _import(self, node):
        src = node.child_by_field_name("source")
        if src is None:
            return
        spec = self._str(src)
        self.imports.append(spec)
        for clause in (c for c in node.children if c.type == "import_clause"):
            for c in clause.children:
                if c.type == "identifier":
                    self.bindings[self.text(c)] = (spec, "default")
                elif c.type == "namespace_import":
                    ident = next((x for x in c.children if x.type == "identifier"), None)
                    if ident is not None:
                        self.bindings[self.text(ident)] = (spec, "*")
                elif c.type == "named_imports":
                    for sp in (x for x in c.children if x.type == "import_specifier"):
                        n, a = sp.child_by_field_name("name"), sp.child_by_field_name("alias")
                        orig = self.text(n)
                        self.bindings[self.text(a) if a is not None else orig] = (spec, orig)

    def _call(self, node, scope) -> bool:
        fn = node.child_by_field_name("function")
        if fn is None:
            return False
        if fn.type == "identifier":
            if self.text(fn) == "require":
                spec = self._require_spec(node)
                if spec:
                    self.imports.append(spec)
                    return True
            self.record_call(scope, self.text(fn), None)
        elif fn.type == "member_expression":
            prop, obj = fn.child_by_field_name("property"), fn.child_by_field_name("object")
            if prop is not None:
                self.record_call(scope, self.text(prop),
                                 self.text(obj) if obj is not None and obj.type in ("identifier", "this") else "?")
        return False


def language_of(path: str) -> str | None:
    return LANG_BY_EXT.get(PurePosixPath(path).suffix.lower())


def parse_file(path: str, text: str) -> ParsedFile | None:
    """Parse one file. Returns None for unsupported languages."""
    lang = language_of(path)
    if lang is None:
        return None
    src = text.encode("utf-8")
    ex = (_Py if lang == "python" else _Js)(path, lang, src)
    try:
        tree = _get_parser(lang).parse(src)
        ex.visit(tree.root_node, [])
    except RecursionError:                       # pathological/generated file: fall back to text chunking
        return ParsedFile(path, lang, parse_error=True)
    return ParsedFile(path, lang, ex.symbols, ex.imports, ex.bindings, tree.root_node.has_error)
