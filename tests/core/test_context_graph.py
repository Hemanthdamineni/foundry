"""Tests for ContextGraph — symbol-level repository understanding."""

from __future__ import annotations

import pytest

from foundry.core.context_graph import (
    ContextGraph,
    Relationship,
    RelationshipKind,
    Symbol,
    SymbolKind,
)


class TestSymbol:
    def test_qualified_name_no_parent(self) -> None:
        sym = Symbol(
            name="my_func",
            kind=SymbolKind.FUNCTION,
            file_path="mod.py",
            line_start=1,
            line_end=5,
            parent_module="mod",
        )
        assert sym.qualified_name == "mod.my_func"

    def test_qualified_name_with_class(self) -> None:
        sym = Symbol(
            name="my_method",
            kind=SymbolKind.METHOD,
            file_path="mod.py",
            line_start=1,
            line_end=5,
            parent_class="MyClass",
            parent_module="mod",
        )
        assert sym.qualified_name == "mod.MyClass.my_method"

    def test_to_dict_roundtrip(self) -> None:
        sym = Symbol(
            name="test_func",
            kind=SymbolKind.FUNCTION,
            file_path="test.py",
            line_start=1,
            line_end=10,
            docstring="A test function.",
        )
        d = sym.to_dict()
        assert d["name"] == "test_func"
        assert d["kind"] == "function"
        assert d["docstring"] == "A test function."


class TestContextGraphParsing:
    def test_add_file_with_class(self) -> None:
        graph = ContextGraph()
        content = '''
class MyClass:
    """A test class."""

    def my_method(self):
        """A method."""
        pass
'''
        count = graph.add_file("test.py", content)
        assert count == 2  # class + method

        symbols = graph.get_file_symbols("test.py")
        names = [s.name for s in symbols]
        assert "MyClass" in names
        assert "my_method" in names

    def test_add_file_with_functions(self) -> None:
        graph = ContextGraph()
        content = '''
def add(a, b):
    """Add two numbers."""
    return a + b

def subtract(a, b):
    """Subtract two numbers."""
    return a - b
'''
        count = graph.add_file("math.py", content)
        assert count == 2

        symbols = graph.get_file_symbols("math.py")
        names = [s.name for s in symbols]
        assert "add" in names
        assert "subtract" in names

    def test_docstring_extraction(self) -> None:
        graph = ContextGraph()
        content = '''
def documented():
    """This is the docstring."""
    pass
'''
        graph.add_file("mod.py", content)
        symbols = graph.get_file_symbols("mod.py")
        assert len(symbols) == 1
        assert symbols[0].docstring == "This is the docstring."

    def test_multiline_docstring(self) -> None:
        graph = ContextGraph()
        content = '''
def documented():
    """
    This is a multi-line
    docstring.
    """
    pass
'''
        graph.add_file("mod.py", content)
        symbols = graph.get_file_symbols("mod.py")
        assert len(symbols) == 1
        assert "multi-line" in symbols[0].docstring


class TestContextGraphQuery:
    def test_query_by_name(self) -> None:
        graph = ContextGraph()
        content = '''
def authenticate_user(username, password):
    """Authenticate a user."""
    pass

def get_user(user_id):
    """Get a user by ID."""
    pass
'''
        graph.add_file("auth.py", content)

        results = graph.query("authenticate user login")
        assert len(results) > 0
        assert results[0].name == "authenticate_user"

    def test_query_by_docstring(self) -> None:
        graph = ContextGraph()
        content = '''
def calculate_tax(amount, rate):
    """Calculate sales tax for an invoice."""
    return amount * rate
'''
        graph.add_file("billing.py", content)

        results = graph.query("tax calculation invoice")
        assert len(results) > 0
        assert results[0].name == "calculate_tax"

    def test_query_no_match(self) -> None:
        graph = ContextGraph()
        content = '''
def foo():
    pass
'''
        graph.add_file("mod.py", content)

        results = graph.query("xyzzy")
        assert len(results) == 0


class TestContextGraphRelationships:
    def test_call_relationships(self) -> None:
        graph = ContextGraph()
        content = '''
def helper():
    pass

def main():
    helper()
'''
        graph.add_file("app.py", content)

        callees = graph.get_callees("app.main")
        callee_names = [s.name for s in callees]
        assert "helper" in callee_names

    def test_inheritance_relationships(self) -> None:
        graph = ContextGraph()
        content = '''
class Base:
    pass

class Derived(Base):
    pass
'''
        graph.add_file("inherit.py", content)

        inherits = graph.get_inherits("inherit.Derived")
        inherit_names = [s.name for s in inherits]
        assert "Base" in inherit_names


class TestContextGraphSearch:
    def test_search_by_name(self) -> None:
        graph = ContextGraph()
        content = '''
def authenticate_user():
    pass

def authorization_check():
    pass
'''
        graph.add_file("auth.py", content)

        results = graph.search_by_name("auth")
        assert len(results) == 2

    def test_get_symbol(self) -> None:
        graph = ContextGraph()
        content = '''
def my_func():
    pass
'''
        graph.add_file("mod.py", content)

        sym = graph.get_symbol("mod.my_func")
        assert sym is not None
        assert sym.name == "my_func"

    def test_stats(self) -> None:
        graph = ContextGraph()
        content = '''
class MyClass:
    def method(self):
        pass

def standalone():
    pass
'''
        graph.add_file("mod.py", content)
        stats = graph.stats
        assert stats["total_symbols"] == 3
        assert stats["files_indexed"] == 1
        assert stats["symbols_by_kind"]["class"] == 1
        assert stats["symbols_by_kind"]["method"] == 1
        assert stats["symbols_by_kind"]["function"] == 1
