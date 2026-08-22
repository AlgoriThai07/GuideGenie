"""Tests for the Places API (New) v1 migration in app.services.places_service."""

from unittest.mock import MagicMock

from app.services.places_service import PlacesService, normalize_v1_place


# --- normalize_v1_place -------------------------------------------------------


def _v1_place(**overrides):
    base = {
        "id": "abc123",
        "displayName": {"text": "Ichiran Ramen Shinjuku", "languageCode": "en"},
        "formattedAddress": "1 Chome, Shinjuku",
        "location": {"latitude": 35.6, "longitude": 139.7},
        "rating": 4.6,
        "priceLevel": "PRICE_LEVEL_MODERATE",
        "types": ["restaurant", "food"],
        "regularOpeningHours": {"periods": [{"open": {"day": 1, "hour": 11}, "close": {"day": 1, "hour": 22}}]},
    }
    base.update(overrides)
    return base


def test_normalize_v1_place_full_mapping():
    result = normalize_v1_place(_v1_place())
    assert result == {
        "place_id": "abc123",
        "name": "Ichiran Ramen Shinjuku",
        "formatted_address": "1 Chome, Shinjuku",
        "geometry": {"location": {"lat": 35.6, "lng": 139.7}},
        "rating": 4.6,
        "price_level": 2,
        "types": ["restaurant", "food"],
        "opening_hours": {"periods": [{"open": {"day": 1, "hour": 11}, "close": {"day": 1, "hour": 22}}]},
    }


def test_normalize_v1_place_price_level_unspecified_maps_to_none():
    result = normalize_v1_place(_v1_place(priceLevel="PRICE_LEVEL_UNSPECIFIED"))
    assert result["price_level"] is None


def test_normalize_v1_place_missing_price_level_maps_to_none():
    result = normalize_v1_place(_v1_place(priceLevel=None))
    assert result["price_level"] is None


def test_normalize_v1_place_missing_id_returns_none():
    assert normalize_v1_place(_v1_place(id=None)) is None


def test_normalize_v1_place_missing_display_name_returns_none():
    assert normalize_v1_place(_v1_place(displayName=None)) is None


def test_normalize_v1_place_missing_regular_opening_hours_is_none():
    result = normalize_v1_place(_v1_place(regularOpeningHours=None))
    assert result["opening_hours"] is None


# --- text_search ---------------------------------------------------------------


def _mock_response(status_code: int, json_body):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


def test_text_search_returns_normalized_first_result(monkeypatch):
    monkeypatch.setattr(
        "app.services.places_service.requests.post",
        lambda *a, **k: _mock_response(200, {"places": [_v1_place(), _v1_place(id="other")]}),
    )
    result = PlacesService.text_search("Ichiran Ramen, Tokyo")
    assert result["place_id"] == "abc123"


def test_text_search_empty_body_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.places_service.requests.post",
        lambda *a, **k: _mock_response(200, {}),
    )
    assert PlacesService.text_search("Nonexistent Place") is None


def test_text_search_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(
        "app.services.places_service.requests.post",
        lambda *a, **k: _mock_response(403, {"error": {"message": "denied"}}),
    )
    assert PlacesService.text_search("Anything") is None


def test_text_search_network_error_returns_none(monkeypatch):
    def raise_error(*args, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("app.services.places_service.requests.post", raise_error)
    assert PlacesService.text_search("Anything") is None


# --- find_or_create_place enrichment -------------------------------------------


def test_find_or_create_place_enriches_legacy_row_with_fresh_hours():
    from app.models.place import Place

    existing = Place(
        id=1, google_place_id="abc123", name="Old Name", lat=0.0, lng=0.0,
        opening_hours={"open_now": True},
    )
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = existing

    fresh_hours = {"periods": [{"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 17}}]}
    api_result = normalize_v1_place(_v1_place(regularOpeningHours=fresh_hours))

    result = PlacesService.find_or_create_place(db, "abc123", api_result)
    assert result is existing
    assert existing.opening_hours == fresh_hours


def test_find_or_create_place_does_not_overwrite_existing_periods():
    from app.models.place import Place

    original_hours = {"periods": [{"open": {"day": 2, "hour": 8}, "close": {"day": 2, "hour": 20}}]}
    existing = Place(id=1, google_place_id="abc123", name="Old Name", lat=0.0, lng=0.0, opening_hours=original_hours)
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = existing

    fresh_hours = {"periods": [{"open": {"day": 1, "hour": 9}, "close": {"day": 1, "hour": 17}}]}
    api_result = normalize_v1_place(_v1_place(regularOpeningHours=fresh_hours))

    PlacesService.find_or_create_place(db, "abc123", api_result)
    assert existing.opening_hours == original_hours
