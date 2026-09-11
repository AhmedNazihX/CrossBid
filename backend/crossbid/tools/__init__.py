"""The tools the agent may call, and the contract every one of them keeps.

A tool module owns three names and nothing else:

    MANIFEST: ToolManifest      what it is, whether it leaves the process, default on/off
    build_tool(ToolContext)     the bound LangChain tool, scoped to one company and bid
    <the tool's own schema>     a Pydantic argument model, so the model cannot invent args

`ToolContext` carries the scope rather than each tool re-deriving it: `company_id` is the
tenant predicate every retrieval statement needs (ADR-0009), and a tool that reaches the
database is built with one, never handed a global. That is what keeps "the agent searched
the wrong tenant's documents" out of the space of possible bugs.

The registry that reads `MANIFEST`, honours `runtime.enabled_tools` and binds the result to
the model is S1.4.1; it lands once the tools it registers exist.
"""

from crossbid.tools.manifest import ToolContext, ToolManifest

__all__ = ["ToolContext", "ToolManifest"]
