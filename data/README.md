# Rooftop-PV dataset generation

`generate_pvgis_rooftop_data.py` creates aggregate 15-minute PVGIS-derived data
for the forecasting pipeline. It queries one representative coordinate per
STEG district and scales the PVGIS production to that district's aggregate
installed capacity. The older `generate_rooftop_dataset.py` remains available
only as an explicit synthetic/offline fallback.

- historical-style hourly weather and PV output;
- forecast-weather noise that increases with lead time;
- daily and yearly cyclical features;
- separate trainable aggregate rows per STEG commercial district.

This project intentionally does **not** generate individual rooftop geometry or
individual PV-system rows. Each row represents the aggregate rooftop fleet of a
commercial district. The PV count is inferred from the district capacity and the
official Prosol average system size of 3.62 kWc.

Example:

```bash
python -m data.generate_rooftop_dataset \
  --start 2024-01-01 \
  --end 2025-01-01 \
  --output results/datasets/rooftop_training.csv
```

Generate only selected districts by repeating `--district`:

```bash
python -m data.generate_rooftop_dataset \
  --start 2024-06-01 \
  --end 2024-07-01 \
  --district "TUNIS VILLE" \
  --district "SFAX VILLE" \
  --output results/datasets/rooftop_sample.csv
```

The PVGIS output is a modeled satellite-resource estimate, not a STEG meter
measurement. It is more physically grounded than the synthetic fallback but
must still be labeled as modeled PVGIS data until validated STEG measurements
are imported.
