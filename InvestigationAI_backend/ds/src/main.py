"""
Entry point for the application.
Run using: python -m src.main
"""
import sys
import logging
from pathlib import Path
import uvicorn

# Inject project root directly into sys.path to resolve imports
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.agents.app import create_app
from src.config.settings import settings

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
)

application = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "main:application",
        host=settings.SEARCH_AGENT_HOST,
        port=settings.SEARCH_AGENT_PORT,
        reload=True,
    )
