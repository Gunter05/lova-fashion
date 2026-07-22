from fastapi import FastAPI

from app.modules.auth_catalogues.router import router as auth_catalogues_router
# from app.modules.measurements.router import router as measurements_router
# from app.modules.business_rules.router import router as business_rules_router

app = FastAPI(title="Remote Custom-Fit Styling — AWS re:Deploy 2026")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(auth_catalogues_router, prefix="/api/v1")
# app.include_router(measurements_router, prefix="/api/v1")
# app.include_router(business_rules_router, prefix="/api/v1")
