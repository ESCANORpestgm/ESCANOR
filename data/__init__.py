"""Domain reference data for the PréSol rooftop-PV forecast platform.

Layout:
  - ``steg_districts``  — the 50 STEG commercial districts, 7 Directions, and
    programme constants (capacity, dust, saturation, displacement factors).
  - ``climate``         — climate-zone and PV-geometry constants shared by the
    data generators and the feature pipeline.
  - ``paths``           — project-wide artifact-path registry (results/ layout).
  - ``features``        — feature derivations shared with generated datasets.
  - ``schema``          — the canonical aggregate dataset column contract.
  - ``prosol_report_schema`` — typed structure of official Prosol report rows.
  - ``generate_*``      — dataset generation entry points.
  - ``governorates``    — compatibility shim for the pre-district naming.

Keep this ``__init__`` free of eager imports: the API process imports these
modules directly at startup, and ``models``/``reports``/``api`` all depend on
this package.
"""
