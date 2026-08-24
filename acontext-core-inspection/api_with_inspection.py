from contextlib import asynccontextmanager

from api import app
from inspection import router
from ledger_startup import install


_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def lifespan(app):
    await install()
    async with _original_lifespan(app):
        yield

app.include_router(router)
app.router.lifespan_context = lifespan
