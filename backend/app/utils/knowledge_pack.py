"""
Knowledge pack loader utility.

Provides a centralized, fault-tolerant loader for knowledge_pack.json.
The knowledge pack is OPTIONAL - if missing or invalid, an empty dict is used.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)


def load_knowledge_pack(path: Path) -> Dict[str, Any]:
    """
    Load knowledge pack from JSON file with graceful fallback.

    Args:
        path: Path to the knowledge_pack.json file

    Returns:
        Dict containing knowledge pack data, or empty dict if:
        - File does not exist
        - File cannot be read
        - JSON parsing fails

    The app will NEVER crash due to a missing or invalid knowledge pack.
    """
    if not path.exists():
        logger.warning(
            "knowledge_pack.json not found at %s, using empty fallback. "
            "This is normal for Docker/Render deployments.",
            path,
        )
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug("Loaded knowledge_pack.json from %s", path)
            return data
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse knowledge_pack.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return {}
    except OSError as e:
        logger.warning(
            "Failed to read knowledge_pack.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return {}
    except Exception as e:
        logger.warning(
            "Unexpected error loading knowledge_pack.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return {}


# Default path for knowledge pack (relative to app/ directory)
DEFAULT_KNOWLEDGE_PACK_PATH = Path(__file__).parent.parent / "knowledge_pack.json"

# Pre-load the knowledge pack at module level for convenience
KNOWLEDGE_PACK = load_knowledge_pack(DEFAULT_KNOWLEDGE_PACK_PATH)
