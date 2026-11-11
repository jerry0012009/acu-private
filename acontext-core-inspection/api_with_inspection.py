from contextlib import asynccontextmanager

from api import app
from inspection import router
from ledger_startup import install
from usage_ledger import ledger
from deployment import install as install_deployment


_original_lifespan = app.router.lifespan_context
_deployment = install_deployment(app, ledger)


@asynccontextmanager
async def lifespan(app):
    await install()
    async with _original_lifespan(app):
        yield
        await _deployment.stop()
        await ledger.close()

app.include_router(router)
app.router.lifespan_context = lifespan
