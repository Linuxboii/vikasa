"""Build the bundled city climate files used by the Species Risk Checker.

The numbers below were retrieved from NASA POWER (monthly T2M, MERRA-2, 1981-2025)
on 2026-11-15 through a browser session, because the build sandbox could not reach
the API directly. Each record holds the 1991-2020 monthly climatology and the
annual means for 1981-2025 (stored as POWER's month-13 annual rows), plus the
SHA-256 of the API response. Re-run ``vikasa climate fetch`` on a networked
machine to replace any of them with a full monthly series.

Usage: python tools/build_city_regions.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "evolution_sim" / "climate" / "data"
URL = ("https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M"
       "&community=AG&longitude={lon}&latitude={lat}&start=1981&end=2025&format=JSON")
RETRIEVED = "2026-11-15T06:50:00Z"

# key | name | lat | lon | sha256 | monthly 1991-2020 climatology | annual means 1981-2025
RAW = """\
hyderabad|Hyderabad|17.385|78.487|b2176c6630ce134523ef6c6692d26f584d7befc32919ea1708f4f3c1b458d7b0|21.5307,24.7523,28.8763,31.8050,33.3087,28.8617,26.3737,25.4017,25.0760,24.0510,21.9867,20.5050|25.2500,25.7200,26.1608,26.2817,26.0567,26.4217,26.0300,25.9850,25.8800,25.6475,26.3650,26.0675,26.0033,25.8808,25.2242,25.5933,26.0650,26.4850,25.8650,25.8825,26.1050,26.6633,26.4308,25.6475,25.5483,25.3283,25.7458,25.4592,26.5708,26.3108,25.9467,26.4733,25.4942,26.0742,26.9300,26.2383,26.1142,26.5225,26.6142,25.6725,25.3858,25.5967,25.9883,26.4483,25.2200
bengaluru|Bengaluru|12.972|77.594|0e3a76ba8de03c4cf5e1f135eab0483fb48d249b84741ecb0b002b2cd7714d2d|20.8843,23.5457,26.8390,28.4083,27.1103,24.2103,23.3440,23.1370,23.0230,22.3337,20.9697,19.8410|23.1492,23.3083,24.1508,23.4025,23.7025,23.7567,23.8100,23.5200,23.5533,24.1742,24.0617,23.3317,23.4142,23.5900,23.3258,23.1250,23.5425,23.7383,22.9442,23.2192,23.3833,23.9850,24.3775,23.1708,23.3050,23.2475,23.2500,22.7575,23.5033,23.7742,23.4825,24.3725,23.6075,24.0633,23.8650,24.4967,23.7400,23.9675,24.5750,23.8992,23.2683,23.1450,23.9725,24.7217,23.7258
chennai|Chennai|13.083|80.270|2e979ffa0a15f3162a8a07adfb0d512ea3add0dc902558f790eae9849df51fa0|23.9860,25.6380,28.3840,30.5550,31.5683,30.5153,29.5897,28.9697,28.3050,27.3117,25.7277,24.2350|27.3842,27.5617,28.0625,27.4792,27.3983,27.8683,28.0817,27.8808,27.7633,27.9067,28.0775,27.8942,27.7042,27.7767,27.2675,27.5150,28.0850,28.3167,27.7000,27.8225,28.1467,28.1092,28.2242,27.4883,27.8942,27.7983,27.6192,27.6517,28.2117,27.8250,27.7125,27.9692,27.7783,27.9683,27.8542,28.1092,28.1208,28.0650,28.3608,27.8975,27.5983,27.6342,27.9808,28.3608,27.7617
mumbai|Mumbai|19.076|72.878|17ae8f04fef5d5b748e685346ab6b064cada541f75913861b62dde16ecbe2bc0|23.1080,25.4490,28.6167,30.5483,31.0333,28.6380,26.5960,25.9960,26.0467,26.1253,24.5163,23.0950|26.4508,26.4258,25.8267,26.3367,26.2425,26.3975,27.0500,26.7325,26.4500,26.3550,26.3658,26.5767,26.4592,26.0967,26.6292,26.3583,26.3575,26.7383,26.2033,26.2817,26.5158,27.1225,27.0783,26.8225,26.3917,26.6533,26.8483,26.4758,27.2175,26.9667,26.5042,26.4492,26.4142,26.9600,26.9517,26.5575,26.7642,26.9375,26.9600,26.7642,26.8708,26.4625,27.0108,27.2075,26.6183
kolkata|Kolkata|22.573|88.364|91cdd8feb2af5ab85b01aefe560214e5e3cd5948c2b19ae77a0958bb19f31db7|17.6023,22.1773,27.5573,31.2257,31.5473,29.8150,28.5830,28.1640,27.5853,25.9543,21.8780,17.7847|25.3183,25.9683,26.7625,25.9017,26.3900,26.1725,26.0900,26.3392,26.0283,25.7325,26.3350,26.0192,25.8792,25.8250,25.8417,25.8975,25.8383,25.8133,25.7842,25.4358,25.7367,25.8017,25.8375,25.6692,25.9575,25.9067,25.4658,25.3025,26.0425,26.2333,25.6650,25.6158,25.5450,25.7008,26.0567,26.4750,26.0050,25.5275,26.1408,25.3317,26.0933,25.5342,26.6092,26.3325,25.6792
jaipur|Jaipur|26.912|75.787|dc19444bbe746680fd9b75f822cf611d09826d884caa5454706fc134c8f5dbc7|14.6220,17.9873,23.7650,29.8700,34.1540,34.7573,31.2993,28.9340,28.0643,25.6567,20.9847,16.4410|25.2425,24.5008,24.7017,25.3292,25.6125,25.3508,26.5708,26.4717,25.6942,25.4258,25.9158,25.0233,25.9983,25.3567,25.1942,25.0733,24.3975,25.3917,26.6767,26.2742,25.7800,27.0775,25.3792,25.8775,25.4550,26.3000,25.8183,25.4033,26.3858,25.7275,24.9625,24.7342,24.5075,25.1233,25.2033,26.0992,25.7708,25.5333,24.8083,25.0908,25.1917,25.3850,24.7475,25.1983,24.7617
shimla|Shimla|31.104|77.173|f503dd75d8e679680debf86b08717b345b51b24a84097f96592228ba6974157c|10.7057,13.2630,18.1940,24.1890,29.1467,30.3533,27.8040,25.7383,23.9350,20.6167,16.3167,12.5310|20.5892,20.1033,20.9417,21.0233,21.1475,21.0767,22.1800,21.7450,21.0050,21.0742,21.0842,20.6292,20.9225,20.8558,20.6017,20.4933,20.0425,21.2008,22.2700,21.4750,21.3583,22.1608,21.0367,21.6283,20.9517,21.7225,21.3625,20.4417,21.6333,21.5900,20.4183,21.0550,20.7942,21.1108,21.0175,22.0058,21.2317,20.7092,20.2000,19.9800,20.8975,20.9650,20.0975,21.2050,20.8017
"""


def _ols(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    centred = x - x.mean()
    slope = float(centred @ (y - y.mean()) / (centred @ centred))
    residuals = y - (y.mean() + slope * centred)
    variance = float(residuals @ residuals) / (len(x) - 2)
    return slope, (variance / float(centred @ centred)) ** 0.5


def build_records() -> list[dict]:
    records = []
    for line in RAW.strip().splitlines():
        key, name, lat, lon, sha, clim, annual = line.split("|")
        monthly = [float(v) for v in clim.split(",")]
        means = [float(v) for v in annual.split(",")]
        if len(monthly) != 12 or len(means) != 45:
            raise ValueError(f"{key}: expected 12 monthly and 45 annual values")
        years = np.arange(1981, 2026, dtype=float)
        slope, se = _ols(years, np.array(means))
        records.append({
            "key": key, "name": name, "latitude": float(lat), "longitude": float(lon),
            "monthly_c": monthly, "annual_mean_c": float(np.mean(monthly)),
            "seasonal_amplitude_c": (max(monthly) - min(monthly)) / 2.0,
            "trend_c_per_decade": 10.0 * slope, "trend_se_c_per_decade": 10.0 * se,
            "first_year": 1981, "last_year": 2025,
            "series": [[1981 + i, 13, value] for i, value in enumerate(means)],
            "provenance": {
                "source": "NASA POWER", "dataset": "NASA POWER MERRA-2 T2M monthly",
                "parameter": "T2M (2 m air temperature, °C)",
                "url": URL.format(lat=lat, lon=lon), "retrieved_utc": RETRIEVED,
                "sha256": sha,
                "note": ("Series holds annual means (month 13) for 1981-2025; climatology "
                         "is the 1991-2020 monthly mean. Values are for the reanalysis "
                         "grid cell, not a weather station."),
            },
        })
    return records


def main() -> None:
    for record in build_records():
        path = TARGET / f"{record['key']}.json"
        path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                        encoding="utf-8", newline="\n")
        print(f"{path.name}: mean {record['annual_mean_c']:.1f} °C, "
              f"amplitude ±{record['seasonal_amplitude_c']:.1f} °C, "
              f"trend {record['trend_c_per_decade']:+.3f} °C/decade")


if __name__ == "__main__":
    main()
