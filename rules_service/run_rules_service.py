"""Start the rules service on 127.0.0.1:8791 (port 8788 is Cairn's on the server)."""
import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("rules_service.app:app", host="127.0.0.1",
                port=int(os.environ.get("MTG_RULES_PORT", "8791")), log_level="info")
