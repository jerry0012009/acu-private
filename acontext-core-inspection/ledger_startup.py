from contextlib import asynccontextmanager

from usage_ledger import install


@asynccontextmanager
async def lifespan(app):
    await install()
    yield
