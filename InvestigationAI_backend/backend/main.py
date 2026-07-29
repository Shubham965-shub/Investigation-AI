"""Entry point. Run using: python -m backend.main"""
import logging

import uvicorn

from backend.app import create_app
from backend.config.settings import settings

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)

application = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:application",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=True,
    )
