from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import FRONTEND_URL
from app.api.routes.assistant import router as assistant_router
from app.api.routes.availability import router as availability_router

app = FastAPI(title="Hotel Guest Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assistant_router, prefix="/api")
app.include_router(availability_router, prefix="/api")


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred."},
    )


@app.get("/")
def root() -> dict:
    return {"message": "Hotel Guest Assistant API"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
