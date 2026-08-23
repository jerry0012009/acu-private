from api import app
from inspection import router

app.include_router(router)
