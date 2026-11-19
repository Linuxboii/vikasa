"""Fetch the Conservation Planner's survey sites from NASA POWER.

Each site is a full monthly T2M series (1981 to last year) written with the same
provenance (URL, retrieval time, SHA-256 of the response) as ``vikasa climate fetch``.
Needs a network connection. Existing files are kept unless ``--force`` is given.

Usage: python tools/build_survey_regions.py [--force]
"""

from __future__ import annotations

import argparse
import datetime as dt

from evolution_sim.climate.data import (
    DATA_DIR,
    SURVEY_REGIONS,
    fetch_power_monthly,
    region_from_power,
    save_region,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="Re-fetch existing sites")
    args = parser.parse_args()
    end = dt.date.today().year - 1
    for key, (name, lat, lon) in SURVEY_REGIONS.items():
        target = DATA_DIR / f"{key}.json"
        if target.exists() and not args.force:
            print(f"keep   {key}")
            continue
        raw, url = fetch_power_monthly(lat, lon, 1981, end)
        stamp = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        region = region_from_power(key, name, lat, lon, raw, url, stamp)
        save_region(region, target)
        print(f"fetch  {key:<11} mean {region.annual_mean_c:5.1f} °C  "
              f"seasons ±{region.seasonal_amplitude_c:4.1f} °C")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
