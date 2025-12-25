"""WarPie Web Control Panel - Target Lists Routes.

Manages Target Lists for Targeted Devices capture mode.
Each Target List contains OUI prefixes that are captured in targeted mode.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, render_template, request

from web.config import TARGET_LISTS_CONFIG

targets_bp = Blueprint("targets", __name__)

# Example target list to demonstrate the feature
# Users can create their own lists via the web UI or config file
BUILTIN_LISTS = {
    "targeted-devices-example": {
        "id": "targeted-devices-example",
        "name": "Targeted Devices Example",
        "description": "Example list - add OUI prefixes to target specific device manufacturers",
        "builtin": True,
        "ouis": [
            {"oui": "00:00:00:*", "description": "Example OUI prefix (replace with actual)", "builtin": True},
        ],
    },
}


def load_target_lists() -> dict[str, Any]:
    """Load target lists from config file.

    Returns:
        Dictionary of target lists by ID.
    """
    lists = dict(BUILTIN_LISTS)
    hidden_lists: set[str] = set()

    config_path = Path(TARGET_LISTS_CONFIG)
    if config_path.exists():
        try:
            user_data = json.loads(config_path.read_text())

            # Get hidden builtin lists
            hidden_lists = set(user_data.get("hidden_lists", []))

            # Merge user-created lists
            for list_id, list_data in user_data.get("lists", {}).items():
                if list_id in lists:
                    # Merge user OUIs into built-in list
                    for oui in list_data.get("ouis", []):
                        if not oui.get("builtin"):
                            lists[list_id]["ouis"].append(oui)
                else:
                    # Add user-created list
                    lists[list_id] = list_data
        except (json.JSONDecodeError, KeyError):
            pass

    # Remove hidden builtin lists from display
    for hidden_id in hidden_lists:
        if hidden_id in lists:
            del lists[hidden_id]

    return lists


def save_target_lists(lists: dict[str, Any], hidden_lists: list[str] | None = None) -> bool:
    """Save target lists to config file.

    Args:
        lists: Dictionary of target lists.
        hidden_lists: List of builtin list IDs to hide.

    Returns:
        True if save was successful.
    """
    config_path = Path(TARGET_LISTS_CONFIG)

    # Load existing hidden_lists if not provided
    existing_hidden: list[str] = []
    if hidden_lists is None and config_path.exists():
        try:
            existing_data = json.loads(config_path.read_text())
            existing_hidden = existing_data.get("hidden_lists", [])
        except (json.JSONDecodeError, KeyError):
            pass
        hidden_lists = existing_hidden

    # Only save user-created lists and user-added OUIs
    user_data: dict[str, Any] = {"lists": {}}

    # Add hidden_lists if any
    if hidden_lists:
        user_data["hidden_lists"] = hidden_lists

    for list_id, list_data in lists.items():
        if list_data.get("builtin"):
            # For built-in lists, only save user-added OUIs
            user_ouis = [oui for oui in list_data.get("ouis", []) if not oui.get("builtin")]
            if user_ouis:
                user_data["lists"][list_id] = {"ouis": user_ouis}
        else:
            # Save entire user-created list
            user_data["lists"][list_id] = list_data

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(user_data, indent=2))
        return True
    except Exception:
        return False


def get_hidden_lists() -> list[str]:
    """Get list of hidden builtin list IDs.

    Returns:
        List of hidden list IDs.
    """
    config_path = Path(TARGET_LISTS_CONFIG)
    if config_path.exists():
        try:
            user_data = json.loads(config_path.read_text())
            return user_data.get("hidden_lists", [])
        except (json.JSONDecodeError, KeyError):
            pass
    return []


def hide_builtin_list(list_id: str) -> bool:
    """Hide a builtin list by adding it to hidden_lists.

    Args:
        list_id: The builtin list ID to hide.

    Returns:
        True if successful.
    """
    hidden = get_hidden_lists()
    if list_id not in hidden:
        hidden.append(list_id)

    # Load lists and save with updated hidden list
    lists = load_target_lists()
    return save_target_lists(lists, hidden)


def get_target_lists_data() -> list[dict]:
    """Get target lists formatted for display.

    Returns:
        List of target list dictionaries with counts.
    """
    lists = load_target_lists()
    result = []
    for list_id, list_data in lists.items():
        ouis = list_data.get("ouis", [])
        builtin_count = sum(1 for o in ouis if o.get("builtin"))
        user_count = len(ouis) - builtin_count

        result.append({
            "id": list_id,
            "name": list_data.get("name", list_id),
            "description": list_data.get("description", ""),
            "builtin": list_data.get("builtin", False),
            "oui_count": len(ouis),
            "builtin_oui_count": builtin_count,
            "user_oui_count": user_count,
        })
    return result


@targets_bp.route("/targets/lists")
def api_list_target_lists():
    """List all target lists.

    Returns HTML for HTMX or JSON based on HX-Request header.
    Uses different templates based on context (target picker vs filter flyout).
    """
    result = get_target_lists_data()

    # Return HTML for HTMX requests (HTMX sends HX-Request: true header)
    if request.headers.get("HX-Request"):
        # Check which template to use based on query param
        template_type = request.args.get("view", "checkboxes")
        if template_type == "manage":
            return render_template("partials/_target_lists.html", lists=result)
        return render_template("partials/_target_list_checkboxes.html", lists=result)

    return jsonify({"success": True, "lists": result})


@targets_bp.route("/targets/lists", methods=["POST"])
def api_create_target_list():
    """Create a new target list."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Name required"}), 400

    # Generate ID from name
    list_id = name.lower().replace(" ", "-")
    list_id = "".join(c for c in list_id if c.isalnum() or c == "-")

    lists = load_target_lists()

    if list_id in lists:
        return jsonify({"success": False, "error": "List with this name already exists"}), 400

    lists[list_id] = {
        "id": list_id,
        "name": name,
        "description": description,
        "builtin": False,
        "ouis": [],
        "created_at": datetime.now().isoformat(),
    }

    if save_target_lists(lists):
        return jsonify({"success": True, "id": list_id, "message": f"Created list: {name}"})
    else:
        return jsonify({"success": False, "error": "Failed to save list"}), 500


@targets_bp.route("/targets/lists/<list_id>")
def api_get_target_list(list_id: str):
    """Get details of a specific target list.

    Returns HTML (OUI list) for HTMX requests, JSON otherwise.
    """
    lists = load_target_lists()

    if list_id not in lists:
        if request.headers.get("HX-Request"):
            return '<div class="error-message">List not found</div>', 404
        return jsonify({"success": False, "error": "List not found"}), 404

    target_list = lists[list_id]

    # Return HTML for HTMX requests
    if request.headers.get("HX-Request"):
        return render_template("partials/_oui_list.html", ouis=target_list.get("ouis", []))

    return jsonify({"success": True, "list": target_list})


@targets_bp.route("/targets/lists/<list_id>", methods=["PUT"])
def api_update_target_list(list_id: str):
    """Update a target list (name/description only)."""
    lists = load_target_lists()

    if list_id not in lists:
        return jsonify({"success": False, "error": "List not found"}), 404

    if lists[list_id].get("builtin"):
        return jsonify({"success": False, "error": "Cannot modify built-in list metadata"}), 400

    data = request.get_json() or {}
    if "name" in data:
        lists[list_id]["name"] = data["name"].strip()
    if "description" in data:
        lists[list_id]["description"] = data["description"].strip()

    lists[list_id]["updated_at"] = datetime.now().isoformat()

    if save_target_lists(lists):
        return jsonify({"success": True, "message": "List updated"})
    else:
        return jsonify({"success": False, "error": "Failed to save list"}), 500


@targets_bp.route("/targets/lists/<list_id>", methods=["DELETE"])
def api_delete_target_list(list_id: str):
    """Delete a target list.

    For builtin lists, this hides them from the UI.
    For user-created lists, this removes them entirely.
    """
    # Check in BUILTIN_LISTS first to see if it's a builtin that might be hidden
    is_builtin = list_id in BUILTIN_LISTS

    lists = load_target_lists()

    if list_id not in lists and not is_builtin:
        return jsonify({"success": False, "error": "List not found"}), 404

    if is_builtin:
        # Hide builtin list instead of deleting
        if hide_builtin_list(list_id):
            return jsonify({"success": True, "message": "List hidden"})
        else:
            return jsonify({"success": False, "error": "Failed to hide list"}), 500

    del lists[list_id]

    if save_target_lists(lists):
        return jsonify({"success": True, "message": "List deleted"})
    else:
        return jsonify({"success": False, "error": "Failed to save changes"}), 500


@targets_bp.route("/targets/lists/<list_id>/ouis", methods=["POST"])
def api_add_oui(list_id: str):
    """Add an OUI to a target list."""
    lists = load_target_lists()

    if list_id not in lists:
        return jsonify({"success": False, "error": "List not found"}), 404

    data = request.get_json() or {}
    oui = data.get("oui", "").strip().upper()
    description = data.get("description", "").strip()

    if not oui:
        return jsonify({"success": False, "error": "OUI required"}), 400

    # Validate OUI format (XX:XX:XX:* or similar)
    if not oui.replace(":", "").replace("*", "").replace("?", "").isalnum():
        return jsonify({"success": False, "error": "Invalid OUI format"}), 400

    # Check if OUI already exists
    for existing in lists[list_id].get("ouis", []):
        if existing.get("oui") == oui:
            return jsonify({"success": False, "error": "OUI already in list"}), 400

    lists[list_id]["ouis"].append({
        "oui": oui,
        "description": description or f"Added {datetime.now().strftime('%Y-%m-%d')}",
        "builtin": False,
        "added_at": datetime.now().isoformat(),
    })

    if save_target_lists(lists):
        return jsonify({"success": True, "message": f"Added {oui} to {lists[list_id]['name']}"})
    else:
        return jsonify({"success": False, "error": "Failed to save changes"}), 500


@targets_bp.route("/targets/lists/<list_id>/ouis/<path:oui>", methods=["DELETE"])
def api_remove_oui(list_id: str, oui: str):
    """Remove an OUI from a target list."""
    lists = load_target_lists()

    if list_id not in lists:
        return jsonify({"success": False, "error": "List not found"}), 404

    # Find and check the OUI
    oui_upper = oui.upper()
    oui_found = None
    for existing in lists[list_id].get("ouis", []):
        if existing.get("oui") == oui_upper:
            oui_found = existing
            break

    if not oui_found:
        return jsonify({"success": False, "error": "OUI not found in list"}), 404

    if oui_found.get("builtin"):
        return jsonify({"success": False, "error": "Cannot remove built-in OUI"}), 400

    lists[list_id]["ouis"] = [o for o in lists[list_id]["ouis"] if o.get("oui") != oui_upper]

    if save_target_lists(lists):
        return jsonify({"success": True, "message": f"Removed {oui_upper}"})
    else:
        return jsonify({"success": False, "error": "Failed to save changes"}), 500
