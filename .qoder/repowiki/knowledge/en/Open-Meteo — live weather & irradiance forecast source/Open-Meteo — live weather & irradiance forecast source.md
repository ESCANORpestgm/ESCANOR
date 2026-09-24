---
kind: external_dependency
name: Open-Meteo — live weather & irradiance forecast source
slug: open-meteo
category: external_dependency
category_hints:
    - vendor_identity
    - client_constraint
scope:
    - '**'
---

Free, no-API-key hourly weather/irradiance service used as the primary live data source for all 50 STEG districts. The platform calls `https://api.open-meteo.com/v1/forecast` with variables shortwave_radiation, diffuse_radiation, direct_normal_irradiance, temperature_2m, cloud_cover, wind_speed_10m and timezone Africa/Tunis; forecasts are capped at 16 days (the API limit) and fetched concurrently via httpx.AsyncClient across all governorates.

- Client constraint: requests target Tunisia coordinates (`Africa/Tunis` timezone); results are per-governorate/district lat/lon so each district gets its own series.
- Verify exact parameter names against the official Open-Meteo forecast API docs.