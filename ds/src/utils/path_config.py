"""Path configuration to ensure project root is accessible."""
import sys
from pathlib import Path

# Add project root to Python path
# This allows imports like 'from config.settings import settings'
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

