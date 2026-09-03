"""Shared test fixtures. Stubs the SDK so guard/tool logic tests run offline."""
import sys, types
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def _install_sdk_stub():
    if "claude_agent_sdk" in sys.modules:
        return
    mod = types.ModuleType("claude_agent_sdk")
    tmod = types.ModuleType("claude_agent_sdk.types")
    class PermissionResultAllow:
        def __init__(self, updated_input=None):
            self.kind="allow"; self.updated_input=updated_input
    class PermissionResultDeny:
        def __init__(self, message="", interrupt=False):
            self.kind="deny"; self.message=message; self.interrupt=interrupt
    tmod.PermissionResultAllow=PermissionResultAllow
    tmod.PermissionResultDeny=PermissionResultDeny
    def tool(name, desc, schema):
        def deco(fn):
            fn._tool_meta=(name,desc,schema); return fn
        return deco
    def create_sdk_mcp_server(name, version, tools):
        return {"name":name,"version":version,"tools":[t._tool_meta[0] for t in tools]}
    mod.tool=tool; mod.create_sdk_mcp_server=create_sdk_mcp_server; mod.types=tmod
    sys.modules["claude_agent_sdk"]=mod
    sys.modules["claude_agent_sdk.types"]=tmod

_install_sdk_stub()
