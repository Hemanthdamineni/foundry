from __future__ import annotations

import pytest

from sdlc_mcp.adapters.base import ToolCapability
from sdlc_mcp.adapters.tools.graphify import GraphifyAdapter
from sdlc_mcp.adapters.tools.tree_sitter import TreeSitterAdapter
from sdlc_mcp.engine.dependency_graph import (
    DependencyGraphEngine,
    _detect_language,
    _extract_imports_python,
    _extract_python_symbols,
    parse_file,
    resolve_import_to_file,
)
from sdlc_mcp.models import (
    CodeSymbol,
    ContextChunk,
    DependencyGraph,
    FileIndex,
    ImportInfo,
    IndexConfig,
    SymbolKind,
)
from sdlc_mcp.runtime.pipelines.default import IndexPipeline, _should_index


class TestModels:
    def test_code_symbol_defaults(self) -> None:
        s = CodeSymbol(name="foo", file_path="/test.py")
        assert s.kind == SymbolKind.UNKNOWN
        assert s.start_line == 0
        assert s.parent is None

    def test_code_symbol_with_kind(self) -> None:
        s = CodeSymbol(
            name="MyClass", kind=SymbolKind.CLASS, file_path="/test.py", start_line=10, end_line=50,
        )
        assert s.kind == SymbolKind.CLASS
        assert s.start_line == 10

    def test_import_info(self) -> None:
        imp = ImportInfo(source="os", file_path="/test.py", line=1)
        assert imp.source == "os"
        assert imp.is_relative is False

    def test_file_index_roundtrip(self) -> None:
        fi = FileIndex(
            path="/test.py",
            language="python",
            symbols=[CodeSymbol(name="foo", kind=SymbolKind.FUNCTION, file_path="/test.py")],
            imports=[ImportInfo(source="sys", file_path="/test.py")],
        )
        data = fi.model_dump(mode="json")
        restored = FileIndex(**data)
        assert restored.symbols[0].name == "foo"
        assert restored.imports[0].source == "sys"

    def test_dependency_graph_defaults(self) -> None:
        dg = DependencyGraph()
        assert dg.file_count == 0
        assert dg.files == {}

    def test_context_chunk(self) -> None:
        c = ContextChunk(
            file_path="/test.py",
            content="def foo(): pass",
            start_line=1,
            end_line=3,
            relevance_score=0.9,
        )
        assert c.symbol_name is None
        assert c.relevance_score == 0.9

    def test_index_config_defaults(self) -> None:
        cfg = IndexConfig()
        assert cfg.enabled is True
        assert cfg.max_files == 5000
        assert "*.py" in cfg.include_patterns


class TestLanguageDetection:
    def test_python(self) -> None:
        assert _detect_language("foo.py") == "python"

    def test_javascript(self) -> None:
        assert _detect_language("foo.js") == "javascript"
        assert _detect_language("foo.jsx") == "jsx"

    def test_typescript(self) -> None:
        assert _detect_language("foo.ts") == "typescript"
        assert _detect_language("foo.tsx") == "tsx"

    def test_unknown(self) -> None:
        assert _detect_language("foo.xyz") == "unknown"

    def test_yaml(self) -> None:
        assert _detect_language("config.yaml") == "yaml"

    def test_markdown(self) -> None:
        assert _detect_language("readme.md") == "markdown"


class TestPythonASTParsing:
    def test_extract_function(self) -> None:
        code = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        symbols = _extract_python_symbols("/test.py", code)
        assert len(symbols) == 1
        assert symbols[0].name == "greet"
        assert symbols[0].kind == SymbolKind.FUNCTION

    def test_extract_class_with_methods(self) -> None:
        code = """class Greeter:
    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        return f"Hello, {self.name}!"
"""
        symbols = _extract_python_symbols("/test.py", code)
        names = {s.name for s in symbols}
        kinds = {(s.name, s.kind) for s in symbols}
        assert "Greeter" in names
        assert ("Greeter", SymbolKind.CLASS) in kinds
        assert ("__init__", SymbolKind.METHOD) in kinds
        assert ("greet", SymbolKind.METHOD) in kinds

    def test_extract_async_function(self) -> None:
        code = "async def fetch(url: str) -> dict:\n    return {'ok': True}\n"
        symbols = _extract_python_symbols("/test.py", code)
        assert len(symbols) == 1
        assert symbols[0].name == "fetch"

    def test_syntax_error_returns_empty(self) -> None:
        code = "def broken(\n"
        symbols = _extract_python_symbols("/test.py", code)
        assert symbols == []

    def test_extract_imports_standard(self) -> None:
        code = "import os\nimport sys\n"
        imports = _extract_imports_python("/test.py", code)
        sources = {imp.source for imp in imports}
        assert "os" in sources
        assert "sys" in sources

    def test_extract_imports_from(self) -> None:
        code = "from typing import List, Optional\n"
        imports = _extract_imports_python("/test.py", code)
        sources = {imp.source for imp in imports}
        assert "List" in sources
        assert "Optional" in sources

    def test_extract_imports_from_module(self) -> None:
        code = "from collections.abc import Iterable\n"
        imports = _extract_imports_python("/test.py", code)
        assert any(imp.source == "Iterable" for imp in imports)


class TestDependencyGraphEngine:
    @pytest.mark.asyncio
    async def test_update_and_retrieve(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello(): pass\n")
        fi = parse_file(str(test_file))
        await engine.update_file(str(test_file), fi)
        assert str(test_file) in engine.graph.files
        assert engine.graph.file_count == 1

    @pytest.mark.asyncio
    async def test_remove_file(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("def a(): pass\n")
        f2.write_text("def b(): pass\n")
        await engine.update_file(str(f1), parse_file(str(f1)))
        await engine.update_file(str(f2), parse_file(str(f2)))
        assert engine.graph.file_count == 2
        await engine.remove_file(str(f1))
        assert engine.graph.file_count == 1
        assert str(f1) not in engine.graph.files

    @pytest.mark.asyncio
    async def test_get_symbol(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("class MyClass:\n    pass\n\ndef my_func(): pass\n")
        await engine.update_file(str(f), parse_file(str(f)))
        symbols = await engine.get_symbol("my_func")
        assert len(symbols) == 1
        assert symbols[0].name == "my_func"

    @pytest.mark.asyncio
    async def test_get_symbols_by_kind(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("class A:\n    pass\nclass B:\n    pass\n")
        await engine.update_file(str(f), parse_file(str(f)))
        classes = await engine.get_symbols_by_kind(SymbolKind.CLASS)
        assert len(classes) == 2

    @pytest.mark.asyncio
    async def test_persist_and_load(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        await engine.update_file(str(f), parse_file(str(f)))
        await engine.persist()

        engine2 = DependencyGraphEngine(tmp_path)
        loaded = await engine2.load()
        assert loaded
        assert engine2.graph.file_count == 1

    @pytest.mark.asyncio
    async def test_empty_load(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        loaded = await engine.load()
        assert loaded is False

    @pytest.mark.asyncio
    async def test_get_file_context(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")
        await engine.update_file(str(f), parse_file(str(f)))
        chunks = await engine.get_file_context(str(f), max_chunks=10)
        assert len(chunks) >= 2
        assert any(c.symbol_name == "foo" for c in chunks)
        assert any(c.symbol_name == "bar" for c in chunks)

    @pytest.mark.asyncio
    async def test_get_file_context_no_symbols(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        f = tmp_path / "notes.md"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        fi = parse_file(str(f))
        await engine.update_file(str(f), fi)
        chunks = await engine.get_file_context(str(f), chunk_size=2)
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_find_files_matching(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        for name in ["a.py", "b.py", "test_a.py"]:
            p = tmp_path / name
            p.write_text("x = 1\n")
            await engine.update_file(str(p), parse_file(str(p)))
        matches = await engine.find_files_matching("test_*.py")
        assert len(matches) == 1
        assert "test_a" in matches[0]

    @pytest.mark.asyncio
    async def test_get_relevant_context(self, tmp_path) -> None:
        engine = DependencyGraphEngine(tmp_path)
        for name in ["core.py", "utils.py", "main.py"]:
            p = tmp_path / name
            p.write_text("def func(): pass\n")
            await engine.update_file(str(p), parse_file(str(p)))
        chunks = await engine.get_relevant_context(
            target_files=[str(tmp_path / "main.py")],
            max_files=5,
            max_chunks=10,
        )
        assert len(chunks) > 0


class TestParseFile:
    def test_parse_python_file(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("import os\n\ndef hello():\n    return 'hi'\n")
        fi = parse_file(str(f))
        assert fi.language == "python"
        assert len(fi.imports) >= 1
        assert len(fi.symbols) >= 1
        assert fi.sha256 != ""

    def test_parse_non_python_file(self, tmp_path) -> None:
        f = tmp_path / "test.js"
        f.write_text("function hello() {\n  return 'hi';\n}\n")
        fi = parse_file(str(f))
        assert fi.language == "javascript"

    def test_parse_nonexistent_file(self) -> None:
        fi = parse_file("/nonexistent/file.py")
        assert fi.sha256 != ""
        assert fi.symbols == []

    def test_parse_markdown_file(self, tmp_path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello\n\nThis is a test.\n")
        fi = parse_file(str(f))
        assert fi.language == "markdown"


class TestResolveImport:
    def test_resolve_python_import(self) -> None:
        imp = ImportInfo(source="os", file_path="/workspace/main.py")
        known = {"/workspace/os.py", "/workspace/utils.py"}
        result = resolve_import_to_file(imp, known, search_paths=["/workspace"])
        assert result == "/workspace/os.py"

    def test_resolve_with_search_paths(self) -> None:
        imp = ImportInfo(source="mymod", file_path="/workspace/src/main.py")
        known = {"/workspace/src/mymod.py", "/workspace/src/mymod/__init__.py"}
        result = resolve_import_to_file(imp, known, search_paths=["/workspace/src"])
        assert result in known

    def test_resolve_unresolvable(self) -> None:
        imp = ImportInfo(source="nonexistent", file_path="/workspace/main.py")
        result = resolve_import_to_file(imp, set())
        assert result is None


class TestTreeSitterAdapter:
    @pytest.mark.asyncio
    async def test_adapter_capability(self) -> None:
        adapter = TreeSitterAdapter()
        assert adapter.name == "tree_sitter"
        assert adapter.capability == ToolCapability.CODE_GRAPH

    @pytest.mark.asyncio
    async def test_healthcheck_always_available(self) -> None:
        adapter = TreeSitterAdapter()
        assert await adapter.healthcheck() is True

    @pytest.mark.asyncio
    async def test_validate_with_path(self, tmp_path) -> None:
        adapter = TreeSitterAdapter()
        assert await adapter.validate({"path": str(tmp_path)}) is True

    @pytest.mark.asyncio
    async def test_validate_no_path(self) -> None:
        adapter = TreeSitterAdapter()
        assert await adapter.validate({}) is False

    @pytest.mark.asyncio
    async def test_execute_on_python_file(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def hello(): pass\nimport os\n")
        adapter = TreeSitterAdapter()
        result = await adapter.execute({"path": str(f)})
        assert result["adapter"] == "tree_sitter"
        assert result["details"]["total_files"] == 1
        assert result["details"]["total_symbols"] >= 1

    @pytest.mark.asyncio
    async def test_execute_syntax_error_graceful(self, tmp_path) -> None:
        f = tmp_path / "broken.py"
        f.write_text("def broken(\n  pass\n")
        adapter = TreeSitterAdapter()
        result = await adapter.execute({"path": str(f)})
        assert "errors" in result["details"]
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_execute_no_path_returns_error(self) -> None:
        adapter = TreeSitterAdapter()
        result = await adapter.execute({})
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_execute_empty_directory(self, tmp_path) -> None:
        adapter = TreeSitterAdapter()
        result = await adapter.execute({"path": str(tmp_path), "recursive": True})
        assert result["details"]["total_files"] == 0

    @pytest.mark.asyncio
    async def test_chunk_file(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("def a():\n    pass\n\ndef b():\n    pass\n")
        adapter = TreeSitterAdapter()
        chunks = await adapter.chunk_file(str(f), max_lines=50)
        assert len(chunks) >= 2

    @pytest.mark.asyncio
    async def test_chunk_file_nonexistent(self) -> None:
        adapter = TreeSitterAdapter()
        chunks = await adapter.chunk_file("/nonexistent.py")
        assert chunks == []

    @pytest.mark.asyncio
    async def test_execute_recursive_directory(self, tmp_path) -> None:
        (tmp_path / "sub").mkdir()
        (tmp_path / "a.py").write_text("def a(): pass\n")
        (tmp_path / "sub/b.py").write_text("def b(): pass\n")
        adapter = TreeSitterAdapter()
        result = await adapter.execute({"path": str(tmp_path), "recursive": True})
        assert result["details"]["total_files"] == 2


class TestGraphifyAdapter:
    @pytest.mark.asyncio
    async def test_adapter_capability(self) -> None:
        adapter = GraphifyAdapter()
        assert adapter.name == "graphify"
        assert adapter.capability == ToolCapability.CODE_GRAPH

    @pytest.mark.asyncio
    async def test_healthcheck_not_installed(self) -> None:
        adapter = GraphifyAdapter(graphify_path="nonexistent_graphify_cli")
        assert await adapter.healthcheck() is False

    @pytest.mark.asyncio
    async def test_execute_no_path(self) -> None:
        adapter = GraphifyAdapter()
        result = await adapter.execute({})
        assert result["passed"] is False
        assert "No workspace" in result["summary"]

    @pytest.mark.asyncio
    async def test_execute_cli_unavailable(self, tmp_path) -> None:
        adapter = GraphifyAdapter(graphify_path="nonexistent_cli")
        result = await adapter.execute({"path": str(tmp_path)})
        assert result["passed"] is False
        assert "not available" in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_validate_with_path(self, tmp_path) -> None:
        adapter = GraphifyAdapter()
        assert await adapter.validate({"path": str(tmp_path)}) is True

    @pytest.mark.asyncio
    async def test_validate_no_path(self) -> None:
        adapter = GraphifyAdapter()
        assert await adapter.validate({}) is False

    @pytest.mark.asyncio
    async def test_query_graph_no_graph(self, tmp_path) -> None:
        adapter = GraphifyAdapter(cache_dir=tmp_path / "missing-graph")
        result = await adapter.query_graph("test query")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_graph_summary_no_graph(self, tmp_path) -> None:
        adapter = GraphifyAdapter(cache_dir=tmp_path / "missing-graph")
        result = await adapter.get_graph_summary()
        assert "error" in result


class TestIndexPipeline:
    @pytest.mark.asyncio
    async def test_initialize(self, tmp_path) -> None:
        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True),
        )
        await pipeline.initialize()
        assert pipeline.stats["enabled"] is True

    @pytest.mark.asyncio
    async def test_full_index_on_python_files(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/main.py").write_text("def main(): pass\n")
        (tmp_path / "src/utils.py").write_text("def util(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        result = await pipeline.run_full_index()
        assert result["status"] == "ok"
        assert result["files_indexed"] == 2
        assert result["total_files"] == 2

    @pytest.mark.asyncio
    async def test_incremental_index(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/a.py").write_text("def a(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, incremental=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        result1 = await pipeline.run_full_index()
        assert result1["files_indexed"] == 1

        result2 = await pipeline.run_incremental_index()
        assert result2["files_skipped"] >= 0
        assert result2["total_files"] == 1

    @pytest.mark.asyncio
    async def test_index_detects_changed_files(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        f = tmp_path / "src/app.py"
        f.write_text("def old(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        await pipeline.run_full_index()
        assert pipeline.graph.graph.file_count == 1

        f.write_text("def new(): pass\n")
        result = await pipeline.run_incremental_index()
        assert result["files_indexed"] >= 1

    @pytest.mark.asyncio
    async def test_context_for_phase(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/main.py").write_text("def start(): pass\n")
        (tmp_path / "src/utils.py").write_text("def help(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        await pipeline.run_full_index()

        ctx = await pipeline.get_context_for_phase(
            phase="Coding",
            target_files=[str(tmp_path / "src/main.py")],
        )
        assert "relevant_files" in ctx
        assert "context_chunks" in ctx
        assert "graph_summary" in ctx

    @pytest.mark.asyncio
    async def test_context_for_phase_disabled(self, tmp_path) -> None:
        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=False),
        )
        await pipeline.initialize()
        ctx = await pipeline.get_context_for_phase(phase="Coding")
        assert ctx["context_chunks"] == []
        assert ctx["graph_summary"] == {}

    @pytest.mark.asyncio
    async def test_dependency_context(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/lib.py").write_text("def lib_func(): pass\n")
        (tmp_path / "src/main.py").write_text("from lib import lib_func\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        await pipeline.run_full_index()

        dep_ctx = await pipeline.get_dependency_context(str(tmp_path / "src/main.py"))
        assert dep_ctx["file"] == str(tmp_path / "src/main.py")
        assert "symbols" in dep_ctx
        assert "dependencies" in dep_ctx
        assert "dependents" in dep_ctx

    @pytest.mark.asyncio
    async def test_index_specific_files(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        f = tmp_path / "src/new.py"
        f.write_text("def new_func(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        result = await pipeline.index_files([str(f)])
        assert result["files_indexed"] == 1
        assert str(f) in pipeline.graph.graph.files

    @pytest.mark.asyncio
    async def test_index_disabled(self, tmp_path) -> None:
        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=False),
        )
        await pipeline.initialize()
        result = await pipeline.run_full_index()
        assert result["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_run_graphify_index_no_adapter(self, tmp_path) -> None:
        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True),
        )
        await pipeline.initialize()
        result = await pipeline.run_graphify_index()
        assert result["status"] == "skipped"
        assert "adapter not available" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_index_non_indexable_files_skipped(self, tmp_path) -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data/big.bin").write_bytes(b"\x00" * 1024 * 1024)

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"], exclude_patterns=["*.bin"]),
        )
        await pipeline.initialize()
        result = await pipeline.run_full_index()
        assert result["total_files"] == 0

    @pytest.mark.asyncio
    async def test_index_prunes_excluded_directories(self, tmp_path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src/app.py").write_text("def app(): pass\n")
        pixi_dir = tmp_path / ".pixi" / "envs" / "default"
        pixi_dir.mkdir(parents=True)
        (pixi_dir / "site.py").write_text("def cached(): pass\n")

        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True),
        )
        await pipeline.initialize()
        result = await pipeline.run_full_index()
        assert result["files_indexed"] == 1
        assert str(tmp_path / "src/app.py") in pipeline.graph.graph.files


class TestShouldIndex:
    def test_included_python(self, tmp_path) -> None:
        f = tmp_path / "test.py"
        f.write_text("x = 1\n")
        cfg = IndexConfig()
        assert _should_index(f, cfg) is True

    def test_excluded_pycache(self, tmp_path) -> None:
        d = tmp_path / "__pycache__"
        d.mkdir()
        f = d / "test.pyc"
        f.write_text("")
        cfg = IndexConfig()
        assert _should_index(f, cfg) is False

    def test_excluded_git(self, tmp_path) -> None:
        d = tmp_path / ".git"
        d.mkdir()
        f = d / "config"
        f.write_text("")
        cfg = IndexConfig()
        assert _should_index(f, cfg) is False

    def test_excluded_nested_pixi_environment(self, tmp_path) -> None:
        d = tmp_path / ".pixi" / "envs" / "default"
        d.mkdir(parents=True)
        f = d / "site.py"
        f.write_text("x = 1\n")
        cfg = IndexConfig()
        assert _should_index(f, cfg) is False

    def test_too_large_skipped(self, tmp_path) -> None:
        f = tmp_path / "huge.py"
        data = "x\n" * 100000
        f.write_text(data)
        cfg = IndexConfig(max_file_size_kb=1)
        assert _should_index(f, cfg) is False

    def test_directory_not_indexed(self, tmp_path) -> None:
        cfg = IndexConfig()
        assert _should_index(tmp_path, cfg) is False

    def test_nonexistent_not_indexed(self, tmp_path) -> None:
        cfg = IndexConfig()
        assert _should_index(tmp_path / "nonexistent.py", cfg) is False


class TestAdapterBaseExt:
    def test_tool_capability_code_graph(self) -> None:
        assert ToolCapability.CODE_GRAPH == "code_graph"
        assert ToolCapability.CODE_GRAPH in ToolCapability


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_ast_parse_error_does_not_crash(self, tmp_path) -> None:
        f = tmp_path / "crash.py"
        f.write_text("""def valid():
    pass

@decorator
def invalid(:
    pass
""")
        ts = TreeSitterAdapter()
        result = await ts.execute({"path": str(f)})
        assert result["passed"] is False
        assert len(result["details"]["errors"]) > 0

    @pytest.mark.asyncio
    async def test_io_error_does_not_crash_pipeline(self, tmp_path) -> None:
        pipeline = IndexPipeline(
            workspace=tmp_path,
            store_dir=tmp_path / "index",
            config=IndexConfig(enabled=True, include_patterns=["*.py"]),
        )
        await pipeline.initialize()
        result = await pipeline.index_files(["/nonexistent/file.py"])
        assert result["files_indexed"] == 0

    @pytest.mark.asyncio
    async def test_binary_file_does_not_crash(self, tmp_path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        ts = TreeSitterAdapter()
        result = await ts.execute({"path": str(f)})
        assert "errors" in result["details"]
