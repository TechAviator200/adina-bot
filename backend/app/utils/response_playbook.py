"""
Response playbook loader utility.

Provides a centralized, fault-tolerant loader for response_playbook.json.
The playbook is OPTIONAL - if missing or invalid, an empty dict is used.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


def load_response_playbook(path: Path) -> Dict[str, Any]:
    """
    Load response playbook from JSON file with graceful fallback.

    Args:
        path: Path to the response_playbook.json file

    Returns:
        Dict containing playbook data, or empty dict with default structure if:
        - File does not exist
        - File cannot be read
        - JSON parsing fails

    The app will NEVER crash due to a missing or invalid playbook.
    """
    if not path.exists():
        logger.warning(
            "response_playbook.json not found at %s, using empty fallback. "
            "This is normal for Docker/Render deployments.",
            path,
        )
        return _empty_playbook()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.debug("Loaded response_playbook.json from %s", path)
            return data
    except json.JSONDecodeError as e:
        logger.warning(
            "Failed to parse response_playbook.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return _empty_playbook()
    except OSError as e:
        logger.warning(
            "Failed to read response_playbook.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return _empty_playbook()
    except Exception as e:
        logger.warning(
            "Unexpected error loading response_playbook.json at %s: %s. Using empty fallback.",
            path,
            e,
        )
        return _empty_playbook()


def _empty_playbook() -> Dict[str, Any]:
    """Return empty playbook structure with expected keys."""
    return {
        "intent_classification": {
            "positive": {"keywords": [], "patterns": []},
            "neutral": {"keywords": [], "patterns": []},
            "objection": {"keywords": [], "patterns": []},
            "deferral": {"keywords": [], "patterns": []},
            "negative": {"keywords": [], "patterns": []},
        },
        "followup_templates": {
            "positive": {"template": "", "tone": ""},
            "neutral": {"template": "", "tone": ""},
            "objection": {"templates_by_objection": {"default": ""}, "tone": ""},
            "deferral": {"template": "", "tone": ""},
            "negative": {"template": "", "tone": ""},
        },
    }


# Default path for response playbook (relative to app/ directory)
DEFAULT_RESPONSE_PLAYBOOK_PATH = Path(__file__).parent.parent / "response_playbook.json"

# Pre-load the response playbook at module level for convenience
RESPONSE_PLAYBOOK = load_response_playbook(DEFAULT_RESPONSE_PLAYBOOK_PATH)
