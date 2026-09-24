"""External data acquisition: live weather, PVGIS reference production, synthetic data.

Layout:
  - ``settings``        — shared upstream endpoints, timeouts, and pipeline column names.
  - ``weather_client``  — Open-Meteo hourly forecast acquisition (async, concurrent).
  - ``pvgis_client``    — PVGIS/JRC historical district production with local cache.
  - ``synthetic_data``  — offline generator reproducing the same schema.

Modules here depend only on the standard library, httpx/requests, numpy, pandas
and the domain constants in ``data.climate`` — never on ``models`` or
``reports`` — so they can be imported from the data generators without creating
a cycle.
"""
