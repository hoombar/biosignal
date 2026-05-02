"""Unit tests for the one-shot HabitSync history import helpers."""
import pytest

from scripts.import_habitsync_history import (
    _canonicalize_habit_name,
    _coerce_value,
    _parse_aliases,
    _parse_csv,
)


class TestParseCsv:
    def test_empty_string_returns_empty_set(self):
        assert _parse_csv("") == set()

    def test_normalizes_each_name(self):
        assert _parse_csv("PM Slump,Coffee Count") == {"pm_slump", "coffee_count"}

    def test_strips_whitespace_and_drops_blanks(self):
        assert _parse_csv(" coffee , , alcohol ") == {"coffee", "alcohol"}


class TestParseAliases:
    def test_empty_string_returns_empty_dict(self):
        assert _parse_aliases("") == {}

    def test_normalizes_source_and_target_names(self):
        assert _parse_aliases("Healthy Meals:Healthy Lunch") == {
            "healthy_meals": "healthy_lunch"
        }

    def test_supports_multiple_aliases(self):
        assert _parse_aliases("PM Slump:Afternoon Slump,Beer:Alcohol") == {
            "pm_slump": "afternoon_slump",
            "beer": "alcohol",
        }

    def test_rejects_invalid_alias_format(self):
        with pytest.raises(ValueError):
            _parse_aliases("healthy_meals")


class TestCanonicalizeHabitName:
    def test_applies_alias_after_normalization(self):
        assert (
            _canonicalize_habit_name(
                "Healthy Meals", {"healthy_meals": "healthy_lunch"}
            )
            == "healthy_lunch"
        )

    def test_returns_normalized_name_without_alias(self):
        assert _canonicalize_habit_name("Healthy Lunch", {}) == "healthy_lunch"


class TestCoerceValueBinary:
    def test_record_value_one_means_one(self):
        assert _coerce_value(1, "binary", None) == 1

    def test_record_value_zero_with_completed_stays_zero(self):
        assert _coerce_value(0, "binary", "COMPLETED") == 0

    def test_record_value_zero_with_completed_by_other_records_stays_zero(self):
        assert _coerce_value(0, "binary", "COMPLETED_BY_OTHER_RECORDS") == 0

    def test_missing_record_value_can_fall_back_to_completion(self):
        assert _coerce_value(None, "binary", "COMPLETED") == 1

    def test_record_value_zero_with_missed_means_zero(self):
        assert _coerce_value(0, "binary", "MISSED") == 0

    def test_record_value_above_one_clipped_to_one(self):
        assert _coerce_value(5, "binary", None) == 1

    def test_none_record_value_with_missed_treated_as_zero(self):
        assert _coerce_value(None, "binary", "MISSED") == 0


class TestCoerceValueCounter:
    def test_record_value_passes_through_as_int(self):
        assert _coerce_value(3, "counter", None) == 3

    def test_float_record_value_truncates(self):
        assert _coerce_value(2.7, "counter", None) == 2

    def test_negative_record_value_clamped_to_zero(self):
        assert _coerce_value(-1, "counter", None) == 0

    def test_none_record_value_is_zero(self):
        assert _coerce_value(None, "counter", None) == 0
