"""
STEG Prosol Report Generator.
Generates official, print-ready reports that replicate the exact structure,
metrics, and design of STEG's "Tableau de Bord Programme Prosol".

Produces:
- Standalone print-optimized HTML report with STEG branding and tables
- Structured JSON summary of all 8 Prosol indicators
"""

import os
import sys
from datetime import datetime
from typing import Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from data.steg_districts import STEG_DISTRICTS, DIRECTIONS, calculate_displacement, direction_summary, NATIONAL_ROOFTOP_PV_MWC


def get_prosol_summary_metrics(month_str: str = "Mars 2026") -> Dict[str, Any]:
    """
    Generate the official 8 canonical Prosol metrics table matching Section 1.1 of the report.
    """
    # Ground truth values extracted from Mars 2026 STEG Report
    return {
        "report_period": month_str,
        "emission_date": "11/05/2026",
        "direction_tutelle": "Direction Centrale de la Distribution — Direction Commerciale et Marketing",
        "recap_executions": {
            "period": "Mars 2026",
            "executes_current": 9340,
            "executes_prev": 6225,
            "executes_var_pct": 50.0,
            "pending_current": 3171,
            "pending_prev": 1466,
            "pending_var_pct": 116.3,
            "completion_rate_pct": 74.7,
        },
        "indicators": [
            {
                "id": 1,
                "label": "Nombre d’installations PV",
                "unit": "sites",
                "month_current": 3211,
                "month_prev": 3642,
                "month_var": -12.0,
                "ytd_current": 9340,
                "ytd_prev": 6225,
                "ytd_var": 50.0,
                "since_2011": 144979,
            },
            {
                "id": 2,
                "label": "Puissance installée (MW)",
                "unit": "MW",
                "month_current": 11.8,
                "month_prev": 12.5,
                "month_var": -6.0,
                "ytd_current": 33.8,
                "ytd_prev": 22.4,
                "ytd_var": 51.0,
                "since_2011": 456.0,
            },
            {
                "id": 3,
                "label": "Production des IPV (GWh)",
                "unit": "GWh",
                "month_current": 62.0,
                "month_prev": 43.4,
                "month_var": 43.0,
                "ytd_current": 175.2,
                "ytd_prev": 122.1,
                "ytd_var": 43.0,
                "since_2011": 2358.3,
            },
            {
                "id": 4,
                "label": "Production STEG Évitée (GWh)",
                "unit": "GWh",
                "month_current": 74.4,
                "month_prev": 52.1,
                "month_var": 43.0,
                "ytd_current": 210.2,
                "ytd_prev": 146.6,
                "ytd_var": 43.0,
                "since_2011": 2830.0,
            },
            {
                "id": 5,
                "label": "Énergie Injectée dans le réseau (GWh)",
                "unit": "GWh",
                "month_current": 35.8,
                "month_prev": 22.4,
                "month_var": 60.0,
                "ytd_current": 113.9,
                "ytd_prev": 77.5,
                "ytd_var": 47.0,
                "since_2011": 1511.1,
            },
            {
                "id": 6,
                "label": "Combustible évité (ktep)",
                "unit": "ktep",
                "month_current": 14.5,
                "month_prev": 9.9,
                "month_var": 46.0,
                "ytd_current": 40.9,
                "ytd_prev": 27.8,
                "ytd_var": 47.0,
                "since_2011": 574.8,
            },
            {
                "id": 7,
                "label": "Coût du combustible évité (MDT)",
                "unit": "MDT",
                "month_current": 16.8,
                "month_prev": 13.2,
                "month_var": 28.0,
                "ytd_current": 47.6,
                "ytd_prev": 37.9,
                "ytd_var": 26.0,
                "since_2011": 635.2,
            },
            {
                "id": 8,
                "label": "Émissions de CO2 évitées (ktonne)",
                "unit": "ktonne",
                "month_current": 34.0,
                "month_prev": 23.3,
                "month_var": 46.0,
                "ytd_current": 96.2,
                "ytd_prev": 65.3,
                "ytd_var": 47.0,
                "since_2011": 1350.1,
            },
        ],
        "top_five_districts": [
            {"name": "BEN GUERDENE", "rate_2026": 98.2, "rate_2025": 97.5},
            {"name": "JENDOUBA", "rate_2026": 96.1, "rate_2025": 97.6},
            {"name": "MEDNINE", "rate_2026": 93.9, "rate_2025": 97.5},
            {"name": "BEJA", "rate_2026": 90.8, "rate_2025": 96.6},
            {"name": "MAHRES", "rate_2026": 90.8, "rate_2025": 96.4},
        ],
        "last_five_districts": [
            {"name": "TABARKA", "rate_2026": 0.0, "rate_2025": 55.6},
            {"name": "GABES NORD", "rate_2026": 47.8, "rate_2025": 55.6},
            {"name": "KEBILI", "rate_2026": 49.7, "rate_2025": 56.4},
            {"name": "TOZEUR", "rate_2026": 53.1, "rate_2025": 56.7},
            {"name": "HAMMAMET", "rate_2026": 54.6, "rate_2025": 59.5},
        ]
    }


def generate_html_prosol_report(output_path: str = None) -> str:
    """
    Generate an HTML report strictly styled like STEG's Tableau de Bord Programme Prosol.
    """
    data = get_prosol_summary_metrics("Mars 2026")
    dir_summary = direction_summary()

    html = f"""<!DOCTYPE html>
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
    <p>PROSOL ELECTRIQUE (PHOTOVOLTAÏQUE PV) &bull; ETAT : MARS 2026</p>
  </div>

  <!-- Key Topline KPIs -->
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-val">456.0 MWc</div>
      <div class="kpi-lbl">Puissance Installée Cumulée</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">144 979</div>
      <div class="kpi-lbl">Installations PV Raccordées</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">64.1%</div>
      <div class="kpi-lbl">Taux d'Injection Réseau (1 511 GWh)</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-val">635.2 MDT</div>
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
    for ind in data["indicators"]:
        m_var_cls = "pos" if ind["month_var"] >= 0 else "neg"
        y_var_cls = "pos" if ind["ytd_var"] >= 0 else "neg"
        html += f"""      <tr>
        <td><strong>{ind['label']}</strong></td>
        <td class="num">{ind['month_current']:,}</td>
        <td class="num">{ind['month_prev']:,}</td>
        <td class="num {m_var_cls}">{ind['month_var']:+.0f}%</td>
        <td class="num">{ind['ytd_current']:,}</td>
        <td class="num">{ind['ytd_prev']:,}</td>
        <td class="num {y_var_cls}">{ind['ytd_var']:+.0f}%</td>
        <td class="num"><strong>{ind['since_2011']:,}</strong></td>
      </tr>\n"""

    html += """    </tbody>
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
    for d_name, d_info in dir_summary.items():
        html += f"""      <tr>
        <td><strong>{d_name}</strong></td>
        <td class="num">{d_info['districts_count']}</td>
        <td class="num">{d_info['total_capacity_mwc']} MWc</td>
        <td class="num">{d_info['share_pct']}%</td>
        <td class="num">{d_info['pending_dossiers']:,}</td>
      </tr>\n"""

    html += f"""      <tr style="background:#e2e8f0; font-weight:bold;">
        <td>TOTAL NATIONAL</td>
        <td class="num">{len(STEG_DISTRICTS)}</td>
        <td class="num">{NATIONAL_ROOFTOP_PV_MWC:.1f} MWc</td>
        <td class="num">100.0%</td>
        <td class="num">{sum(d.pending_dossiers for d in STEG_DISTRICTS):,}</td>
      </tr>
    </tbody>
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
    for top in data["top_five_districts"]:
        html += f"""          <tr><td>{top['name']}</td><td class="num pos">{top['rate_2026']}%</td><td class="num">{top['rate_2025']}%</td></tr>\n"""

    html += """        </tbody>
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
    for last in data["last_five_districts"]:
        html += f"""          <tr><td>{last['name']}</td><td class="num neg">{last['rate_2026']}%</td><td class="num">{last['rate_2025']}%</td></tr>\n"""

    html += f"""        </tbody>
      </table>
    </div>
  </div>

  <div class="footer-note">
    <span>Généré par la Plateforme Nationale Intelligente de Prévision PV &bull; Algorithmes PréSol</span>
    <span>Date d'émission : {data['emission_date']} &bull; Source : Données réelles STEG DCD/DCM</span>
  </div>
</div>

</body>
</html>
"""
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

    return html


if __name__ == "__main__":
    out_file = os.path.join(os.path.dirname(__file__), "..", "results", "steg_prosol_mars_2026.html")
    generate_html_prosol_report(out_file)
    print(f"Generated official STEG Prosol report at: {os.path.abspath(out_file)}")
