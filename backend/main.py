from fastapi import FastAPI
from app.modules.measurements.router import router as measurements_router
from app.modules.business_rules.router import router as ease_router
from app.modules.auth_catalogues.router import router as auth_catalogues_router

app = FastAPI(title="Remote Custom-Fit Styling — AWS re:Deploy 2026")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(measurements_router, prefix="/api/v1/measurements", tags=["measurements"])
app.include_router(ease_router, prefix="/api/v1/ease", tags=["ease-allowance"])

# Module 3 (Fabric Catalog) + Module 4 (Pattern Catalog) router
# Module 4 endpoints are mounted at /api/v1/models (within the router itself)
# Module 3 fabric/category endpoints are also served through this router
app.include_router(auth_catalogues_router, prefix="/api/v1", tags=["models"])
