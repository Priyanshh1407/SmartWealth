from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import your new route files
from backend.app.api.routes_run import router as run_router
from backend.app.api.routes_clarify import router as clarify_router
from backend.app.api.routes_state import router as state_router

app = FastAPI(title="Smart Wealth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach the routers to the app with the /api prefix
app.include_router(run_router, prefix="/api")
app.include_router(clarify_router, prefix="/api")
app.include_router(state_router, prefix="/api")

@app.get("/")
def read_root():
    return {"message": "Smart Wealth API is running!"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=8000, reload=True)