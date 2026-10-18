"""Observed regional temperature (NASA POWER) and IPCC AR6 warming pathways."""

from __future__ import annotations

import hashlib
import json
import math
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

POWER_URL = ("https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M"
             "&community=AG&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON")
CLIMATOLOGY_YEARS = (1991, 2020)
MINIMUM_CLIMATOLOGY_YEARS = 20
DATA_DIR = Path(__file__).resolve().parent / "data"

BUNDLED_REGIONS: dict[str, tuple[str, float, float]] = {
    "western-ghats": ("Western Ghats (Agumbe)", 13.52, 75.09),
    "delhi-ncr": ("Delhi NCR", 28.61, 77.21),
    "sundarbans": ("Sundarbans", 21.95, 88.90),
}

# IPCC AR6 WG1 Chapter 4, Table 4.5: global surface air temperature change for
# 2081-2100 relative to 1995-2014, °C: (median, very likely low, very likely high).
SSP_WARMING: dict[str, tuple[float, float, float]] = {
    "SSP1-2.6": (0.9, 0.5, 1.5),
    "SSP2-4.5": (1.8, 1.2, 2.6),
    "SSP3-7.0": (2.8, 2.0, 3.7),
    "SSP5-8.5": (3.5, 2.4, 4.8),
}
SSP_REFERENCE_YEAR = 2005.0  # centre of 1995-2014
SSP_TARGET_YEAR = 2090.0  # centre of 2081-2100
SSP_SOURCE = ("IPCC AR6 WG1 Ch. 4 Table 4.5 (2081-2100 vs 1995-2014, global mean); "
              "linear pathway between period centres, scaled by a regional factor")


@dataclass(frozen=True)
class RegionClimate:
    key: str
    name: str
    latitude: float
    longitude: float
    monthly_c: tuple[float, ...]
    annual_mean_c: float
    seasonal_amplitude_c: float
    trend_c_per_decade: float
    trend_se_c_per_decade: float
    first_year: int
    last_year: int
    series: tuple[tuple[int, int, float], ...]
    provenance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["monthly_c"] = list(self.monthly_c)
        result["series"] = [list(row) for row in self.series]
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RegionClimate:
        return cls(**{**raw, "monthly_c": tuple(float(v) for v in raw["monthly_c"]),
                      "series": tuple((int(y), int(m), float(t)) for y, m, t in raw["series"]),
                      "provenance": dict(raw["provenance"])})


def fetch_power_monthly(lat: float, lon: float, start: int, end: int, *,
                        opener: Callable[..., Any] = urllib.request.urlopen,
                        timeout: float = 60) -> tuple[bytes, str]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or start > end:
        raise ValueError("latitude must be in [-90, 90], longitude in [-180, 180], start <= end")
    url = POWER_URL.format(lat=lat, lon=lon, start=start, end=end)
    try:
        with opener(url, timeout=timeout) as response:
            raw = response.read()
        json.loads(raw)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"NASA POWER request failed for {url}: {exc}") from exc
    return raw, url


def _ols_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    centred = x - x.mean()
    slope = float(centred @ (y - y.mean()) / (centred @ centred))
    residuals = y - (y.mean() + slope * centred)
    dof = len(x) - 2
    variance = float(residuals @ residuals) / dof if dof > 0 else 0.0
    se = math.sqrt(variance / float(centred @ centred))
    return slope, se


def region_from_power(key: str, name: str, lat: float, lon: float, raw: bytes, url: str,
                      retrieved_utc: str) -> RegionClimate:
    try:
        values = json.loads(raw)["properties"]["parameter"]["T2M"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Response is not a NASA POWER monthly T2M document") from exc
    series = []
    for stamp, value in sorted(values.items()):
        year, month = int(stamp[:4]), int(stamp[4:])
        # Month 13 is POWER's annual mean; values at or below -900 are fill.
        if 1 <= month <= 12 and value is not None and float(value) > -900:
            series.append((year, month, float(value)))
    if not series:
        raise ValueError("NASA POWER response contains no valid monthly temperatures")
    monthly = []
    for month in range(1, 13):
        window = [t for y, m, t in series if m == month
                  and CLIMATOLOGY_YEARS[0] <= y <= CLIMATOLOGY_YEARS[1]]
        if len(window) < MINIMUM_CLIMATOLOGY_YEARS:
            raise ValueError(f"climatology needs ≥{MINIMUM_CLIMATOLOGY_YEARS} valid years "
                             f"for month {month} in {CLIMATOLOGY_YEARS[0]}-"
                             f"{CLIMATOLOGY_YEARS[1]}; found {len(window)}")
        monthly.append(float(np.mean(window)))
    complete = sorted({y for y, _, _ in series
                       if sum(1 for yy, _, _ in series if yy == y) == 12})
    annual = np.array([np.mean([t for y, _, t in series if y == year]) for year in complete])
    slope, se = (_ols_slope(np.array(complete, dtype=float), annual)
                 if len(complete) >= 3 else (0.0, 0.0))
    return RegionClimate(
        key=key, name=name, latitude=float(lat), longitude=float(lon),
        monthly_c=tuple(monthly), annual_mean_c=float(np.mean(monthly)),
        seasonal_amplitude_c=(max(monthly) - min(monthly)) / 2.0,
        trend_c_per_decade=10.0 * slope, trend_se_c_per_decade=10.0 * se,
        first_year=series[0][0], last_year=series[-1][0], series=tuple(series),
        provenance={"source": "NASA POWER", "dataset": "NASA POWER MERRA-2 T2M monthly",
                    "parameter": "T2M (2 m air temperature, °C)", "url": url,
                    "retrieved_utc": retrieved_utc,
                    "sha256": hashlib.sha256(raw).hexdigest()},
    )


def save_region(region: RegionClimate, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(region.to_dict(), indent=1, sort_keys=True,
                                    allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(target)
    return target


def load_region(path: str | Path) -> RegionClimate:
    return RegionClimate.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def resolve_region(spec: str) -> RegionClimate:
    if spec in BUNDLED_REGIONS:
        return load_region(DATA_DIR / f"{spec}.json")
    path = Path(spec)
    if path.suffix == ".json" and path.is_file():
        return load_region(path)
    raise ValueError(f"Unknown region {spec!r}; use one of {', '.join(BUNDLED_REGIONS)} "
                     "or a region JSON written by 'vikasa climate fetch'")


def _ssp_target(ssp: str, bound: str) -> float:
    if ssp not in SSP_WARMING:
        raise ValueError(f"Unknown SSP {ssp!r}; use one of {', '.join(SSP_WARMING)}")
    index = {"median": 0, "low": 1, "high": 2}.get(bound)
    if index is None:
        raise ValueError("bound must be 'median', 'low' or 'high'")
    return SSP_WARMING[ssp][index]


def ssp_rate_c_per_year(ssp: str, regional_factor: float = 1.0, bound: str = "median") -> float:
    return _ssp_target(ssp, bound) * regional_factor / (SSP_TARGET_YEAR - SSP_REFERENCE_YEAR)


def ssp_anomaly_c(ssp: str, year: float, regional_factor: float = 1.0,
                  bound: str = "median") -> float:
    rate = ssp_rate_c_per_year(ssp, regional_factor, bound)
    return max(0.0, rate * (year - SSP_REFERENCE_YEAR))
