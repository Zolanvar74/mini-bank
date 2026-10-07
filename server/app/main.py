from fastapi import FastAPI

app = FastAPI(
    title="Mini Banking Transaction Server",
    version="0.1.0",
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "banking-server",
    }