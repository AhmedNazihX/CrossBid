"""The agent's long-term memory: the LangGraph Store namespaces, spelled once each.

`db.py` owns the Store *client* (`Database.store`, an `AsyncPostgresStore` on the one pool).
This package owns the *addresses* — `profile/{company_id}` today, `corrections/{company_id}`
when S3.4.4 lands — because more than one writer needs them and none of them should have to
import another to find out where the agent looks.

Nothing here opens a connection or holds state; a namespace is a tuple of strings.
"""
