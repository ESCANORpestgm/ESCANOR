"""HTML/CSS skeleton of the print-ready STEG "Tableau de Bord Programme Prosol".

The fragments live here so that the report's *presentation* — the only place the
French layout, the STEG stylesheet and the print margins are defined — can be
reviewed without reading any data logic. ``prosol_report_generator`` supplies the
numbers; this module only formats them.

Every fragment reproduces the official document exactly, so the pieces are
concatenated in the same order the tables appear on paper:
``render_head`` → indicator rows → ``DIRECTION_TABLE_START`` → direction rows →
``render_direction_total_row`` → ``EXECUTION_TABLE_START`` → top-five rows →
``LAGGARD_TABLE_START`` → last-five rows → ``render_footer``.
"""

from __future__ import annotations

from typing import Any

# CSS class colouring the district velocity columns of section 3
RATE_CLASS_LEADERS = "pos"
RATE_CLASS_LAGGARDS = "neg"


def render_head(
    *,
    report_period: str,
    installed_capacity_mw: float,
    installed_sites: int,
    injection_rate: float,
    injected_gwh: float,
    avoided_fuel_cost_mdt: float,
) -> str:
    """Document start: stylesheet, STEG letterhead, banner and the four KPI cards."""
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Tableau de Bord Programme Prosol — STEG Mars 2026</title>
<style>
  @page {{ size: A4; margin: 15mm; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    color: #1a252f;
    background: #f8fafc;
    margin: 0;
    padding: 20px;
  }}
  .report-page {{
    max-width: 900px;
    margin: 0 auto 30px auto;
    background: #ffffff;
    padding: 35px 45px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    border-radius: 8px;
  }}
  .steg-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 3px solid #003366;
    padding-bottom: 12px;
    margin-bottom: 25px;
  }}
  .steg-logo-title {{
    font-size: 1.1rem;
    font-weight: bold;
    color: #003366;
    line-height: 1.3;
  }}
  .steg-arabic {{
    font-family: 'Amiri', 'Traditional Arabic', serif;
    font-size: 1.2rem;
    color: #003366;
    text-align: right;
  }}
  .report-title-banner {{
    background: linear-gradient(135deg, #003366 0%, #005599 100%);
    color: white;
    text-align: center;
    padding: 16px;
    border-radius: 6px;
    margin-bottom: 25px;
  }}
  .report-title-banner h1 {{
    margin: 0;
    font-size: 1.5rem;
    letter-spacing: 1px;
    text-transform: uppercase;
  }}
  .report-title-banner p {{
    margin: 4px 0 0 0;
    font-size: 0.95rem;
    opacity: 0.9;
  }}
  h2 {{
    color: #003366;
    font-size: 1.15rem;
    border-left: 4px solid #00A3E0;
    padding-left: 10px;
    margin: 20px 0 12px 0;
  }}
  table.steg-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
    font-size: 0.88rem;
  }}
  table.steg-table th, table.steg-table td {{
    border: 1px solid #cbd5e1;
    padding: 6px 10px;
  }}
  table.steg-table th {{
    background-color: #f1f5f9;
    color: #003366;
    font-weight: 600;
    text-align: center;
  }}
  table.steg-table tr:nth-child(even) {{
    background-color: #f8fafc;
  }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pos {{ color: #16a34a; font-weight: 600; }}
  .neg {{ color: #dc2626; font-weight: 600; }}
  .pill {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 0.78rem;
  }}
  .pill-green {{ background: #dcfce7; color: #15803d; }}
  .pill-amber {{ background: #fef3c7; color: #b45309; }}
  .pill-red {{ background: #fee2e2; color: #b91c1c; }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin-bottom: 25px;
  }}
  .kpi-card {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-top: 3px solid #00A3E0;
    border-radius: 6px;
    padding: 12px;
    text-align: center;
  }}
  .kpi-val {{ font-size: 1.4rem; font-weight: bold; color: #003366; }}
  .kpi-lbl {{ font-size: 0.78rem; color: #64748b; margin-top: 4px; }}
  .footer-note {{
    border-top: 1px solid #e2e8f0;
    padding-top: 10px;
    font-size: 0.75rem;
    color: #94a3b8;
    display: flex;
    justify-content: space-between;
  }}
</style>
</head>
<body>

<div class="report-page">
  <div class="steg-header">
    <div class="steg-logo-title">
      Société Tunisienne de l'Electricité et du Gaz<br>
      <span style="font-size:0.85rem; font-weight:normal; color:#475569;">
        Direction Centrale de la Distribution &bull; Direction Commerciale et Marketing
      </span>
    </div>
    <div class="steg-arabic">
      الشركة التونسية للكهرباء والغاز<br>
      <span style="font-size:0.85rem; color:#475569;">برنامج بروسول (Prosol)</span>
    </div>
  </div>

  <div class="report-title-banner">
    <h1>TABLEAU DE BORD PROGRAMME PROSOL</h1>
    <p>PROSOL ELECTRIQUE (PHOTOVOLTAÏQUE PV) &bull; ETAT : {report_period.upper()}</p>
  </div>

  <!-- Key Topline KPIs -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-val">{installed_capacity_mw:,.1f} MWc</div>
      <div class="kpi-lbl">Puissance Installée Cumulée</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{installed_sites:,}</div>
      <div class="kpi-lbl">Installations PV Raccordées</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{injection_rate:.1f}%</div>
      <div class="kpi-lbl">Taux d'Injection Réseau ({injected_gwh:,.1f} GWh)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">{avoided_fuel_cost_mdt:,.1f} MDT</div>
      <div class="kpi-lbl">Coût Combustible Évité</div>
    </div>
  </div>

  <h2>1. Données Statistiques des IPV (Synthèse Officielle STEG)</h2>
  <table class="steg-table">
    <thead>
      <tr>
        <th rowspan="2">Libellé</th>
        <th colspan="3">Du Mois (Mars)</th>
        <th colspan="3">Cumul de l'Année (Q1)</th>
        <th rowspan="2">Depuis 2011</th>
      </tr>
      <tr>
        <th>Mars-26</th>
        <th>Mars-25</th>
        <th>VAR (%)</th>
        <th>2026</th>
        <th>2025</th>
        <th>VAR (%)</th>
      </tr>
    </thead>
    <tbody>
"""


def render_indicator_row(indicator: dict[str, Any]) -> str:
    """One of the eight canonical Prosol metrics of section 1."""
    month_class = RATE_CLASS_LEADERS if indicator["month_var"] >= 0 else RATE_CLASS_LAGGARDS
    ytd_class = RATE_CLASS_LEADERS if indicator["ytd_var"] >= 0 else RATE_CLASS_LAGGARDS
    return f"""      <tr>
        <td><strong>{indicator['label']}</strong></td>
        <td class="num">{indicator['month_current']:,}</td>
        <td class="num">{indicator['month_prev']:,}</td>
        <td class="num {month_class}">{indicator['month_var']:+.0f}%</td>
        <td class="num">{indicator['ytd_current']:,}</td>
        <td class="num">{indicator['ytd_prev']:,}</td>
        <td class="num {ytd_class}">{indicator['ytd_var']:+.0f}%</td>
        <td class="num"><strong>{indicator['since_2011']:,}</strong></td>
      </tr>\n"""


DIRECTION_TABLE_START = """    </tbody>
  </table>

  <h2>2. Répartition par Direction de Distribution</h2>
  <table class="steg-table">
    <thead>
      <tr>
        <th>Direction de Distribution</th>
        <th>Districts Rattachés</th>
        <th>Puissance Installée (MWc)</th>
        <th>Part Nationale (%)</th>
        <th>Dossiers en Instance</th>
      </tr>
    </thead>
    <tbody>
"""


def render_direction_row(name: str, info: dict[str, Any]) -> str:
    """One distribution direction of section 2."""
    return f"""      <tr>
        <td><strong>{name}</strong></td>
        <td class="num">{info['districts_count']}</td>
        <td class="num">{info['total_capacity_mwc']} MWc</td>
        <td class="num">{info['share_pct']}%</td>
        <td class="num">{info['pending_dossiers']:,}</td>
      </tr>\n"""


def render_direction_total_row(
    district_count: int,
    national_capacity_mwc: float,
    pending_dossiers: int,
) -> str:
    """The shaded national total closing section 2."""
    return f"""      <tr style="background:#e2e8f0; font-weight:bold;">
        <td>TOTAL NATIONAL</td>
        <td class="num">{district_count}</td>
        <td class="num">{national_capacity_mwc:.1f} MWc</td>
        <td class="num">100.0%</td>
        <td class="num">{pending_dossiers:,}</td>
      </tr>
"""


EXECUTION_TABLE_START = """    </tbody>
  </table>

  <h2>3. Suivi de l'Exécution & Dossiers en Instance par District</h2>
  <div style="display:grid; grid-template-columns: 1fr 1fr; gap:15px;">
    <div>
      <h3 style="font-size:0.95rem; color:#15803d; margin:4px 0 8px 0;">Top 5 Réalisations (Vélocité Maximale)</h3>
      <table class="steg-table">
        <thead>
          <tr><th>District</th><th>Taux 2026</th><th>Taux 2025</th></tr>
        </thead>
        <tbody>
"""

LAGGARD_TABLE_START = """        </tbody>
      </table>
    </div>
    <div>
      <h3 style="font-size:0.95rem; color:#b91c1c; margin:4px 0 8px 0;">Last 5 Réalisations (Goulots d'Étranglement)</h3>
      <table class="steg-table">
        <thead>
          <tr><th>District</th><th>Taux 2026</th><th>Taux 2025</th></tr>
        </thead>
        <tbody>
"""


def render_district_rate_row(district: dict[str, Any], rate_class: str) -> str:
    """A top-five or last-five district line of section 3."""
    return f"""          <tr><td>{district['name']}</td><td class="num {rate_class}">{district['rate_2026']}%</td><td class="num">{district['rate_2025']}%</td></tr>\n"""


def render_footer(emission_date: str) -> str:
    """Closing panel: generator credit, emission date and data provenance."""
    return f"""        </tbody>
      </table>
    </div>
  </div>

  <div class="footer-note">
    <span>Généré par la Plateforme Nationale Intelligente de Prévision PV &bull; Algorithmes ESCANOR</span>
    <span>Date d'émission : {emission_date} &bull; Source : Données réelles STEG DCD/DCM</span>
  </div>
</div>

</body>
</html>
"""


__all__ = [
    "DIRECTION_TABLE_START",
    "EXECUTION_TABLE_START",
    "LAGGARD_TABLE_START",
    "RATE_CLASS_LAGGARDS",
    "RATE_CLASS_LEADERS",
    "render_direction_row",
    "render_direction_total_row",
    "render_district_rate_row",
    "render_footer",
    "render_head",
    "render_indicator_row",
]
