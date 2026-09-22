"""
Reference data for Tunisia's 24 governorates.

DATA SOURCE UPDATE (this file was upgraded from a demographic proxy to
REAL data):
STEG's own "Tableau de Bord du Programme Prosol — Mars 2026" (provided
directly by STEG) publishes cumulative installed rooftop PV capacity
and pending-connection backlogs at the level of ~49 commercial
sub-districts (e.g. "TUNIS VILLE", "SFAX NORD", "MOKNINE"...), not at
governorate level directly. We aggregate those sub-districts up to our
24 governorates using standard delegation-to-governorate geography
(e.g. "EZZAHRA" + "MOUROUJ" -> Ben Arous governorate). The resulting
national total (455.7 MWc) matches STEG's own reported national total
(456.0 MWc) to within 0.3 MWc — the small gap reflects STEG's internal
regional bucketing, not an error in the governorate-level figures
below, which are built directly from their published sub-district data.

`pending_connections` is the cumulative number of PV connection
requests still "en instance" (not yet executed) since 2018, aggregated
the same way — a genuine backlog/grid-visibility metric STEG tracks,
not previously in this platform.

Dust/soiling loss remains an engineering estimate (STEG does not
publish this), documented below.
"""

from dataclasses import dataclass

# Real national cumulative rooftop PV capacity, "depuis 2011", per
# STEG's Tableau de Bord Programme Prosol, Mars 2026 (Section 4.3).
NATIONAL_ROOFTOP_PV_MWC = 456.0


@dataclass
class Governorate:
    name: str
    district: str          # STEG operational district grouping (demo grouping)
    lat: float
    lon: float
    population_k: float    # thousands, approx. — kept for reference, no longer used for capacity
    installed_capacity_mwc: float = 0.0  # REAL, from STEG Mars 2026 report
    pending_connections: int = 0         # REAL, cumulative "en instance" since 2018
    dust_loss_pct: float = 0.0           # engineering estimate — soiling loss, higher in the south/interior


# name, district, lat, lon, population_k, installed_capacity_mwc, pending_connections
# Capacity and pending-connections aggregated from STEG's 49 sub-district
# rows (Tableau de Bord Programme Prosol, Mars 2026, sections 4.4 and 7)
# via standard delegation → governorate mapping.
_RAW = [
    ("Tunis",        "Grand Tunis",  36.8065, 10.1815, 1056, 34.0, 559),   # Tunis Ville + Kram + Bardo
    ("Ariana",       "Grand Tunis",  36.8625, 10.1956, 621,  33.6, 242),   # Ariana + El Menzah
    ("Ben Arous",    "Grand Tunis",  36.7533, 10.2282, 674,  20.1, 292),   # Ezzahra + Mourouj
    ("Manouba",      "Grand Tunis",  36.8081, 10.0972, 402,  8.0,  49),
    ("Nabeul",       "Nord-Est",     36.4561, 10.7376, 858,  38.1, 894),   # Nabeul + M.B-Zelfa + M.Temime + Hammamet
    ("Zaghouan",     "Nord-Est",     36.4028, 10.1425, 176,  3.0,  111),
    ("Bizerte",      "Nord-Est",     37.2744, 9.8739,  568,  12.5, 61),    # Bizerte + Menzel Bourguiba
    ("Beja",         "Nord-Ouest",   36.7256, 9.1817,  303,  10.8, 21),
    ("Jendouba",     "Nord-Ouest",   36.5011, 8.7803,  401,  4.1,  9),     # Jendouba + Tabarka
    ("Le Kef",       "Nord-Ouest",   36.1826, 8.7148,  243,  3.8,  31),
    ("Siliana",      "Nord-Ouest",   36.0844, 9.3708,  223,  1.7,  55),
    ("Sousse",       "Centre-Est",   35.8256, 10.6369, 674,  37.2, 273),   # Sousse + Sousse Nord + Msaken + Enfidha
    ("Monastir",     "Centre-Est",   35.7643, 10.8113, 548,  38.9, 413),   # Monastir + Moknine
    ("Mahdia",       "Centre-Est",   35.5047, 11.0622, 410,  17.1, 188),   # Mahdia + El Jem
    ("Sfax",         "Centre-Est",   34.7406, 10.7603, 955,  99.0, 836),   # Sfax Ville+Nord+Sud + Jbeniana + Mahres
    ("Kairouan",     "Centre-Ouest", 35.6781, 10.0963, 570,  8.2,  114),   # Kairouan + Kairouan Nord
    ("Kasserine",    "Centre-Ouest", 35.1676, 8.8365,  439,  1.6,  20),    # Kasserine + Sbeitla
    ("Sidi Bouzid",  "Centre-Ouest", 35.0382, 9.4849,  429,  3.8,  46),    # Sidi Bouzid + Maknassy
    ("Gabes",        "Sud-Est",      33.8815, 10.0982, 374,  12.4, 360),   # Gabes + Gabes Nord
    ("Medenine",     "Sud-Est",      33.3399, 10.4956, 479,  42.6, 458),   # Medenine + Zarzis + Jerba + Ben Guerdane
    ("Tataouine",    "Sud-Est",      32.9297, 10.4518, 149,  6.9,  65),
    ("Gafsa",        "Sud-Ouest",    34.4250, 8.7842,  337,  4.4,  118),   # Gafsa + Metlaoui
    ("Tozeur",       "Sud-Ouest",    33.9197, 8.1335,  108,  4.6,  50),
    ("Kebili",       "Sud-Ouest",    33.7044, 8.9690,  156,  9.3,  210),
]

_total_pop = sum(r[4] for r in _RAW)

# Dust/soiling loss proxy: panels in Tunisia's arid south and interior
# accumulate more dust between cleanings than coastal/northern ones —
# a well-documented effect on real PV yield. This is a simple latitude
# + aridity based estimate (2-3% coastal north, up to 6% deep south),
# meant to be replaced by STEG/ANME's own soiling-loss studies if available.
_SOUTH_DISTRICTS = {"Sud-Est", "Sud-Ouest"}
_INTERIOR_DISTRICTS = {"Centre-Ouest"}

def _dust_loss_for(district: str) -> float:
    if district in _SOUTH_DISTRICTS:
        return 0.055
    if district in _INTERIOR_DISTRICTS:
        return 0.035
    return 0.02  # coastal / northern governorates

GOVERNORATES = [
    Governorate(
        name=r[0],
        district=r[1],
        lat=r[2],
        lon=r[3],
        population_k=r[4],
        installed_capacity_mwc=r[5],
        pending_connections=r[6],
        dust_loss_pct=_dust_loss_for(r[1]),
    )
    for r in _RAW
]

GOVERNORATE_BY_NAME = {g.name: g for g in GOVERNORATES}

DISTRICTS = sorted(set(g.district for g in GOVERNORATES))


def governorates_in_district(district: str):
    return [g for g in GOVERNORATES if g.district == district]


if __name__ == "__main__":
    for g in GOVERNORATES:
        print(f"{g.name:14s} {g.district:12s} cap={g.installed_capacity_mwc:6.2f} MWc  pending={g.pending_connections:4d}")
    print(f"\nTotal capacity: {sum(g.installed_capacity_mwc for g in GOVERNORATES):.1f} MWc  "
          f"(STEG reported: {NATIONAL_ROOFTOP_PV_MWC} MWc)")
    print(f"Total pending connections: {sum(g.pending_connections for g in GOVERNORATES)}  (STEG reported: 5475)")
    print(f"Districts: {DISTRICTS}")

