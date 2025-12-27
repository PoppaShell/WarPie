"""Comprehensive tests for WarPie Flask web application routes.

Tests all HTTP endpoints in the web control panel including:
- Main routes (dashboard, status, mode switching, system controls)
- Filter routes (listing, adding, removing exclusions)
- Target list routes (CRUD operations for OUI targeting)
- Log routes (viewing various log sources)
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from web.app import create_app


@pytest.fixture
def app():
    """Create a test Flask application instance."""
    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a test client for making requests."""
    return app.test_client()


# =============================================================================
# Main Routes Tests
# =============================================================================


class TestMainRoutes:
    """Tests for main dashboard and control routes."""

    def test_index_returns_html(self, client):
        """Index route should return HTML dashboard."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"<!DOCTYPE html>" in response.data or b"<html" in response.data

    @patch("web.routes.main.get_kismet_status")
    @patch("web.routes.main.get_uptime")
    def test_api_status_returns_json(self, mock_uptime, mock_status, client):
        """Status API should return JSON with running state and mode."""
        mock_status.return_value = (True, "Wardrive")
        mock_uptime.return_value = "2h 15m"

        response = client.get("/api/status")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["running"] is True
        assert data["mode"] == "Wardrive"
        assert data["uptime"] == "2h 15m"

    @patch("web.routes.main.get_kismet_status")
    @patch("web.routes.main.get_uptime")
    def test_api_status_html_for_htmx(self, mock_uptime, mock_status, client):
        """Status HTML endpoint should return HTML fragment."""
        mock_status.return_value = (False, "Stopped")
        mock_uptime.return_value = "1h 30m"

        response = client.get("/api/status/html")
        assert response.status_code == 200
        # Should return HTML, not JSON
        assert b"{" not in response.data[:10]

    def test_api_mode_requires_mode_param(self, client):
        """Mode switch should fail without mode parameter."""
        response = client.post("/api/mode", json={})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False
        assert "required" in data["error"].lower()

    def test_api_mode_rejects_invalid_mode(self, client):
        """Mode switch should reject invalid mode names."""
        response = client.post("/api/mode", json={"mode": "invalid_mode"})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False
        assert "invalid" in data["error"].lower()

    @patch("web.routes.main.switch_mode")
    @patch("web.routes.main.get_kismet_status")
    @patch("web.routes.main.get_uptime")
    def test_api_mode_switch_success(
        self, mock_uptime, mock_status, mock_switch, client
    ):
        """Successful mode switch should return updated status HTML."""
        mock_switch.return_value = True
        mock_status.return_value = (True, "Wardrive")
        mock_uptime.return_value = "0h 1m"

        response = client.post("/api/mode", json={"mode": "wardrive"})
        assert response.status_code == 200
        # Returns HTML for HTMX, not JSON

    @patch("web.routes.main.switch_mode")
    def test_api_mode_switch_failure(self, mock_switch, client):
        """Failed mode switch should return error."""
        mock_switch.return_value = False

        response = client.post("/api/mode", json={"mode": "normal"})
        assert response.status_code == 500

        data = json.loads(response.data)
        assert data["success"] is False

    @patch("web.routes.main.get_kismet_status")
    def test_api_mode_buttons(self, mock_status, client):
        """Mode buttons endpoint should return HTML."""
        mock_status.return_value = (True, "Normal")

        response = client.get("/api/mode-buttons")
        assert response.status_code == 200

    @patch("web.routes.main.reboot_system")
    def test_api_reboot_success(self, mock_reboot, client):
        """Successful reboot should return status message."""
        mock_reboot.return_value = True

        response = client.post("/api/reboot")
        assert response.status_code == 200
        assert b"Rebooting" in response.data

    @patch("web.routes.main.reboot_system")
    def test_api_reboot_failure(self, mock_reboot, client):
        """Failed reboot should return error."""
        mock_reboot.return_value = False

        response = client.post("/api/reboot")
        assert response.status_code == 500

    @patch("web.routes.main.shutdown_system")
    def test_api_shutdown_success(self, mock_shutdown, client):
        """Successful shutdown should return status message."""
        mock_shutdown.return_value = True

        response = client.post("/api/shutdown")
        assert response.status_code == 200
        assert b"Shutting down" in response.data

    @patch("web.routes.main.shutdown_system")
    def test_api_shutdown_failure(self, mock_shutdown, client):
        """Failed shutdown should return error."""
        mock_shutdown.return_value = False

        response = client.post("/api/shutdown")
        assert response.status_code == 500


# =============================================================================
# Filter Routes Tests
# =============================================================================


class TestFilterRoutes:
    """Tests for network filter/exclusion routes."""

    @patch("web.routes.filters.call_filter_script")
    def test_api_list_filters(self, mock_script, client):
        """List filters should return JSON with exclusions."""
        mock_script.return_value = {
            "success": True,
            "static_exclusions": [{"ssid": "HomeNetwork", "bssids": []}],
            "dynamic_exclusions": [],
        }

        response = client.get("/api/filters")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "static_exclusions" in data or "success" in data

    @patch("web.routes.filters.call_filter_script")
    def test_api_list_static_filters(self, mock_script, client):
        """List static filters should return WiFi static exclusions."""
        mock_script.return_value = {
            "static_exclusions": [
                {"ssid": "MyNetwork", "bssids": ["AA:BB:CC:DD:EE:FF"]}
            ],
        }

        response = client.get("/api/filters/static")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "static_exclusions" in data

    @patch("web.routes.filters.call_filter_script")
    def test_api_list_static_filters_with_phy(self, mock_script, client):
        """Static filters should support PHY type parameter."""
        mock_script.return_value = {
            "btle_static_exclusions": [{"ssid": "BTDevice", "bssids": []}],
        }

        response = client.get("/api/filters/static?phy=btle")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["phy"] == "btle"

    @patch("web.routes.filters.call_filter_script")
    def test_api_list_static_filters_with_limit(self, mock_script, client):
        """Static filters should support limit parameter."""
        mock_script.return_value = {
            "static_exclusions": [
                {"ssid": "Net1"},
                {"ssid": "Net2"},
                {"ssid": "Net3"},
            ],
        }

        response = client.get("/api/filters/static?limit=2")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert len(data["static_exclusions"]) == 2

    @patch("web.routes.filters.call_filter_script")
    def test_api_list_dynamic_filters(self, mock_script, client):
        """List dynamic filters should return WiFi dynamic exclusions."""
        mock_script.return_value = {
            "dynamic_exclusions": [{"ssid": "iPhone*", "match_type": "pattern"}],
        }

        response = client.get("/api/filters/dynamic")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "dynamic_exclusions" in data

    @patch("web.routes.filters.call_filter_script")
    def test_api_add_static_filter(self, mock_script, client):
        """Adding static filter should call script with correct args."""
        mock_script.return_value = {"success": True, "message": "Added"}

        response = client.post(
            "/api/filters/static",
            json={
                "ssid": "NewNetwork",
                "match_type": "exact",
                "phy": "wifi",
            },
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

    def test_api_add_static_filter_requires_ssid(self, client):
        """Adding static filter should require SSID."""
        response = client.post("/api/filters/static", json={})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False
        assert "required" in data["error"].lower()

    def test_api_add_static_filter_validates_phy(self, client):
        """Adding static filter should validate PHY type."""
        response = client.post(
            "/api/filters/static",
            json={"ssid": "Test", "phy": "invalid"},
        )
        assert response.status_code == 400

        data = json.loads(response.data)
        assert "Invalid PHY" in data["error"]

    @patch("web.routes.filters.call_filter_script")
    def test_api_add_dynamic_filter(self, mock_script, client):
        """Adding dynamic filter should call script correctly."""
        mock_script.return_value = {"success": True}

        response = client.post(
            "/api/filters/dynamic",
            json={
                "ssid": "iPhone*",
                "match_type": "pattern",
                "phy": "wifi",
            },
        )
        assert response.status_code == 200

    def test_api_add_dynamic_filter_requires_ssid(self, client):
        """Adding dynamic filter should require SSID."""
        response = client.post("/api/filters/dynamic", json={})
        assert response.status_code == 400

    @patch("web.routes.filters.call_filter_script")
    def test_api_remove_static_filter(self, mock_script, client):
        """Removing static filter should work."""
        mock_script.return_value = {"success": True}

        response = client.delete("/api/filters/static/TestNetwork")
        assert response.status_code == 200

    @patch("web.routes.filters.call_filter_script")
    def test_api_remove_dynamic_filter(self, mock_script, client):
        """Removing dynamic filter should work."""
        mock_script.return_value = {"success": True}

        response = client.delete("/api/filters/dynamic/iPhone*")
        assert response.status_code == 200

    def test_api_remove_filter_invalid_type(self, client):
        """Removing filter with invalid type should fail."""
        response = client.delete("/api/filters/invalid/Test")
        assert response.status_code == 400

    @patch("web.routes.filters.call_filter_script")
    def test_api_cleanup_filters(self, mock_script, client):
        """Cleanup endpoint should trigger retroactive cleanup."""
        mock_script.return_value = {"success": True, "removed": 5}

        response = client.post("/api/filters/cleanup")
        assert response.status_code == 200

    @patch("web.routes.filters.call_filter_script")
    def test_api_scan_ssid(self, mock_script, client):
        """SSID scan should return discovered networks."""
        mock_script.return_value = {
            "ssid": "TestNet",
            "live": [{"bssid": "AA:BB:CC:DD:EE:FF", "signal": -65}],
            "historical": [],
        }

        response = client.get("/api/scan-ssid?ssid=TestNet")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "networks" in data

    def test_api_scan_ssid_requires_ssid(self, client):
        """SSID scan should require SSID parameter."""
        response = client.get("/api/scan-ssid")
        assert response.status_code == 400

    @patch("web.routes.filters.call_processor_script")
    def test_api_processor_status(self, mock_script, client):
        """Processor status should check if daemon is running."""
        # Mock subprocess.run for pgrep
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="12345\n")

            response = client.get("/api/filters/processor/status")
            assert response.status_code == 200

            data = json.loads(response.data)
            assert data["running"] is True


# =============================================================================
# Target List Routes Tests
# =============================================================================


class TestTargetRoutes:
    """Tests for target list management routes."""

    @patch("web.routes.targets.load_target_lists")
    def test_api_list_target_lists(self, mock_load, client):
        """List target lists should return all lists."""
        mock_load.return_value = {
            "test-list": {
                "id": "test-list",
                "name": "Test List",
                "description": "A test list",
                "builtin": False,
                "ouis": [],
            }
        }

        response = client.get("/api/targets/lists")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert len(data["lists"]) >= 1

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.save_target_lists")
    def test_api_create_target_list(self, mock_save, mock_load, client):
        """Creating a target list should work."""
        mock_load.return_value = {}
        mock_save.return_value = True

        response = client.post(
            "/api/targets/lists",
            json={"name": "New List", "description": "A new list"},
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "id" in data

    def test_api_create_target_list_requires_name(self, client):
        """Creating a target list should require name."""
        response = client.post("/api/targets/lists", json={})
        assert response.status_code == 400

    @patch("web.routes.targets.load_target_lists")
    def test_api_create_target_list_duplicate_name(self, mock_load, client):
        """Creating a list with duplicate name should fail."""
        mock_load.return_value = {
            "existing": {"id": "existing", "name": "Existing"}
        }

        response = client.post("/api/targets/lists", json={"name": "existing"})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert "already exists" in data["error"]

    @patch("web.routes.targets.load_target_lists")
    def test_api_get_target_list(self, mock_load, client):
        """Get specific target list should return details."""
        mock_load.return_value = {
            "test-list": {
                "id": "test-list",
                "name": "Test List",
                "ouis": [{"oui": "AA:BB:CC:*", "description": "Test OUI"}],
            }
        }

        response = client.get("/api/targets/lists/test-list")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert data["list"]["name"] == "Test List"

    @patch("web.routes.targets.load_target_lists")
    def test_api_get_target_list_not_found(self, mock_load, client):
        """Getting non-existent list should return 404."""
        mock_load.return_value = {}

        response = client.get("/api/targets/lists/nonexistent")
        assert response.status_code == 404

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.save_target_lists")
    def test_api_update_target_list(self, mock_save, mock_load, client):
        """Updating a target list should work."""
        mock_load.return_value = {
            "my-list": {
                "id": "my-list",
                "name": "My List",
                "builtin": False,
            }
        }
        mock_save.return_value = True

        response = client.put(
            "/api/targets/lists/my-list",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200

    @patch("web.routes.targets.load_target_lists")
    def test_api_update_builtin_list_fails(self, mock_load, client):
        """Updating a builtin list metadata should fail."""
        mock_load.return_value = {
            "builtin-list": {
                "id": "builtin-list",
                "name": "Builtin",
                "builtin": True,
            }
        }

        response = client.put(
            "/api/targets/lists/builtin-list",
            json={"name": "New Name"},
        )
        assert response.status_code == 400

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.save_target_lists")
    def test_api_delete_user_list(self, mock_save, mock_load, client):
        """Deleting a user-created list should work."""
        mock_load.return_value = {
            "user-list": {
                "id": "user-list",
                "name": "User List",
                "builtin": False,
            }
        }
        mock_save.return_value = True

        response = client.delete("/api/targets/lists/user-list")
        assert response.status_code == 200

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.hide_builtin_list")
    def test_api_delete_builtin_list_hides(self, mock_hide, mock_load, client):
        """Deleting a builtin list should hide it instead."""
        mock_load.return_value = {}  # List not loaded because it will be hidden
        mock_hide.return_value = True

        # Use the actual builtin list ID
        response = client.delete("/api/targets/lists/targeted-devices-example")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert "hidden" in data.get("message", "").lower()

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.save_target_lists")
    def test_api_add_oui(self, mock_save, mock_load, client):
        """Adding an OUI to a list should work."""
        mock_load.return_value = {
            "my-list": {
                "id": "my-list",
                "name": "My List",
                "ouis": [],
            }
        }
        mock_save.return_value = True

        response = client.post(
            "/api/targets/lists/my-list/ouis",
            json={"oui": "AA:BB:CC:*", "description": "Test OUI"},
        )
        assert response.status_code == 200

    @patch("web.routes.targets.load_target_lists")
    def test_api_add_oui_requires_oui(self, mock_load, client):
        """Adding an OUI should require OUI value."""
        mock_load.return_value = {"test": {"ouis": []}}

        response = client.post("/api/targets/lists/test/ouis", json={})
        assert response.status_code == 400

    @patch("web.routes.targets.load_target_lists")
    def test_api_add_oui_to_nonexistent_list(self, mock_load, client):
        """Adding OUI to non-existent list should fail."""
        mock_load.return_value = {}

        response = client.post(
            "/api/targets/lists/nonexistent/ouis",
            json={"oui": "AA:BB:CC:*"},
        )
        assert response.status_code == 404

    @patch("web.routes.targets.load_target_lists")
    def test_api_add_duplicate_oui(self, mock_load, client):
        """Adding duplicate OUI should fail."""
        mock_load.return_value = {
            "my-list": {
                "ouis": [{"oui": "AA:BB:CC:*"}],
            }
        }

        response = client.post(
            "/api/targets/lists/my-list/ouis",
            json={"oui": "AA:BB:CC:*"},
        )
        assert response.status_code == 400

    @patch("web.routes.targets.load_target_lists")
    def test_api_add_invalid_oui_format(self, mock_load, client):
        """Adding invalid OUI format should fail."""
        mock_load.return_value = {"my-list": {"ouis": []}}

        response = client.post(
            "/api/targets/lists/my-list/ouis",
            json={"oui": "invalid!!oui"},
        )
        assert response.status_code == 400

    @patch("web.routes.targets.load_target_lists")
    @patch("web.routes.targets.save_target_lists")
    def test_api_remove_oui(self, mock_save, mock_load, client):
        """Removing an OUI should work."""
        mock_load.return_value = {
            "my-list": {
                "ouis": [
                    {"oui": "AA:BB:CC:*", "builtin": False},
                ],
            }
        }
        mock_save.return_value = True

        response = client.delete("/api/targets/lists/my-list/ouis/AA:BB:CC:*")
        assert response.status_code == 200

    @patch("web.routes.targets.load_target_lists")
    def test_api_remove_builtin_oui_fails(self, mock_load, client):
        """Removing a builtin OUI should fail."""
        mock_load.return_value = {
            "my-list": {
                "ouis": [{"oui": "AA:BB:CC:*", "builtin": True}],
            }
        }

        response = client.delete("/api/targets/lists/my-list/ouis/AA:BB:CC:*")
        assert response.status_code == 400


# =============================================================================
# Log Routes Tests
# =============================================================================


class TestLogRoutes:
    """Tests for log viewing routes."""

    @patch("web.routes.logs.get_logs")
    def test_api_logs_default_source(self, mock_logs, client):
        """Logs API should use wardrive as default source."""
        mock_logs.return_value = ["Log line 1", "Log line 2"]

        response = client.get("/api/logs")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["source"] == "wardrive"
        assert data["lines"] == 2

    @patch("web.routes.logs.get_logs")
    def test_api_logs_with_source(self, mock_logs, client):
        """Logs API should accept source parameter."""
        mock_logs.return_value = ["GPS log line"]

        response = client.get("/api/logs?source=gps")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["source"] == "gps"

    @patch("web.routes.logs.get_logs")
    def test_api_logs_with_lines_param(self, mock_logs, client):
        """Logs API should accept lines parameter."""
        mock_logs.return_value = ["Line 1"] * 50

        response = client.get("/api/logs?lines=50")
        assert response.status_code == 200

        mock_logs.assert_called_once_with("wardrive", 50)

    @patch("web.routes.logs.get_logs")
    def test_api_logs_html_endpoint(self, mock_logs, client):
        """Logs HTML endpoint should return HTML fragment."""
        mock_logs.return_value = ["Test log line"]

        response = client.get("/api/logs/html")
        assert response.status_code == 200
        # Should be HTML, not JSON
        assert b"logs" not in response.data[:20]

    @patch("web.routes.logs.get_logs")
    def test_api_logs_wigle_source(self, mock_logs, client):
        """Logs API should support wigle source."""
        mock_logs.return_value = ["WiGLE CSV data"]

        response = client.get("/api/logs?source=wigle")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["source"] == "wigle"

    @patch("web.routes.logs.get_logs")
    def test_api_logs_network_source(self, mock_logs, client):
        """Logs API should support network source."""
        mock_logs.return_value = ["Network log entry"]

        response = client.get("/api/logs?source=network")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["source"] == "network"


# =============================================================================
# HTMX Request Tests
# =============================================================================


class TestHTMXRequests:
    """Tests for HTMX-specific request handling."""

    @patch("web.routes.filters.call_filter_script")
    def test_static_filters_htmx_returns_html(self, mock_script, client):
        """Static filters with HX-Request should return HTML partial."""
        mock_script.return_value = {"static_exclusions": []}

        response = client.get(
            "/api/filters/static",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        # HTML partials don't start with JSON
        assert not response.data.startswith(b"{")

    @patch("web.routes.filters.call_filter_script")
    def test_dynamic_filters_htmx_returns_html(self, mock_script, client):
        """Dynamic filters with HX-Request should return HTML partial."""
        mock_script.return_value = {"dynamic_exclusions": []}

        response = client.get(
            "/api/filters/dynamic",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert not response.data.startswith(b"{")

    @patch("web.routes.targets.load_target_lists")
    def test_target_lists_htmx_returns_html(self, mock_load, client):
        """Target lists with HX-Request should return HTML partial."""
        mock_load.return_value = {}

        response = client.get(
            "/api/targets/lists",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert not response.data.startswith(b"{")

    @patch("web.routes.targets.load_target_lists")
    def test_target_list_htmx_returns_html(self, mock_load, client):
        """Single target list with HX-Request should return HTML partial."""
        mock_load.return_value = {
            "test": {"ouis": []}
        }

        response = client.get(
            "/api/targets/lists/test",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert not response.data.startswith(b"{")

    @patch("web.routes.filters.call_filter_script")
    def test_scan_ssid_htmx_returns_html(self, mock_script, client):
        """SSID scan with HX-Request should return HTML partial."""
        mock_script.return_value = {"live": [], "historical": []}

        response = client.get(
            "/api/scan-ssid?ssid=Test",
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert not response.data.startswith(b"{")


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in routes."""

    @patch("web.routes.filters.call_filter_script")
    def test_filter_script_error_handling(self, mock_script, client):
        """Filter script errors should be handled gracefully."""
        mock_script.return_value = {"success": False, "error": "Script failed"}

        response = client.get("/api/filters")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data.get("success") is False or "error" in data

    @patch("web.routes.filters.call_filter_script")
    def test_filter_script_timeout(self, mock_script, client):
        """Filter script timeout should return error."""
        mock_script.return_value = {"success": False, "error": "Script timeout"}

        response = client.get("/api/filters")
        # Should not crash, return error gracefully
        assert response.status_code == 200

    @patch("web.routes.targets.save_target_lists")
    @patch("web.routes.targets.load_target_lists")
    def test_save_failure_handling(self, mock_load, mock_save, client):
        """Save failures should be handled gracefully."""
        mock_load.return_value = {}
        mock_save.return_value = False

        response = client.post(
            "/api/targets/lists",
            json={"name": "Test List"},
        )
        assert response.status_code == 500

        data = json.loads(response.data)
        assert data["success"] is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestAppIntegration:
    """Integration tests for the Flask application."""

    def test_app_creates_successfully(self, app):
        """Flask application should create successfully."""
        assert app is not None
        assert app.config["TESTING"] is True

    def test_blueprints_registered(self, app):
        """All blueprints should be registered."""
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "main" in blueprint_names
        assert "filters" in blueprint_names
        assert "targets" in blueprint_names
        assert "logs" in blueprint_names

    def test_routes_exist(self, app):
        """Key routes should exist in the app."""
        rules = [rule.rule for rule in app.url_map.iter_rules()]

        # Main routes
        assert "/" in rules
        assert "/api/status" in rules
        assert "/api/mode" in rules

        # Filter routes
        assert "/api/filters" in rules

        # Target routes
        assert "/api/targets/lists" in rules

        # Log routes
        assert "/api/logs" in rules
