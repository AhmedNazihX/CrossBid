"""The tools the agent may call, and the contract every one of them keeps.

A tool module owns three names and nothing else:

    MANIFEST: ToolManifest      what it is, whether it leaves the process, default on/off
    build_tool(ToolContext)     the bound LangChain tool, scoped to one company and bid
    <the tool's own schema>     a Pydantic argument model, so the model cannot invent args

`ToolContext` carries the scope rather than each tool re-deriving it: `company_id` is the
tenant predicate every retrieval statement needs (ADR-0009), and a tool that reaches the
database is built with one, never handed a global. That is what keeps "the agent searched
the wrong tenant's documents" out of the space of possible bugs.

`registry.py` (S1.4.1) is the only module that imports all of them: it discovers this
package, builds exactly the tools `runtime.enabled_tools` names, and hands the list to the
consumer that binds it to a model (`check_reqs`, F3.3). A tool is registered by existing --
there is no list to add it to -- so the three names above are the whole contract.
"""

from crossbid.tools.manifest import ToolContext, ToolManifest

__all__ = ["ToolContext", "ToolManifest"]
