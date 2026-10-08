"""Joint variation must preserve scaling, degeneracy and unavailable information."""

import hashlib
import json

import numpy as np
import pytest

from evolution_sim.analytics import metrics
from evolution_sim.io.export import export_experiment


def test_two_independent_axes_have_hand_derived_covariance_and_dimension():
    points = np.zeros((4, 6))
    points[:, :2] = [[0, 0], [1, 0], [0, 1], [1, 1]]
    result = metrics.trait_geometry(points, np.zeros(6), np.ones(6))
    assert result["normalized_mean"] == [.5, .5, 0, 0, 0, 0]
    expected = np.diag([1 / 3, 1 / 3, 0, 0, 0, 0])
    np.testing.assert_allclose(result["covariance"], expected, atol=1e-15)
    assert result["effective_dimension"] == pytest.approx(2)
    assert result["explained_fraction"] == pytest.approx([.5, .5, 0, 0, 0, 0])
    assert result["correlation"][0][1] == 0
    assert result["correlation"][0][2] is None
    assert result["degenerate_axes"] is True
    assert sum(result["histograms"][0]) == 4


def test_joint_geometry_is_invariant_to_trait_units():
    points = np.array([[.1] * 6, [.4] * 6, [.9] * 6])
    first = metrics.trait_geometry(points, np.zeros(6), np.ones(6))
    scales = np.array([1, 100, 10, .1, 1000, 2])
    second = metrics.trait_geometry(3 + points * scales, np.full(6, 3), 3 + scales)
    np.testing.assert_allclose(first["covariance"], second["covariance"], atol=1e-14)
    assert first["effective_dimension"] == pytest.approx(1)


@pytest.mark.parametrize("points", [np.empty((0, 6)), np.full((1, 6), .5)])
def test_insufficient_population_does_not_fabricate_covariance(points):
    result = metrics.trait_geometry(points, np.zeros(6), np.ones(6))
    assert result["covariance"] is None
    assert result["effective_dimension"] is None


def test_identical_population_has_no_defined_explained_fraction():
    result = metrics.trait_geometry(np.full((4, 6), .5), np.zeros(6), np.ones(6))
    assert result["eigenvalues"] == [0] * 6
    assert result["explained_fraction"] is None
    assert result["effective_dimension"] is None


def test_decimal_constant_cloud_has_exactly_no_variation():
    result = metrics.trait_geometry(np.full((3, 6), .1), np.zeros(6), np.ones(6))
    assert result["eigenvalues"] == [0] * 6
    assert result["explained_fraction"] is None


def test_tiny_finite_variation_has_finite_dimension_and_correlation():
    cloud = np.repeat(np.array([0, 1e-100, 2e-100])[:, None], 6, axis=1)
    result = metrics.trait_geometry(cloud, np.zeros(6), np.ones(6))
    assert result["effective_dimension"] == pytest.approx(1)
    assert result["correlation"][0][1] == pytest.approx(1)
    json.dumps(result, allow_nan=False)
    independent = np.zeros((4, 6))
    independent[:, :2] = np.array([[0, 0], [1, 0], [0, 1], [1, 1]]) * 1e-100
    result = metrics.trait_geometry(independent, np.zeros(6), np.ones(6))
    assert result["correlation"][0][1] == pytest.approx(0, abs=1e-14)


def test_overflowing_bound_span_is_rejected():
    with pytest.raises(ValueError):
        metrics.trait_geometry(np.zeros((3, 6)), np.full(6, -1e308), np.full(6, 1e308))


def test_invalid_trait_cloud_is_rejected():
    with pytest.raises(ValueError):
        metrics.trait_geometry(np.full((4, 6), np.nan), np.zeros(6), np.ones(6))


def test_export_includes_hashed_individual_trait_geometry(tiny_config, tmp_path):
    from evolution_sim.simulation.engine import SimulationEngine

    engine = SimulationEngine(tiny_config, 7)
    engine.step(20)
    manifest = export_experiment(engine, tmp_path)
    assert "trait-space.json" in manifest.files
    data = json.loads((tmp_path / "trait-space.json").read_text())
    assert [row["id"] for row in data["individuals"]] == sorted(engine.creatures)
    assert data["geometry"]["population"] == len(engine.creatures)
    assert manifest.files["trait-space.json"] == hashlib.sha256(
        (tmp_path / "trait-space.json").read_bytes()).hexdigest()


def test_chart_export_renders_joint_geometry(tiny_config, tmp_path):
    from evolution_sim.experiments.charts import export_charts
    from evolution_sim.simulation.engine import SimulationEngine

    engine = SimulationEngine(tiny_config, 7)
    paths = export_charts(engine, tmp_path)
    assert "trait_space.png" in [path.name for path in paths]
    assert (tmp_path / "trait_space.png").read_bytes().startswith(b"\x89PNG")


def test_observing_traits_does_not_change_future(tiny_config, tmp_path):
    from evolution_sim.simulation.engine import SimulationEngine

    observed, control = (SimulationEngine(tiny_config, 7) for _ in range(2))
    export_experiment(observed, tmp_path)
    observed.step(30)
    control.step(30)
    assert observed.snapshot() == control.snapshot()
