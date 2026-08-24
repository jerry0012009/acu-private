from api import app
from inspection import router
from ledger_startup import lifespan

app.include_router(router)
app.router.lifespan_context = lifespan
