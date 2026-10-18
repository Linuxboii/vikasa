"""Temperature in °C from a monthly climatology plus a warming-anomaly pathway."""

from __future__ import annotations

import bisect
import math

from evolution_sim.config import ClimateConfig


class ClimateForcing:
    """Deterministic T(tick) = seasonal climatology(phase) + anomaly(year).

    Month m is centred at phase (m + 0.5) / 12; between centres the
    climatology is linearly interpolated and wraps from December to January.
    Anomaly knots are linear in years since simulation start and held
    constant outside their range.
    """

    def __init__(self, config: ClimateConfig) -> None:
        self.config = config
        self.annual_mean_c = config.annual_mean_c
        self._years = [year for year, _ in config.anomaly_c]
        self._values = [value for _, value in config.anomaly_c]

    def year(self, tick: int) -> float:
        return tick / self.config.ticks_per_year

    def phase(self, tick: int) -> float:
        return (tick % self.config.ticks_per_year) / self.config.ticks_per_year

    def seasonal_c(self, phase: float) -> float:
        position = (phase * 12.0 - 0.5) % 12.0
        lower = math.floor(position) % 12
        weight = position - math.floor(position)
        monthly = self.config.monthly_c
        return (1.0 - weight) * monthly[lower] + weight * monthly[(lower + 1) % 12]

    def anomaly_c(self, year: float) -> float:
        if not self._years:
            return 0.0
        if year <= self._years[0]:
            return self._values[0]
        if year >= self._years[-1]:
            return self._values[-1]
        upper = bisect.bisect_right(self._years, year)
        y0, y1 = self._years[upper - 1], self._years[upper]
        v0, v1 = self._values[upper - 1], self._values[upper]
        return v0 + (v1 - v0) * (year - y0) / (y1 - y0)

    def temperature_c(self, tick: int) -> float:
        return self.seasonal_c(self.phase(tick)) + self.anomaly_c(self.year(tick))

    def annual_temperature_c(self, tick: int) -> float:
        return self.annual_mean_c + self.anomaly_c(self.year(tick))

    def season_index(self, tick: int) -> int:
        return min(3, int(4 * self.phase(tick)))

    def normalized(self, temperature_c: float) -> float:
        """Map °C onto the engine's dimensionless 0-1 temperature for visuals."""
        return min(1.0, max(0.0, 0.6 + (temperature_c - self.annual_mean_c) / 20.0))
