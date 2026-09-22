# Prosol source reports

These files are extracted from the official STEG documents:

- `prosol_mars_2026_1.txt`
- `prosol_mars_2026_2.txt`

The source report is a **monthly aggregate rooftop-PV report**. The main
hierarchy is:

```text
Report period
├── National indicators
├── Financing of PV installations
├── Monthly and cumulative installation history
├── Monthly and cumulative installed-power history
├── Direction de Distribution breakdown
├── Commercial-district breakdown
├── Rooftop system-size breakdown (1–12 kWc)
└── Pending PV dossiers by commercial district
```

The report also contains a separate section for **Chauffe-Eau-Solaire (CES)**.
CES values must remain separate from photovoltaic installation and production
metrics; they must not be included in the PV forecast training dataset.

The canonical Python representation is in `data/prosol_report_schema.py`.

To import a new extracted report and generate a normalized snapshot under
`reports/`, run:

```bash
python -m reports.prosol_report_importer \
  data/source/prosol_mars_2026_2.txt \
  --output reports/generated/prosol_mars_2026.json
```

The API exposes the generated snapshot at `/reports/prosol/snapshot`.
All imported report snapshots should retain:

- report period
- emission date
- source filename
- current-month values
- previous-year-month values
- current-year cumulative values
- previous-year cumulative values
- since-program-start values
- percentage variations where reported
