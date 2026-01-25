## Backend Testing

### Run all tests
```bash
pytest
```

### Run routing-specific tests
```bash
pytest tests/test_routing.py
pytest tests/test_routing_transitions.py
pytest tests/test_point_to_point.py
```

### Notes
- External routing calls are mocked in `tests/conftest.py`.
- Transition logic is unit-tested via `_apply_connector_segments` helpers.
