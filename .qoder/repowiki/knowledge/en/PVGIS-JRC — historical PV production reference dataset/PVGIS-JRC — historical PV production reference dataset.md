---
kind: external_dependency
name: PVGIS-JRC — historical PV production reference dataset
slug: pvgis-jrc
category: external_dependency
category_hints:
    - vendor_identity
    - sdk_real_api
scope:
    - '**'
---

European Commission Joint Research Centre's PVGIS service provides historical hourly PV production simulation for training/validation when real STEG metering data is unavailable. The platform calls `https://re.jrc.ec.europa.eu/api/v5_2/seriescalc` with `mountingplace=building`, `outputformat=json`, and a 1 kWc reference system with ~14% system loss.

- SDK shape: uses the JRC v5.2 seriescalc endpoint with `lat`, `lon`, `startyear`, `endyear`, `peakpower`, `loss`, `pvcalculation=1`; confirm current endpoint version and parameter set against the official PVGIS API documentation before changing.
- Constraint: free, no API key required; intended as historical reference, not a real-time feed.