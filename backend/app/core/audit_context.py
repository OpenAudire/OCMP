"""Give each request its own audit actor context.

The actor is set when the request authenticates; this keeps it from leaking
into anything that runs afterwards in the same context (e.g. tests calling the
app in-process).
"""

from starlette.types import ASGIApp, Receive, Scope, Send

from app.services.audit import actor_scope


class AuditContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        with actor_scope(None):
            await self.app(scope, receive, send)
