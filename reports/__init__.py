"""Reporting layer: forecast evaluation, metering intake and official Prosol reports.

Two families live here, both reading their artifacts through ``data.paths``:

- Forecast quality — ``measurement_importer`` validates raw meters into immutable
  snapshots, ``forecast_evaluator`` scores forecasts against them,
  ``historical_evaluation`` replays a stored dataset through the model, and
  ``evaluation_registry`` collects every run the dashboard can show.
- Prosol programme reports — ``prosol_report_importer`` turns the official PDF
  text into a JSON snapshot, ``prosol_history_db`` stores those snapshots in
  SQLite, ``prosol_updates`` overlays manual connections approved between two
  snapshots, and ``prosol_report_generator`` renders the metrics payload and the
  print report (through ``prosol_report_template``, which holds no data).

Nothing here imports ``api``; the FastAPI layer depends on this package, not the
other way round.
"""
