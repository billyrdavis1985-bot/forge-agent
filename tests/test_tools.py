"""append_log is contained by construction — no path argument to abuse."""
from pathlib import Path
import pytest
from src.agent_tools import append_log, build_tools_server, APPEND_LOG_TOOL

@pytest.fixture
def memdir(tmp_path):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "research_log.md").write_text("# Research Log\n")
    build_tools_server(d)
    return d

class TestAppendLogContainment:
    def test_schema_has_only_entry_no_path(self):
        name, desc, schema = append_log._tool_meta
        assert set(schema.keys()) == {"entry"}, "append_log must expose ONLY 'entry'"
    def test_permission_name_is_namespaced(self):
        assert APPEND_LOG_TOOL == "mcp__forge__append_log"
    @pytest.mark.asyncio
    async def test_append_writes_entry(self, memdir):
        r = await append_log({"entry": "did recon; found 2 figures"})
        body = (memdir / "research_log.md").read_text()
        assert "did recon" in body
        assert not r.get("is_error")
    @pytest.mark.asyncio
    async def test_append_never_truncates(self, memdir):
        await append_log({"entry": "first"})
        await append_log({"entry": "second"})
        body = (memdir / "research_log.md").read_text()
        assert "# Research Log" in body
        assert "first" in body and "second" in body
    @pytest.mark.asyncio
    async def test_empty_entry_refused(self, memdir):
        r = await append_log({"entry": "   "})
        assert r.get("is_error") is True
    @pytest.mark.asyncio
    async def test_adds_timestamp_header(self, memdir):
        await append_log({"entry": "x"})
        body = (memdir / "research_log.md").read_text()
        assert "## " in body and "UTC" in body
