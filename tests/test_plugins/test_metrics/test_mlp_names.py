"""``molab.plugins.metrics.mlp_names`` — filename gate for host metrics / plots.

``is_mlp_metrics_surface`` matches ``*.mlp.jsonl`` only. Leftover zarr / index
names do not activate the metrics tab. ``*.mlp.vl.json`` still activates plots.
"""

from __future__ import annotations

from molab.plugins.metrics.mlp_names import is_mlp_metrics_surface, is_mlp_plot_surface


class TestIsMlpMetricsSurface:
    def test_jsonl_is_metrics_surface(self) -> None:
        assert is_mlp_metrics_surface("metrics.mlp.jsonl") is True

    def test_zarr_is_not_metrics_surface(self) -> None:
        assert is_mlp_metrics_surface("metrics.mlp.zarr") is False

    def test_index_is_not_metrics_surface(self) -> None:
        assert is_mlp_metrics_surface("metrics.mlp.index.json") is False


class TestIsMlpPlotSurface:
    def test_vl_json_is_plot_surface(self) -> None:
        assert is_mlp_plot_surface("loss.mlp.vl.json") is True
