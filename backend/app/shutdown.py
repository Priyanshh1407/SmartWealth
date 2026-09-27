from threading import Event


# Uvicorn waits for open streaming responses before it runs the FastAPI
# lifespan shutdown hook. The server signal handler sets this event first so
# SSE generators can finish and let graceful shutdown continue.
shutdown_requested = Event()
