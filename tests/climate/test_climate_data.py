from __future__ import annotations

import json
import re
import urllib.error

import pytest

from evolution_sim.climate import data
from evolution_sim.climate.data import (
    BUNDLED_REGIONS,
    fetch_power_monthly,
    load_region,
    region_from_power,
    resolve_region,
    save_region,
    ssp_anomaly_c,
    ssp_rate_c_per_year,
)

BASE = [20.0, 21.0, 23.0, 26.0, 28.0, 27.0, 25.0, 24.0, 24.5, 23.5, 22.0, 20.5]
TREND_PER_YEAR = 0.03


def power_payload(first=1985, last=2020, *, fill=(2000, 5), drop_months=()) -> bytes:
    values = {}
    for year in range(first, last + 1):
        for month in range(1, 13):
            if month in drop_months and year >= 1991:
                continue
            values[f"{year}{month:02d}"] = BASE[month - 1] + TREND_PER_YEAR * (year - 2005.5)
        values[f"{year}13"] = 99.0
    values[f"{fill[0]}{fill[1]:02d}"] = -999.0
    return json.dumps({"properties": {"parameter": {"T2M": values}},
                       "header": {"sources": ["MERRA2"]}}).encode()


def region(**kwargs):
    return region_from_power("test", "Test", 10.0, 70.0, power_payload(**kwargs),
                             "https://example.invalid", "2026-10-18T00:00:00Z")


def test_parse_fixture_excludes_fill_and_annual_keys() -> None:
    result = region()
    for month, value in enumerate(result.monthly_c):
        # 1991-2020 mean of the trend term is zero, except May drops year 2000 (fill).
        expected = BASE[month] + (TREND_PER_YEAR * (sum(y - 2005.5 for y in range(1991, 2021)
                                                        if y != 2000) / 29) if month == 4 else 0)
        assert value == pytest.approx(expected, abs=1e-9)
    assert all(row[2] > -900 for row in result.series)
    assert all(row[1] <= 12 for row in result.series)
    assert result.seasonal_amplitude_c == pytest.approx(4.0, abs=0.01)


def test_trend_recovers_known_slope() -> None:
    result = region(fill=(1800, 1))
    assert result.trend_c_per_decade == pytest.approx(10 * TREND_PER_YEAR, abs=1e-9)
    assert result.first_year == 1985 and result.last_year == 2020


def test_insufficient_years_raises() -> None:
    with pytest.raises(ValueError, match="month 3"):
        region(drop_months=(3,))


def test_region_json_round_trip(tmp_path) -> None:
    original = region()
    save_region(original, tmp_path / "r.json")
    assert load_region(tmp_path / "r.json") == original


def test_bundled_regions_load_and_are_plausible() -> None:
    for key in BUNDLED_REGIONS:
        result = resolve_region(key)
        assert 15 < result.annual_mean_c < 35
        assert len(result.monthly_c) == 12
        assert re.fullmatch(r"[0-9a-f]{64}", result.provenance["sha256"])
        assert result.last_year >= 2020


def test_unknown_region_is_friendly() -> None:
    with pytest.raises(ValueError, match="Unknown region"):
        resolve_region("atlantis")


def test_ssp_values_and_rate() -> None:
    assert ssp_anomaly_c("SSP2-4.5", 2090) == pytest.approx(1.8)
    assert ssp_anomaly_c("SSP2-4.5", 2000) == 0.0
    assert ssp_anomaly_c("SSP5-8.5", 2090, regional_factor=1.5) == pytest.approx(5.25)
    assert ssp_anomaly_c("SSP5-8.5", 2090, bound="high") == pytest.approx(4.8)
    assert ssp_rate_c_per_year("SSP2-4.5") == pytest.approx(1.8 / 85)
    with pytest.raises(ValueError, match="Unknown SSP"):
        ssp_rate_c_per_year("SSP9")


def test_fetch_uses_opener_and_wraps_errors() -> None:
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return power_payload()

    def ok_opener(url, timeout):
        calls.append(url)
        return Response()

    raw, url = fetch_power_monthly(13.5, 75.1, 1981, 2024, opener=ok_opener)
    assert "latitude=13.5" in url and calls == [url] and raw.startswith(b"{")

    def bad_opener(url, timeout):
        raise urllib.error.URLError("offline")

    with pytest.raises(RuntimeError, match=r"power.larc.nasa.gov"):
        fetch_power_monthly(13.5, 75.1, 1981, 2024, opener=bad_opener)
    assert data.POWER_URL.startswith("https://power.larc.nasa.gov/")
