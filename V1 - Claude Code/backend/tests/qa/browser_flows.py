"""Browser QA flow definitions.

These flows are executed by the runner script using cursor-ide-browser MCP.
Each flow returns a dict with {name, steps[], expected_checks[]}.
The runner calls MCP tools for each step and records pass/fail.

This file defines the flows — the runner (run_v1_qa.py) executes them.
"""
from __future__ import annotations
from typing import Any, Dict, List


def get_browser_flows() -> List[Dict[str, Any]]:
    return [
        {
            "name": "Chat-to-route",
            "steps": [
                {"action": "navigate", "url": "http://localhost:3000/planner"},
                {"action": "screenshot", "filename": "qa_01_planner_loaded.png"},
                {"action": "snapshot", "note": "Find chat input"},
                {"action": "type_in_chat", "text": "Plan me a 5 mile gravel loop near Boulder"},
                {"action": "wait", "seconds": 5},
                {"action": "screenshot", "filename": "qa_02_chat_sent.png"},
                {"action": "wait_for_response", "max_seconds": 120},
                {"action": "screenshot", "filename": "qa_03_route_result.png"},
                {"action": "snapshot", "note": "Check for route on map and response text"},
            ],
            "checks": [
                "planner_page_loaded",
                "chat_input_found",
                "response_appeared",
                "no_error_toast",
            ],
        },
        {
            "name": "Sport type switching",
            "steps": [
                {"action": "navigate", "url": "http://localhost:3000/planner"},
                {"action": "snapshot", "note": "Find sport selector"},
                {"action": "click_sport_type", "sport": "road"},
                {"action": "screenshot", "filename": "qa_04_road_mode.png"},
                {"action": "snapshot", "note": "Verify road mode active"},
            ],
            "checks": [
                "sport_selector_found",
                "sport_changed_to_road",
            ],
        },
        {
            "name": "Error resilience",
            "steps": [
                {"action": "navigate", "url": "http://localhost:3000/planner"},
                {"action": "type_in_chat", "text": "asdkjfhaskdjfh gibberish nonsense"},
                {"action": "wait_for_response", "max_seconds": 120},
                {"action": "screenshot", "filename": "qa_05_gibberish.png"},
                {"action": "snapshot", "note": "Verify no crash, message present"},
            ],
            "checks": [
                "app_did_not_crash",
                "response_message_present",
            ],
        },
        {
            "name": "Page load performance",
            "steps": [
                {"action": "navigate", "url": "http://localhost:3000/planner"},
                {"action": "wait", "seconds": 3},
                {"action": "snapshot", "note": "Check page rendered — map, sidebar, chat"},
                {"action": "screenshot", "filename": "qa_06_full_load.png"},
            ],
            "checks": [
                "map_container_present",
                "sidebar_present",
                "no_loading_spinner_stuck",
            ],
        },
        {
            "name": "Inspector panel after route",
            "steps": [
                {"action": "navigate", "url": "http://localhost:3000/planner"},
                {"action": "type_in_chat", "text": "Quick 3 mile road loop"},
                {"action": "wait_for_response", "max_seconds": 120},
                {"action": "snapshot", "note": "Check inspector panel visible with route data"},
                {"action": "screenshot", "filename": "qa_07_inspector.png"},
            ],
            "checks": [
                "inspector_panel_visible",
                "shows_distance",
                "shows_elevation",
            ],
        },
    ]
