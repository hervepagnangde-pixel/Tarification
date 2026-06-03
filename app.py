import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import secrets as secrets_lib
from PIL import Image

import os
from datetime import datetime

# ════════════════════════════════════════════
# BASE DE DONNÉES — SQLite (local) OU PostgreSQL (Streamlit Cloud)
# ════════════════════════════════════════════
# Configurez DATABASE_URL dans les Secrets Streamlit pour PostgreSQL.
# Sans DATABASE_URL → SQLite local (/tmp/) utilisé automatiquement.

def _get_db_url():
    """Lit DATABASE_URL depuis st.secrets à chaque appel."""
    url = None
    try:
        # Streamlit Cloud secrets
        url = st.secrets.get("DATABASE_URL")
    except Exception:
        pass
    if not url:
        # Fallback env variable
        url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    # Accepte "postgres://" ET "postgresql://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url if url.startswith("postgresql://") else None

def _get_conn():
    """Retourne une connexion SQLite ou PostgreSQL selon la config."""
    url = _get_db_url()
    if url:
        import psycopg2
        return psycopg2.connect(url), "pg"
    import sqlite3
    _DB_PATH = os.environ.get("ATLANTICRE_DB", "/tmp/atlanticre_sessions.db")
    return sqlite3.connect(_DB_PATH), "sqlite"

def _ph(n=1):
    """Placeholder SQL : %s pour PostgreSQL, ? pour SQLite."""
    url = _get_db_url()
    if url: return ",".join(["%s"]*n) if n>1 else "%s"
    return ",".join(["?"]*n) if n>1 else "?"

def db_init():
    """Crée les tables si elles n'existent pas."""
    con, db = _get_conn()
    cur = con.cursor()
    if db == "pg":
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          SERIAL PRIMARY KEY,
                user_email  TEXT NOT NULL,
                nom_session TEXT,
                gnpi        FLOAT,
                programme   TEXT,
                created_at  TIMESTAMP DEFAULT NOW(),
                updated_at  TIMESTAMP DEFAULT NOW()
            )""")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resultats (
                id         SERIAL PRIMARY KEY,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                etape      TEXT,
                data_json  TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )""")
    else:
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_email  TEXT NOT NULL,
                nom_session TEXT,
                gnpi        REAL,
                programme   TEXT,
                created_at  TEXT DEFAULT (datetime('now','localtime')),
                updated_at  TEXT DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS resultats (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER REFERENCES sessions(id) ON DELETE CASCADE,
                etape      TEXT,
                data_json  TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );""")
    con.commit(); con.close()

def db_save_session(user_email, gnpi_val, tranches, nom=None):
    db_init()
    import json
    sid = st.session_state.get("db_session_id")
    prog_json = json.dumps(tranches, default=str)
    con, db = _get_conn(); cur = con.cursor()
    p = _ph()
    if sid:
        if db == "pg":
            cur.execute(f"UPDATE sessions SET gnpi={p},programme={p},updated_at=NOW() WHERE id={p}",
                        (gnpi_val, prog_json, sid))
        else:
            cur.execute(f"UPDATE sessions SET gnpi={p},programme={p},updated_at=datetime('now','localtime') WHERE id={p}",
                        (gnpi_val, prog_json, sid))
    else:
        nom_auto = nom or f"Session {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        if db == "pg":
            cur.execute(f"INSERT INTO sessions (user_email,gnpi,programme,nom_session) VALUES ({_ph(4)}) RETURNING id",
                        (user_email, gnpi_val, prog_json, nom_auto))
            sid = cur.fetchone()[0]
        else:
            cur.execute(f"INSERT INTO sessions (user_email,gnpi,programme,nom_session) VALUES ({_ph(4)})",
                        (user_email, gnpi_val, prog_json, nom_auto))
            sid = cur.lastrowid
        st.session_state["db_session_id"] = sid
    con.commit(); con.close()
    return sid

def db_save_etape(etape, data):
    db_init()
    import json
    sid = st.session_state.get("db_session_id")
    if not sid: return
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    # Vérifie que la session existe dans CETTE base (SQLite → PG peut diverger)
    cur.execute(f"SELECT id FROM sessions WHERE id={p}", (sid,))
    if not cur.fetchone():
        # Session introuvable → réinitialise et crée une nouvelle
        st.session_state.pop("db_session_id", None)
        con.close()
        return  # sera recréée au prochain db_save_session
    cur.execute(f"DELETE FROM resultats WHERE session_id={p} AND etape={p}", (sid, etape))
    cur.execute(f"INSERT INTO resultats (session_id,etape,data_json) VALUES ({_ph(3)})",
                (sid, etape, json.dumps(data, default=str)))
    con.commit(); con.close()

def db_load_session(session_id):
    db_init()
    import json, pandas as pd
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"SELECT etape,data_json FROM resultats WHERE session_id={p}", (session_id,))
    rows = cur.fetchall()
    cur.execute(f"SELECT gnpi,programme,nom_session FROM sessions WHERE id={p}", (session_id,))
    sess = cur.fetchone(); con.close()
    if not sess: return None
    st.session_state["db_session_id"] = session_id
    for etape, data_json in rows:
        d = json.loads(data_json)
        if etape == "bc":   st.session_state["resultats_bc"] = d
        elif etape == "sim":st.session_state["resultats_sim"] = d
        elif etape == "mkt":
            st.session_state["resultats_mkt"]  = d.get("resultats_mkt",[])
            st.session_state["taux_mkt_final"] = d.get("taux_mkt_final",[])
        elif etape == "rapport":
            rows_r = d.get("rows",[])
            if rows_r:
                st.session_state["df_rapport"]   = pd.DataFrame(rows_r)
                st.session_state["prime_totale"] = d.get("prime_totale", 0)
    return sess[2] or f"Session #{session_id}"

def db_list_sessions(user_email):
    db_init()
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"""SELECT id,nom_session,gnpi,
        {"to_char(created_at,'DD/MM/YYYY HH24:MI')" if db=="pg" else "created_at"},
        {"to_char(updated_at,'DD/MM/YYYY HH24:MI')" if db=="pg" else "updated_at"}
        FROM sessions WHERE user_email={p} ORDER BY updated_at DESC LIMIT 50""",
        (user_email,))
    rows = cur.fetchall(); con.close()
    return rows

def db_delete_session(session_id):
    db_init()
    con, _ = _get_conn(); p = _ph()
    con.execute(f"DELETE FROM sessions WHERE id={p}", (session_id,))
    con.commit(); con.close()

def db_get_previous_session(user_email, current_id):
    db_init()
    import json
    con, db = _get_conn(); cur = con.cursor(); p = _ph()
    cur.execute(f"""SELECT id FROM sessions WHERE user_email={p} AND id!={p}
        ORDER BY updated_at DESC LIMIT 1""", (user_email, current_id or 0))
    row = cur.fetchone()
    if not row: con.close(); return None
    cur.execute(f"SELECT data_json FROM resultats WHERE session_id={p} AND etape='rapport'", (row[0],))
    rr = cur.fetchone(); con.close()
    if rr: return json.loads(rr[0]).get("rows",[])
    return None

# ════════════════════════════════════════════
# GENERATION PDF PROFESSIONNEL
# ════════════════════════════════════════════
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, PageBreak, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import io as _io_db

_VERT  = colors.HexColor("#2d8a4e")
_NOIR  = colors.HexColor("#1a1a1a")
_GRIS  = colors.HexColor("#f4f6f4")
_GRIS2 = colors.HexColor("#888888")

def _pdf_styles():
    s = getSampleStyleSheet()
    for nm, kwargs in [
        ("AR_Title",  dict(fontName="Helvetica-Bold", fontSize=26, textColor=_NOIR,   spaceAfter=6,  alignment=TA_CENTER)),
        ("AR_Sub",    dict(fontName="Helvetica",      fontSize=12, textColor=_GRIS2,  spaceAfter=4,  alignment=TA_CENTER)),
        ("AR_H1",     dict(fontName="Helvetica-Bold", fontSize=14, textColor=_VERT,   spaceBefore=14,spaceAfter=6)),
        ("AR_H2",     dict(fontName="Helvetica-Bold", fontSize=10, textColor=_NOIR,   spaceBefore=8, spaceAfter=3)),
        ("AR_Body",   dict(fontName="Helvetica",      fontSize=9,  leading=14,        textColor=_NOIR,spaceAfter=4)),
        ("AR_Caption",dict(fontName="Helvetica-Oblique",fontSize=8,textColor=_GRIS2,  spaceAfter=8)),
        ("AR_Cell",   dict(fontName="Helvetica",      fontSize=8,  leading=11,        textColor=_NOIR)),
        ("AR_CellB",  dict(fontName="Helvetica-Bold", fontSize=8,  leading=11,        textColor=_NOIR)),
    ]:
        if nm not in s.byName:
            kwargs.pop("alignment", None)
            s.add(ParagraphStyle(nm, parent=s["Normal"], **kwargs))
    return s

def _pdf_table_rl(data_rows, col_widths=None):
    S = _pdf_styles()
    rows = []
    for i, row in enumerate(data_rows):
        r = []
        for cell in row:
            sty = S["AR_CellB"] if i == 0 else S["AR_Cell"]
            r.append(Paragraph(str(cell), sty))
        rows.append(r)
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),  (-1,0),  _NOIR),
        ("TEXTCOLOR",     (0,0),  (-1,0),  colors.white),
        ("ROWBACKGROUNDS",(0,1),  (-1,-1), [colors.white, _GRIS]),
        ("GRID",          (0,0),  (-1,-1), 0.3, colors.HexColor("#e0e0e0")),
        ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0),  (-1,-1), 4),
        ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
        ("LEFTPADDING",   (0,0),  (-1,-1), 5),
    ]))
    return t

def generer_pdf_rapport(user_email, gnpi_val, tranches,
                         resultats_bc, resultats_sim, taux_mkt_final,
                         df_rapport, prime_totale,
                         analyse_claude="", annee=2026):
    buf = _io_db.BytesIO()
    S   = _pdf_styles()
    W, H = A4
    m   = 1.8*cm
    doc = SimpleDocTemplate(buf, pagesize=A4,
          leftMargin=m, rightMargin=m, topMargin=1.5*cm, bottomMargin=1.5*cm,
          title=f"Rapport Tarification Atlantic Re {annee}")
    story = []
    PW = W - 2*m

    # ── COUVERTURE ──
    story += [Spacer(1, 1.5*cm),
              Paragraph("ATLANTIC RE", ParagraphStyle("T", parent=S["Normal"],
                  fontName="Helvetica-Bold", fontSize=32, textColor=_NOIR, alignment=1,
                  spaceAfter=6)),
              Paragraph(f"Rapport de Tarification {annee}", ParagraphStyle("S",
                  parent=S["Normal"], fontName="Helvetica", fontSize=14,
                  textColor=_GRIS2, alignment=1, spaceAfter=4)),
              Paragraph("Reassurance Non-Proportionnelle · Automobile · Maroc",
                  ParagraphStyle("S2", parent=S["Normal"], fontName="Helvetica",
                  fontSize=10, textColor=_GRIS2, alignment=1, spaceAfter=16)),
              HRFlowable(width=PW, thickness=2, color=_VERT),
              Spacer(1, 0.6*cm)]

    cv = [["GNPI", f"{gnpi_val:,.0f} MAD"],
          ["Prime totale", f"{prime_totale:,.0f} MAD"],
          ["Taux global", f"{prime_totale/gnpi_val:.4%}" if gnpi_val else "-"],
          ["Tranches", str(len(tranches))],
          ["Date", datetime.now().strftime("%d/%m/%Y %H:%M")],
          ["Prepare par", "Atlantic Re IA - Agent Actuariel"]]
    story.append(_pdf_table_rl([["Indicateur","Valeur"]]+cv, [PW*0.45, PW*0.55]))
    story.append(PageBreak())

    # ── 1. PROGRAMME ──
    story += [Paragraph("1. Programme de Reassurance", S["AR_H1"]),
              HRFlowable(width=PW, thickness=1, color=_VERT), Spacer(1, 0.3*cm)]
    ph = ["Tranche","Type","Priorite (MAD)","Portee (MAD)","Reconst.","Brokage","Frais","Marge"]
    pr = [[t.get("nom",""), t.get("type",""), f"{t.get('priorite',0):,.0f}",
           f"{t.get('portee',0):,.0f}",
           f"{t.get('nb_reconstitutions',1)}x{t.get('taux_reconstitution',100):.0f}%",
           f"{t.get('brokage',0):.0%}", f"{t.get('frais',0):.0%}", f"{t.get('marge',0):.0%}"]
          for t in tranches]
    story.append(_pdf_table_rl([ph]+pr,
        [PW*0.16,PW*0.13,PW*0.13,PW*0.12,PW*0.12,PW*0.10,PW*0.10,PW*0.10]))
    story.append(Spacer(1, 0.4*cm))

    # ── 2. BURNING COST ──
    if resultats_bc:
        story += [Paragraph("2. Burning Cost", S["AR_H1"]),
                  HRFlowable(width=PW, thickness=1, color=_VERT), Spacer(1, 0.3*cm),
                  Paragraph("Ck = min(max(S'k - D, 0), L) x coeff_stab | "
                             "R1: tau_risque = tau_pur + sigma_hist x 20% | "
                             "R2: tau_BC=0 si annees non-nulles < 3 | "
                             "tau_tech = tau_risque x (1-Rec) / (1-BK-FG-Marge-Retro)", S["AR_Caption"])]
        bh = ["Tranche","Type","Charge moy.","Rec","Taux pur","Taux risque","Taux tech.","Charg. majeurs"]
        br = [[r.get("tranche",""), r.get("type",""),
               f"{r.get('charge_moy', r.get('charge_moy_MAD',0)):,.0f}",
               f"{r.get('Rec',0):.4%}", f"{r.get('taux_pur',0):.4%}",
               f"{r.get('taux_risque',0):.4%}", f"{r.get('taux_technique',0):.4%}",
               f"{r.get('chargement_majeurs',0):.4%}"] for r in resultats_bc]
        story.append(_pdf_table_rl([bh]+br,
            [PW*0.18,PW*0.12,PW*0.14,PW*0.10,PW*0.11,PW*0.11,PW*0.12,PW*0.12]))
        story.append(Spacer(1, 0.4*cm))

    # ── 3. SIMULATION ──
    if resultats_sim:
        story += [Paragraph("3. Simulation Pareto / Poisson", S["AR_H1"]),
                  HRFlowable(width=PW, thickness=1, color=_VERT), Spacer(1, 0.3*cm)]
        sh = ["Tranche","Taux pur","Taux risque","Taux tech.","Charg. majeurs","Sans AAL","Sans AAD","Sans reconst."]
        sr = [[r.get("tranche",""), f"{r.get('taux_pur',0):.4%}", f"{r.get('taux_risque',0):.4%}",
               f"{r.get('taux_technique',0):.4%}", f"{r.get('chargement_majeurs',0):.4%}",
               f"{r.get('sans_aal',0):.4%}", f"{r.get('sans_aad',0):.4%}",
               f"{r.get('sans_rec',0):.4%}"] for r in resultats_sim]
        story.append(_pdf_table_rl([sh]+sr,
            [PW*0.17,PW*0.11,PW*0.12,PW*0.11,PW*0.11,PW*0.10,PW*0.10,PW*0.14]))
        story.append(Spacer(1, 0.4*cm))

    # ── 4. MARKET CURVE ──
    if taux_mkt_final:
        story += [Paragraph("4. Market Curve  ROL = a x x^(-b)", S["AR_H1"]),
                  HRFlowable(width=PW, thickness=1, color=_VERT), Spacer(1, 0.3*cm)]
        mh = ["Tranche","Type","x=(D+C/2)/GNPI","ROL","Taux pur","Taux tech.","Taux final"]
        mr = [[t.get("tranche",""), t.get("type",""), f"{t.get('x_norm',0):.5f}",
               f"{t.get('rol',0):.4%}", f"{t.get('taux_pur',0):.4%}",
               f"{t.get('taux_tech',0):.4%}", f"{t.get('taux',0):.4%}"]
              for t in taux_mkt_final]
        story.append(_pdf_table_rl([mh]+mr,
            [PW*0.17,PW*0.12,PW*0.16,PW*0.11,PW*0.11,PW*0.11,PW*0.12]))
        story.append(Spacer(1, 0.4*cm))

    # ── 5. SYNTHESE FINALE ──
    story += [PageBreak(),
              Paragraph("5. Synthese de Tarification", S["AR_H1"]),
              HRFlowable(width=PW, thickness=2, color=_VERT), Spacer(1, 0.3*cm)]

    if df_rapport is not None and not df_rapport.empty:
        cols = list(df_rapport.columns)
        drows = [cols] + [list(map(str, r)) for r in df_rapport.values.tolist()]
        cw = PW / len(cols)
        story.append(_pdf_table_rl(drows, [cw]*len(cols)))
        story.append(Spacer(1, 0.4*cm))

    story.append(_pdf_table_rl(
        [["Indicateur","Valeur"],
         ["Prime totale", f"{prime_totale:,.0f} MAD"],
         ["Taux global",  f"{prime_totale/gnpi_val:.4%}" if gnpi_val else "-"],
         ["GNPI",         f"{gnpi_val:,.0f} MAD"]],
        [PW*0.45, PW*0.55]))

    # ── 6. ANALYSE CLAUDE ──
    if analyse_claude and len(analyse_claude.strip()) > 10:
        story += [PageBreak(),
                  Paragraph("6. Analyse Claude - Recommandations", S["AR_H1"]),
                  HRFlowable(width=PW, thickness=1, color=_VERT), Spacer(1, 0.3*cm)]
        for line in analyse_claude.split("\n"):
            line = line.strip()
            if not line: story.append(Spacer(1, 0.15*cm)); continue
            line_c = line.replace("**","").replace("*","").replace("`","").replace("#","")
            if line.startswith("## "): story.append(Paragraph(line[3:], S["AR_H2"]))
            elif line.startswith("# "): story.append(Paragraph(line[2:], S["AR_H1"]))
            else: story.append(Paragraph(line_c, S["AR_Body"]))

    # ── FOOTER ──
    story += [Spacer(1, 0.8*cm),
              HRFlowable(width=PW, thickness=0.5, color=_GRIS2),
              Spacer(1, 0.2*cm),
              Paragraph(f"Document genere par Atlantic Re IA - Agent Actuariel Autonome | "
                        f"Atlantic Re {annee} | {datetime.now().strftime('%d/%m/%Y %H:%M')} | Confidentiel",
                        S["AR_Caption"])]

    doc.build(story)
    return buf.getvalue()


def _json_safe(obj):
    """Convertit les types numpy non-sérialisables en types Python natifs"""
    if isinstance(obj, dict):  return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_json_safe(v) for v in obj]
    if isinstance(obj, np.bool_):   return bool(obj)
    if isinstance(obj, np.integer): return int(obj)
    if isinstance(obj, np.floating):return float(obj)
    if isinstance(obj, np.ndarray): return obj.tolist()
    return obj



# ════════════════════════════════════════════
# MODULE OPTIMISATION PROGRAMME — 3 VARIANTES
# ════════════════════════════════════════════

def optimiser_programme_variantes(tranches, gnpi_val, resultats_sim, resultats_bc, taux_mkt_final):
    """Génère 3 variantes de programme optimal (A=cédante, B=réassureur, C=équilibre)."""
    from scipy.optimize import minimize
    import numpy as np

    def taux_sim_pour_tranche(idx, portee_new, priorite_new, aal_new, aad_new, nb_recon_new):
        """Estime le taux technique pour des paramètres modifiés (interpolation linéaire)."""
        if idx >= len(resultats_sim): return 0.0
        r = resultats_sim[idx]
        base = r.get("taux_technique", 0)
        # Sensibilités approximatives
        t_orig = tranches[idx]
        ratio_portee   = portee_new   / max(t_orig["portee"],   1)
        ratio_priorite = priorite_new / max(t_orig["priorite"], 1)
        # Taux varie ~ sqrt(portee) et ~ 1/priorite^0.5 (approximation log-log)
        adj = (ratio_portee ** 0.5) / (ratio_priorite ** 0.3)
        # Chargement AAL / reconstitutions
        r_sans_aal = r.get("sans_aal", base); r_sans_rec = r.get("sans_rec", base)
        adj_aal = 0.0 if aal_new > 0 else (r_sans_aal - base)
        adj_rec = (nb_recon_new / max(t_orig["nb_reconstitutions"], 1) - 1) * (r_sans_rec - base) * 0.5
        return max(base * adj + adj_aal + adj_rec, 0)

    base_tranches = [dict(t) for t in tranches]
    resultats_variantes = {}

    for perspective in ["cedante", "reassureur", "equilibre"]:
        variante_tranches = []
        for i, t in enumerate(base_tranches):
            t_var = dict(t)
            if perspective == "cedante":
                # Maximiser protection : élargir portée, baisser priorité, plus de reconstitutions
                t_var["portee"]             = round(t["portee"] * 1.15 / 500_000) * 500_000
                t_var["priorite"]           = round(t["priorite"] * 0.90 / 500_000) * 500_000
                t_var["nb_reconstitutions"] = min(t["nb_reconstitutions"] + 1, 3)
                if t["type"] == "travaillante":
                    t_var["AAL"]            = round(t_var["portee"] * 2.0 / 100_000) * 100_000
                    t_var["AAD"]            = round(t.get("AAD", 0) * 0.80 / 100_000) * 100_000 if t.get("AAD") else None
            elif perspective == "reassureur":
                # Maximiser rendement : réduire portée, augmenter priorité, moins de reconstitutions
                t_var["portee"]             = round(t["portee"] * 0.85 / 500_000) * 500_000
                t_var["priorite"]           = round(t["priorite"] * 1.10 / 500_000) * 500_000
                t_var["nb_reconstitutions"] = max(t["nb_reconstitutions"] - 1, 1)
                if t["type"] == "travaillante":
                    t_var["AAL"]            = round(t_var["portee"] * 1.5 / 100_000) * 100_000
                    t_var["AAD"]            = round((t.get("AAD", 0) or t["portee"]*0.3) * 1.20 / 100_000) * 100_000
            else:  # equilibre
                # Compromis : légère optimisation des deux côtés
                t_var["portee"]             = t["portee"]
                t_var["priorite"]           = t["priorite"]
                t_var["nb_reconstitutions"] = t["nb_reconstitutions"]
                if t["type"] == "travaillante" and t.get("AAL"):
                    t_var["AAL"] = round(t["AAL"] * 1.05 / 100_000) * 100_000

            # Garantir valeurs minimales
            t_var["portee"]   = max(t_var["portee"],   1_000_000)
            t_var["priorite"] = max(t_var["priorite"], 500_000)
            variante_tranches.append(t_var)

        # Calculer prime estimée pour cette variante
        prime_v = 0.0
        taux_v  = []
        for i, t_var in enumerate(variante_tranches):
            tt = taux_sim_pour_tranche(i,
                t_var["portee"], t_var["priorite"],
                t_var.get("AAL", 0) or 0,
                t_var.get("AAD", 0) or 0,
                t_var["nb_reconstitutions"])
            prime_v += gnpi_val * tt
            taux_v.append(tt)

        resultats_variantes[perspective] = {
            "tranches":    variante_tranches,
            "taux":        taux_v,
            "prime":       prime_v,
            "taux_global": prime_v / gnpi_val if gnpi_val else 0,
        }

    return resultats_variantes


def afficher_variantes_optimisation(variantes, gnpi_val, tranches_ref):
    """Affiche les 3 variantes dans Tab6."""
    st.markdown("---")
    st.markdown("""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d2d2d 100%);
        border-radius:12px;padding:20px 24px;margin-bottom:20px">
        <div style="font-size:18px;font-weight:700;color:white">⚡ Optimisation du Programme — 3 Variantes</div>
        <div style="font-size:13px;color:#aaa;margin-top:4px">
        En tant que leader (Partner Re) : propositions structurées pour la négociation
        </div></div>""", unsafe_allow_html=True)

    cols = st.columns(3)
    configs = [
        ("cedante",    "💼 Variante A", "Avantage Cédante",    "#3b82f6", "Maximise la protection — portée +15%, priorité -10%, reconstitutions +1"),
        ("reassureur", "📈 Variante B", "Avantage Réassureur", "#ef4444", "Maximise le rendement — portée -15%, priorité +10%, AAD renforcé"),
        ("equilibre",  "⚖️ Variante C", "Programme Équilibré", "#2d8a4e", "Compromis optimal — proposition de négociation finale Partner Re"),
    ]

    for col, (key, label, subtitle, color, desc) in zip(cols, configs):
        v = variantes.get(key, {}); t_list = v.get("tranches", [])
        prime = v.get("prime", 0); taux_g = v.get("taux_global", 0)
        with col:
            st.markdown(f"""<div style="background:white;border-radius:12px;padding:16px;
                border-top:4px solid {color};box-shadow:0 2px 8px rgba(0,0,0,0.08);margin-bottom:12px">
                <div style="font-size:15px;font-weight:700;color:{color}">{label}</div>
                <div style="font-size:12px;font-weight:600;color:#333;margin:4px 0">{subtitle}</div>
                <div style="font-size:11px;color:#666;margin-bottom:12px">{desc}</div>
                <div style="font-size:20px;font-weight:700;color:#1a1a1a">{prime:,.0f} MAD</div>
                <div style="font-size:12px;color:#888">Taux global : {taux_g:.4%}</div>
                </div>""", unsafe_allow_html=True)
            if t_list:
                rows_v = []
                for i, t_v in enumerate(t_list):
                    t_ref = tranches_ref[i] if i < len(tranches_ref) else {}
                    delta_p = t_v["portee"] - t_ref.get("portee", t_v["portee"])
                    delta_d = t_v["priorite"] - t_ref.get("priorite", t_v["priorite"])
                    rows_v.append({
                        "Tranche": t_v["nom"],
                        "Portée": f"{t_v['portee']/1e6:.0f}M {'↑' if delta_p>0 else '↓' if delta_p<0 else '='}",
                        "Priorité": f"{t_v['priorite']/1e6:.0f}M {'↑' if delta_d>0 else '↓' if delta_d<0 else '='}",
                        "Reconst.": f"{t_v['nb_reconstitutions']}x100%",
                        "AAL": f"{(t_v.get('AAL') or 0)/1e6:.0f}M" if t_v.get("AAL") else "—",
                    })
                tableau_resultats(rows_v)

    # Tableau comparatif
    st.markdown("### 📊 Comparaison des 3 variantes vs Programme actuel")
    prime_base = sum(gnpi_val * v.get("taux",[0])[i] if i < len(v.get("taux",[])) else 0
                     for i in range(len(tranches_ref))
                     for kk, v in variantes.items() if kk == "equilibre") or 0
    rows_comp = []
    prime_actuelle = None
    for key, label, *_ in configs:
        v = variantes.get(key, {})
        prime_v = v.get("prime", 0)
        if prime_actuelle is None: prime_actuelle = prime_v
        rows_comp.append({
            "Variante": label.replace("💼 ","").replace("📈 ","").replace("⚖️ ",""),
            "Prime estimée": f"{prime_v:,.0f} MAD",
            "Taux global": f"{v.get('taux_global',0):.4%}",
            "Écart vs équilibre": f"{(prime_v - variantes.get('equilibre',{}).get('prime',prime_v))/gnpi_val*100:+.2f} pts",
            "Recommandation": "⬆️ Protège la cédante" if key=="cedante" else "⬇️ Protège le réassureur" if key=="reassureur" else "✅ Proposition finale"
        })
    tableau_resultats(rows_comp)
    st.info("💡 En tant que leader Partner Re : proposer la Variante C comme base de négociation, avec la Variante B comme position de repli en cas de sinistralité élevée.")


def afficher_panneau_audit(tranches, resultats_bc, resultats_sim, taux_mkt_final,
                            df_rapport, prime_totale, gnpi_val):
    """Panneau de transparence pour managers — explicabilité complète."""
    st.markdown("---")
    with st.expander("🔍 Panneau Transparence & Audit — Pour la direction", expanded=False):
        st.markdown("""<div style="background:rgba(59,130,246,0.08);border-left:4px solid #3b82f6;
            border-radius:0 8px 8px 0;padding:14px 18px;margin-bottom:16px">
            <b style="color:#3b82f6">Ce panneau est destiné au comité de direction.</b><br>
            Il montre comment chaque chiffre a été calculé, quelles règles ont été appliquées,
            et où se trouvent les zones d'incertitude. L'actuaire reste décisionnaire.
            </div>""", unsafe_allow_html=True)

        st.markdown("#### 1️⃣ Règles actuarielles appliquées")
        regles = []
        for r in resultats_bc:
            n_nz = r.get("n_ann_nonzero", 0)
            sigma = r.get("sigma_hist", 0)
            regle = "R2 — BC=0 (< 3 ans non nuls)" if n_nz < 3 else f"R1 — τ_risque = τ_pur + σ ({sigma:.4%}) × 20%"
            statut = "⚠️ Données insuffisantes" if n_nz < 3 else "✅ Données suffisantes"
            regles.append({
                "Tranche": r["tranche"], "Type": r["type"],
                "Années non-nulles": f"{n_nz}",
                "σ historique": f"{sigma:.4%}",
                "Règle appliquée": regle,
                "Statut": statut,
            })
        tableau_resultats(regles)

        st.markdown("#### 2️⃣ Comparaison des 3 méthodes")
        comp_m = []
        for i, t in enumerate(tranches):
            nom = t["nom"]
            bc_t = next((r.get("taux_technique",0) for r in resultats_bc if r["tranche"]==nom), 0)
            si_t = next((r.get("taux_technique",0) for r in resultats_sim if r["tranche"]==nom), 0)
            mk_t = next((r.get("taux",0) for r in taux_mkt_final if r["tranche"]==nom), 0) if t["type"]!="travaillante" else None
            rpt  = df_rapport[df_rapport["Tranche"]==nom].iloc[0] if not df_rapport.empty and nom in df_rapport["Tranche"].values else {}
            retenu = rpt.get("Taux retenu","—") if hasattr(rpt,"get") else "—"
            comp_m.append({
                "Tranche": nom, "Type": t["type"],
                "BC": f"{bc_t:.4%}" if bc_t else "0% (R2)",
                "Simulation": f"{si_t:.4%}",
                "Market curve": f"{mk_t:.4%}" if mk_t is not None else "N/A (trav.)",
                "Taux retenu": retenu if isinstance(retenu,str) else f"{retenu:.4%}",
                "Logique": f"max(BC,Sim)" if t["type"]=="travaillante" else "max(Sim,Mkt)",
            })
        tableau_resultats(comp_m)

        st.markdown("#### 3️⃣ Piste d'audit — Décisions de l'agent")
        st.markdown(f"""<div style="background:#f9fafb;border-radius:8px;padding:14px;font-size:12px;
            font-family:monospace;border:1px solid #e0e0e0">
            📅 Date : {datetime.now().strftime("%d/%m/%Y %H:%M")} |
            GNPI : {gnpi_val:,} MAD |
            Prime totale : {prime_totale:,.0f} MAD |
            Taux global : {prime_totale/gnpi_val:.4%} |
            Tranches : {len(tranches)}<br>
            Formule τ_risque : τ_pur + σ_hist × 20% (CAS actuarial standards)<br>
            Règle R2 : BC = 0 si années non-nulles < 3<br>
            Market curve : cat uniquement (R² ≥ 0.45)<br>
            Sélection finale : max(BC, Sim) trav. | max(Sim, Mkt) cat
            </div>""", unsafe_allow_html=True)

        st.markdown("#### 4️⃣ Questions fréquentes managers")
        with st.expander("❓ Pourquoi le BC de certaines tranches cat est à 0 ?"):
            st.markdown("Parce que la règle actuarielle R2 interdit d'extrapoler à partir de moins de 3 années de sinistralité observée. Ce n'est pas une erreur — c'est une règle de prudence qui évite de construire une tarification sur des données insuffisantes.")
        with st.expander("❓ Comment vérifier les calculs ?"):
            st.markdown("Chaque calcul intermédiaire est affiché dans les onglets BC, Simulation et Market Curve. Les formules sont codées explicitement — il n'y a pas d'algorithme opaque.")
        with st.expander("❓ L'IA peut-elle se tromper ?"):
            st.markdown("Oui, comme tout outil de calcul. C'est pourquoi l'actuaire vérifie les résultats intermédiaires avant validation. L'avantage de cet outil : chaque hypothèse est documentée et traçable, contrairement à un fichier Excel.")
        with st.expander("❓ Qui est responsable du taux final ?"):
            st.markdown("L'actuaire qui valide le rapport. L'IA propose, l'actuaire décide. Le bouton 'Générer le rapport' est un acte de validation explicite.")

def _lookup_taux(results_list, nom, idx, key="taux_technique"):
    """Lookup par nom de tranche. Fallback par index si nom introuvable."""
    # Recherche par nom exact
    for r in results_list:
        if r.get("tranche","") == nom:
            return r.get(key, 0)
    # Fallback par index
    if idx < len(results_list):
        return results_list[idx].get(key, 0)
    return 0

def _lookup_result(results_list, nom, idx):
    """Retourne le dict complet par nom puis par index."""
    for r in results_list:
        if r.get("tranche","") == nom:
            return r
    if idx < len(results_list):
        return results_list[idx]
    return {}

# ════════════════════════════════════════════
# SET PAGE CONFIG — UNE SEULE FOIS EN HAUT
# ════════════════════════════════════════════
try:
    icon = Image.open("icon.png")
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon="🎯")

# ════════════════════════════════════════════
# ACCESS CONTROL
# ════════════════════════════════════════════

def get_admin_password():
    try: return st.secrets["admin_password"]
    except: return "Admin@AtlanticRe2026"

def get_users():
    try: return dict(st.secrets["users"])
    except: return {"demo@atlanticre.ia": "DEMO2026"}

def check_access(email, code):
    return get_users().get(email.lower().strip()) == code.strip()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #1a1a1a 0%, #2d8a4e 100%); }
    .stButton > button { background-color: #1a1a1a; color: white; border: 2px solid #2d8a4e; border-radius: 8px; padding: 8px 20px; font-weight: 600; }
    .stButton > button:hover { background-color: #2d8a4e; }
    </style>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("<div style='text-align:center; padding:40px 0 20px 0'>", unsafe_allow_html=True)
        st.markdown("# 🎯")
        st.markdown("### Atlantic Re IA")
        st.caption("Tarification Réassurance Non-Proportionnelle")
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()
        email = st.text_input("📧 Adresse email", placeholder="votre@email.com", key="login_email")
        code  = st.text_input("🔑 Code d'accès", type="password", placeholder="CODE123", key="login_code")
        if st.button("Se connecter", type="primary", use_container_width=True):
            if check_access(email, code):
                st.session_state["authenticated"] = True
                st.session_state["user_email"]    = email
                st.rerun()
            else:
                st.error("❌ Email ou code d'accès incorrect")
        st.caption("Accès réservé. Contactez l'administrateur.")
    st.stop()

# ════════════════════════════════════════════
# LANDING PAGE
# ════════════════════════════════════════════

if "page" not in st.session_state:
    st.session_state["page"] = "landing"
    # Auto-init DB
    try: db_init()
    except: pass

if st.session_state["page"] == "landing":
    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0d0d0d 0%, #1a1a1a 50%, #0d2b1a 100%) !important; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
        min-height:85vh;text-align:center;padding:40px 20px">
        <div style="width:160px;height:160px;margin-bottom:32px">
            <svg viewBox="0 0 160 160" xmlns="http://www.w3.org/2000/svg">
                <circle cx="80" cy="80" r="75" fill="none" stroke="#2d8a4e" stroke-width="2" opacity="0.3"/>
                <circle cx="80" cy="80" r="65" fill="none" stroke="#2d8a4e" stroke-width="1" opacity="0.2"/>
                <circle cx="80" cy="80" r="55" fill="#1a1a1a" stroke="#2d8a4e" stroke-width="2"/>
                <circle cx="80" cy="75" r="32" fill="#2d2d2d"/>
                <circle cx="68" cy="70" r="6" fill="#2d8a4e"/>
                <circle cx="92" cy="70" r="6" fill="#2d8a4e"/>
                <circle cx="70" cy="69" r="2" fill="white"/>
                <circle cx="94" cy="69" r="2" fill="white"/>
                <path d="M 67 83 Q 80 93 93 83" stroke="#2d8a4e" stroke-width="2.5" fill="none" stroke-linecap="round"/>
                <line x1="80" y1="43" x2="80" y2="30" stroke="#2d8a4e" stroke-width="2"/>
                <circle cx="80" cy="27" r="5" fill="#2d8a4e"/>
                <line x1="68" y1="45" x2="58" y2="33" stroke="#2d8a4e" stroke-width="1.5"/>
                <circle cx="55" cy="30" r="3" fill="#2d8a4e" opacity="0.6"/>
                <line x1="92" y1="45" x2="102" y2="33" stroke="#2d8a4e" stroke-width="1.5"/>
                <circle cx="105" cy="30" r="3" fill="#2d8a4e" opacity="0.6"/>
                <rect x="58" y="100" width="44" height="18" rx="9" fill="#2d8a4e"/>
                <text x="80" y="113" text-anchor="middle" fill="white" font-size="10" font-weight="bold">IA</text>
            </svg>
        </div>
        <h1 style="color:white;font-size:42px;font-weight:800;margin:0 0 8px 0;letter-spacing:-1px;font-family:Inter,sans-serif">
            Atlantic Re <span style="color:#2d8a4e">IA</span>
        </h1>
        <p style="color:#aaa;font-size:16px;margin:0 0 8px 0">Agent de tarification · Réassurance Non-Proportionnelle</p>
        <p style="color:#666;font-size:13px;margin:0 0 40px 0">Atlantic Re · Automobile · Maroc</p>
        <div style="display:flex;gap:16px;margin-bottom:48px;flex-wrap:wrap;justify-content:center">
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🔥</div>
                <div style="color:white;font-size:13px;font-weight:600">Burning Cost</div>
                <div style="color:#888;font-size:11px">As-If · Stabilisation · CL</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🎲</div>
                <div style="color:white;font-size:13px;font-weight:600">Simulation</div>
                <div style="color:#888;font-size:11px">Pareto · Poisson · TVE</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">📈</div>
                <div style="color:white;font-size:13px;font-weight:600">Market Curve</div>
                <div style="color:#888;font-size:11px">Modèle puissance log-log</div>
            </div>
            <div style="background:rgba(45,138,78,0.1);border:1px solid rgba(45,138,78,0.3);border-radius:12px;padding:16px 20px;min-width:140px">
                <div style="font-size:24px;margin-bottom:6px">🤖</div>
                <div style="color:white;font-size:13px;font-weight:600">Agent Claude</div>
                <div style="color:#888;font-size:11px">Analyse · Recommandations</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀  Lancer l'outil de tarification", type="primary", use_container_width=True):
            st.session_state["page"] = "app"
            st.rerun()
        st.markdown(f"<p style='text-align:center;color:#555;font-size:12px;margin-top:12px'>Connecté : {st.session_state.get('user_email','')}</p>", unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════
# APP CONFIG CSS
# ════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp { background-color: #f4f6f4; }
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #f1f1f1; }
::-webkit-scrollbar-thumb { background: #2d8a4e; border-radius: 3px; }
h1 { color: #1a1a1a; font-weight: 700; letter-spacing: -0.5px; }
h2 { color: #1a1a1a; border-bottom: 3px solid #2d8a4e; padding-bottom: 10px; margin-bottom: 20px; font-weight: 600; }
h3 { color: #2d8a4e; font-weight: 600; }
.stButton > button { background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); color: white; border: none; border-radius: 8px; padding: 10px 24px; font-weight: 600; font-size: 14px; transition: all 0.25s ease; box-shadow: 0 2px 8px rgba(0,0,0,0.15); }
.stButton > button:hover { background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%); transform: translateY(-2px); box-shadow: 0 6px 16px rgba(45,138,78,0.35); }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #2d8a4e 0%, #25a85e 100%); }
.stButton > button[kind="primary"]:hover { background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); }
.stTabs [data-baseweb="tab-list"] { background: #1a1a1a; border-radius: 12px; padding: 6px; gap: 4px; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
.stTabs [data-baseweb="tab"] { color: #888; font-weight: 500; font-size: 13px; border-radius: 8px; padding: 8px 16px; transition: all 0.2s ease; }
.stTabs [data-baseweb="tab"]:hover { color: white; background: rgba(255,255,255,0.1); }
.stTabs [aria-selected="true"] { background: linear-gradient(135deg, #2d8a4e, #25a85e) !important; color: white !important; border-radius: 8px; box-shadow: 0 2px 8px rgba(45,138,78,0.4); }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #1a1a1a 0%, #2a2a2a 100%); border-right: 1px solid #2d8a4e; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: #2d8a4e !important; border-bottom: 1px solid #333 !important; }
[data-testid="stSidebar"] .stTextInput input, [data-testid="stSidebar"] .stNumberInput input { background: #2a2a2a; border: 1px solid #444; color: white !important; border-radius: 6px; }
[data-testid="stMetric"] { background: white; border-radius: 12px; padding: 16px 20px; border: 1px solid #e8e8e8; box-shadow: 0 2px 8px rgba(0,0,0,0.06); border-left: 4px solid #2d8a4e; transition: transform 0.2s ease; }
[data-testid="stMetric"]:hover { transform: translateY(-2px); }
[data-testid="stMetricLabel"] { color: #666 !important; font-size: 13px !important; font-weight: 500 !important; }
[data-testid="stMetricValue"] { color: #1a1a1a !important; font-weight: 700 !important; }
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; box-shadow: 0 2px 12px rgba(0,0,0,0.08); border: 1px solid #e8e8e8; }
.stTextInput input, .stNumberInput input, .stTextArea textarea { border: 1.5px solid #e0e0e0; border-radius: 8px; padding: 10px 14px; font-size: 14px; transition: all 0.2s ease; background: white; }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus { border-color: #2d8a4e; box-shadow: 0 0 0 3px rgba(45,138,78,0.15); outline: none; }
.stSelectbox > div > div { border: 1.5px solid #e0e0e0; border-radius: 8px; }
.stSelectbox > div > div:hover { border-color: #2d8a4e; }
.streamlit-expanderHeader { background: white; border-radius: 10px; border: 1px solid #e8e8e8; font-weight: 500; color: #1a1a1a; padding: 12px 16px; transition: all 0.2s ease; }
.streamlit-expanderHeader:hover { border-color: #2d8a4e; color: #2d8a4e; }
.streamlit-expanderContent { border: 1px solid #e8e8e8; border-top: none; border-radius: 0 0 10px 10px; background: #fafafa; padding: 16px; }
hr { border: none; border-top: 2px solid #e8e8e8; margin: 20px 0; }
.stProgress > div > div { background: linear-gradient(90deg, #2d8a4e, #25a85e); border-radius: 4px; }
.stProgress > div { background: #e8e8e8; border-radius: 4px; }
</style>
""", unsafe_allow_html=True)


def card(titre, valeur, couleur="#2d8a4e", icone="📊"):
    st.markdown(f"""<div style="background:white;border-radius:12px;padding:20px 24px;border:1px solid #e8e8e8;
        border-left:5px solid {couleur};box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:12px;">
        <div style="font-size:12px;color:#888;font-weight:500;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px">{icone} {titre}</div>
        <div style="font-size:24px;font-weight:700;color:#1a1a1a">{valeur}</div></div>""", unsafe_allow_html=True)


def section_header(titre, sous_titre="", icone=""):
    st.markdown(f"""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d2d2d 100%);border-radius:12px;
        padding:20px 24px;margin-bottom:20px;box-shadow:0 4px 12px rgba(0,0,0,0.15);">
        <div style="font-size:20px;font-weight:700;color:white">{icone} {titre}</div>
        {f'<div style="font-size:13px;color:#aaa;margin-top:4px">{sous_titre}</div>' if sous_titre else ''}
        </div>""", unsafe_allow_html=True)


def tableau_resultats(donnees, titre=""):
    if not donnees: return
    if titre:
        st.markdown(f"<h4 style='color:#1a1a1a;margin-bottom:12px'>{titre}</h4>", unsafe_allow_html=True)
    colonnes = list(donnees[0].keys())
    html = """<div style="overflow-x:auto;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
    <thead><tr style="background:linear-gradient(135deg,#1a1a1a,#2d2d2d)">"""
    for col in colonnes:
        html += f'<th style="padding:12px 16px;text-align:left;color:white;font-weight:600">{col}</th>'
    html += "</tr></thead><tbody>"
    for i, row in enumerate(donnees):
        bg = "white" if i % 2 == 0 else "#f9fafb"
        html += f'<tr style="background:{bg}" onmouseover="this.style.background=\'#f0fff4\'" onmouseout="this.style.background=\'{bg}\'">'
        for col in colonnes:
            val = row.get(col, "")
            color = "#1a1a1a"
            if "%" in str(val) and any(c.isdigit() for c in str(val)):
                try:
                    num = float(str(val).replace("%",""))
                    if num > 5: color = "#ef4444"
                    elif num > 2: color = "#f59e0b"
                    else: color = "#2d8a4e"
                except: pass
            if "✅" in str(val): color = "#2d8a4e"
            if "⚠️" in str(val): color = "#f59e0b"
            html += f'<td style="padding:11px 16px;border-bottom:1px solid #f0f0f0;color:{color};font-weight:500">{val}</td>'
        html += "</tr>"
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def progress_steps(steps, current):
    html = '<div style="display:flex;align-items:center;gap:0;margin:16px 0;overflow-x:auto">'
    for i, (label, done) in enumerate(steps):
        if done:         bg, fg, border = "#2d8a4e", "white", "#2d8a4e"
        elif i==current: bg, fg, border = "#1a1a1a", "white", "#1a1a1a"
        else:            bg, fg, border = "white", "#999", "#ddd"
        check     = "✓ " if done else ""
        connector = '<div style="height:2px;background:#ddd;flex:1;min-width:8px"></div>' if i < len(steps)-1 else ""
        html += '<div style="display:flex;align-items:center;flex:1;min-width:80px">'
        html += f'<div style="background:{bg};color:{fg};border:2px solid {border};border-radius:20px;padding:6px 12px;font-size:11px;font-weight:600;white-space:nowrap;text-align:center;width:100%">{check}{label}</div>'
        html += connector + '</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ════════════════════════════════════════════
# PROMPT ENGINEERING
# ════════════════════════════════════════════

def prompt_inputs(key_prefix, placeholder_contexte="", placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    with st.expander("✏️ Personnaliser le prompt Claude", expanded=False):
        st.markdown("##### 🎯 Prompt Engineering")
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area("📌 Contexte",
                placeholder=placeholder_contexte or "Ex: Portefeuille automobile Maroc 2026...",
                height=80, key=f"{key_prefix}_contexte")
            instructions = st.text_area("📋 Instructions spécifiques",
                placeholder=placeholder_instructions or "Ex: Être attentif à la tranche Cat L1...",
                height=80, key=f"{key_prefix}_instructions")
        with c2:
            input_data = st.text_area("📥 Données supplémentaires",
                placeholder=placeholder_input or "Ex: Taux marché de référence : 3.2%...",
                height=80, key=f"{key_prefix}_input")
            output_instructions = st.text_area("📤 Format de sortie souhaité",
                placeholder=placeholder_output or "Ex: Tableau structuré + recommandation chiffrée...",
                height=80, key=f"{key_prefix}_output")
    return contexte, instructions, input_data, output_instructions


def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    prompt = f"""
════════════════════════════════════════════
RÔLE
════════════════════════════════════════════
{role}

════════════════════════════════════════════
RÈGLES ABSOLUES
════════════════════════════════════════════
1. ANTI-HALLUCINATION : Ne jamais inventer. Si incertain → "Information insuffisante."
2. TRIANGLE INTERDIT : Ne JAMAIS générer, afficher ou simuler un triangle de développement dans tes réponses texte. Les données réelles sont visibles dans l'onglet 🔥 Burning Cost → expander "Triangle individuel". Dis simplement : "Consultez le triangle réel dans l'onglet BC."
2. RAISONNEMENT : [Observation] → [Analyse] → [Conclusion] avec chiffres.
3. CONTRAINTES MÉTIER :
{contraintes if contraintes else "   - Taux techniques positifs et < 50%\n   - Ecart BC/Sim > 25% signalé\n   - BC=0 tranche cat NORMAL"}
4. VÉRIFICATION : chiffres présents ? cohérence ? hiérarchie taux_pur < taux_risque < taux_tech ?
5. EXEMPLES :
{exemples if exemples else '   BON : "Taux BC 2.94%, simulation 3.98%, ecart 35% -> retenir simulation."\n   MAUVAIS : "Le taux est acceptable."'}

════════════════════════════════════════════
CONTEXTE GLOBAL
════════════════════════════════════════════
{contexte_global if contexte_global else "Non fourni."}

════════════════════════════════════════════
CONTEXTE SPECIFIQUE
════════════════════════════════════════════
{contexte if contexte else "Aucun."}

════════════════════════════════════════════
TACHE
════════════════════════════════════════════
{task}

════════════════════════════════════════════
DONNEES
════════════════════════════════════════════
{data}
{("DONNEES SUPPLEMENTAIRES :\n" + input_data) if input_data else ""}

════════════════════════════════════════════
INSTRUCTIONS SPECIFIQUES
════════════════════════════════════════════
{instructions if instructions else "Suivre la tache telle que decrite."}

════════════════════════════════════════════
FORMAT DE SORTIE
════════════════════════════════════════════
{output_instructions if output_instructions else "1. SYNTHESE (2-3 phrases)\n2. ANALYSE PAR TRANCHE\n3. POINTS D'ATTENTION\n4. CONCLUSION"}

La precision prime sur l'exhaustivite.
════════════════════════════════════════════
"""
    return prompt.strip()


def claude_stream(api_key, prompt, max_tokens=2000, session_key="", use_opus=False):
    """
    use_opus=True  → claude-opus-4-5   (agent autonome, calculs complexes)
    use_opus=False → claude-haiku-4-5  (analyses copilote, 20x moins cher)
    """
    model = "claude-opus-4-5" if use_opus else "claude-haiku-4-5-20251001"
    client = anthropic.Anthropic(api_key=api_key)
    placeholder = st.empty()
    full_text = ""
    label_model = "Opus" if use_opus else "Haiku ⚡"
    with st.status(f"🤖 Agent Claude ({label_model}) en cours...", expanded=True) as status:
        st.write("🔗 Connexion au modèle...")
        st.write("📊 Chargement des données actuarielles...")
        try:
            with client.messages.stream(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                st.write("✍️ Génération de l'analyse...")
                for text in stream.text_stream:
                    full_text += text
                    placeholder.markdown(full_text + "▌")
            status.update(label="✅ Analyse terminée", state="complete", expanded=False)
        except Exception as e:
            status.update(label="❌ Erreur", state="error")
            st.error(f"Erreur API : {e}")
            return ""
    placeholder.markdown(full_text)
    if session_key:
        st.session_state[session_key] = full_text
    return full_text


def guide_prompt(etape, exemples_contexte, exemples_instructions, exemples_input, exemples_output):
    with st.expander("💡 Conseils pour bien prompter Claude sur cette étape", expanded=False):
        st.markdown(f"""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;
            padding:14px 18px;margin-bottom:12px"><b style="color:#2d8a4e">🎯 Meilleure analyse pour : {etape}</b></div>""",
            unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📌 Contexte — quoi mettre**")
            for ex in exemples_contexte: st.markdown(f"- {ex}")
            st.markdown("**📋 Instructions — quoi demander**")
            for ex in exemples_instructions: st.markdown(f"- {ex}")
        with c2:
            st.markdown("**📥 Données supplémentaires**")
            for ex in exemples_input: st.markdown(f"- {ex}")
            st.markdown("**📤 Format de sortie**")
            for ex in exemples_output: st.markdown(f"- {ex}")
        st.markdown("""<div style="background:#fff8f0;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;
            padding:10px 14px;margin-top:8px;font-size:12px">
            ⚠️ <b>Règle d'or :</b> Plus vous donnez de contexte métier, plus l'analyse sera pertinente et actionnelle.
            </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════
# FONCTIONS ACTUARIELLES
# ════════════════════════════════════════════

def selectionner_seuil_pareto(X, D):
    X = np.array(X); X = X[X > 0]
    k_hill = min(59, len(X)-1); k_gerten = min(43, len(X)-1)
    X_desc = np.sort(X)[::-1]
    seuils = {"MLE": np.min(X),
               "Hill": X_desc[k_hill-1] if k_hill > 0 else np.min(X),
               "Gerten": X_desc[k_gerten-1] if k_gerten > 0 else np.min(X),
               "MeanExc": 1_800_000,
               "p50": 0.50*D, "p75": 0.75*D, "p80": 0.80*D, "p85": 0.85*D, "p90": 0.90*D}
    resultats = []
    for nom, s in seuils.items():
        Xs = X[X >= s]
        if len(Xs) < 5: continue
        t_min = np.min(Xs); n = len(Xs)
        alpha_hat = n / np.sum(np.log(Xs / t_min))
        Xs_sorted = np.sort(Xs)
        cdf_emp = np.arange(1, n+1) / n
        cdf_par = 1 - (t_min / Xs_sorted) ** alpha_hat
        ks_stat = np.max(np.abs(cdf_emp - cdf_par))
        ks_pval = np.exp(-2 * n * ks_stat**2)
        resultats.append({"Seuil": nom, "t": round(s), "n": n,
                           "alpha": round(alpha_hat, 4), "KS_pval": round(ks_pval, 4)})
    return pd.DataFrame(resultats), seuils.get("p80", 0.80*D)


def identifier_sinistres_majeurs(df_proj, gnpi, D, C_tranche,
                                  nb_annees_obs=10, retour_ans=20, percentile_seuil=99.5):
    X = df_proj['Sprime_ultime'].values; X = X[X > 0]
    Pm = np.percentile(X, percentile_seuil)
    mask_maj = df_proj['Sprime_ultime'] >= Pm
    df_majeurs = df_proj[mask_maj].copy(); df_courants = df_proj[~mask_maj].copy()
    seuil_model = 0.80 * D
    X_model = X[(X >= seuil_model) & (X < Pm)]
    if len(X_model) < 3: X_model = X[X >= seuil_model]
    t_min = np.min(X_model) if len(X_model) > 0 else seuil_model
    n_model = len(X_model)
    alpha_hat = n_model / np.sum(np.log(X_model / t_min)) if n_model > 0 else 1.5
    def charge_nette(x): return min(max(x - D, 0), C_tranche)
    rows_charg = []
    for _, row in df_majeurs.iterrows():
        x = row['Sprime_ultime']; cn = charge_nette(x); chg = (1/retour_ans) * cn / gnpi
        rows_charg.append({"Annee": row.get('annee_surv','—'), "Montant_stab": round(x),
                            "Charge_nette": round(cn), "p_j": round(1/retour_ans, 4),
                            "Chargement": round(chg, 6)})
    df_chargements = pd.DataFrame(rows_charg)
    chargement_total = df_chargements['Chargement'].sum() if len(df_chargements) > 0 else 0.0
    return {"df_majeurs": df_majeurs, "df_courants": df_courants, "Pm": Pm,
            "chargement": chargement_total, "df_chargements": df_chargements,
            "alpha": alpha_hat, "n_majeurs": len(df_majeurs), "n_courants": len(df_courants)}


# ════════════════════════════════════════════
# HEADER + SIDEBAR
# ════════════════════════════════════════════

st.title("Atlantic Re")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning cost · Simulation · Market curve · IA")

with st.sidebar:
    if st.button("🚪 Déconnexion"):
        st.session_state["authenticated"] = False; st.rerun()
    if st.button("🏠 Accueil"):
        st.session_state["page"] = "landing"; st.rerun()
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("🔑 Clé API Claude", type="password", placeholder="sk-ant-...",
                           help="Analyses copilote : Haiku (économique) | Agent autonome : Opus (puissant)")
    if api_key:
        st.caption("⚡ Haiku pour analyses | 🔬 Opus pour agents autonomes uniquement")
    gnpi    = st.number_input("💰 GNPI (MAD)", value=183_000_000, step=1_000_000)
    st.divider()
    st.markdown("### 📊 Statut des étapes")
    for nom, key in [("Programme","df_prog"),("Données","df_liq"),
                     ("Burning cost","resultats_bc"),("Simulation","resultats_sim"),
                     ("Market curve","resultats_mkt")]:
        st.markdown(f"{'✅' if key in st.session_state else '⬜'} {nom}")
    st.divider()
    st.divider()
    st.markdown("### 💾 Base de données")
    _db_url_val = _get_db_url()
    _db_type = "🐘 PostgreSQL (Supabase)" if _db_url_val else "🗄️ SQLite local"
    _db_sid  = st.session_state.get("db_session_id")
    st.markdown(f"{_db_type}")
    if not _db_url_val:
        try:
            raw = st.secrets.get("DATABASE_URL", "")
            if raw:
                st.caption(f"⚠️ Format inattendu : {raw[:25]}...")
            else:
                st.caption("❌ DATABASE_URL absent des Secrets")
        except:
            st.caption("❌ Secrets non accessibles")

    if st.button("🔌 Tester la connexion DB", key="btn_test_db", use_container_width=True):
        st.markdown("---")
        # 1. Lecture secrets
        raw_url = None
        try:
            raw_url = st.secrets.get("DATABASE_URL")
            if raw_url:
                st.success(f"✅ Secret trouvé : {raw_url[:30]}...")
            else:
                st.error("❌ DATABASE_URL vide ou absent des Secrets")
        except Exception as e:
            st.error(f"❌ Erreur lecture secrets : {e}")

        # 2. Normalisation URL
        if raw_url:
            if raw_url.startswith("postgres://"):
                raw_url = raw_url.replace("postgres://", "postgresql://", 1)
                st.info("ℹ️ URL normalisée : postgres:// → postgresql://")

        # 3. Test connexion
        if raw_url and raw_url.startswith("postgresql://"):
            try:
                import psycopg2
                con = psycopg2.connect(raw_url, connect_timeout=5)
                cur = con.cursor()
                cur.execute("SELECT version()")
                v = cur.fetchone()[0]
                con.close()
                st.success(f"✅ Connexion PostgreSQL OK !")
                st.caption(v[:60])
            except ImportError:
                st.error("❌ psycopg2 non installé — ajoutez psycopg2-binary dans requirements.txt")
            except Exception as e:
                st.error(f"❌ Connexion échouée : {e}")
        elif raw_url:
            st.error(f"❌ Format URL non reconnu : {raw_url[:40]}")
    if _db_sid:
        chargé_sidebar = []
        if "resultats_bc"   in st.session_state: chargé_sidebar.append("🔥 BC")
        if "resultats_sim"  in st.session_state: chargé_sidebar.append("🎲 Sim")
        if "taux_mkt_final" in st.session_state and st.session_state.get("taux_mkt_final"): chargé_sidebar.append("📈 Mkt")
        if "df_rapport"     in st.session_state: chargé_sidebar.append("📋 Rapport")
        st.caption(f"Session #{_db_sid}")
        if chargé_sidebar:
            st.caption(" · ".join(chargé_sidebar))
    else:
        st.caption("Aucune session active")
    if st.button("💾 Sauvegarder maintenant", key="btn_save_now", use_container_width=True):
        try:
            sid = db_save_session(st.session_state.get("user_email",""), gnpi,
                                     st.session_state.get("tranches_input", []))
            if "resultats_bc" in st.session_state:
                db_save_etape("bc", [{k:v for k,v in r.items() if k!="detail_annuel"}
                                      for r in st.session_state["resultats_bc"]])
            if "resultats_sim" in st.session_state:
                db_save_etape("sim", st.session_state["resultats_sim"])
            if "resultats_mkt" in st.session_state:
                db_save_etape("mkt", {"resultats_mkt": [{k:v for k,v in r.items() if k!="taux_tranches"}
                                       for r in st.session_state["resultats_mkt"]],
                                      "taux_mkt_final": st.session_state.get("taux_mkt_final",[])})
            if st.session_state.get("df_rapport") is not None:
                db_save_etape("rapport", {"rows": st.session_state["df_rapport"].to_dict("records"),
                                           "prime_totale": st.session_state.get("prime_totale",0)})
            st.success(f"✅ Sauvegardé — Session #{sid}")
            st.rerun()
        except Exception as _e:
            st.error(f"Erreur DB : {_e}")
    st.markdown("### 🌍 Contexte global")
    instructions_globales = st.text_area("Contexte portefeuille",
        placeholder="Ex: Portefeuille automobile Maroc, forte croissance 2023...",
        height=120, key="instructions_globales",
        help="Inclus dans TOUS les prompts Claude")

# ════════════════════════════════════════════
# ACCUEIL INTELLIGENT
# ════════════════════════════════════════════

# ── Bandeau accueil statique (0 token) ──
etapes_faites     = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                      ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                      ("Market Curve","resultats_mkt")] if k in st.session_state]
etapes_manquantes = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                      ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                      ("Market Curve","resultats_mkt")] if k not in st.session_state]
etapes_html = " → ".join([f"<span style='color:#2d8a4e;font-weight:700'>{e}</span>" for e in etapes_faites]) if etapes_faites else "Aucune étape complétée"
prochaine   = etapes_manquantes[0] if etapes_manquantes else "✅ Toutes les étapes complétées !"
st.markdown(f"""<div style="background:linear-gradient(135deg,#1a1a1a 0%,#2d8a4e 100%);
    border-radius:16px;padding:20px 28px;margin-bottom:16px;box-shadow:0 6px 20px rgba(0,0,0,0.2)">
    <div style="font-size:17px;font-weight:700;color:white">🤖 Atlantic Re IA — Tarification XL Non-Proportionnelle</div>
    <div style="font-size:12px;color:rgba(255,255,255,0.7);margin-top:6px">
        Workflow : <b style="color:white">Programme → Triangle → BC → Simulation → Market Curve → Rapport</b>
    </div>
    <div style="font-size:12px;color:rgba(255,255,255,0.6);margin-top:4px">
        ✅ Complétées : {etapes_html if etapes_faites else '<span style="color:#aaa">Aucune</span>'}
        &nbsp;|&nbsp; ⏭️ Prochaine étape : <b style="color:#f59e0b">{prochaine}</b>
    </div></div>""", unsafe_allow_html=True)

# ── Analyse IA sur demande uniquement (évite les appels automatiques coûteux) ──
if "accueil_ia_msg" in st.session_state:
    with st.expander("🤖 Dernière analyse IA", expanded=False):
        st.markdown(st.session_state["accueil_ia_msg"])

if api_key:
    col_ia1, col_ia2 = st.columns([3, 1])
    with col_ia2:
        if st.button("🤖 Analyser ma session", key="btn_accueil_ia", use_container_width=True,
                     help="Appel API payant — utiliser avec parcimonie"):
            etapes_faites_2     = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                                  ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                                  ("Market Curve","resultats_mkt")] if k in st.session_state]
            etapes_manquantes_2 = [n for n, k in [("Programme","df_prog"),("Triangle","df_liq"),
                                  ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                                  ("Market Curve","resultats_mkt")] if k not in st.session_state]
            prompt_accueil = build_prompt(
                role="Assistant actuariel expert en reassurance non-proportionnelle automobile.",
                task="Genere un message d'accueil intelligent : 1. Etat de la session 2. Prochaine action recommandee 3. Point d'attention si anomalie. Maximum 8 lignes.",
                data=f"Etapes completes : {etapes_faites_2}\nEtapes restantes : {etapes_manquantes_2}\nGNPI : {gnpi:,} MAD",
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Maximum 8 lignes\n- Concis\n- Ne pas inventer")
            with st.spinner("🤖 Analyse en cours..."):
                client_acc = __import__('anthropic').Anthropic(api_key=api_key)
                try:
                    msg = client_acc.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=400,
                        messages=[{"role":"user","content":prompt_accueil}])
                    txt = msg.content[0].text
                    st.session_state["accueil_ia_msg"] = txt
                    st.rerun()
                except Exception as e_acc:
                    st.error(f"Erreur : {e_acc}")

# ════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab_agent, tab_full, tab_hist, tab_admin = st.tabs([
    "📋 Programme", "📂 Données & Triangle",
    "🔥 Burning Cost", "🎲 Simulation",
    "📈 Market Curve", "📋 Rapport Final",
    "🤖 Agent Python", "🚀 Agent LLM", "📜 Historique", "🔐 Admin"
])

etapes_progress = [
    ("Programme",    "df_prog"       in st.session_state),
    ("Triangle",     "df_liq"        in st.session_state),
    ("Burning Cost", "resultats_bc"  in st.session_state),
    ("Simulation",   "resultats_sim" in st.session_state),
    ("Market Curve", "resultats_mkt" in st.session_state),
]
progress_steps(etapes_progress, current=0)

# ════════════════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════════════════

with tab1:
    st.header("Programme de Réassurance")
    st.caption("Définissez les tranches, conditions et paramètres de chargement")
    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)
    tranches_input = []
    defaults = {
        0: {"type": "travaillante", "priorite": 2_000_000,  "portee": 13_000_000},
        1: {"type": "cat",          "priorite": 15_000_000, "portee": 10_000_000},
        2: {"type": "cat",          "priorite": 25_000_000, "portee": 15_000_000},
    }
    for i in range(nb_tranches):
        d = defaults.get(i, {"type": "travaillante", "priorite": 2_000_000, "portee": 13_000_000})
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i==0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Identification**")
                nom      = st.text_input("Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
                type_idx = ["travaillante","non_travaillante","cat"].index(d["type"])
                type_t   = st.selectbox("Type", ["travaillante","non_travaillante","cat"], index=type_idx, key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)", value=float(d["priorite"]), step=500_000.0,
                                           format="%.0f", key=f"prio_{i}")
                portee   = st.number_input("Portée (MAD)",   value=float(d["portee"]),   step=500_000.0,
                                           format="%.0f", key=f"port_{i}")
            with c2:
                st.markdown("**Conditions contractuelles**")
                has_aal  = st.checkbox("AAL", key=f"aal_{i}")
                aal_val  = st.number_input("Montant AAL (MAD)", value=0.0, step=100_000.0,
                                           format="%.2f", key=f"aal_v_{i}", disabled=not has_aal)
                has_aad  = st.checkbox("AAD", key=f"aad_{i}")
                aad_val  = st.number_input("Montant AAD (MAD)", value=0.0, step=100_000.0,
                                           format="%.2f", key=f"aad_v_{i}", disabled=not has_aad)
                has_indices = st.checkbox("Clause d'indexation", key=f"idx_{i}")
            with c3:
                st.markdown("**Frais & Charges**")
                brokage      = st.number_input("Brokage %",       value=10.0, min_value=0.0, max_value=30.0,
                                               step=0.01, format="%.2f", key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %", value=5.0,  min_value=0.0, max_value=20.0,
                                               step=0.01, format="%.2f", key=f"frais_{i}")
                marge        = st.number_input("Marge %",          value=10.0, min_value=0.0, max_value=30.0,
                                               step=0.01, format="%.2f", key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",   value=0.0,  min_value=0.0, max_value=50.0,
                                               step=0.01, format="%.2f", key=f"retro_{i}")

            # ── Reconstitutions : nb + taux individuel par reconstitution ──
            st.markdown("**Reconstitutions**")
            nb_recon = st.number_input("Nombre de reconstitutions", value=1, min_value=0, max_value=5,
                                       step=1, key=f"recon_{i}")
            taux_recons = []
            if nb_recon > 0:
                cols_rec = st.columns(min(nb_recon, 5))
                for r_idx in range(nb_recon):
                    with cols_rec[r_idx]:
                        t_r = st.number_input(
                            f"Reconst. {r_idx+1} %",
                            value=100.0, min_value=0.0, max_value=200.0,
                            step=0.5, format="%.1f",
                            key=f"txrecon_{i}_{r_idx}",
                            help=f"Taux de la {r_idx+1}ᵉ reconstitution")
                        taux_recons.append(t_r)
            if taux_recons:
                st.caption(f"Reconstitutions : {' | '.join([f'{r_idx+1}ᵉ→{t:.1f}%' for r_idx,t in enumerate(taux_recons)])}")

        tranches_input.append({
            "numero": i+1, "nom": nom, "type": type_t,
            "priorite": float(priorite), "portee": float(portee),
            "AAL": float(aal_val) if has_aal else None,
            "AAD": float(aad_val) if has_aad else None,
            "nb_reconstitutions": int(nb_recon),
            "taux_reconstitution": taux_recons[0] if taux_recons else 100.0,  # compat. ancienne formule
            "taux_reconstitutions": taux_recons,   # ← liste individuelle
            "indices": has_indices,
            "brokage": brokage/100, "frais": frais/100,
            "marge": marge/100, "retrocession": retrocession/100
        })
    if st.button("💾 Valider le programme", type="primary"):
        st.session_state["tranches_input"] = tranches_input
        st.session_state["df_prog"] = pd.DataFrame([{
            "Tranche": t["nom"], "Type": t["type"],
            "Priorité": f"{t['priorite']:,.0f}", "Portée": f"{t['portee']:,.0f}",
            "AAL": f"{t['AAL']:,.0f}" if t["AAL"] else "—",
            "AAD": f"{t['AAD']:,.0f}" if t["AAD"] else "—",
            "Reconst.": " | ".join([f"{r_idx+1}→{tr:.0f}%" for r_idx,tr in enumerate(t['taux_reconstitutions'])]) if t.get("taux_reconstitutions") else f"{t['nb_reconstitutions']}x{t['taux_reconstitution']:.0f}%",
            "Indices": "✅" if t["indices"] else "—",
            "Brokage": f"{t['brokage']:.2%}", "Frais": f"{t['frais']:.2%}",
            "Marge": f"{t['marge']:.2%}", "Rétro": f"{t['retrocession']:.2%}",
        } for t in tranches_input])
        st.success("✅ Programme validé !")
    if "df_prog" in st.session_state:
        st.dataframe(st.session_state["df_prog"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Travaillantes", sum(1 for t in tranches_input if t["type"]=="travaillante"))
        c2.metric("Cat",           sum(1 for t in tranches_input if t["type"]=="cat"))
        c3.metric("Non-trav.",     sum(1 for t in tranches_input if t["type"]=="non_travaillante"))

# ════════════════════════════════════════════
# TAB 2 — DONNÉES & TRIANGLE
# ════════════════════════════════════════════

with tab2:
    st.header("Données de base & Transformation triangle")
    type_branche = st.radio("Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche", horizontal=True)
    is_long = "long" in type_branche
    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader("📁 Triangle développement", type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader("📁 Base GNPIs",             type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader("📁 Table indices",          type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation (n)", value=2026, step=1)
    seuil_stabilisation = st.number_input(
        "Seuil stabilisation (% inflation, 0 = toujours)",
        value=0.0, min_value=0.0, max_value=50.0, step=5.0) / 100
    pct_seuil = st.number_input(
        "Percentile seuil Pareto (p80 par défaut)",
        value=0.80, min_value=0.50, max_value=0.99, step=0.05, format="%.2f")

    if st.button("▶ Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")
            df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx') else pd.read_csv(f_gnpis)
            df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
            df_gnpis_df.columns = [str(c).strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [str(c).strip() for c in df_idx_df.columns]

            progress.progress(10, text="Nettoyage indices...")
            df_idx_df['Annee'] = pd.to_numeric(
                df_idx_df['Annee'].astype(str).str.strip().str.replace('.0','',regex=False), errors='coerce')
            df_idx_df['Coefficients'] = pd.to_numeric(
                df_idx_df['Coefficients'].astype(str).str.strip()
                .str.replace(',','.',regex=False).str.replace(' ','',regex=False), errors='coerce')
            df_idx_df = df_idx_df.dropna(subset=['Annee','Coefficients'])
            df_idx_df['Annee'] = df_idx_df['Annee'].astype(int)
            df_idx_df = df_idx_df.sort_values('Annee')
            df_idx_set = df_idx_df.set_index('Annee')['Coefficients']

            def get_indice(annee):
                annee = int(annee)
                annees = df_idx_set.index.values.astype(int)
                valeurs = df_idx_set.values.astype(float)
                if annee in annees: return float(df_idx_set.loc[annee])
                if annee < annees[0]:
                    return float(valeurs[0] - (valeurs[1]-valeurs[0]) * (annees[0]-annee))
                if annee > annees[-1]:
                    return float(valeurs[-1] + (valeurs[-1]-valeurs[-2]) * (annee-annees[-1]))
                return float(np.interp(annee, annees, valeurs))

            I_cotation_val = get_indice(annee_cotation)
            st.info(f"📐 I_cotation({annee_cotation}) = {I_cotation_val:.4f}")

            progress.progress(20, text="Parsing triangle...")
            df_raw = pd.read_excel(f_triangle, header=None)

            # ══════════════════════════════════════════════════════════
            # PARSER ROBUSTE — Format : UW Year | PAID OS TOTAL par an
            # ══════════════════════════════════════════════════════════

            # ── ÉTAPE 1 : Trouver la ligne des années de règlement ──
            # C'est la ligne qui contient le plus de valeurs numériques 2000-2050
            header_year_row = 0
            best_year_count = 0
            for row_idx in range(min(8, len(df_raw))):
                row_vals = df_raw.iloc[row_idx].tolist()
                cnt = 0
                for v in row_vals:
                    try:
                        vi = int(float(str(v).strip()))
                        if 1990 <= vi <= 2060: cnt += 1
                    except: pass
                if cnt > best_year_count:
                    best_year_count = cnt
                    header_year_row = row_idx
            header_type_row = header_year_row + 1
            data_start_row  = header_type_row + 1

            st.info(f"📋 En-têtes : ligne {header_year_row+1} (années) | ligne {header_type_row+1} (PAID/OS/TOTAL) | Données à partir de la ligne {data_start_row+1}")

            # ── ÉTAPE 2 : Construire col_info — (annee_regl, type) par colonne ──
            ligne_annees = df_raw.iloc[header_year_row].tolist()
            ligne_types  = df_raw.iloc[header_type_row].tolist()
            annee_courante = None
            col_info = []  # liste de (annee_regl, type_normalise) pour chaque colonne
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0:
                    col_info.append(('UW_YEAR', 'UW_YEAR'))
                    continue
                # Mise à jour de l'année courante si on trouve une année valide
                try:
                    a = int(float(str(ann).strip()))
                    if 1990 <= a <= 2060:
                        annee_courante = a
                except: pass
                # Normalisation du type de colonne
                typ_str = str(typ).strip().upper() if pd.notna(typ) and str(typ).strip() not in ('nan','NaN','') else ''
                # Mapping vers types normalisés
                if   typ_str in ('TOTAL', 'TOT', 'CUMUL', 'AMOUNT', 'MONTANT', 'INCURRED'):
                    typ_norm = 'TOTAL'
                elif typ_str in ('PAID', 'PAY', 'PAID LOSS', 'PAYE', 'PAYÉ', 'REGLEMENT', 'RÈGLEMENT'):
                    typ_norm = 'PAID'
                elif typ_str in ('OS', 'O/S', 'OUTSTANDING', 'RESERVE', 'RÉSERVE', 'SUSPENS', 'IBNR'):
                    typ_norm = 'OS'
                else:
                    typ_norm = typ_str  # garder tel quel
                col_info.append((annee_courante, typ_norm))

            # Résumé des colonnes détectées
            cols_total = [(i, a) for i,(a,t) in enumerate(col_info) if t=='TOTAL']
            cols_paid  = [(i, a) for i,(a,t) in enumerate(col_info) if t=='PAID']
            cols_os    = [(i, a) for i,(a,t) in enumerate(col_info) if t=='OS']
            annees_reg_detectees = sorted(set(a for a,t in col_info if t=='TOTAL' and a is not None))
            st.success(f"✅ Colonnes détectées — TOTAL : {len(cols_total)} | PAID : {len(cols_paid)} | OS : {len(cols_os)} | Années règlement : {annees_reg_detectees[0] if annees_reg_detectees else '?'} → {annees_reg_detectees[-1] if annees_reg_detectees else '?'}")

            if len(cols_total) == 0:
                st.error("❌ Aucune colonne TOTAL trouvée. Vérifiez que la ligne des types contient bien 'TOTAL'.")
                st.dataframe(df_raw.iloc[:data_start_row], use_container_width=True)
                st.stop()

            # ── ÉTAPE 3 : Extraire les données — 1 ligne = 1 sinistre ──
            df_data = df_raw.iloc[data_start_row:].reset_index(drop=True)
            # Propagation de l'année de survenance (cellules fusionnées → ffill)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction sinistres...")
            records = []
            sinistre_counter = {}  # {annee_surv: compteur} pour numéroter les sinistres
            for idx_row, row in df_data.iterrows():
                # Lire l'année de survenance (colonne A)
                try:
                    raw_uw = str(row.iloc[0]).strip().replace('.0','')
                    annee_surv = int(float(raw_uw))
                    if not (1990 <= annee_surv <= 2060): continue
                except: continue

                # Numéroter chaque sinistre dans l'année de survenance
                sinistre_counter[annee_surv] = sinistre_counter.get(annee_surv, 0) + 1
                sin_num = sinistre_counter[annee_surv]
                sinistre_id = f"{annee_surv}_S{sin_num:04d}"

                # Lire les colonnes TOTAL pour chaque année de règlement
                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ != 'TOTAL' or annee_reg is None: continue
                    val = row.iloc[col_idx]
                    try:
                        if pd.isna(val): continue
                        if isinstance(val, str):
                            val = val.strip().replace(',','.').replace(' ','').replace('\xa0','')
                            if not val or any(c.isalpha() for c in val) or '#' in val: continue
                        val = float(val)
                        if val <= 0 or np.isnan(val) or np.isinf(val): continue
                    except: continue
                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 15: continue  # max 15 ans de dev (flexible)
                    records.append({
                        'sinistre_id': sinistre_id,
                        'annee_surv':  annee_surv,
                        'annee_reg':   annee_reg,
                        'dev':         dev,
                        'total':       val
                    })

            if not records:
                st.error("❌ Aucune donnée extraite. Vérifiez le format du fichier.")
                st.markdown("**5 premières lignes du fichier brut :**")
                st.dataframe(df_raw.head(5), use_container_width=True)
                st.stop()

            # Résumé du parsing
            annees_surv_uniq = sorted(set(r['annee_surv'] for r in records))
            st.success(f"✅ Extraction OK — {len(records):,} observations | {len(annees_surv_uniq)} années de survenance ({annees_surv_uniq[0]}→{annees_surv_uniq[-1]}) | {sum(sinistre_counter.values()):,} sinistres")

            df_liq = pd.DataFrame(records)
            # ── Trier par sinistre et développement croissant (obligatoire pour le décumul) ──
            df_liq = df_liq.sort_values(['sinistre_id', 'dev']).reset_index(drop=True)

            progress.progress(48, text="Indices...")
            df_liq['I_reg']  = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv'] = df_liq['annee_surv'].apply(get_indice)
            # I_ultime gardé pour affichage / compatibilité
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)

            progress.progress(50, text="Décumul → As-If sur incréments...")
            # ── ÉTAPE 1 : DÉCUMULER ──
            # Le triangle est cumulatif : total[dev] = PAID+OS cumulés jusqu'à dev
            # On calcule l'incrément entre deux périodes consécutives
            df_liq['prev_total'] = df_liq.groupby('sinistre_id')['total'].shift(1).fillna(0)
            df_liq['increment']  = (df_liq['total'] - df_liq['prev_total']).clip(lower=0)
            # Note : clip(lower=0) — un incrément négatif (réduction de réserve) → 0
            # pour éviter les montants négatifs dans la modélisation

            # ── ÉTAPE 2 : AS-IF SUR L'INCRÉMENT ──
            # Chaque paiement/variation de réserve est revalué à l'année de cotation
            # inc_asif = inc × (I_cotation / I_reg_au_moment_du_paiement)
            df_liq['inc_asif'] = df_liq['increment'] * (I_cotation_val / df_liq['I_reg'])

            progress.progress(55, text="Stabilisation sur incréments...")
            # ── ÉTAPE 3 : STABILISATION SUR L'INCRÉMENT ──
            # Si I_reg/I_surv ≥ 1+seuil → le réassureur peut ajuster sa priorité
            # On neutralise cette inflation en appliquant I_surv/I_reg
            df_liq['ratio_check'] = df_liq['I_reg'] / df_liq['I_surv']
            mask_stab = df_liq['ratio_check'] >= (1.0 + seuil_stabilisation)
            df_liq['inc_stab'] = np.where(
                mask_stab,
                df_liq['inc_asif'] * (df_liq['I_surv'] / df_liq['I_reg']),
                df_liq['inc_asif']
            )
            n_stab = mask_stab.sum()
            annees_reg_stab = sorted(df_liq[mask_stab]['annee_reg'].unique().tolist())
            st.info(f"📊 Décumul + Stab | Seuil : {seuil_stabilisation*100:.0f}% | Incréments stab. : {n_stab} | Années règlement : {annees_reg_stab}")

            # ── ÉTAPE 4 : RECUMULER ──
            # Sk      = cumul des incréments As-If
            # S_prime_k = cumul des incréments stabilisés
            df_liq['Sk']        = df_liq.groupby('sinistre_id')['inc_asif'].cumsum()
            df_liq['S_prime_k'] = df_liq.groupby('sinistre_id')['inc_stab'].cumsum()

            # coeff_stab = Sk / S_prime_k : utilisé dans le BC pour convertir S'ultime → Sk
            df_liq['coeff_stab'] = np.where(
                df_liq['S_prime_k'] > 0,
                df_liq['Sk'] / df_liq['S_prime_k'],
                1.0
            )

            # Vérification : n sinistres avec incrément négatif (réductions de réserves)
            n_neg = (df_liq['increment'] < 0).sum()
            if n_neg > 0:
                st.warning(f"⚠️ {n_neg} incréments négatifs détectés (réductions de réserves) → mis à 0 pour la modélisation")


            if is_long:
                progress.progress(65, text="Chain Ladder...")
                facteurs = {k: [] for k in range(9)}
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            t_k = grp.loc[k, 'S_prime_k']; t_k1 = grp.loc[k+1, 'S_prime_k']
                            if t_k > 0:
                                f = t_k1 / t_k
                                if 0.9 <= f <= 2.5: facteurs[k].append(f)
                f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

                progress.progress(75, text="Projection...")
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p = grp['annee_surv'].iloc[0]
                    dev_max = grp.index.max()
                    Sprime_ultime = grp.loc[dev_max, 'S_prime_k']
                    coeff_sin = grp.loc[dev_max, 'coeff_stab']
                    for k in range(dev_max, 9): Sprime_ultime *= f_moyens[k]
                    projections.append({'sinistre_id': sin_id, 'annee_surv': annee_surv_p,
                                        'dev_max': dev_max, 'Sprime_ultime': Sprime_ultime,
                                        'Sk_ultime': Sprime_ultime * coeff_sin, 'coeff_stab': coeff_sin})
                df_facteurs_df = pd.DataFrame({
                    'Dev.': [f"{k}→{k+1}" for k in range(9)],
                    'Facteur moyen': [round(f_moyens[k], 4) for k in range(9)],
                    'Nb observations': [len(facteurs[k]) for k in range(9)]})
            else:
                progress.progress(65, text="Branche courte...")
                df_liq['S_prime_k']  = df_liq['Sk']
                df_liq['coeff_stab'] = 1.0
                f_moyens = {k: 1.0 for k in range(9)}
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv_p = grp['annee_surv'].iloc[0]
                    dev_max = grp.index.max()
                    Sk_actuel = grp.loc[dev_max, 'Sk']
                    projections.append({'sinistre_id': sin_id, 'annee_surv': annee_surv_p,
                                        'dev_max': dev_max, 'Sprime_ultime': Sk_actuel,
                                        'Sk_ultime': Sk_actuel, 'coeff_stab': 1.0})
                df_facteurs_df = pd.DataFrame({'Info': ['Branche courte']})

            df_proj = pd.DataFrame(projections)
            progress.progress(85, text="Alpha & Lambda...")
            D_trav = next((t['priorite'] for t in tranches_input if t['type'] == 'travaillante'), 2_000_000)
            seuil_model = pct_seuil * D_trav
            X_all = df_proj['Sprime_ultime'].values; X_all = X_all[X_all > 0]
            Pm_proxy = np.percentile(X_all, 99.5)
            X_model = X_all[(X_all >= seuil_model) & (X_all < Pm_proxy)]
            if len(X_model) < 5: X_model = X_all[X_all >= seuil_model]
            t_min = np.min(X_model); n_model = len(X_model)
            alpha_est = n_model / np.sum(np.log(X_model / t_min))
            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col = df_gnpis_df.columns[1]
            df_proj_model = df_proj[(df_proj['Sprime_ultime'] >= seuil_model) & (df_proj['Sprime_ultime'] < Pm_proxy)]
            N_obs = df_proj_model.groupby('annee_surv').size()
            N_asif_vals = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except: N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0
            coeffs_raw = df_proj['coeff_stab'].values
            coeffs = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

            C_trav = next((t['portee'] for t in tranches_input if t['type'] == 'travaillante'), 13_000_000)
            res_maj = identifier_sinistres_majeurs(df_proj=df_proj, gnpi=gnpi, D=D_trav, C_tranche=C_trav,
                nb_annees_obs=df_proj['annee_surv'].nunique(), retour_ans=20)
            df_seuils, _ = selectionner_seuil_pareto(X=df_proj['Sprime_ultime'].values, D=D_trav)

            progress.progress(100, text="Terminé !")
            st.session_state.update({
                "df_liq": df_liq, "df_proj": df_proj, "f_moyens": f_moyens,
                "alpha_est": float(alpha_est), "lambda_est": float(lambda_est),
                "seuil_est": float(seuil_model), "Pm_proxy": float(Pm_proxy),
                "coeffs": coeffs, "is_long": is_long,
                "I_cotation": I_cotation_val, "annee_cotation": annee_cotation,
                "seuil_stabilisation": seuil_stabilisation,
                "df_gnpis_df": df_gnpis_df, "df_facteurs": df_facteurs_df,
                "res_majeurs": res_maj, "df_seuils_pareto": df_seuils,
                "chargement_majeurs": res_maj["chargement"],
            })
            st.success("✅ Transformation terminée !")

    if "df_liq" in st.session_state:
        # ── DIAGNOSTIC — ce que le parser a réellement lu ──
        with st.expander("🔎 Diagnostic parsing — Vérifiez que le triangle est bien lu", expanded=True):
            df_liq_diag = st.session_state["df_liq"]
            annees_surv  = sorted(df_liq_diag["annee_surv"].unique().tolist())
            annees_regl  = sorted(df_liq_diag["annee_reg"].unique().tolist())
            devs         = sorted(df_liq_diag["dev"].unique().tolist())
            st.markdown(f"""<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px">
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Années de survenance (UW Year)</b><br>
                    <span style="font-size:13px">{annees_surv[0]} → {annees_surv[-1]} | {len(annees_surv)} années</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Années de règlement (colonnes)</b><br>
                    <span style="font-size:13px">{annees_regl[0]} → {annees_regl[-1]} | {len(annees_regl)} années</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Développements trouvés</b><br>
                    <span style="font-size:13px">{devs}</span>
                </div>
                <div style="background:#f0fff4;border:1px solid #2d8a4e;border-radius:8px;padding:10px 16px">
                    <b style="color:#2d8a4e">Total observations</b><br>
                    <span style="font-size:13px">{len(df_liq_diag):,} lignes | {df_liq_diag['sinistre_id'].nunique():,} sinistres</span>
                </div></div>""", unsafe_allow_html=True)

            # Tableau récapitulatif par année de survenance
            recap = df_liq_diag.groupby("annee_surv").agg(
                nb_sinistres=("sinistre_id","nunique"),
                dev_max=("dev","max"),
                total_brut=("total","sum"),
                S_prime_moy=("S_prime_k","mean")
            ).reset_index()
            recap.columns = ["UW Year","Nb sinistres","Dev max obs.","Total brut (MAD)","S'k moyen (MAD)"]
            recap["Total brut (MAD)"] = recap["Total brut (MAD)"].apply(lambda x: f"{x:,.0f}")
            recap["S'k moyen (MAD)"]  = recap["S'k moyen (MAD)"].apply(lambda x: f"{x:,.0f}")
            st.markdown("**Résumé par année de survenance — si les années ne correspondent pas à votre fichier, vérifiez ci-dessous :**")
            st.dataframe(recap, use_container_width=True)

            # Afficher les 5 premières lignes brutes pour déboguer
            with st.expander("🔬 Données brutes parsées (5 premières lignes)", expanded=False):
                st.dataframe(df_liq_diag.head(10), use_container_width=True)
                st.caption("Si les années de survenance ou les montants sont faux → votre fichier a probablement une ligne de titre supplémentaire en haut, ou les colonnes TOTAL sont nommées différemment.")

        c1b, c2b, c3b = st.columns(3)
        c1b.metric("Observations", len(st.session_state['df_liq']))
        c2b.metric("Sinistres",    st.session_state['df_liq']['sinistre_id'].nunique())
        c3b.metric("Années",       st.session_state['df_liq']['annee_surv'].nunique())
        branch_label = "Longue" if st.session_state.get("is_long") else "Courte"
        st.info(f"🌿 Branche : **{branch_label}** | I_cotation({st.session_state.get('annee_cotation')}) = {st.session_state.get('I_cotation',1):.4f}")
        st.info(f"📐 Seuil : {st.session_state.get('seuil_est',0):,.0f} | Pm P99.5 : {st.session_state.get('Pm_proxy',0):,.0f} | Alpha : {st.session_state.get('alpha_est',0):.4f} | Lambda : {st.session_state.get('lambda_est',0):.4f}")
        if "res_majeurs" in st.session_state:
            res = st.session_state["res_majeurs"]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Sinistres majeurs",  res["n_majeurs"])
            c2.metric("Sinistres courants", res["n_courants"])
            c3.metric("Pm (niveau retour)", f"{res['Pm']:,.0f} MAD")
            c4.metric("Chargement majeurs", f"{res['chargement']:.4%}")
            with st.expander("📊 Détail sinistres majeurs"):
                st.dataframe(res["df_chargements"], use_container_width=True)
            if "df_seuils_pareto" in st.session_state:
                with st.expander("📊 Sélection seuil Pareto (TVE)"):
                    st.dataframe(st.session_state["df_seuils_pareto"], use_container_width=True)
        with st.expander("📊 Triangle — vérification stabilisation"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev','total','I_surv','I_reg','ratio_check','Sk','S_prime_k','coeff_stab']
            st.dataframe(st.session_state["df_liq"][[c for c in cols_show if c in st.session_state["df_liq"].columns]].head(50), use_container_width=True)
        if "df_facteurs" in st.session_state:
            with st.expander("📊 Facteurs Chain Ladder"):
                st.dataframe(st.session_state["df_facteurs"], use_container_width=True)
        if "df_proj" in st.session_state:
            with st.expander("📊 Projections"):
                st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════

with tab3:
    section_header("Burning Cost", "Charges historiques réassurance par tranche", "🔥")
    st.caption("Ck = min(max(S’k_ultime − D, 0), L) × coeff_stab")
    st.markdown("""<div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
        border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:12px">
        <b>R1</b> — τ_risque = τ_pur + σ_hist × 20% (écart-type BC annuels non nuls × chargement sécurité) —
        <b>R2</b> — Si années non nulles < 3 → τ_BC = 0 (données insuffisantes)
        </div>""", unsafe_allow_html=True)

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        if st.button("▶ Calculer le Burning Cost", type="primary"):
            with st.spinner("Calcul en cours..."):
                df_proj = st.session_state["df_proj"]
                resultats_bc = []
                for t_info in tranches_input:
                    D = t_info["priorite"]; L = t_info["portee"]
                    aal = t_info["AAL"]; aad = t_info["AAD"]
                    n_rec = t_info["nb_reconstitutions"]; t_r = t_info["taux_reconstitution"] / 100
                    cap = (n_rec + 1) * L
                    df_proj["Ck"] = df_proj.apply(
                        lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
                    charges_ann = df_proj.groupby("annee_surv")["Ck"].sum()
                    charges_finales = []
                    for ann, ch in charges_ann.items():
                        if aad: ch = max(ch - aad, 0)
                        if aal: ch = min(ch, aal)
                        ch = min(ch, cap)
                        charges_finales.append({"annee": ann, "charge": ch})
                    df_ch = pd.DataFrame(charges_finales); N = len(df_ch)
                    # Reconstitutions avec taux individuels par reconstitution
                    taux_rec_list = t_info.get("taux_reconstitutions", [t_info.get("taux_reconstitution", 100)] * n_rec)
                    Pr_Rec = 0.0
                    for C_n in df_ch["charge"].values:
                        for r_idx, t_r_i in enumerate(taux_rec_list):
                            Pr_Rec += (t_r_i / 100) * min(L, max(C_n - r_idx * L, 0))
                    Pr_Rec /= L if L > 0 else 1
                    Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0
                    charge_moy  = df_ch["charge"].mean()
                    charges_nonzero = [c for c in df_ch["charge"].values if c > 0]
                    n_ann_nonzero   = len(charges_nonzero)
                    charg_maj = st.session_state.get("chargement_majeurs", 0.0)
                    # R2 — Moins de 3 années non nulles → BC = 0 (données insuffisantes)
                    if n_ann_nonzero < 3:
                        taux_pur = taux_risque = taux_technique = 0.0
                        sigma_hist = 0.0
                    else:
                        taux_pur   = charge_moy / gnpi
                        sigma_hist = float(np.std(charges_nonzero)) / gnpi
                        # R1 — τ_risque = τ_pur + σ_hist × 20% (chargement sécurité)
                        taux_risque    = taux_pur + sigma_hist * 0.20
                        taux_technique = (taux_risque * (1 - Rec)) / (
                            1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"])
                    resultats_bc.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "charge_moy": charge_moy, "Pr_Rec": Pr_Rec, "Rec": Rec,
                        "n_ann_nonzero": n_ann_nonzero, "sigma_hist": sigma_hist if n_ann_nonzero >= 3 else 0.0,
                        "taux_pur": taux_pur, "taux_risque": taux_risque,
                        "taux_technique": taux_technique,
                        "chargement_majeurs": charg_maj,
                        "detail_annuel": df_ch.to_dict("records")
                    })
                st.session_state["resultats_bc"] = resultats_bc
                # ── Auto-save ──
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                    db_save_etape("bc", [{k:v for k,v in r.items() if k!="detail_annuel"} for r in resultats_bc])
                    st.toast("💾 BC sauvegardé", icon="✅")
                except Exception as _e:
                    st.toast(f"⚠️ Sauvegarde DB : {_e}", icon="⚠️")

    if "resultats_bc" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Type": r["type"],
            "Ans non-nuls": f"{r.get('n_ann_nonzero',0)} {'⚠️' if r.get('n_ann_nonzero',0)<3 else '✅'}",
            "Charge moy.": f"{r.get('charge_moy', r.get('charge_moy_MAD', 0)):,.0f} MAD",
            "σ hist.": f"{r.get('sigma_hist',0):.4%}",
            "Rec": f"{r['Rec']:.4%}",
            "Taux pur": f"{r['taux_pur']:.4%}", "Taux risque": f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Charg. majeurs": f"{r.get('chargement_majeurs', 0):.4%}",
        } for r in st.session_state["resultats_bc"]], titre="📊 Résultats Burning Cost")

        # ── Triangle individuel + traçabilité ──
        with st.expander("📐 Triangle individuel — 1 ligne = 1 sinistre", expanded=False):
            if "df_liq" in st.session_state:
                df_liq_bc = st.session_state["df_liq"].copy()
                st.markdown("""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;
                    border-radius:0 8px 8px 0;padding:10px 14px;margin-bottom:12px;font-size:12px">
                    <b>Logique :</b> 1️⃣ Chaque sinistre est projeté individuellement à l'ultime →
                    2️⃣ Charge XL individuelle : <code>Ck = min(max(S'ultime − D, 0), L)</code> →
                    3️⃣ Agrégation par UW Year = BC annuel
                    </div>""", unsafe_allow_html=True)

                etape_view = st.radio(
                    "Montants à afficher :",
                    ["1 Bruts Excel (TOTAL=PAID+OS)",
                     "2 As-If Sk",
                     "3 Stabilises Sprimek"],
                    key="tri_etape_view", horizontal=True)

                col_val = "total" if etape_view.startswith("1") else ("Sk" if etape_view.startswith("2") else "S_prime_k")

                # Triangle individuel : 1 ligne = 1 sinistre, colonnes = années règlement
                pivot_ind = df_liq_bc.pivot_table(
                    index=["annee_surv", "sinistre_id"],
                    columns="annee_reg",
                    values=col_val,
                    aggfunc="last"
                )
                pivot_ind.index.names = ["UW Year", "ID Sinistre"]
                pivot_ind.columns = [str(int(c)) for c in pivot_ind.columns]
                fmt_fn = getattr(pivot_ind, "map", getattr(pivot_ind, "applymap", None))
                st.markdown(f"**{len(pivot_ind)} sinistres × {len(pivot_ind.columns)} années de règlement**")
                st.dataframe(fmt_fn(lambda x: f"{x:,.0f}" if pd.notna(x) else "—"),
                             use_container_width=True, height=400)

                if etape_view.startswith("1"):
                    st.markdown("**Lignes brutes (30 premières) — comparez avec votre Excel :**")
                    df_chk = df_liq_bc[["sinistre_id","annee_surv","annee_reg","dev","total"]].head(30).copy()
                    df_chk["total"] = df_chk["total"].apply(lambda x: f"{x:,.0f}")
                    df_chk.columns = ["ID Sinistre","UW Year","Année règlement","Dev","TOTAL brut"]
                    st.dataframe(df_chk, use_container_width=True)

            if "df_proj" in st.session_state:
                st.divider()
                st.markdown("**S'prime_ultime individuel — projection de chaque sinistre à l'ultime :**")
                df_proj_show = st.session_state["df_proj"][
                    ["sinistre_id","annee_surv","dev_max","Sprime_ultime","coeff_stab"]].copy()
                df_proj_show["Sprime_ultime"] = df_proj_show["Sprime_ultime"].apply(lambda x: f"{x:,.0f}")
                df_proj_show["coeff_stab"]    = df_proj_show["coeff_stab"].apply(lambda x: f"{x:.4f}")
                df_proj_show.columns = ["ID Sinistre","UW Year","Dev max","S'prime ultime","Coeff stab."]
                st.dataframe(df_proj_show, use_container_width=True, height=300)
                st.caption(f"{len(df_proj_show)} sinistres individuels projetés")

            st.divider()
            st.markdown("**BC agrégé par UW Year (somme des Ck individuels) :**")
            for r in st.session_state["resultats_bc"]:
                detail = r.get("detail_annuel", [])
                if detail:
                    df_det = pd.DataFrame(detail)
                    df_det["charge"] = df_det["charge"].apply(lambda x: f"{x:,.0f}")
                    df_det.columns   = ["UW Year","Charge XL nette (MAD)"]
                    with st.expander(f"  {r['tranche']} | {r['type']} | tau_pur={r['taux_pur']:.4%}", expanded=False):
                        st.dataframe(df_det, use_container_width=True)



        st.divider()
        guide_prompt("Burning Cost",
            ["Sinistralité exceptionnelle 2020 (COVID)", "Portefeuille en croissance +15%/an", "Historique 10 ans, branche longue"],
            ["Comparer avec taux marché attendu 2-4%", "Signaler si BC < simulation de plus de 30%", "Identifier les années atypiques"],
            ["Taux BC N-1 : R&C=2.5%, CatL1=0%", "Objectif prime totale < 12M MAD", "Taux Partner Re 2025 : R&C=2.30%"],
            ["Tableau par tranche avec verdict ✅/⚠️/❌", "Recommandation unique par tranche", "Maximum 1 page"])

        st.markdown("### 🤖 Analyse Claude — Burning Cost")
        ctx_bc, inst_bc, inp_bc, out_bc = prompt_inputs(
            key_prefix="bc",
            placeholder_contexte="Ex: Sinistralité exceptionnelle 2020...",
            placeholder_instructions="Ex: Comparer avec taux marché 3-4%...",
            placeholder_input="Ex: Taux BC N-1 : R&C=2.5%",
            placeholder_output="Ex: Tableau par tranche + verdict OK/ALERTE/RÉVISER")

        if api_key and st.button("🤖 Recommandations Claude — BC"):
            prompt = build_prompt(
                role="Expert actuaire senior en reassurance non-proportionnelle automobile, 15 ans d'experience XL et cat.",
                task="1. Evalue le niveau du taux vs normes marche\n2. Verifie coherence inter-tranches\n3. Analyse impact Rec\n4. Verdict : OK | A verifier | Probleme",
                data=f"BC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}\nGNPI : {gnpi:,} MAD",
                contexte=ctx_bc, instructions=inst_bc, input_data=inp_bc, output_instructions=out_bc,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- tau_tech < tau_risque (Rec reduit - NORMAL)\n- BC=0 tranche cat NORMAL\n- Ne pas inventer comparatifs marche")
            claude_stream(api_key, prompt, max_tokens=2000, session_key="analyse_bc")

        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])

# ════════════════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════════════════

with tab4:
    st.header("Simulation Pareto / Poisson")
    st.caption("Simule S'0 sur Pareto — applique coeff Sk/S'k pour charge réassurance")

    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        # ══ Section 0 : Analyse distributions (Hill, MEF, CDF, fits) ══
        with st.expander("Analyse des distributions — Seuil · Hill · MEF · Gertensgarbe · Fits · CDF", expanded=False):
            section_analyse_distributions()
        is_long_sim = st.session_state.get("is_long", True)
        st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | Seuil : {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.number_input("Alpha",         value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
        with c2: st.number_input("Lambda",        value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
        with c3: st.number_input("Seuil (MAD)",   value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
        with c4: st.number_input("Nb simulations", value=10000, step=1000,               key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                alpha_f = st.session_state["alpha_input"]; lambda_f = st.session_state["lambda_input"]
                seuil_f = st.session_state["seuil_input"]; n_s = int(st.session_state["nsim_input"])
                coeffs  = st.session_state["coeffs"]
                np.random.seed(42)
                resultats_sim = []
                for idx_t, t_info in enumerate(tranches_input):
                    progress_sim.progress(int((idx_t/len(tranches_input))*100), text=f"Simulation {t_info['nom']}...")
                    D = t_info["priorite"]; P = t_info["portee"]
                    r = t_info["nb_reconstitutions"]; aal = t_info["AAL"]; aad = t_info["AAD"]
                    cap = (r + 1) * P

                    def simuler(avec_aal, avec_aad, avec_rec):
                        charges = []
                        for _ in range(n_s):
                            N = np.random.poisson(lambda_f); S_total = 0
                            if N > 0:
                                U = np.random.uniform(size=N)
                                Sprime_sim = seuil_f * (U ** (-1/alpha_f))
                                idx_c = np.random.choice(len(coeffs), size=N, replace=True)
                                for i in range(N):
                                    S_prime = Sprime_sim[i]; c = coeffs[idx_c[i]]
                                    if S_prime <= D: S_i = 0
                                    elif S_prime <= D + P: S_i = c * (S_prime - D)
                                    else: S_i = c * P
                                    S_total += S_i
                            ch = S_total
                            if avec_aad and aad: ch = max(ch - aad, 0)
                            if avec_aal and aal: ch = min(ch, aal)
                            charges.append(min(ch, cap) if avec_rec else ch)
                        return np.array(charges)

                    def calc_taux(ch):
                        P0 = np.mean(ch); sig = np.std(ch)
                        tp = P0 / gnpi; tr = (P0 + 0.2 * sig) / gnpi
                        tt = tr / (1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"])
                        return tp, tr, tt

                    c_base = simuler(True, True, True); c_sans_aal = simuler(False, True, True)
                    c_sans_aad = simuler(True, False, True); c_sans_rec = simuler(True, True, False)
                    tp, tr, tt = calc_taux(c_base)
                    tp2, tr2, tt2 = calc_taux(c_sans_aal)
                    tp3, tr3, tt3 = calc_taux(c_sans_aad)
                    tp4, tr4, tt4 = calc_taux(c_sans_rec)
                    resultats_sim.append({
                        "tranche": t_info["nom"], "type": t_info["type"],
                        "taux_pur": tp, "taux_risque": tr, "taux_technique": tt,
                        "chargement_majeurs": st.session_state.get("chargement_majeurs", 0.0),
                        "sans_aal": tt2, "sans_aad": tt3, "sans_rec": tt4,
                        "impact_aal": round(tt2 - tt, 6), "impact_aad": round(tt3 - tt, 6), "impact_rec": round(tt4 - tt, 6),
                    })
                progress_sim.progress(100, text="Terminé !")
                st.session_state["resultats_sim"] = resultats_sim
                # ── Auto-save ──
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                    db_save_etape("sim", resultats_sim)
                    st.toast("💾 Simulation sauvegardée", icon="✅")
                except Exception as _e:
                    st.toast(f"⚠️ Sauvegarde DB : {_e}", icon="⚠️")

    if "resultats_sim" in st.session_state:
        tableau_resultats([{
            "Tranche": r["tranche"], "Taux pur": f"{r['taux_pur']:.4%}",
            "Taux risque": f"{r['taux_risque']:.4%}", "Taux technique": f"{r['taux_technique']:.4%}",
            "Charg. majeurs": f"{r.get('chargement_majeurs', 0):.4%}",
            "Sans AAL": f"{r['sans_aal']:.4%}", "Sans AAD": f"{r['sans_aad']:.4%}",
            "Sans reconst.": f"{r['sans_rec']:.4%}",
        } for r in st.session_state["resultats_sim"]], titre="📊 Résultats Simulation")

        st.divider()
        guide_prompt("Simulation Pareto/Poisson",
            ["Alpha calibré sur données 2016-2025", "Lambda estimé sur portefeuille 183M MAD", "Seuil TVE retenu : p80 x D"],
            ["Analyser impact AAL sur tranche cat", "Comparer BC vs Simulation par tranche", "Recommander montant optimal des conditions"],
            ["Alpha R=1.45, Lambda R=3.2", "Résultats simulation N-1 : R&C=3.1%", "Période de retour majeurs : 20 ans"],
            ["Impact par condition en points de taux", "Classement NECESSAIRE/A AJUSTER/INUTILE", "Recommandation chiffrée par condition"])

        st.markdown("### 🤖 Analyse Claude — Simulation & Conditions")
        ctx_sim, inst_sim, inp_sim, out_sim = prompt_inputs(
            key_prefix="sim",
            placeholder_contexte="Ex: Nouveau modèle cat, lambda revu à la hausse...",
            placeholder_instructions="Ex: Seuil d'alerte écart = 20%...",
            placeholder_input="Ex: Résultats simulation N-1...",
            placeholder_output="Ex: Verdict par condition + impact en points de taux")

        if api_key and st.button("🤖 Recommandations Claude — Simulation"):
            prompt = build_prompt(
                role="Expert en modelisation catastrophe et simulation stochastique reassurance.",
                task="1. Impact par condition en points de taux\n2. Classe NECESSAIRE/A AJUSTER/INUTILE\n3. Montant optimal\n4. Compare BC vs Simulation",
                data=f"Simulation : {json.dumps(st.session_state['resultats_sim'], indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}",
                contexte=ctx_sim, instructions=inst_sim, input_data=inp_sim, output_instructions=out_sim,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Ne pas supprimer AAL sur cat\n- AAD trop eleve = tranche inutile\n- Ecart BC/Sim>50% = anomalie majeure")
            claude_stream(api_key, prompt, max_tokens=2000, session_key="analyse_sim")

        if "analyse_sim" in st.session_state:
            st.markdown(st.session_state["analyse_sim"])

# ════════════════════════════════════════════
# TAB 5 — MARKET CURVE
# ════════════════════════════════════════════

with tab5:
    st.header("Market Curve")
    st.caption("ROL = a x x^(-b)  |  x = (D + C/2) / GNPI  |  tau_pur = ROL x C / GNPI")
    st.markdown("""<div style="background:rgba(239,68,68,0.08);border-left:4px solid #ef4444;
        border-radius:0 8px 8px 0;padding:8px 14px;margin-bottom:8px;font-size:12px">
        ⚠️ <b>R4</b> — La market curve est utilisée <b>UNIQUEMENT pour les tranches cat</b>.
        Elle n’intervient pas dans la tarification de la tranche travaillante.
        Critères qualité : <b>R² ≥ 0.45</b>, <b>N ≥ 15 points</b>, <b>cohérence ROL T2 > T3</b>.
        </div>""", unsafe_allow_html=True)

    f_mkt = st.file_uploader("📁 Données marché", type=["xlsx","csv"], key="f_mkt")

    with st.expander("⚙️ Paramètres de filtrage", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            rol_min = st.number_input("ROL minimum (%)",  value=5.0,   step=1.0)  / 100
            rol_max = st.number_input("ROL maximum (%)",  value=100.0, step=10.0) / 100
        with c2:
            tolerance = st.number_input("Tolérance proximité ROL≈Midpoint (%)", value=50.0, step=5.0) / 100
            r2_min    = st.number_input("R² minimum accepté (%)", value=30.0, step=5.0) / 100
        with c3:
            filtre_branche = st.text_input("Filtre branche (INT_BUSINESS)", value="EVENEMENT")
            st.caption("Laisser vide = pas de filtre")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
            df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)
            df_mkt.columns = [c.strip() for c in df_mkt.columns]
            for col in ['ROLs', 'midpoints', 'Garantie en MAD', 'Priorité en MAD']:
                if col in df_mkt.columns and df_mkt[col].dtype == object:
                    df_mkt[col] = (df_mkt[col].astype(str).str.replace('%','').str.replace(' ','').str.replace(',','.')
                                   .apply(lambda x: float(x)/100 if x not in ['nan',''] and float(x) > 1.5
                                          else (float(x) if x not in ['nan',''] else np.nan)))
            df_mkt = df_mkt.dropna(subset=['ROLs', 'midpoints'])
            n_avant = len(df_mkt)
            if filtre_branche.strip():
                col_business = next((c for c in df_mkt.columns if 'BUSINESS' in c.upper()), None)
                if col_business:
                    df_mkt = df_mkt[df_mkt[col_business].astype(str).str.strip().str.upper()
                                    .str.contains(filtre_branche.strip().upper(), regex=False, na=False)]
            n_filtre = n_avant - len(df_mkt)
            mask_rol = (df_mkt['ROLs'] >= rol_min) & (df_mkt['ROLs'] <= rol_max)
            df_excl_rol = df_mkt[~mask_rol].copy(); df_mkt = df_mkt[mask_rol].copy(); n_rol = len(df_excl_rol)
            df_mkt['diff_rel'] = np.where(df_mkt['midpoints'] != 0,
                np.abs(df_mkt['ROLs'] - df_mkt['midpoints']) / np.abs(df_mkt['midpoints']), 1.0)
            df_excl_prox = df_mkt[df_mkt['diff_rel'] < tolerance].copy()
            df_mkt = df_mkt[df_mkt['diff_rel'] >= tolerance].copy(); n_prox = len(df_excl_prox)
            df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()
            st.markdown(f"""<div style="background:#f0fff4;border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;padding:12px 16px;margin:8px 0">
                ✅ <b>{len(df_mkt)} points retenus</b> sur {n_avant} | Filtre branche : {n_filtre} | ROL hors bornes : {n_rol} | ROL≈Midpoint : {n_prox}
                </div>""", unsafe_allow_html=True)
            if len(df_mkt) < 5:
                st.error("❌ Moins de 5 points retenus."); st.stop()

            def fit_power(x, y):
                log_x = np.log(x); log_y = np.log(y)
                coeffs = np.polyfit(log_x, log_y, 1)
                a = np.exp(coeffs[1]); b = -coeffs[0]
                log_y_pred = np.polyval(coeffs, log_x)
                r2 = 1 - np.sum((log_y-log_y_pred)**2) / np.sum((log_y-log_y.mean())**2)
                return a, b, r2

            def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))

            def calc_taux_tranche(t, a, b):
                x_norm = (t['priorite'] + t['portee'] / 2) / gnpi
                rol = predict_rol(x_norm, a, b)
                taux_pur = rol * (t['portee'] / gnpi)
                taux_risque = taux_pur * 1.002
                taux_tech = taux_risque / (1 - t['brokage'] - t['frais'] - t['marge'] - t['retrocession'])
                n_rec = t['nb_reconstitutions']; t_r = t['taux_reconstitution'] / 100; L = t['portee']
                C_rep = taux_pur * gnpi
                Pr_Rec = sum(t_r * min(L, max(C_rep - (r-1)*L, 0)) for r in range(1, n_rec+1))
                Pr_Rec /= L if L > 0 else 1
                Rec = Pr_Rec / (Pr_Rec + 10) if (Pr_Rec + 10) > 0 else 0
                charg_maj_mkt = st.session_state.get("chargement_majeurs", 0.0)
                return {"tranche": t["nom"], "type": t["type"], "x_norm": x_norm,
                        "rol": rol, "taux_pur": taux_pur, "taux_tech": taux_tech,
                        "chargement_majeurs": charg_maj_mkt, "taux": taux_tech}

            resultats_mkt = []
            for q in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]:
                mid_max = np.quantile(df_mkt['midpoints'], q)
                port_max = np.quantile(df_mkt['Garantie en MAD'], q) if 'Garantie en MAD' in df_mkt.columns else np.inf
                df_q = df_mkt[(df_mkt['midpoints'] <= mid_max) &
                               (df_mkt['Garantie en MAD'] <= port_max if 'Garantie en MAD' in df_mkt.columns else True)]
                if len(df_q) < 5: continue
                try:
                    a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
                    if b <= 0: continue
                    taux_tranches = []; taux_nuls = 0
                    for t in tranches_input:
                        tt = calc_taux_tranche(t, a, b)
                        if tt['taux'] <= 0 or np.isnan(tt['taux']) or np.isinf(tt['taux']): taux_nuls += 1
                        taux_tranches.append(tt)
                    if taux_nuls > 0: continue
                    taux_vals = [tt["taux"] for tt in taux_tranches]
                    median_taux = np.median(taux_vals)
                    cv_taux = np.std(taux_vals) / median_taux if median_taux > 0 else 99
                    resultats_mkt.append({"quantile": q, "n_points": len(df_q), "a": a, "b": b,
                                          "r2": r2, "cv_taux": cv_taux, "taux_tranches": taux_tranches,
                                          "r2_ok": r2 >= r2_min})
                except: continue

            if not resultats_mkt:
                st.warning("⚠️ Relâchement contrainte.")
                for q in [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.0]:
                    mid_max = np.quantile(df_mkt['midpoints'], q)
                    df_q = df_mkt[df_mkt['midpoints'] <= mid_max]
                    if len(df_q) < 5: continue
                    try:
                        a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
                        if b <= 0: continue
                        taux_tranches = [calc_taux_tranche(t, a, b) for t in tranches_input]
                        taux_vals = [tt["taux"] for tt in taux_tranches]
                        median_taux = np.median(taux_vals)
                        cv_taux = np.std(taux_vals) / median_taux if median_taux > 0 else 99
                        resultats_mkt.append({"quantile": q, "n_points": len(df_q), "a": a, "b": b,
                                              "r2": r2, "cv_taux": cv_taux, "taux_tranches": taux_tranches,
                                              "r2_ok": r2 >= r2_min})
                    except: continue

            if not resultats_mkt:
                st.error("❌ Impossible d'ajuster la courbe."); st.stop()

            all_t = [tt["taux"] for r in resultats_mkt for tt in r.get("taux_tranches",[])]
            med_g = np.median([t for t in all_t if t > 0]) if any(t > 0 for t in all_t) else 1
            r2v = [r["r2"] for r in resultats_mkt]; r2min_v, r2max_v = min(r2v), max(r2v)
            for r in resultats_mkt:
                tm = np.mean([tt["taux"] for tt in r.get("taux_tranches",[])])
                r2_norm = (r["r2"] - r2min_v) / (r2max_v - r2min_v + 1e-10)
                ecart_med = abs(tm - med_g) / (med_g + 1e-10)
                taux_nuls = sum(1 for tt in r.get("taux_tranches",[]) if tt.get("taux",0) <= 0)
                r["score"] = 0.5*r2_norm - 0.3*ecart_med - 0.2*r["cv_taux"] - taux_nuls*10.0 + (0.5 if r["r2_ok"] else 0)
            resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)
            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt
            # ── Auto-save ──
            try:
                db_save_etape("mkt", {"resultats_mkt": [{k:v for k,v in r.items() if k!="taux_tranches"} for r in resultats_mkt],
                                      "taux_mkt_final": resultats_mkt[0]["taux_tranches"] if resultats_mkt else []})
                st.toast("💾 Market Curve sauvegardée", icon="✅")
            except Exception as _e:
                st.toast(f"⚠️ Sauvegarde DB : {_e}", icon="⚠️")

    if "resultats_mkt" in st.session_state and "df_mkt_clean" in st.session_state:
        rmt = st.session_state.get("resultats_mkt", [])
        # Vérification du format : resultats_mkt doit contenir des dicts avec clé "quantile"
        # (pas taux_mkt_final qui a un format différent)
        if rmt and not isinstance(rmt[0], dict):
            rmt = []
        if rmt and "quantile" not in rmt[0]:
            rmt = []
        dmc = st.session_state.get("df_mkt_clean")
        def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))
        if not rmt or dmc is None:
            st.info("Market curve non disponible pour cette session. Lancez le calcul dans l'onglet Market Curve.")
        else:
            rows_recap = []
            for r in rmt:
                row = {"Q": f"Q{int(r['quantile']*100)}", "N": r["n_points"],
                       "a": f"{r['a']:.5f}", "b": f"{r['b']:.4f}",
                       "R2": f"{r['r2']:.4f}", "R2ok": "OK" if r["r2_ok"] else "faible",
                       "Score": f"{r['score']:.4f}"}
                for tt in r.get("taux_tranches",[]):
                    row[tt["tranche"]] = f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
                rows_recap.append(row)
            st.subheader("Comparaison ajustements — ROL = a x x^(-b)  |  x = (D+C/2)/GNPI")
            tableau_resultats(rows_recap)
            best = rmt[0]
            st.success(f"Meilleur : Q{int(best['quantile']*100)} — a={best['a']:.5f}, b={best['b']:.4f} | R2={best['r2']:.4f} | Score={best['score']:.4f}")

            choix_q = st.selectbox("Choisir la combinaison",
                options=[f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} R2={r['r2']:.4f} Score={r['score']:.4f}" for r in rmt], index=0)
            idx_choix = [f"Q{int(r['quantile']*100)} — a={r['a']:.5f} b={r['b']:.4f} R2={r['r2']:.4f} Score={r['score']:.4f}" for r in rmt].index(choix_q)
            choix = rmt[idx_choix]

            x_all = dmc['midpoints'].values; y_all = dmc['ROLs'].values
            x_range = np.linspace(min(x_all), max(x_all), 300)
            y_fit = predict_rol(x_range, choix['a'], choix['b'])
            fig, ax = plt.subplots(figsize=(10, 5))
            fig.patch.set_facecolor('#f5f5f5'); ax.set_facecolor('#fafafa')
            ax.scatter(x_all, y_all, color='#2d8a4e', s=60, zorder=5, alpha=0.7, label='Données marché')
            ax.plot(x_range, y_fit, color='#1a1a1a', lw=2.5,
                    label=f"ROL = {choix['a']:.5f} x x^(-{choix['b']:.4f}) | R2={choix['r2']:.4f}")
            ax.set_xlabel('Midpoint normalisé x = (D+C/2)/GNPI'); ax.set_ylabel('ROL')
            ax.set_title('Market Curve — ROL = a x x^(-b)', fontweight='bold', color='#1a1a1a')
            ax.legend(); ax.grid(alpha=0.3, linestyle='--')
            st.pyplot(fig)

            st.subheader("Taux marché retenus")
            tableau_resultats([{
                "Tranche": tt["tranche"], "Type": tt["type"],
                "x=(D+C/2)/GNPI": f"{tt['x_norm']:.5f}",
                "ROL estimé": f"{tt['rol']:.4%}", "Taux pur": f"{tt['taux_pur']:.4%}",
                "Taux tech.": f"{tt['taux_tech']:.4%}",
                "Taux final": f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
            } for tt in choix.get("taux_tranches",[])])
            st.session_state["taux_mkt_final"] = choix.get("taux_tranches",[])

        st.divider()
        guide_prompt("Market Curve",
            ["Marché 2025, 40 cotations XL événement", "Marché en durcissement +10-15%", "Modèle puissance ROL = a x x^(-b)"],
            ["Privilégier R2 >= 45% avec taux non nuls", "Signaler taux marché > 3x simulation", "Recommander UN seul ajustement"],
            ["Taux référence Cat L1=1.5%", "a=0.0487, b=0.605 (rapport FST)", "R2 acceptable > 40%"],
            ["Justification R2 + robustesse N", "Comparaison avec simulation", "Ajustement retenu avec a, b, R2"])

        st.markdown("### 🤖 Analyse Claude — Market Curve")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs(
            key_prefix="mkt",
            placeholder_contexte="Ex: Marché en durcissement, hausse 15%...",
            placeholder_instructions="Ex: Privilégier N > 20 points...",
            placeholder_input="Ex: Taux référence Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification R2")

        if api_key and st.button("🤖 Recommandations Claude — Market Curve"):
            prompt = build_prompt(
                role="Expert en reassurance catastrophe et market curve, specialiste marches emergents.",
                task=f"Analyse ajustements market curve. Critere : R2>={r2_min*100:.0f}% avec taux non nuls prime. Recommande UN seul ajustement justifie.",
                data=f"Ajustements : {json.dumps(rows_recap, indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}\nGNPI : {gnpi:,} MAD",
                contexte=ctx_mkt, instructions=inst_mkt, input_data=inp_mkt, output_instructions=out_mkt,
                contexte_global=st.session_state.get("instructions_globales", ""),
                contraintes=f"- b>0 obligatoire\n- R2>={r2_min*100:.0f}% avec taux non nuls preferable\n- N<10 faible robustesse\n- Taux>3x simulation=suspect")
            claude_stream(api_key, prompt, max_tokens=1500, session_key="analyse_mkt")

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])

# ════════════════════════════════════════════
# TAB 6 — RAPPORT FINAL
# ════════════════════════════════════════════

with tab6:
    st.header("Rapport Final de Tarification")
    st.markdown("""<div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
        border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:12px">
        <b>Règles de sélection finale</b> —
        T1 (travaillante) : max(τ_BC, τ_Sim) |
        T2, T3 (cat) : max(τ_Sim, τ_Marché) —
        Market curve appliquée <b>uniquement aux tranches cat</b>.
        </div>""", unsafe_allow_html=True)
    manquants = [n for n, k in [("BC","resultats_bc"),("Simulation","resultats_sim"),("Market Curve","taux_mkt_final")]
                 if k not in st.session_state]
    if manquants:
        st.warning(f"⚠️ Complétez d'abord : {', '.join(manquants)}")
    else:
        _bc_list  = st.session_state["resultats_bc"]
        _sim_list = st.session_state["resultats_sim"]
        _mkt_list = st.session_state["taux_mkt_final"]
        rows_rapport = []; prime_totale = 0
        for idx_t, t in enumerate(tranches_input):
            nom = t["nom"]
            bc_tt  = _lookup_taux(_bc_list,  nom, idx_t, "taux_technique")
            sim_tt = _lookup_taux(_sim_list, nom, idx_t, "taux_technique")
            # Market curve uniquement pour tranches cat
            mkt = _lookup_taux(_mkt_list, nom, idx_t, "taux") if t["type"] != "travaillante" else 0.0
            if t["type"] == "travaillante":
                # T1 : max(BC, Sim) — méthode la plus conservative
                taux_retenu = max(bc_tt, sim_tt)
                methode_base = "BC" if bc_tt >= sim_tt else "Simulation"
                ecart = abs(bc_tt-sim_tt)/max(bc_tt,sim_tt)*100 if max(bc_tt,sim_tt)>0 else 0
                methode = f"max(BC,Sim)→{methode_base} | écart {ecart:.0f}% {'⚠️' if ecart>25 else '✅'}"
            else:
                # T2, T3 cat : max(Sim, Marché) — toujours côté sécurité
                taux_retenu = max(sim_tt, mkt)
                methode = f"max(Sim,Mkt)→{'Marché' if mkt >= sim_tt else 'Simulation'}"
            prime = gnpi * taux_retenu; prime_totale += prime
            rows_rapport.append({
                "Tranche": nom, "Type": t["type"],
                "Taux BC": f"{bc_tt:.4%}", "Taux Sim.": f"{sim_tt:.4%}",
                "Taux Marché": f"{mkt:.4%}", "Taux retenu": f"{taux_retenu:.4%}",
                "Prime (MAD)": f"{prime:,.0f}", "Méthode": methode
            })
        st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
        st.session_state["prime_totale"] = prime_totale
        # ── Auto-save rapport ──
        try:
            db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
            db_save_etape("rapport", {"rows": rows_rapport, "prime_totale": prime_totale})
            st.toast("💾 Rapport sauvegardé", icon="✅")
        except Exception as _e:
            st.toast(f"⚠️ Sauvegarde DB : {_e}", icon="⚠️")
        st.subheader("📊 Synthèse de tarification")
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        with c1: card("Prime totale", f"{prime_totale:,.0f} MAD", couleur="#2d8a4e", icone="💰")
        with c2: card("Taux global",  f"{prime_totale/gnpi:.4%}", couleur="#1a1a1a",  icone="📊")
        with c3: card("Tranches",     str(len(tranches_input)),   couleur="#2d8a4e",  icone="📋")

        # ── EXPORT PDF + EXCEL ──
        st.markdown("### 📥 Exports")
        col_pdf, col_xls, col_name = st.columns([1, 1, 2])
        with col_pdf:
            if st.button("📄 Télécharger PDF", type="primary", use_container_width=True):
                try:
                    with st.spinner("Génération PDF..."):
                        pdf_bytes = generer_pdf_rapport(
                            user_email=st.session_state.get("user_email",""),
                            gnpi_val=gnpi,
                            tranches=tranches_input,
                            resultats_bc=st.session_state.get("resultats_bc",[]),
                            resultats_sim=st.session_state.get("resultats_sim",[]),
                            taux_mkt_final=st.session_state.get("taux_mkt_final",[]),
                            df_rapport=st.session_state.get("df_rapport"),
                            prime_totale=prime_totale,
                            analyse_claude=st.session_state.get("reco_finale",""),
                            annee=2026
                        )
                    st.download_button(
                        "⬇️ Cliquer pour télécharger",
                        data=pdf_bytes,
                        file_name=f"atlantic_re_rapport_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.success("✅ PDF prêt !")
                except Exception as e_pdf:
                    st.error(f"Erreur PDF : {e_pdf}")
        with col_xls:
            if st.button("📊 Télécharger Excel", use_container_width=True):
                try:
                    import io as _io_xls
                    xls_buf = _io_xls.BytesIO()
                    with pd.ExcelWriter(xls_buf, engine='openpyxl') as writer:
                        st.session_state["df_rapport"].to_excel(writer, sheet_name="Rapport", index=False)
                        if st.session_state.get("resultats_bc"):
                            pd.DataFrame([{k:v for k,v in r.items() if k!="detail_annuel"}
                                           for r in st.session_state["resultats_bc"]]).to_excel(
                                writer, sheet_name="Burning Cost", index=False)
                        if st.session_state.get("resultats_sim"):
                            pd.DataFrame(st.session_state["resultats_sim"]).to_excel(
                                writer, sheet_name="Simulation", index=False)
                    st.download_button(
                        "⬇️ Cliquer pour télécharger",
                        data=xls_buf.getvalue(),
                        file_name=f"atlantic_re_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                    st.success("✅ Excel prêt !")
                except Exception as e_xls:
                    st.error(f"Erreur Excel : {e_xls}")
        with col_name:
            nom_session_input = st.text_input("💾 Nommer cette session",
                placeholder="Ex: Atlantic Re 2026 — Version finale",
                key="nom_session_input")
            if st.button("Enregistrer le nom", key="btn_save_nom"):
                try:
                    db_save_session(st.session_state.get("user_email",""), gnpi,
                                    tranches_input, nom=nom_session_input)
                    st.success(f"✅ Session nommée : {nom_session_input}")
                except Exception as _e: st.error(str(_e))

        st.divider()
        guide_prompt("Rapport Final",
            ["Négociation avec Partner Re / Munich Re", "Comité de tarification 15 janvier 2026", "Objectif prime < 14M MAD"],
            ["Justifier chaque taux retenu vs alternatives", "Comparer avec taux N-1 fournis", "Conclure sur positionnement vs marché"],
            ["Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%", "Cotation Partner Re : R&C=2.30%", "Chargement majeurs = 0.05%"],
            ["Synthèse exécutive 5 lignes max", "Tableau récapitulatif final obligatoire", "Verdict : ACCEPTER / NEGOCIER / REFUSER"])

        st.markdown("### 🤖 Rapport Claude — Analyse finale")
        ctx_r, inst_r, inp_r, out_r = prompt_inputs(
            key_prefix="rapport",
            placeholder_contexte="Ex: Négociation réassureur XYZ, objectif prime < 14M MAD...",
            placeholder_instructions="Ex: Justifier chaque taux, comparer avec N-1...",
            placeholder_input="Ex: Taux N-1 : R&C=3.1%, CatL1=1.2%, CatL2=0.8%",
            placeholder_output="Ex: Rapport 1 page max, tableau synthèse obligatoire")

        if api_key and st.button("🤖 Générer le rapport Claude", type="primary"):
            prompt = build_prompt(
                role="Expert senior tarification reassurance non-proportionnelle, specialiste automobile marches emergents.",
                task="1. SYNTHESE EXECUTIVE (5 lignes max)\n2. ANALYSE PAR TRANCHE (BC/Sim/Marche -> Verdict)\n3. COHERENCE INTER-METHODES\n4. ANOMALIES\n5. TABLEAU FINAL\n6. RECOMMANDATION GLOBALE",
                data=f"Rapport : {json.dumps(rows_rapport, indent=2)}\nBC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}\nSim : {json.dumps(st.session_state['resultats_sim'], indent=2)}\nGNPI : {gnpi:,} MAD | Prime : {prime_totale:,.0f} MAD | Taux global : {prime_totale/gnpi:.4%}",
                contexte=ctx_r, instructions=inst_r, input_data=inp_r, output_instructions=out_r,
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Ne jamais recommander taux < taux pur\n- BC=0 cat = normal\n- Mentionner incertitudes et limites")
            claude_stream(api_key, prompt, max_tokens=2500, session_key="reco_finale")

    if "reco_finale" in st.session_state:
        st.divider()
        st.subheader("🤖 Rapport Claude")
        st.markdown(st.session_state["reco_finale"])

    # ── Optimisation A/B/C ──
    if (st.session_state.get("resultats_sim") and
        st.session_state.get("resultats_bc")  and
        st.session_state.get("df_rapport") is not None):
        if st.button("⚡ Générer les variantes de programme optimal (A/B/C)", type="primary", key="btn_optim"):
            with st.spinner("Optimisation en cours..."):
                variantes = optimiser_programme_variantes(
                    tranches_input, gnpi,
                    st.session_state["resultats_sim"],
                    st.session_state["resultats_bc"],
                    st.session_state.get("taux_mkt_final", []))
                st.session_state["variantes_optimisation"] = variantes
        if "variantes_optimisation" in st.session_state:
            afficher_variantes_optimisation(
                st.session_state["variantes_optimisation"],
                gnpi, tranches_input)

    # ── Panneau Audit Managers ──
    if (st.session_state.get("resultats_bc") and
        st.session_state.get("resultats_sim") and
        st.session_state.get("df_rapport") is not None):
        afficher_panneau_audit(
            tranches_input,
            st.session_state["resultats_bc"],
            st.session_state["resultats_sim"],
            st.session_state.get("taux_mkt_final", []),
            st.session_state["df_rapport"],
            st.session_state.get("prime_totale", 0),
            gnpi)


# ════════════════════════════════════════════
# MODULE AGENTIQUE V2 — RAISONNEMENT · CRITIQUE · ML · MÉMOIRE · CHALLENGER
# ════════════════════════════════════════════

class AgentRaisonnement:
    def planifier(self, contexte):
        plan = []
        def add(code, titre, justification, priorite="normale"):
            plan.append({"code":code,"titre":titre,"justification":justification,"priorite":priorite})
        add("validation","Valider les paramètres","Contrôler alpha, lambda, GNPI, tranches.","haute")
        if contexte.get("has_triangle"):
            add("burning_cost","Calculer le Burning Cost","Triangle disponible — lecture historique.","haute")
        else:
            add("missing_triangle","Bloquer le BC","Aucune donnée projetée — BC non simulable.","critique")
        add("simulation","Lancer la simulation","Comparer expérience historique et vision stochastique.","haute")
        if contexte.get("has_market"):
            add("market_curve","Ajuster la Market Curve","Données marché disponibles — benchmark cat.","normale")
        else:
            add("market_curve_skip","Ignorer la Market Curve","Aucune donnée marché fiable.","normale")
        add("critique","Auditer les résultats","Détecter incohérences et taux extrêmes.","haute")
        if contexte.get("n_rows",0) >= 30:
            add("machine_learning","Tester des modèles ML","Volume minimal disponible.","normale")
        else:
            add("machine_learning_skip","Ne pas surinterpréter le ML","Volume trop faible pour ML robuste.","normale")
        add("selection","Sélectionner le taux retenu","Appliquer règle prudente par tranche.","haute")
        add("negociation","Proposer des variantes","Programmes selon intérêt cédante/réassureur.","normale")
        return plan


class AgentCritique:
    def __init__(self, seuil_ecart_warn=0.30, seuil_ecart_critique=0.50, seuil_taux_extreme=0.50):
        self.seuil_ecart_warn = seuil_ecart_warn
        self.seuil_ecart_critique = seuil_ecart_critique
        self.seuil_taux_extreme = seuil_taux_extreme

    @staticmethod
    def _map_by_name(rows):
        return {r.get("tranche",r.get("Tranche","")): r for r in (rows or [])}

    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "": return default
            if isinstance(x, str):
                return float(x.replace("%","").replace(",",".").strip())
            return float(x)
        except: return default

    def auditer(self, tranches, gnpi, resultats_bc, resultats_sim, resultats_mkt, rapport_rows):
        alertes = []; decisions = []; score = 100
        bc_map = self._map_by_name(resultats_bc)
        sim_map = self._map_by_name(resultats_sim)
        mkt_map = self._map_by_name(resultats_mkt)
        rpt_map = self._map_by_name(rapport_rows)

        def alerte(niveau, tranche, message, impact=-5):
            nonlocal score
            alertes.append({"niveau":niveau,"tranche":tranche,"message":message})
            score += impact

        for i, t in enumerate(tranches or []):
            nom = t.get("nom",f"Tranche {i+1}"); typ = t.get("type","")
            bc=bc_map.get(nom,{}); sim=sim_map.get(nom,{}); rpt=rpt_map.get(nom,{})
            bc_pur=self._num(bc.get("taux_pur")); bc_risque=self._num(bc.get("taux_risque"))
            bc_tech=self._num(bc.get("taux_technique")); sim_tech=self._num(sim.get("taux_technique"))
            retenu=self._num(rpt.get("taux_retenu"))
            n_nz = int(self._num(bc.get("n_ann_nonzero"),0))

            if bc_tech>0 and not (bc_pur<=bc_risque<=bc_tech+1e-12):
                alerte("CRITIQUE",nom,"Hiérarchie BC incohérente : τ_pur ≤ τ_risque ≤ τ_tech non respectée.",-15)

            if n_nz<3 and typ=="travaillante":
                alerte("WARN",nom,f"BC fragile : {n_nz} année(s) non nulle(s). Simulation prioritaire.",-6)
            elif n_nz<3 and typ=="cat":
                decisions.append({"tranche":nom,"decision":"BC nul acceptable pour tranche cat."})

            if bc_tech>0 and sim_tech>0:
                ecart=abs(bc_tech-sim_tech)/max(bc_tech,1e-12)
                if ecart>=self.seuil_ecart_critique:
                    alerte("CRITIQUE",nom,f"Écart BC/Sim très élevé : {ecart:.0%}. Vérifier seuil et stabilisation.",-15)
                elif ecart>=self.seuil_ecart_warn:
                    alerte("WARN",nom,f"Écart BC/Sim significatif : {ecart:.0%}. Justification obligatoire.",-8)

            for label,val in [("BC",bc_tech),("Sim",sim_tech),("Retenu",retenu)]:
                if val<0: alerte("CRITIQUE",nom,f"Taux {label} négatif.",-20)
                if 0<val>self.seuil_taux_extreme: alerte("CRITIQUE",nom,f"Taux {label} > {self.seuil_taux_extreme:.0%}.",-20)

            if t.get("portee",0)<=0 or t.get("priorite",0)<0:
                alerte("CRITIQUE",nom,"Priorité ou portée invalide.",-20)

        score=max(0,min(100,score))
        verdict="ROBUSTE" if score>=85 else "ACCEPTABLE AVEC RÉSERVES" if score>=65 else "À REVOIR"
        return {"synthese":{"score":score,"verdict":verdict,"nb_alertes":len(alertes),
                "nb_critiques":sum(1 for a in alertes if a["niveau"]=="CRITIQUE"),
                "nb_warn":sum(1 for a in alertes if a["niveau"]=="WARN")},
                "alertes":alertes,"decisions":decisions}


class AgentML:
    def __init__(self, random_state=42): self.random_state=random_state

    def entrainer_depuis_df_proj(self, df, target="Sprime_ultime"):
        try:
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            from sklearn.tree import DecisionTreeRegressor
            from sklearn.ensemble import RandomForestRegressor
        except Exception as e:
            return {"disponible":False,"message":f"scikit-learn indisponible : {e}","modeles":[],"meilleur_modele":None,"importance":[]}

        if df is None or df.empty or target not in df.columns:
            return {"disponible":False,"message":"Target indisponible.","modeles":[],"meilleur_modele":None,"importance":[]}

        data=df.copy().replace([np.inf,-np.inf],np.nan)
        y=pd.to_numeric(data[target],errors="coerce"); X=data.drop(columns=[target],errors="ignore")
        keep=[c for c in X.columns if X[c].notna().mean()>=0.60]; X=X[keep]
        for c in X.columns:
            if X[c].dtype=="object": X[c]=X[c].astype(str).fillna("NA")
            else: X[c]=pd.to_numeric(X[c],errors="coerce")
        mask=y.notna(); X=X.loc[mask].copy(); y=y.loc[mask].copy()
        if len(X)<30: return {"disponible":False,"message":"Moins de 30 observations exploitables.","modeles":[],"meilleur_modele":None,"importance":[]}
        X_enc=pd.get_dummies(X,dummy_na=True).fillna(0)

        X_tr,X_te,y_tr,y_te=train_test_split(X_enc,y,test_size=0.25,random_state=self.random_state)
        models={"Arbre":DecisionTreeRegressor(max_depth=4,min_samples_leaf=5,random_state=self.random_state),
                "Random Forest":RandomForestRegressor(n_estimators=250,max_depth=8,min_samples_leaf=3,random_state=self.random_state,n_jobs=-1)}
        try:
            from xgboost import XGBRegressor
            models["XGBoost"]=XGBRegressor(n_estimators=300,max_depth=4,learning_rate=0.05,subsample=0.85,colsample_bytree=0.85,objective="reg:squarederror",random_state=self.random_state)
        except: pass

        resultats=[]; best_name=None; best_mae=None; best_model=None
        for name,model in models.items():
            try:
                model.fit(X_tr,y_tr); pred=model.predict(X_te)
                mae=float(mean_absolute_error(y_te,pred)); rmse=float(np.sqrt(mean_squared_error(y_te,pred))); r2=float(r2_score(y_te,pred))
                resultats.append({"modele":name,"MAE":mae,"RMSE":rmse,"R2":r2,"n_train":int(len(X_tr)),"n_test":int(len(X_te))})
                if best_mae is None or mae<best_mae: best_mae=mae; best_name=name; best_model=model
            except Exception as e:
                resultats.append({"modele":name,"MAE":None,"RMSE":None,"R2":None,"erreur":str(e)})

        importance=[]
        if best_model is not None and hasattr(best_model,"feature_importances_"):
            imp=pd.Series(best_model.feature_importances_,index=X_enc.columns).sort_values(ascending=False).head(10)
            importance=[{"variable":k,"importance":float(v)} for k,v in imp.items()]

        return {"disponible":True,"message":"Benchmark ML exécuté. Interprétation prudente recommandée.",
                "modeles":resultats,"meilleur_modele":best_name,"importance":importance}


class AgentMemoireMetier:
    @staticmethod
    def _to_float(x, default=0.0):
        try:
            if x is None or x=="": return default
            if isinstance(x,str):
                s=x.replace("%","").replace(" ","").replace(",",".")
                val=float(s); return val/100 if "%"in x or val>1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _row_get(row,*keys,default=None):
        for k in keys:
            if isinstance(row,dict) and k in row: return row.get(k)
        return default

    def charger_rapports_historiques(self, user_email, current_session_id=None, limite=100):
        try:
            con,db=_get_conn(); cur=con.cursor(); p=_ph()
            if current_session_id:
                cur.execute(f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                    JOIN resultats r ON r.session_id=s.id
                    WHERE s.user_email={p} AND r.etape='rapport' AND s.id!={p}
                    ORDER BY s.updated_at DESC LIMIT {int(limite)}""",(user_email,current_session_id))
            else:
                cur.execute(f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                    JOIN resultats r ON r.session_id=s.id
                    WHERE s.user_email={p} AND r.etape='rapport'
                    ORDER BY s.updated_at DESC LIMIT {int(limite)}""",(user_email,))
            rows=cur.fetchall(); con.close()
        except: return []
        historiques=[]
        for sid,nom,gnpi_h,data_json in rows:
            try:
                d=json.loads(data_json); rr=d.get("rows",[]); pt=d.get("prime_totale",0)
                if rr: historiques.append({"session_id":sid,"nom_session":nom,"gnpi":gnpi_h,"prime_totale":pt,"rows":rr})
            except: continue
        return historiques

    def benchmark(self, user_email, tranches, rapport_rows, gnpi, current_session_id=None):
        historiques=self.charger_rapports_historiques(user_email,current_session_id=current_session_id)
        if not historiques:
            return {"disponible":False,"message":"Aucun ancien rapport exploitable dans la mémoire métier.","comparaisons":[],"synthese":{}}
        current_by_type={}
        for r in rapport_rows or []:
            typ=str(self._row_get(r,"type","Type",default="")).lower()
            taux=self._to_float(self._row_get(r,"taux_retenu","Taux retenu",default=0))
            if typ and taux>0: current_by_type.setdefault(typ,[]).append(taux)
        hist_by_type={}; hist_global=[]
        for h in historiques:
            rows=h.get("rows",[]); pt=self._to_float(h.get("prime_totale",0)); gh=self._to_float(h.get("gnpi",0))
            if gh>0 and pt>0: hist_global.append(pt/gh)
            for r in rows:
                typ=str(self._row_get(r,"type","Type",default="")).lower()
                taux=self._to_float(self._row_get(r,"taux_retenu","Taux retenu",default=0))
                if typ and taux>0: hist_by_type.setdefault(typ,[]).append(taux)
        comparaisons=[]
        for typ,vals in current_by_type.items():
            if typ not in hist_by_type or len(hist_by_type[typ])<2: continue
            cur_med=float(np.median(vals)); hist_med=float(np.median(hist_by_type[typ]))
            hist_q25=float(np.quantile(hist_by_type[typ],0.25)); hist_q75=float(np.quantile(hist_by_type[typ],0.75))
            ecart=(cur_med-hist_med)/max(hist_med,1e-12)
            comparaisons.append({"type":typ,"taux_dossier":cur_med,"mediane_historique":hist_med,
                "q25_historique":hist_q25,"q75_historique":hist_q75,"ecart_vs_mediane":ecart,
                "diagnostic":"au-dessus" if ecart>0.20 else "sous la référence" if ecart<-0.20 else "proche de l'historique",
                "n_reference":len(hist_by_type[typ])})
        pt_curr=sum(self._to_float(self._row_get(r,"prime_MAD","Prime (MAD)",default=0)) for r in rapport_rows or [])
        tg=pt_curr/gnpi if gnpi else 0
        return {"disponible":True,"message":"Mémoire métier activée.","comparaisons":comparaisons,
                "synthese":{"nb_dossiers_reference":len(historiques),"taux_global_dossier":tg,
                "mediane_taux_global_historique":float(np.median(hist_global)) if hist_global else 0,"memoire_active":True}}


class AgentChallenger:
    @staticmethod
    def _num(x,default=0.0):
        try:
            if x is None or x=="": return default
            if isinstance(x,str):
                s=x.replace("%","").replace(" ","").replace(",",".")
                val=float(s); return val/100 if "%"in x or val>1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _map(rows): return {r.get("tranche",r.get("Tranche","")): r for r in (rows or [])}

    def challenger(self, tranches, resultats_bc, resultats_sim, resultats_mkt, rapport_rows):
        bc=self._map(resultats_bc); sim=self._map(resultats_sim)
        mkt=self._map(resultats_mkt); rpt=self._map(rapport_rows)
        avis=[]
        for i,t in enumerate(tranches or []):
            nom=t.get("nom",f"Tranche {i+1}"); typ=t.get("type","")
            bt=self._num(bc.get(nom,{}).get("taux_technique"))
            stt=self._num(sim.get(nom,{}).get("taux_technique"))
            mt=self._num(mkt.get(nom,{}).get("taux",mkt.get(nom,{}).get("taux_tech")))
            rt=self._num(rpt.get(nom,{}).get("taux_retenu"))
            n_nz=int(self._num(bc.get(nom,{}).get("n_ann_nonzero"),0))
            prudent=max(bt,stt,mt)
            marche=mt if (typ!="travaillante" and mt>0) else stt if stt>0 else bt
            equilibre=np.mean([x for x in [bt,stt,mt] if x>0]) if any(x>0 for x in [bt,stt,mt]) else 0
            dispersion=(max(p for p in [prudent,marche,equilibre])-min(p for p in [prudent,marche,equilibre]))/max(equilibre,1e-12) if equilibre else 0
            conflit="fort" if dispersion>0.35 else "modéré" if dispersion>0.15 else "faible"
            arbitrage="Conserver le taux retenu" if (rt>=min(prudent,equilibre) or rt==0) else "Relever le taux ou documenter l'écart"
            if typ=="travaillante" and n_nz<3: arbitrage="Ne pas se reposer sur le BC — jugement expert documenté"
            avis.append({"tranche":nom,"type":typ,"taux_retenu":rt,"avis_prudentiel":prudent,
                "avis_marche":marche,"avis_equilibre":equilibre,"conflit":conflit,"arbitrage":arbitrage})
        return {"avis":avis,"nb_conflits_forts":sum(1 for a in avis if a["conflit"]=="fort")}


class AgentOptimisationProgramme:
    def __init__(self, gnpi): self.gnpi=gnpi

    @staticmethod
    def _base_rate(t, idx, rbc, rsim, rmkt):
        nom=t.get("nom","")
        def lk(rows,key):
            for r in rows or []:
                if r.get("tranche")==nom: return float(r.get(key,0) or 0)
            if idx<len(rows or []): return float((rows or [])[idx].get(key,0) or 0)
            return 0.0
        bc=lk(rbc,"taux_technique"); sim=lk(rsim,"taux_technique"); mkt=lk(rmkt,"taux")
        return max(bc,sim) if t.get("type")=="travaillante" else max(sim,mkt)

    def _estimate_rate(self, t_ref, t_new, base_rate):
        p0=max(float(t_ref.get("priorite",1)),1); l0=max(float(t_ref.get("portee",1)),1)
        p1=max(float(t_new.get("priorite",p0)),1); l1=max(float(t_new.get("portee",l0)),1)
        rec0=max(float(t_ref.get("nb_reconstitutions",1)),1); rec1=max(float(t_new.get("nb_reconstitutions",rec0)),1)
        adj=(l1/l0)**0.55*(p0/p1)**0.35*(rec1/rec0)**0.08
        return max(base_rate*adj,0)

    def explorer(self, tranches, rbc, rsim, rmkt, objectif="equilibre", prime_cible=None, top_n=8):
        if not tranches: return {"alternatives":[],"message":"Programme vide."}
        alternatives=[]
        for mp in [0.85,1.00,1.15]:
            for md in [0.90,1.00,1.10]:
                for dr in [-1,0,1]:
                    new_t=[]; prime=0.0; protection=0.0
                    for i,t in enumerate(tranches):
                        tn=dict(t)
                        tn["portee"]=round(float(t.get("portee",0))*mp/500_000)*500_000
                        tn["priorite"]=round(float(t.get("priorite",0))*md/500_000)*500_000
                        tn["portee"]=max(tn["portee"],500_000); tn["priorite"]=max(tn["priorite"],0)
                        tn["nb_reconstitutions"]=int(max(1,min(4,int(t.get("nb_reconstitutions",1))+dr)))
                        base=self._base_rate(t,i,rbc,rsim,rmkt)
                        taux=self._estimate_rate(t,tn,base)
                        prime+=self.gnpi*taux; protection+=tn["portee"]*(1+tn["nb_reconstitutions"]*tn.get("taux_reconstitution",100)/100)
                        new_t.append(tn)
                    taux_g=prime/self.gnpi if self.gnpi else 0
                    pen=abs(prime-prime_cible)/max(prime_cible,1) if prime_cible else 0
                    if objectif=="cedante": score=protection/1e6-60*taux_g-10*pen
                    elif objectif=="reassureur": score=100*taux_g-0.03*protection/1e6-5*pen
                    else: score=protection/1e6-35*taux_g-8*pen
                    alternatives.append({"label":f"Portée {mp:.0%}|Priorité {md:.0%}|Rec {dr:+d}",
                        "prime":prime,"taux_global":taux_g,"protection_theorique":protection,"score":score,"tranches":new_t})
        alternatives=sorted(alternatives,key=lambda x:x["score"],reverse=True)[:top_n]
        return {"alternatives":alternatives,"message":f"{len(alternatives)} alternatives selon objectif {objectif}."}


def afficher_plan_agentique(plan):
    if not plan: return
    tableau_resultats([{"Ordre":i,"Étape":p["titre"],"Priorité":p["priorite"],"Justification":p["justification"]}
        for i,p in enumerate(plan,1)],"Plan de raisonnement agentique")

def afficher_critique_agentique(critique):
    if not critique: return
    syn=critique.get("synthese",{})
    c1,c2,c3=st.columns(3)
    with c1: card("Score audit",f"{syn.get('score',0)}/100",icone="🧠")
    with c2: card("Verdict",syn.get("verdict","—"),couleur="#1a1a1a",icone="⚖️")
    with c3: card("Alertes",f"{syn.get('nb_alertes',0)}",couleur="#f59e0b",icone="⚠️")
    alertes=critique.get("alertes",[])
    if alertes: tableau_resultats([{"Niveau":a["niveau"],"Tranche":a["tranche"],"Message":a["message"]} for a in alertes],"Alertes critiques")

def afficher_memoire_metier(memoire):
    if not memoire: return
    st.markdown("#### Mémoire métier inter-dossiers")
    if not memoire.get("disponible"): st.info(memoire.get("message","Mémoire indisponible.")); return
    syn=memoire.get("synthese",{})
    c1,c2,c3=st.columns(3)
    with c1: card("Dossiers référence",syn.get("nb_dossiers_reference",0),icone="🧠")
    with c2: card("Taux dossier",f"{syn.get('taux_global_dossier',0):.4%}",couleur="#1a1a1a",icone="📌")
    with c3: card("Médiane historique",f"{syn.get('mediane_taux_global_historique',0):.4%}",couleur="#3b82f6",icone="📚")
    rows=[{"Type":c["type"],"Dossier":f"{c['taux_dossier']:.4%}","Médiane hist.":f"{c['mediane_historique']:.4%}",
        "Q25-Q75":f"{c['q25_historique']:.4%}/{c['q75_historique']:.4%}","Écart":f"{c['ecart_vs_mediane']:+.1%}",
        "Diagnostic":c["diagnostic"],"N":c["n_reference"]} for c in memoire.get("comparaisons",[])]
    if rows: tableau_resultats(rows)

def afficher_challenger(challenge):
    if not challenge: return
    st.markdown("#### Agent challenger contradictoire")
    rows=[{"Tranche":a["tranche"],"Type":a["type"],"Retenu":f"{a['taux_retenu']:.4%}",
        "Prudentiel":f"{a['avis_prudentiel']:.4%}","Marché":f"{a['avis_marche']:.4%}",
        "Équilibre":f"{a['avis_equilibre']:.4%}","Conflit":a["conflit"],"Arbitrage":a["arbitrage"]}
        for a in challenge.get("avis",[])]
    if rows: tableau_resultats(rows)

def afficher_optimisation_avancee(opt):
    if not opt: return
    st.markdown("#### Optimisation avancée du programme")
    st.caption(opt.get("message",""))
    rows=[{"Rang":i,"Scénario":a["label"],"Prime":f"{a['prime']:,.0f} MAD",
        "Taux global":f"{a['taux_global']:.4%}","Score":f"{a['score']:.2f}"}
        for i,a in enumerate(opt.get("alternatives",[]),1)]
    if rows: tableau_resultats(rows)

def afficher_ml_agentique(ml):
    if not ml: return
    st.markdown("#### Benchmark Machine Learning")
    if not ml.get("disponible"): st.info(ml.get("message","ML non disponible.")); return
    rows=[{"Modèle":r.get("modele"),"MAE":f"{r.get('MAE',0):,.0f}" if r.get("MAE") else "Erreur",
        "RMSE":f"{r.get('RMSE',0):,.0f}" if r.get("RMSE") else "Erreur",
        "R²":f"{r.get('R2',0):.4f}" if r.get("R2") else "Erreur",
        "Statut":"✅" if r.get("MAE") else r.get("erreur","Erreur")} for r in ml.get("modeles",[])]
    tableau_resultats(rows,"Comparaison des modèles ML")
    if ml.get("importance"):
        tableau_resultats([{"Variable":x["variable"],"Importance":f"{x['importance']:.4f}"} for x in ml["importance"]],
            f"Variables importantes — {ml.get('meilleur_modele')}")


# ════════════════════════════════════════════
# AGENT PYTHON PUR — LOGIQUE ACTUARIELLE CODÉE
# ════════════════════════════════════════════

class AgentActuarielPython:
    """
    Agent de tarification 100% Python — aucun LLM, aucune API.
    Logique actuarielle codée explicitement. Fonctionne hors ligne.
    """

    def __init__(self, tranches, gnpi, df_proj, coeffs,
                 alpha_est, lambda_est, seuil_est, Pm_proxy,
                 chargement_majeurs, df_mkt_clean=None):
        self.tranches           = tranches
        self.gnpi               = gnpi
        self.df_proj            = df_proj
        self.coeffs             = coeffs
        self.alpha              = alpha_est
        self.lambda_            = lambda_est
        self.seuil              = seuil_est
        self.Pm_proxy           = Pm_proxy
        self.chargement_majeurs = chargement_majeurs
        self.df_mkt             = df_mkt_clean
        self.log                = []   # journal des décisions
        self.anomalies          = []   # alertes détectées
        self.resultats_bc       = []
        self.resultats_sim      = []
        self.resultats_mkt      = []
        self.rapport_rows       = []
        self.prime_totale       = 0.0

    # ────────────────────────────────────────────
    def _log(self, etape, decision, detail=""):
        self.log.append({"etape": etape, "decision": decision, "detail": detail})

    def _alerte(self, niveau, message):
        """niveau: INFO / WARN / CRITIQUE"""
        icone = {"INFO": "ℹ️", "WARN": "⚠️", "CRITIQUE": "🚨"}.get(niveau, "ℹ️")
        self.anomalies.append({"niveau": niveau, "icone": icone, "message": message})

    # ────────────────────────────────────────────
    # ÉTAPE 1 — VALIDATION DES PARAMÈTRES
    # ────────────────────────────────────────────
    def etape_0_validation(self):
        self._log("Validation", "Vérification des paramètres actuariels")

        # Alpha
        if self.alpha < 0.8:
            self._alerte("CRITIQUE", f"Alpha = {self.alpha:.4f} < 0.8 — queue trop lourde, résultats suspects")
        elif self.alpha > 4.0:
            self._alerte("WARN", f"Alpha = {self.alpha:.4f} > 4.0 — distribution proche normale, vérifier la modélisation")
        else:
            self._log("Alpha", f"OK — {self.alpha:.4f} dans la plage [0.8, 4.0]")

        # Lambda
        if self.lambda_ < 0.5:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} très faible — fréquence quasi nulle au-dessus du seuil")
        elif self.lambda_ > 50:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} très élevé — vérifier le seuil de modélisation")
        else:
            self._log("Lambda", f"OK — {self.lambda_:.4f} sinistres/an au-dessus du seuil")

        # Programme
        trav = [t for t in self.tranches if t["type"] == "travaillante"]
        cat  = [t for t in self.tranches if t["type"] == "cat"]
        if not trav:
            self._alerte("WARN", "Aucune tranche travaillante dans le programme")
        if not cat:
            self._alerte("INFO", "Aucune tranche cat — market curve non applicable")
        self._log("Programme", f"{len(trav)} travaillante(s), {len(cat)} cat")

    # ────────────────────────────────────────────
    # ÉTAPE 2 — BURNING COST
    # ────────────────────────────────────────────
    def etape_1_burning_cost(self):
        self._log("Burning Cost", "Calcul BC individuel par sinistre, agrégation annuelle")
        resultats = []
        for t_info in self.tranches:
            D   = t_info["priorite"];  L  = t_info["portee"]
            aal = t_info["AAL"];       aad = t_info["AAD"]
            n_rec = t_info["nb_reconstitutions"]
            taux_rec_list = t_info.get("taux_reconstitutions",
                            [t_info.get("taux_reconstitution", 100)] * n_rec)
            cap = (n_rec + 1) * L

            # Charge annuelle
            df_p = self.df_proj.copy()
            df_p["Ck"] = df_p.apply(
                lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
            charges_ann = df_p.groupby("annee_surv")["Ck"].sum()
            charges_finales = []
            for ann, ch in charges_ann.items():
                if aad: ch = max(ch - aad, 0)
                if aal: ch = min(ch, aal)
                charges_finales.append({"annee": int(ann), "charge": float(min(ch, cap))})

            df_ch = pd.DataFrame(charges_finales); N = len(df_ch)
            charges_nonzero = [c["charge"] for c in charges_finales if c["charge"] > 0]
            n_nz = len(charges_nonzero)

            # Reconstitutions individuelles
            Pr_Rec = 0.0
            for C_n in df_ch["charge"].values:
                for r_idx, t_r_i in enumerate(taux_rec_list):
                    Pr_Rec += (t_r_i / 100) * min(L, max(C_n - r_idx * L, 0))
            Pr_Rec /= L if L > 0 else 1
            Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0

            # R2 — données insuffisantes
            if n_nz < 3:
                tp = tr = tt = sigma = 0.0
                self._alerte("WARN",
                    f"{t_info['nom']} : BC = 0 — seulement {n_nz} année(s) non nulle(s) (règle R2 : min 3 requis)")
            else:
                charge_moy = df_ch["charge"].mean()
                tp    = charge_moy / self.gnpi
                sigma = float(np.std(charges_nonzero)) / self.gnpi
                tr    = tp + sigma * 0.20   # R1
                tt    = (tr * (1 - Rec)) / max(
                    1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"],
                    0.01)

            resultats.append({
                "tranche": t_info["nom"], "type": t_info["type"],
                "charge_moy": df_ch["charge"].mean() if n_nz >= 3 else 0.0,
                "n_ann_nonzero": n_nz, "sigma_hist": round(sigma if n_nz >= 3 else 0.0, 6),
                "Pr_Rec": round(Pr_Rec, 6), "Rec": round(Rec, 6),
                "taux_pur": round(tp, 6), "taux_risque": round(tr, 6),
                "taux_technique": round(tt, 6),
                "chargement_majeurs": round(self.chargement_majeurs, 6),
                "detail_annuel": charges_finales
            })
            self._log("BC", f"{t_info['nom']}: τ_pur={tp:.4%} τ_tech={tt:.4%} Rec={Rec:.4%} ({n_nz} ans non nuls)")

        self.resultats_bc = resultats
        return resultats

    # ────────────────────────────────────────────
    # ÉTAPE 3 — SIMULATION
    # ────────────────────────────────────────────
    def etape_2_simulation(self, n_sim=10000):
        self._log("Simulation", f"Pareto(α={self.alpha:.4f}) × Poisson(λ={self.lambda_:.4f}) — {n_sim:,} simulations")
        np.random.seed(42)
        resultats = []
        for t_info in self.tranches:
            D = t_info["priorite"]; P = t_info["portee"]
            r = t_info["nb_reconstitutions"]
            aal = t_info["AAL"]; aad = t_info["AAD"]
            cap = (r + 1) * P

            def simuler(avec_aal, avec_aad, avec_rec):
                charges = []
                for _ in range(n_sim):
                    N_sin = np.random.poisson(self.lambda_)
                    S_tot = 0.0
                    if N_sin > 0:
                        U  = np.random.uniform(size=N_sin)
                        Sp = self.seuil * (U ** (-1 / self.alpha))
                        ic = np.random.choice(len(self.coeffs), size=N_sin, replace=True)
                        for k in range(N_sin):
                            s = Sp[k]; c = self.coeffs[ic[k]]
                            if   s <= D:     S_i = 0
                            elif s <= D + P: S_i = c * (s - D)
                            else:            S_i = c * P
                            S_tot += S_i
                    ch = S_tot
                    if avec_aad and aad: ch = max(ch - aad, 0)
                    if avec_aal and aal: ch = min(ch, aal)
                    charges.append(min(ch, cap) if avec_rec else ch)
                return np.array(charges)

            def calc(ch):
                P0 = np.mean(ch); sig = np.std(ch)
                tp = P0 / self.gnpi
                tr = (P0 + 0.2 * sig) / self.gnpi
                tt = tr / max(1 - t_info["brokage"] - t_info["frais"] -
                              t_info["marge"] - t_info["retrocession"], 0.01)
                return round(tp,6), round(tr,6), round(tt,6)

            c_base = simuler(True,  True,  True)
            c_saal = simuler(False, True,  True)
            c_saad = simuler(True,  False, True)
            c_srec = simuler(True,  True,  False)
            tp,tr,tt   = calc(c_base)
            _,_,tt_aal = calc(c_saal)
            _,_,tt_aad = calc(c_saad)
            _,_,tt_rec = calc(c_srec)

            resultats.append({
                "tranche": t_info["nom"], "type": t_info["type"],
                "taux_pur": tp, "taux_risque": tr, "taux_technique": tt,
                "chargement_majeurs": round(self.chargement_majeurs, 6),
                "sans_aal": tt_aal, "sans_aad": tt_aad, "sans_rec": tt_rec,
                "impact_aal": round(tt_aal - tt, 6),
                "impact_aad": round(tt_aad - tt, 6),
                "impact_rec": round(tt_rec - tt, 6),
            })
            self._log("Sim", f"{t_info['nom']}: τ_pur={tp:.4%} τ_tech={tt:.4%}")

        self.resultats_sim = resultats
        return resultats

    # ────────────────────────────────────────────
    # ÉTAPE 4 — DÉTECTION ANOMALIES BC vs SIM
    # ────────────────────────────────────────────
    def etape_3_controles(self):
        self._log("Contrôles", "Vérification cohérence BC / Simulation")
        bc_map  = {r["tranche"]: r for r in self.resultats_bc}
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        for t in self.tranches:
            nom   = t["nom"]
            bc_tt = bc_map.get(nom, {}).get("taux_technique", 0)
            si_tt = sim_map.get(nom, {}).get("taux_technique", 0)
            if t["type"] == "travaillante" and bc_tt > 0 and si_tt > 0:
                ecart = abs(bc_tt - si_tt) / bc_tt
                if ecart > 0.50:
                    self._alerte("CRITIQUE",
                        f"{nom}: écart BC/Sim = {ecart:.0%} > 50% — anomalie majeure, vérifier les données")
                elif ecart > 0.30:
                    self._alerte("WARN",
                        f"{nom}: écart BC/Sim = {ecart:.0%} > 30% — simulation retenue (méthode conservative)")
                else:
                    self._log("Contrôle BC/Sim", f"{nom}: écart = {ecart:.0%} ✅")
            if t["type"] == "cat" and bc_tt == 0:
                self._log("Cat BC=0", f"{nom}: normal — tranche cat sans sinistres historiques au-dessus de la priorité")

    # ────────────────────────────────────────────
    # ÉTAPE 5 — MARKET CURVE (cat uniquement)
    # ────────────────────────────────────────────
    def etape_4_market_curve(self, r2_min=0.40):
        cat_tranches = [t for t in self.tranches if t["type"] != "travaillante"]
        if not cat_tranches:
            self._log("Market Curve", "Aucune tranche cat — market curve non applicable")
            self.resultats_mkt = []
            return []
        if self.df_mkt is None:
            self._alerte("INFO", "Données marché non fournies — market curve ignorée")
            self.resultats_mkt = []
            return []

        self._log("Market Curve", f"Ajustement ROL = a × x^(-b) sur {len(self.df_mkt)} points — cat uniquement")

        def fit_power(x, y):
            lx = np.log(x); ly = np.log(y)
            c  = np.polyfit(lx, ly, 1)
            a  = np.exp(c[1]); b = -c[0]
            ly_pred = np.polyval(c, lx)
            r2 = 1 - np.sum((ly-ly_pred)**2) / (np.sum((ly-ly.mean())**2) + 1e-10)
            return a, b, r2

        def calc_taux_cat(t, a, b):
            x   = (t["priorite"] + t["portee"] / 2) / self.gnpi
            rol = a * (x ** (-b))
            tp  = rol * t["portee"] / self.gnpi
            tr  = tp * 1.002
            tt  = tr / max(1 - t["brokage"] - t["frais"] - t["marge"] - t["retrocession"], 0.01)
            return {"tranche": t["nom"], "type": t["type"], "x_norm": round(x,6),
                    "rol": round(rol,6), "taux_pur": round(tp,6),
                    "taux_tech": round(tt,6), "taux": round(tt,6),
                    "chargement_majeurs": round(self.chargement_majeurs,6)}

        best = None
        for q in [0.40, 0.60, 0.80, 1.0, 0.20]:
            mq   = np.quantile(self.df_mkt["midpoints"], q)
            df_q = self.df_mkt[self.df_mkt["midpoints"] <= mq]
            if len(df_q) < 8: continue
            try:
                a, b, r2 = fit_power(df_q["midpoints"].values, df_q["ROLs"].values)
                if b <= 0: continue
                tts = [calc_taux_cat(t, a, b) for t in cat_tranches]
                if any(tt["taux"] <= 0 for tt in tts): continue
                # Vérification cohérence ROL : tranche plus basse = ROL plus élevé
                if len(tts) >= 2:
                    rols = [tt["rol"] for tt in tts]
                    if rols != sorted(rols, reverse=True):
                        self._alerte("INFO", f"Q{int(q*100)}: hiérarchie ROL non respectée — ajustement écarté")
                        continue
                score = r2 + (0.3 if r2 >= r2_min else 0) + 0.01 * len(df_q)
                if best is None or score > best["score"]:
                    best = {"a": a, "b": b, "r2": r2, "n": len(df_q),
                            "quantile": q, "taux_tranches": tts, "score": score}
            except: continue

        if best is None:
            self._alerte("CRITIQUE", "Aucun ajustement market curve valide — taux marché = 0 pour les tranches cat")
            self.resultats_mkt = []
            return []

        if best["r2"] < r2_min:
            self._alerte("WARN", f"R² = {best['r2']:.3f} < {r2_min} — market curve de faible qualité, simultion prioritaire")
        else:
            self._log("Market Curve", f"R²={best['r2']:.3f} N={best['n']} a={best['a']:.5f} b={best['b']:.4f} ✅")

        # Compléter avec taux=0 pour les tranches travaillantes
        all_tts = []
        cat_map = {tt["tranche"]: tt for tt in best["taux_tranches"]}
        for t in self.tranches:
            if t["nom"] in cat_map:
                all_tts.append(cat_map[t["nom"]])
            else:
                all_tts.append({"tranche": t["nom"], "type": t["type"],
                                 "x_norm":0, "rol":0, "taux_pur":0,
                                 "taux_tech":0, "taux":0, "chargement_majeurs":0})
        self.resultats_mkt = all_tts
        return all_tts

    # ────────────────────────────────────────────
    # ÉTAPE 6 — RAPPORT FINAL + SÉLECTION MÉTHODE
    # ────────────────────────────────────────────
    def etape_5_rapport(self):
        self._log("Rapport", "Sélection méthode : max(BC,Sim) trav. | max(Sim,Mkt) cat")
        bc_map  = {r["tranche"]: r for r in self.resultats_bc}
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        mkt_map = {r["tranche"]: r["taux"] for r in self.resultats_mkt}
        rows = []; pt = 0.0
        for idx_t, t in enumerate(self.tranches):
            nom   = t["nom"]
            bc_tt = _lookup_taux(self.resultats_bc,  nom, idx_t, "taux_technique")
            si_tt = _lookup_taux(self.resultats_sim, nom, idx_t, "taux_technique")
            mkt   = mkt_map.get(nom, 0.0) if t["type"] != "travaillante" else 0.0
            if t["type"] == "travaillante":
                taux = max(bc_tt, si_tt)
                meth = f"max(BC={bc_tt:.4%}, Sim={si_tt:.4%}) → {'BC' if bc_tt >= si_tt else 'Sim'}"
            else:
                taux = max(si_tt, mkt)
                meth = f"max(Sim={si_tt:.4%}, Mkt={mkt:.4%}) → {'Mkt' if mkt >= si_tt else 'Sim'}"
            prime = self.gnpi * taux; pt += prime
            ecart = abs(bc_tt - si_tt) / bc_tt * 100 if bc_tt > 0 else 0
            rows.append({
                "tranche": nom, "type": t["type"],
                "taux_bc": round(bc_tt,6), "taux_sim": round(si_tt,6),
                "taux_mkt": round(mkt,6), "taux_retenu": round(taux,6),
                "methode": meth, "prime_MAD": round(prime,2),
                "ecart_bc_sim_pct": round(ecart,1)
            })
            self._log("Sélection", f"{nom}: {meth} | prime={prime:,.0f} MAD")
        self.rapport_rows = rows
        self.prime_totale = pt
        return rows, pt

    # ────────────────────────────────────────────
    # ÉTAPE 6 — 5 VARIANTES DE PROGRAMME OPTIMAL
    # ────────────────────────────────────────────
    def etape_6_optimisation(self):
        """
        Génère 5 variantes de programme basées sur :
        - Analyse technique (taux, simulation, market curve)
        - Sensibilité des conditions (AAL, AAD, reconstitutions)
        - Logique de leader : Partner Re fixe les conditions de référence
        """
        self._log("Optimisation", "Génération de 5 variantes de programme — perspective leader")
        sim_map = {r["tranche"]: r for r in self.resultats_sim}
        bc_map  = {r["tranche"]: r for r in self.resultats_bc}
        mkt_map = {r["tranche"]: r for r in self.resultats_mkt}

        def taux_technique_modifie(t_info, taux_pur_ref, coeff_portee=1.0,
                                    coeff_priorite=1.0, nb_recon_new=None, aal_ratio=None):
            """Estime le taux technique pour un programme modifié."""
            portee_new   = t_info["portee"]   * coeff_portee
            priorite_new = t_info["priorite"] * coeff_priorite
            # Sensibilité log-log : taux ~ portee^0.6 / priorite^0.35
            adj = (coeff_portee**0.6) / (coeff_priorite**0.35)
            # Impact reconstitutions
            n_rec = nb_recon_new if nb_recon_new is not None else t_info["nb_reconstitutions"]
            adj_rec = (n_rec / max(t_info["nb_reconstitutions"], 1)) ** 0.3
            # Impact AAL
            adj_aal = 1.0
            if aal_ratio is not None and t_info.get("AAL"):
                adj_aal = aal_ratio ** 0.2
            return taux_pur_ref * adj * adj_rec * adj_aal

        variantes = {}

        # ── VARIANTE 1 — Programme de référence (tarif technique) ──
        v1 = []
        for t in self.tranches:
            r = sim_map.get(t["nom"], {})
            v1.append({**t, "_taux": r.get("taux_technique", 0),
                       "_prime": self.gnpi * r.get("taux_technique", 0)})
        variantes["ref"] = {
            "label": "Programme de référence",
            "description": "Conditions actuelles — taux techniques issus de la simulation",
            "angle": "Base de comparaison",
            "tranches": v1,
            "prime": sum(t["_prime"] for t in v1)
        }

        # ── VARIANTE 2 — Optimisation priorité (+10%) ──
        # Augmenter la priorité réduit l'exposition du réassureur sur les sinistres courants
        v2 = []
        for t in self.tranches:
            t2 = dict(t)
            t2["priorite"] = round(t["priorite"] * 1.10 / 500_000) * 500_000
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(t, r.get("taux_technique",0), coeff_priorite=1.10)
            v2.append({**t2, "_taux": tt, "_prime": self.gnpi * tt})
        variantes["priorite_haute"] = {
            "label": "Priorité relevée (+10%)",
            "description": f"Priorité T1 : {self.tranches[0]['priorite']*1.10/1e6:.1f}M MAD — réduit l'exposition sur sinistres courants",
            "angle": "Protège le réassureur sur la tranche travaillante",
            "tranches": v2,
            "prime": sum(t["_prime"] for t in v2)
        }

        # ── VARIANTE 3 — Portée réduite (−15%) ──
        # Limite l'engagement maximum par sinistre
        v3 = []
        for t in self.tranches:
            t3 = dict(t)
            t3["portee"] = round(t["portee"] * 0.85 / 500_000) * 500_000
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(t, r.get("taux_technique",0), coeff_portee=0.85)
            v3.append({**t3, "_taux": tt, "_prime": self.gnpi * tt})
        variantes["portee_reduite"] = {
            "label": "Portée réduite (−15%)",
            "description": "Réduit l'engagement maximal — adapté si sinistralité catastrophique élevée",
            "angle": "Limite le MPL (Maximum Possible Loss)",
            "tranches": v3,
            "prime": sum(t["_prime"] for t in v3)
        }

        # ── VARIANTE 4 — Conditions restrictives (AAD relevé + reconstitutions limitées) ──
        v4 = []
        for t in self.tranches:
            t4 = dict(t)
            # AAD relevé pour filtrer les petits sinistres agrégés
            if t["type"] == "travaillante":
                aad_actuel = t.get("AAD") or 0
                t4["AAD"] = round(max(aad_actuel * 1.25, t["portee"] * 0.15) / 100_000) * 100_000
            # Reconstitutions limitées à 1 pour les cat
            if t["type"] == "cat":
                t4["nb_reconstitutions"] = max(t["nb_reconstitutions"] - 1, 1)
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(t, r.get("taux_technique",0),
                nb_recon_new=t4["nb_reconstitutions"])
            v4.append({**t4, "_taux": tt, "_prime": self.gnpi * tt})
        variantes["conditions_restrictives"] = {
            "label": "Conditions restrictives",
            "description": "AAD renforcé + reconstitutions cat limitées — réduit la fréquence de mise en jeu",
            "angle": "Meilleure rentabilité technique pour le réassureur",
            "tranches": v4,
            "prime": sum(t["_prime"] for t in v4)
        }

        # ── VARIANTE 5 — Programme élargi cédante (portée +15%, priorité −10%) ──
        # Maximise la protection de la cédante
        v5 = []
        for t in self.tranches:
            t5 = dict(t)
            t5["portee"]   = round(t["portee"]   * 1.15 / 500_000) * 500_000
            t5["priorite"] = round(t["priorite"] * 0.90 / 500_000) * 500_000
            r = sim_map.get(t["nom"], {})
            tt = taux_technique_modifie(t, r.get("taux_technique",0),
                coeff_portee=1.15, coeff_priorite=0.90)
            v5.append({**t5, "_taux": tt, "_prime": self.gnpi * tt})
        variantes["elargi_cedante"] = {
            "label": "Programme élargi",
            "description": "Portée +15%, priorité −10% — protection maximale pour la cédante",
            "angle": "Proposition cédante si marché favorable / négociation de renouvellement",
            "tranches": v5,
            "prime": sum(t["_prime"] for t in v5)
        }

        # ── Scoring des variantes ──
        taux_ref = variantes["ref"]["prime"] / self.gnpi if self.gnpi else 0
        for key, v in variantes.items():
            taux_v = v["prime"] / self.gnpi if self.gnpi else 0
            v["taux_global"] = taux_v
            v["ecart_ref_pts"] = (taux_v - taux_ref) * 100
            # Score leader : équilibre rendement / protection
            v["score_leader"] = taux_v - abs(taux_v - taux_ref) * 0.5

        self._log("Optimisation", f"5 variantes générées | Prime ref : {variantes['ref']['prime']:,.0f} MAD")
        return variantes

    def generer_rapport_texte(self):
        taux_global = self.prime_totale / self.gnpi if self.gnpi else 0
        lignes = [
            "=" * 60,
            "  RAPPORT DE TARIFICATION — AGENT PYTHON AUTONOME",
            "=" * 60,
            f"  GNPI        : {self.gnpi:,.0f} MAD",
            f"  Prime totale: {self.prime_totale:,.0f} MAD",
            f"  Taux global : {taux_global:.4%}",
            f"  Tranches    : {len(self.tranches)}",
            "=" * 60,
            "",
            "── PARAMÈTRES CALIBRÉS ─────────────────────────────",
            f"  Alpha Pareto (MLE-Hill) : {self.alpha:.4f}",
            f"  Lambda Poisson          : {self.lambda_:.4f}",
            f"  Seuil modélisation      : {self.seuil:,.0f} MAD",
            f"  Pm proxy (P99.5)        : {self.Pm_proxy:,.0f} MAD",
            f"  Chargement majeurs      : {self.chargement_majeurs:.4%}",
            "",
            "── RÉSULTATS PAR TRANCHE ───────────────────────────",
        ]
        for r in self.rapport_rows:
            statut = "⚠️" if r["ecart_bc_sim_pct"] > 30 else "✅"
            lignes += [
                f"",
                f"  [{r['type'].upper()}] {r['tranche']}",
                f"  BC={r['taux_bc']:.4%} | Sim={r['taux_sim']:.4%} | Mkt={r['taux_mkt']:.4%}",
                f"  → Retenu : {r['taux_retenu']:.4%} ({r['methode']})",
                f"  → Prime  : {r['prime_MAD']:,.0f} MAD {statut} (écart BC/Sim : {r['ecart_bc_sim_pct']:.0f}%)",
            ]
        if self.anomalies:
            lignes += ["", "── ALERTES ─────────────────────────────────────────"]
            for a in self.anomalies:
                lignes.append(f"  {a['icone']} [{a['niveau']}] {a['message']}")
        lignes += [
            "",
            "── JOURNAL DES DÉCISIONS ───────────────────────────",
        ]
        for entry in self.log:
            lignes.append(f"  [{entry['etape']}] {entry['decision']}" +
                          (f" — {entry['detail']}" if entry['detail'] else ""))
        lignes += ["", "=" * 60]
        return "\n".join(lignes)

    # ────────────────────────────────────────────
    # PIPELINE COMPLET
    # ────────────────────────────────────────────
    def run(self, n_sim=10000):
        self.etape_0_validation()
        self.etape_1_burning_cost()
        self.etape_2_simulation(n_sim)
        self.etape_3_controles()
        self.etape_4_market_curve()
        self.etape_5_rapport()
        self.variantes = self.etape_6_optimisation()
        return self.generer_rapport_texte()


# ════════════════════════════════════════════
# FONCTIONS EXÉCUTEURS — partagées par Agent Python et Agent LLM
# ════════════════════════════════════════════

def _executer_burning_cost():
    """Calcul BC — utilisé par l'Agent LLM (tab_full)"""
    if "df_proj" not in st.session_state: return {"erreur": "df_proj manquant"}
    df_proj = st.session_state["df_proj"].copy()
    resultats = []
    for t_info in tranches_input:
        D = t_info["priorite"]; L = t_info["portee"]
        aal = t_info["AAL"]; aad = t_info["AAD"]
        n_rec = t_info["nb_reconstitutions"]
        taux_rec_list = t_info.get("taux_reconstitutions",
                        [t_info.get("taux_reconstitution", 100)] * n_rec)
        cap = (n_rec + 1) * L
        df_proj["Ck"] = df_proj.apply(
            lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
        charges_ann = df_proj.groupby("annee_surv")["Ck"].sum()
        charges_finales = []
        for ann, ch in charges_ann.items():
            if aad: ch = max(ch - aad, 0)
            if aal: ch = min(ch, aal)
            charges_finales.append({"annee": int(ann), "charge": round(float(min(ch, cap)), 2)})
        df_ch = pd.DataFrame(charges_finales); N = len(df_ch)
        # Reconstitutions individuelles
        Pr_Rec = 0.0
        for C_n in df_ch["charge"].values:
            for r_idx, t_r_i in enumerate(taux_rec_list):
                Pr_Rec += (t_r_i / 100) * min(L, max(C_n - r_idx * L, 0))
        Pr_Rec /= L if L > 0 else 1
        Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0
        charges_nz = [c["charge"] for c in charges_finales if c["charge"] > 0]
        n_nz = len(charges_nz)
        charg_maj = st.session_state.get("chargement_majeurs", 0.0)
        if n_nz < 3:
            tp = tr = tt = 0.0; sigma = 0.0
        else:
            charge_moy = df_ch["charge"].mean()
            tp    = charge_moy / gnpi
            sigma = float(np.std(charges_nz)) / gnpi
            tr    = tp + sigma * 0.20
            tt    = (tr * (1 - Rec)) / max(
                1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"], 0.01)
        resultats.append({
            "tranche": t_info["nom"], "type": t_info["type"],
            "charge_moy": df_ch["charge"].mean(),
            "n_ann_nonzero": n_nz, "sigma_hist": round(sigma if n_nz >= 3 else 0.0, 6),
            "Pr_Rec": round(Pr_Rec, 6), "Rec": round(Rec, 6),
            "taux_pur": round(tp, 6), "taux_risque": round(tr, 6),
            "taux_technique": round(tt, 6),
            "chargement_majeurs": round(charg_maj, 6),
            "detail_annuel": charges_finales
        })
    st.session_state["resultats_bc"] = resultats
    return {"status": "ok", "resultats": [{k:v for k,v in r.items() if k!="detail_annuel"} for r in resultats]}


def _executer_simulation(alpha, lambda_, seuil, n_sim):
    """Simulation Pareto/Poisson — utilisée par l'Agent LLM (tab_full)"""
    if "coeffs" not in st.session_state: return {"erreur": "coeffs manquants"}
    coeffs = st.session_state["coeffs"]
    np.random.seed(42)
    resultats = []
    for t_info in tranches_input:
        D = t_info["priorite"]; P = t_info["portee"]
        r = t_info["nb_reconstitutions"]; aal = t_info["AAL"]; aad = t_info["AAD"]
        cap = (r + 1) * P
        def simuler(avec_aal, avec_aad, avec_rec):
            charges = []
            for _ in range(n_sim):
                N_s = np.random.poisson(lambda_); S_total = 0
                if N_s > 0:
                    U = np.random.uniform(size=N_s)
                    Sp = seuil * (U ** (-1/alpha))
                    idx_c = np.random.choice(len(coeffs), size=N_s, replace=True)
                    for i in range(N_s):
                        s = Sp[i]; c = coeffs[idx_c[i]]
                        if s <= D: S_i = 0
                        elif s <= D + P: S_i = c * (s - D)
                        else: S_i = c * P
                        S_total += S_i
                ch = S_total
                if avec_aad and aad: ch = max(ch - aad, 0)
                if avec_aal and aal: ch = min(ch, aal)
                charges.append(min(ch, cap) if avec_rec else ch)
            return np.array(charges)
        def calc_taux(ch):
            P0 = np.mean(ch); sig = np.std(ch)
            tp = P0 / gnpi; tr = (P0 + 0.2 * sig) / gnpi
            tt = tr / max(1 - t_info["brokage"] - t_info["frais"] - t_info["marge"] - t_info["retrocession"], 0.01)
            return round(tp,6), round(tr,6), round(tt,6)
        c_base = simuler(True, True, True)
        tp, tr, tt     = calc_taux(c_base)
        _, _, tt_aal   = calc_taux(simuler(False, True, True))
        _, _, tt_aad   = calc_taux(simuler(True, False, True))
        _, _, tt_rec   = calc_taux(simuler(True, True, False))
        resultats.append({
            "tranche": t_info["nom"], "type": t_info["type"],
            "taux_pur": tp, "taux_risque": tr, "taux_technique": tt,
            "chargement_majeurs": round(st.session_state.get("chargement_majeurs", 0.0), 6),
            "sans_aal": tt_aal, "sans_aad": tt_aad, "sans_rec": tt_rec,
            "impact_aal": round(tt_aal-tt,6), "impact_aad": round(tt_aad-tt,6),
            "impact_rec": round(tt_rec-tt,6)
        })
    st.session_state["resultats_sim"] = resultats
    return _json_safe({"status": "ok",
        "parametres": {"alpha": alpha, "lambda": lambda_, "seuil": seuil, "n_sim": n_sim},
        "resultats": resultats})


def _executer_market_curve(rol_min, rol_max, r2_min, tolerance):
    """Market curve — utilisée par l'Agent LLM (tab_full)"""
    if "df_mkt_clean" not in st.session_state:
        return {"erreur": "Données marché manquantes"}
    df_mkt = st.session_state["df_mkt_clean"].copy()
    mask = (df_mkt['ROLs'] >= rol_min) & (df_mkt['ROLs'] <= rol_max)
    df_mkt = df_mkt[mask].copy()
    df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()
    if len(df_mkt) < 5: return {"erreur": f"Moins de 5 points après filtrage ({len(df_mkt)})"}
    def fit_power(x, y):
        lx = np.log(x); ly = np.log(y)
        c = np.polyfit(lx, ly, 1)
        a = np.exp(c[1]); b = -c[0]
        r2 = 1 - np.sum((ly-np.polyval(c,lx))**2) / (np.sum((ly-ly.mean())**2)+1e-10)
        return a, b, r2
    def calc_tt(t, a, b):
        x = (t['priorite'] + t['portee']/2) / gnpi
        rol = a * (x**(-b)); tp = rol * t['portee'] / gnpi
        tr = tp * 1.002
        tt = tr / max(1 - t['brokage'] - t['frais'] - t['marge'] - t['retrocession'], 0.01)
        return {"tranche": t["nom"], "type": t["type"], "x_norm": round(x,6),
                "rol": round(rol,6), "taux_pur": round(tp,6), "taux_tech": round(tt,6), "taux": round(tt,6),
                "chargement_majeurs": round(st.session_state.get("chargement_majeurs",0.0),6)}
    resultats_mkt = []
    for q in [0.20, 0.40, 0.60, 0.80, 1.0]:
        df_q = df_mkt[df_mkt['midpoints'] <= np.quantile(df_mkt['midpoints'], q)]
        if len(df_q) < 5: continue
        try:
            a, b, r2 = fit_power(df_q['midpoints'].values, df_q['ROLs'].values)
            if b <= 0: continue
            tts = [calc_tt(t, a, b) for t in tranches_input]
            if any(tt['taux'] <= 0 for tt in tts): continue
            resultats_mkt.append({"quantile": q, "n_points": len(df_q), "a": round(a,6),
                "b": round(b,4), "r2": round(r2,4), "r2_ok": r2 >= r2_min,
                "taux_tranches": tts, "score": r2-(0 if r2>=r2_min else 0.5)})
        except: continue
    if not resultats_mkt: return {"erreur": "Aucun ajustement valide"}
    best = max(resultats_mkt, key=lambda x: x["score"])
    st.session_state["resultats_mkt"]  = resultats_mkt
    st.session_state["taux_mkt_final"] = best["taux_tranches"]
    return _json_safe({"status": "ok",
        "meilleur_ajustement": {k:v for k,v in best.items() if k!="taux_tranches"},
        "taux_par_tranche": best["taux_tranches"]})



# ══════════════════════════════════════════════════════════
# MODULE ANALYSE DISTRIBUTIONS — Seuils · Fits · CDF · Tests
# ══════════════════════════════════════════════════════════

def _hill_estimates(sorted_desc, k_max=None):
    n = len(sorted_desc)
    if k_max is None: k_max = min(n-1, 200)
    hills, ks = [], []
    for k in range(1, k_max+1):
        log_ratios = np.log(sorted_desc[:k] / sorted_desc[k])
        h = k / np.sum(log_ratios) if np.sum(log_ratios) > 0 else np.nan
        hills.append(h); ks.append(k)
    return np.array(ks), np.array(hills)


def _mean_excess(data, n_points=40):
    data_s = np.sort(data)
    u_min, u_max = np.percentile(data_s, 50), np.percentile(data_s, 95)
    thresholds = np.linspace(u_min, u_max, n_points)
    mef = []
    for u in thresholds:
        exc = data_s[data_s > u] - u
        mef.append(np.mean(exc) if len(exc) >= 5 else np.nan)
    return thresholds, np.array(mef)


def _gertensgarbe_k(ks, hills):
    valid = ~np.isnan(hills)
    h = hills[valid]; k = ks[valid]
    if len(h) < 10: return k[len(k)//2]
    n = len(h)
    s_prog = np.zeros(n); s_reg = np.zeros(n)
    for i in range(1, n):
        s_prog[i] = s_prog[i-1] + sum(1 for j in range(i) if h[j] < h[i])
    h_rev = h[::-1]
    for i in range(1, n):
        s_reg[i] = s_reg[i-1] + sum(1 for j in range(i) if h_rev[j] < h_rev[i])
    s_reg = s_reg[::-1]
    crossings = np.where(np.diff(np.sign(s_prog - s_reg)))[0]
    idx = crossings[0] if len(crossings) > 0 else np.argmin(np.abs(hills - np.nanmedian(hills)))
    return int(k[min(idx, len(k)-1)])


def _fit_severity(exceedances, threshold):
    from scipy import stats
    results = {}
    x = exceedances
    if len(x) < 10: return results
    try:
        alpha_h = len(x) / np.sum(np.log(x / threshold))
        ks_p, pval_p = stats.kstest(x, lambda v: 1-(v/threshold)**(-alpha_h))
        results["Pareto"] = {"alpha": alpha_h, "xm": threshold, "ks": ks_p, "pval": pval_p}
    except: pass
    try:
        log_x = np.log(x); mu_ln, sigma_ln = np.mean(log_x), np.std(log_x)
        ks_ln, pval_ln = stats.kstest(x, lambda v: stats.lognorm.cdf(v, s=sigma_ln, scale=np.exp(mu_ln)))
        results["Log-Normale"] = {"mu": mu_ln, "sigma": sigma_ln, "ks": ks_ln, "pval": pval_ln}
    except: pass
    try:
        y = x - threshold
        xi, loc, beta = stats.genpareto.fit(y, floc=0)
        ks_gp, pval_gp = stats.kstest(y, lambda v: stats.genpareto.cdf(v, xi, loc=0, scale=beta))
        results["GPD"] = {"xi": xi, "beta": beta, "ks": ks_gp, "pval": pval_gp, "threshold": threshold}
    except: pass
    return results


def _fit_frequency(counts):
    from scipy import stats
    results = {}
    if len(counts) < 3: return results
    mu = np.mean(counts); var = np.var(counts)
    try:
        ks_po, pval_po = stats.kstest(counts, lambda v: stats.poisson.cdf(v, mu))
        results["Poisson"] = {"lambda": mu, "ks": ks_po, "pval": pval_po}
    except: pass
    try:
        if var > mu:
            r_nb = mu**2 / (var - mu); p_nb = r_nb / (r_nb + mu)
            ks_nb, pval_nb = stats.kstest(counts, lambda v: stats.nbinom.cdf(v, r_nb, p_nb))
            results["BN"] = {"r": r_nb, "p": p_nb, "ks": ks_nb, "pval": pval_nb}
        else:
            results["BN"] = {"note": "var <= mean — BN non applicable"}
    except: pass
    return results


def _threshold_table(data, thresholds_pct):
    from scipy import stats
    rows = []
    for pct in thresholds_pct:
        u = np.percentile(data, pct)
        exc = data[data > u]; n_exc = len(exc)
        if n_exc < 5:
            rows.append({"Seuil %": f"p{pct}", "Seuil MAD": f"{u:,.0f}", "N exc.": n_exc,
                         "Alpha Hill": "—", "KS stat": "—", "p-val KS": "—", "AD stat": "—", "Qualite": "Insuf."})
            continue
        alpha_h = n_exc / np.sum(np.log(exc / u))
        ks_s, pval_ks = stats.kstest(exc, lambda v: 1-(v/u)**(-alpha_h))
        try:
            cdf_v = np.sort(1-(np.sort(exc)/u)**(-alpha_h))
            nn = len(cdf_v); i_a = np.arange(1, nn+1)
            ad_stat = -nn - np.mean((2*i_a-1)*(np.log(np.clip(cdf_v,1e-10,1-1e-10))+
                                               np.log(np.clip(1-cdf_v[::-1],1e-10,1-1e-10))))
        except: ad_stat = np.nan
        qual = "Bon" if pval_ks>0.05 and not np.isnan(ad_stat) and ad_stat<2.5 else                "Acceptable" if pval_ks>0.01 else "Rejeté"
        rows.append({"Seuil %": f"p{pct}", "Seuil MAD": f"{u:,.0f}", "N exc.": n_exc,
                     "Alpha Hill": f"{alpha_h:.4f}", "KS stat": f"{ks_s:.4f}",
                     "p-val KS": f"{pval_ks:.4f}",
                     "AD stat": f"{ad_stat:.4f}" if not np.isnan(ad_stat) else "—", "Qualite": qual})
    return rows


def section_analyse_distributions():
    import matplotlib.pyplot as plt
    from scipy import stats as sp_stats

    if "df_proj" not in st.session_state or "alpha_est" not in st.session_state:
        st.info("Transformez d\'abord le triangle.")
        return

    df_proj  = st.session_state["df_proj"]
    seuil_0  = float(st.session_state["seuil_est"])
    alpha_0  = float(st.session_state["alpha_est"])
    lambda_0 = float(st.session_state["lambda_est"])

    all_sev  = df_proj["Sprime_ultime"].values; all_sev = all_sev[all_sev > 0]
    sev_data = all_sev[all_sev > seuil_0]
    freq_data = df_proj.groupby("annee_surv").size().values

    if len(sev_data) < 10:
        st.warning(f"Seulement {len(sev_data)} sinistres au-dessus du seuil — augmentez le triangle ou réduisez le seuil.")
        return

    tabs_d = st.tabs(["Sélection du seuil", "Sévérité — Fits & CDF", "Fréquence", "Paramètres manuels"])

    # ── Onglet A : seuil ──
    with tabs_d[0]:
        sorted_desc = np.sort(all_sev)[::-1]
        ks_arr, hills_arr = _hill_estimates(sorted_desc, k_max=min(len(sorted_desc)-1, 150))
        k_gert = _gertensgarbe_k(ks_arr, hills_arr)
        alpha_gert = float(hills_arr[k_gert-1]) if k_gert <= len(hills_arr) else alpha_0

        col_h, col_m = st.columns(2)
        with col_h:
            fig_h, ax_h = plt.subplots(figsize=(6,3))
            ax_h.plot(ks_arr, hills_arr, color="#1a1a1a", lw=1.5)
            ax_h.axvline(k_gert, color="#ef4444", ls="--", lw=1.5,
                         label=f"Gertensgarbe k={k_gert} → α={alpha_gert:.3f}")
            ax_h.axhline(alpha_0, color="#2d8a4e", ls=":", lw=1.2, label=f"α actuel={alpha_0:.3f}")
            ax_h.set_xlabel("k"); ax_h.set_ylabel("α(k)"); ax_h.set_title("Hill Plot")
            ax_h.legend(fontsize=8); ax_h.grid(alpha=0.3)
            st.pyplot(fig_h); plt.close()
        with col_m:
            u_mef, e_mef = _mean_excess(all_sev)
            fig_m, ax_m = plt.subplots(figsize=(6,3))
            ax_m.plot(u_mef, e_mef, color="#2d8a4e", lw=2)
            ax_m.axvline(seuil_0, color="#ef4444", ls="--", lw=1.5, label=f"Seuil={seuil_0:,.0f}")
            ax_m.set_xlabel("u"); ax_m.set_ylabel("e(u)"); ax_m.set_title("Mean Excess Function")
            ax_m.legend(fontsize=8); ax_m.grid(alpha=0.3)
            st.pyplot(fig_m); plt.close()

        pcts = [50, 60, 70, 75, 80, 85, 90, 95]
        rows_s = _threshold_table(all_sev, pcts)
        df_s = pd.DataFrame(rows_s)
        st.dataframe(df_s, use_container_width=True)
        st.caption("Bon = KS p-val > 5% et AD < 2.5 | Acceptable = KS p-val > 1%")

        best_row = next((r for r in rows_s if r["Qualite"] == "Bon"), None)
        if best_row:
            st.success(f"Recommandé : {best_row['Seuil %']} = {best_row['Seuil MAD']} MAD — α={best_row['Alpha Hill']}")
            if st.button("Appliquer", key="btn_apply_seuil"):
                st.session_state["seuil_est"] = float(best_row["Seuil MAD"].replace(",","").replace(" ",""))
                st.session_state["alpha_est"] = float(best_row["Alpha Hill"])
                st.rerun()

    # ── Onglet B : sévérité ──
    with tabs_d[1]:
        fits_sev = _fit_severity(sev_data, seuil_0)
        if fits_sev:
            st.dataframe(pd.DataFrame([{
                "Distribution": n,
                "Paramètres": (f"α={f['alpha']:.4f}" if n=="Pareto" else
                               f"μ={f['mu']:.3f} σ={f['sigma']:.3f}" if n=="Log-Normale" else
                               f"ξ={f['xi']:.4f} β={f['beta']:.0f}"),
                "KS": f"{f['ks']:.4f}", "p-val": f"{f['pval']:.4f}",
                "Adéquation": "Bon" if f["pval"]>0.05 else "Acceptable" if f["pval"]>0.01 else "Rejeté"
            } for n, f in fits_sev.items()]), use_container_width=True)

        fig_c, axes_c = plt.subplots(1, 2, figsize=(12,4))
        x_s = np.sort(sev_data)
        axes_c[0].plot(x_s, np.arange(1,len(x_s)+1)/len(x_s), "k-", lw=2.5, label="Empirique")
        colors_d = {"Pareto":"#ef4444","Log-Normale":"#3b82f6","GPD":"#2d8a4e"}
        for nom, f in fits_sev.items():
            try:
                col = colors_d.get(nom,"#888")
                if nom=="Pareto": y = np.clip(1-(x_s/f["xm"])**(-f["alpha"]),0,1)
                elif nom=="Log-Normale": y = sp_stats.lognorm.cdf(x_s, s=f["sigma"], scale=np.exp(f["mu"]))
                elif nom=="GPD": y = sp_stats.genpareto.cdf(x_s-seuil_0, f["xi"], loc=0, scale=f["beta"])
                else: continue
                axes_c[0].plot(x_s, y, "--", color=col, lw=1.8, label=f"{nom} p={f['pval']:.3f}")
            except: pass
        axes_c[0].set_xlabel("MAD"); axes_c[0].set_ylabel("F(x)")
        axes_c[0].set_title("CDF Sévérité"); axes_c[0].legend(fontsize=8); axes_c[0].grid(alpha=0.3)
        # QQ-Plot
        log_x = np.log(np.sort(sev_data)/seuil_0); n_q = len(log_x)
        th_q = -np.log(1-(np.arange(1,n_q+1)/(n_q+1)))
        axes_c[1].scatter(th_q, log_x, color="#2d8a4e", s=15, alpha=0.7)
        mn_q = min(th_q.min(), log_x.min()); mx_q = max(th_q.max(), log_x.max())
        axes_c[1].plot([mn_q,mx_q],[mn_q,mx_q],"r--",lw=1.5)
        axes_c[1].set_xlabel("Quantiles Exp(1)"); axes_c[1].set_ylabel("log(X/seuil)")
        axes_c[1].set_title("QQ-Plot Pareto"); axes_c[1].grid(alpha=0.3)
        st.pyplot(fig_c); plt.close()

    # ── Onglet C : fréquence ──
    with tabs_d[2]:
        fits_freq = _fit_frequency(freq_data)
        if fits_freq:
            rows_fr = []
            for nom, f in fits_freq.items():
                if "note" in f: rows_fr.append({"Distribution":nom,"Paramètres":f["note"],"KS":"—","p-val":"—","Adéquation":"—"})
                else: rows_fr.append({"Distribution":nom,
                    "Paramètres": f"λ={f['lambda']:.3f}" if nom=="Poisson" else f"r={f['r']:.3f} p={f['p']:.4f}",
                    "KS": f"{f['ks']:.4f}", "p-val": f"{f['pval']:.4f}",
                    "Adéquation": "Bon" if f["pval"]>0.05 else "Acceptable" if f["pval"]>0.01 else "Rejeté"})
            st.dataframe(pd.DataFrame(rows_fr), use_container_width=True)

        fig_fr, ax_fr = plt.subplots(figsize=(8,4))
        v, c = np.unique(freq_data, return_counts=True)
        ax_fr.bar(v, c/len(freq_data), color="#2d8a4e", alpha=0.7, label="Observée", zorder=3)
        x_r = np.arange(0, max(freq_data)+2)
        if "Poisson" in fits_freq and "pval" in fits_freq["Poisson"]:
            ax_fr.plot(x_r, sp_stats.poisson.pmf(x_r, fits_freq["Poisson"]["lambda"]),
                       "r--o", ms=5, lw=1.5, label=f"Poisson(λ={fits_freq['Poisson']['lambda']:.2f})")
        if "BN" in fits_freq and "r" in fits_freq["BN"]:
            f_nb = fits_freq["BN"]
            ax_fr.plot(x_r, sp_stats.nbinom.pmf(x_r, f_nb["r"], f_nb["p"]),
                       "b--s", ms=5, lw=1.5, label=f"BN(r={f_nb['r']:.2f})")
        ax_fr.set_xlabel("Sinistres/an"); ax_fr.set_title("Fréquence annuelle")
        ax_fr.legend(); ax_fr.grid(alpha=0.3)
        st.pyplot(fig_fr); plt.close()
        disp_ratio = float(np.var(freq_data)/max(np.mean(freq_data),0.01))
        st.info(f"Indice de dispersion = {disp_ratio:.2f} ({'surdispersion → BN pertinente' if disp_ratio>1.2 else 'équidispersion → Poisson adapté'})")

    # ── Onglet D : manuel ──
    with tabs_d[3]:
        c1,c2,c3 = st.columns(3)
        with c1: alpha_m  = st.slider("Alpha",  0.5, 5.0,  float(alpha_0),  0.05, key="alpha_manual")
        with c2: lambda_m = st.slider("Lambda", 0.5, 30.0, float(lambda_0), 0.5,  key="lambda_manual")
        with c3:
            p40 = int(np.percentile(all_sev, 40)); p92 = int(np.percentile(all_sev, 92))
            seuil_m = st.slider("Seuil MAD", p40, p92, int(seuil_0), 50000, key="seuil_manual")

        exc_m = all_sev[all_sev > seuil_m]
        if len(exc_m) >= 5:
            fig_mn, ax_mn = plt.subplots(figsize=(8,3))
            xs_m = np.sort(exc_m)
            ax_mn.plot(xs_m, np.arange(1,len(xs_m)+1)/len(xs_m), "k-", lw=2, label="Empirique")
            ax_mn.plot(xs_m, np.clip(1-(xs_m/seuil_m)**(-alpha_m),0,1), "r--", lw=1.8,
                       label=f"Pareto(α={alpha_m:.2f})")
            ax_mn.set_xlabel("MAD"); ax_mn.set_title("CDF Sévérité — paramètres manuels")
            ax_mn.legend(); ax_mn.grid(alpha=0.3)
            st.pyplot(fig_mn); plt.close()
        if st.button("Appliquer ces paramètres", type="primary", key="apply_manual"):
            st.session_state["alpha_est"]  = alpha_m
            st.session_state["lambda_est"] = lambda_m
            st.session_state["seuil_est"]  = float(seuil_m)
            st.success(f"Paramètres mis à jour : α={alpha_m:.4f}, λ={lambda_m:.4f}, seuil={seuil_m:,.0f}")
            st.rerun()

    # Stocker pour l\'agent LLM
    try:
        fits_sev_stored = _fit_severity(sev_data, seuil_0)
        fits_freq_stored = _fit_frequency(freq_data)
        st.session_state["dist_fit_results"] = {
            "severity": {k: {kk: float(vv) if isinstance(vv,(int,float,np.floating)) else vv
                             for kk,vv in v.items() if kk != "threshold"}
                         for k,v in fits_sev_stored.items()},
            "frequency": {k: {kk: float(vv) if isinstance(vv,(int,float,np.floating)) else vv
                               for kk,vv in v.items()}
                          for k,v in fits_freq_stored.items()},
            "n_exceedances": int(len(sev_data)),
            "overdispersion_ratio": float(np.var(freq_data)/max(np.mean(freq_data),0.01)),
            "alpha_gert": alpha_gert,
        }
    except: pass


# ════════════════════════════════════════════
# TAB AGENT — AGENT PYTHON PUR (HORS LIGNE)
# ════════════════════════════════════════════

with tab_agent:
    section_header("Agent de Tarification Autonome", "Calcul actuariel complet — BC · Simulation · Market Curve · Optimisation du programme", "")

    st.markdown("""<div style="background:linear-gradient(135deg,#0d2b1a,#1a1a1a);border-radius:12px;
        padding:18px 24px;margin-bottom:16px;border:1px solid rgba(45,138,78,0.4)">
        <div style="color:#2d8a4e;font-weight:700;font-size:15px;margin-bottom:8px">
            Séquence de tarification
        </div>
        <div style="color:#ccc;font-size:13px;line-height:1.9">
            Validation des paramètres &rarr;
            Burning Cost (formule &sigma;) &rarr;
            Simulation Pareto/Poisson &rarr;
            Contrôles de cohérence &rarr;
            Market Curve (tranches cat) &rarr;
            Rapport de tarification &rarr;
            Optimisation du programme (5 variantes)
        </div></div>""", unsafe_allow_html=True)

    # Prérequis
    prereqs = {
        "Programme"  : True,
        "Triangle"   : "df_proj" in st.session_state,
        "Paramètres" : "alpha_est" in st.session_state,
    }
    c1, c2, c3 = st.columns(3)
    for col, (nom_p, ok) in zip([c1,c2,c3], prereqs.items()):
        col.markdown(f"""<div style="background:{'rgba(45,138,78,0.12)' if ok else 'rgba(239,68,68,0.08)'};
            border:1px solid {'#2d8a4e' if ok else '#ef4444'};border-radius:10px;
            padding:12px;text-align:center">
            <div style="font-size:14px;font-weight:700;color:{'#2d8a4e' if ok else '#ef4444'}">
                {'Prêt' if ok else 'Requis'}</div>
            <div style="font-size:11px;color:#aaa;margin-top:2px">{nom_p}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        n_sim_py = st.number_input("Nombre de simulations", value=10000, step=5000, min_value=1000, key="nsim_py")
    with c_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        lancer_py = st.button("Lancer la tarification", type="primary", use_container_width=True,
                              disabled="df_proj" not in st.session_state)

    if "df_proj" not in st.session_state:
        st.info("Transformez d'abord le triangle dans l'onglet Données & Triangle")

    elif lancer_py:
        with st.spinner("⚙️ Pipeline en cours..."):
            prog_bar = st.progress(0, text="Initialisation...")

            agent = AgentActuarielPython(
                tranches           = tranches_input,
                gnpi               = gnpi,
                df_proj            = st.session_state["df_proj"],
                coeffs             = st.session_state.get("coeffs", np.array([1.0])),
                alpha_est          = st.session_state.get("alpha_est", 1.5),
                lambda_est         = st.session_state.get("lambda_est", 5.0),
                seuil_est          = st.session_state.get("seuil_est", 1_600_000),
                Pm_proxy           = st.session_state.get("Pm_proxy", 0),
                chargement_majeurs = st.session_state.get("chargement_majeurs", 0.0),
                df_mkt_clean       = st.session_state.get("df_mkt_clean"),
            )

            prog_bar.progress(10, "Validation paramètres...")
            agent.etape_0_validation()
            prog_bar.progress(25, "Burning Cost...")
            agent.etape_1_burning_cost()
            prog_bar.progress(50, "Simulation...")
            agent.etape_2_simulation(int(n_sim_py))
            prog_bar.progress(65, "Contrôles...")
            agent.etape_3_controles()
            prog_bar.progress(75, "Market Curve...")
            agent.etape_4_market_curve()
            prog_bar.progress(90, "Rapport...")
            agent.etape_5_rapport()
            prog_bar.progress(95, "Optimisation du programme...")
            agent.variantes = agent.etape_6_optimisation()
            rapport_txt = agent.generer_rapport_texte()
            prog_bar.progress(100, "Terminé.")

            # ── Moteurs agentiques V2 ──
            contexte_ag = {
                "has_triangle": "df_proj" in st.session_state,
                "has_market":   st.session_state.get("df_mkt_clean") is not None,
                "n_rows":       len(agent.df_proj) if agent.df_proj is not None else 0,
            }
            plan_ag     = AgentRaisonnement().planifier(contexte_ag)
            critique_ag = AgentCritique().auditer(agent.tranches, agent.gnpi,
                              agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, agent.rapport_rows)
            # Remonter les alertes critique dans l'agent
            for a in critique_ag.get("alertes",[]):
                agent._alerte(a.get("niveau","INFO"), f"{a.get('tranche','')}: {a.get('message','')}")
            ml_ag       = AgentML().entrainer_depuis_df_proj(agent.df_proj)
            memoire_ag  = AgentMemoireMetier().benchmark(
                              user_email=st.session_state.get("user_email",""),
                              tranches=agent.tranches, rapport_rows=agent.rapport_rows,
                              gnpi=agent.gnpi,
                              current_session_id=st.session_state.get("db_session_id"))
            challenge_ag = AgentChallenger().challenger(
                              agent.tranches, agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, agent.rapport_rows)
            opt_ag       = AgentOptimisationProgramme(agent.gnpi).explorer(
                              agent.tranches, agent.resultats_bc, agent.resultats_sim,
                              agent.resultats_mkt, objectif="equilibre", top_n=8)

            # Stocker dans session_state
            st.session_state["resultats_bc"]        = agent.resultats_bc
            st.session_state["resultats_sim"]        = agent.resultats_sim
            st.session_state["taux_mkt_final"]       = agent.resultats_mkt
            st.session_state["df_rapport"]           = pd.DataFrame(agent.rapport_rows)
            st.session_state["prime_totale"]         = agent.prime_totale
            st.session_state["agent_py_log"]         = agent.log
            st.session_state["agent_py_anomalies"]   = agent.anomalies
            st.session_state["agent_py_rapport"]     = rapport_txt
            st.session_state["agent_py_variantes"]          = agent.variantes
            st.session_state["agent_plan_agentique"]         = plan_ag
            st.session_state["agent_critique"]               = critique_ag
            st.session_state["agent_ml"]                     = ml_ag
            st.session_state["agent_memoire_metier"]         = memoire_ag
            st.session_state["agent_challenger"]             = challenge_ag
            st.session_state["agent_optimisation_avancee"]   = opt_ag
            st.session_state["agent_py_done"]                = True

            # Auto-save
            try:
                db_save_session(st.session_state.get("user_email",""), gnpi, tranches_input)
                db_save_etape("bc",  [{k:v for k,v in r.items() if k!="detail_annuel"} for r in agent.resultats_bc])
                db_save_etape("sim", agent.resultats_sim)
                if agent.resultats_mkt:
                    db_save_etape("mkt", {"resultats_mkt":[], "taux_mkt_final": agent.resultats_mkt})
                db_save_etape("rapport", {"rows": agent.rapport_rows, "prime_totale": agent.prime_totale})
            except: pass

    # ── Affichage des résultats ──
    if st.session_state.get("agent_py_done"):

        # ── Moteurs agentiques V2 ──
        if any(st.session_state.get(k) for k in ["agent_plan_agentique","agent_critique","agent_ml","agent_memoire_metier","agent_challenger","agent_optimisation_avancee"]):
            with st.expander("Raisonnement · Critique · Mémoire · Challenger · ML · Optimisation avancée", expanded=True):
                afficher_plan_agentique(st.session_state.get("agent_plan_agentique"))
                afficher_critique_agentique(st.session_state.get("agent_critique"))
                afficher_memoire_metier(st.session_state.get("agent_memoire_metier"))
                afficher_challenger(st.session_state.get("agent_challenger"))
                afficher_ml_agentique(st.session_state.get("agent_ml"))
                afficher_optimisation_avancee(st.session_state.get("agent_optimisation_avancee"))

        # ── Alertes
        anomalies = st.session_state.get("agent_py_anomalies", [])
        if anomalies:
            st.markdown("#### Points d'attention")
            for a in anomalies:
                color = {"CRITIQUE":"#ef4444","WARN":"#f59e0b","INFO":"#3b82f6"}.get(a["niveau"],"#888")
                st.markdown(f"""<div style="border-left:3px solid {color};padding:8px 14px;
                    margin:3px 0;font-size:13px;background:rgba(0,0,0,0.03)">
                    [{a['niveau']}] {a['message']}</div>""", unsafe_allow_html=True)

        # ── Taux par méthode ──
        if st.session_state.get("resultats_bc"):
            c_bc, c_sim = st.columns(2)
            with c_bc:
                st.markdown("#### Burning Cost")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "Années non nulles": r.get("n_ann_nonzero",0),
                    "Taux pur": f"{r['taux_pur']:.4%}",
                    "Ecart-type": f"{r.get('sigma_hist',0):.4%}",
                    "Taux technique": f"{r['taux_technique']:.4%}",
                } for r in st.session_state["resultats_bc"]])
            with c_sim:
                st.markdown("#### Simulation")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "Taux pur": f"{r['taux_pur']:.4%}",
                    "Taux technique": f"{r['taux_technique']:.4%}",
                    "Impact rec.": f"{r.get('impact_rec',0):.4%}",
                } for r in st.session_state["resultats_sim"]])

        # ── Rapport de tarification ──
        if st.session_state.get("df_rapport") is not None:
            st.markdown("#### Tarification retenue")
            def _g(row, *keys):
                for k in keys:
                    if k in row: return row[k]
                return ""
            tableau_resultats([{
                "Tranche": _g(row,"tranche","Tranche"),
                "BC": f"{float(_g(row,'taux_bc',0) or 0):.4%}",
                "Simulation": f"{float(_g(row,'taux_sim',0) or 0):.4%}",
                "Marché": f"{float(_g(row,'taux_mkt',0) or 0):.4%}",
                "Taux retenu": f"{float(_g(row,'taux_retenu',0) or 0):.4%}",
                "Prime (MAD)": f"{float(_g(row,'prime_MAD',0) or 0):,.0f}",
                "Sélection": _g(row,"methode","Méthode"),
            } for row in st.session_state["df_rapport"].to_dict("records")])
            pt = st.session_state.get("prime_totale",0)
            c1,c2 = st.columns(2)
            with c1: card("Prime totale", f"{pt:,.0f} MAD", icone="💰")
            with c2: card("Taux global",  f"{pt/gnpi:.4%}", couleur="#1a1a1a", icone="")

        # ── 5 VARIANTES DE PROGRAMME OPTIMAL ──
        variantes = st.session_state.get("agent_py_variantes", {})
        if variantes:
            st.markdown("---")
            st.markdown("#### Optimisation du programme — 5 variantes (perspective leader)")
            st.caption("En tant que leader, ces variantes structurent la proposition de tarification et la marge de négociation.")

            cols = st.columns(len(variantes))
            colors_v = ["#1a1a1a","#2d8a4e","#3b82f6","#f59e0b","#7c3aed"]
            for col, (key, v), color in zip(cols, variantes.items(), colors_v):
                delta = v["ecart_ref_pts"]
                delta_str = f"{delta:+.2f} pts" if key != "ref" else "référence"
                with col:
                    st.markdown(f"""<div style="border-top:3px solid {color};background:white;
                        border-radius:0 0 8px 8px;padding:14px 12px;
                        box-shadow:0 2px 8px rgba(0,0,0,0.06);margin-bottom:8px">
                        <div style="font-size:13px;font-weight:700;color:{color}">{v['label']}</div>
                        <div style="font-size:11px;color:#555;margin:4px 0">{v['angle']}</div>
                        <div style="font-size:18px;font-weight:700;color:#1a1a1a;margin:8px 0">
                            {v['taux_global']:.4%}</div>
                        <div style="font-size:11px;color:#888">{v['prime']:,.0f} MAD</div>
                        <div style="font-size:11px;color:{color};font-weight:600;margin-top:4px">
                            {delta_str}</div>
                        </div>""", unsafe_allow_html=True)

            # Tableau comparatif détaillé
            with st.expander("Détail des 5 variantes — paramètres et justifications", expanded=False):
                rows_v = []
                for key, v in variantes.items():
                    for t in v["tranches"]:
                        rows_v.append({
                            "Variante": v["label"],
                            "Tranche": t["nom"],
                            "Priorité (MAD)": f"{t['priorite']:,.0f}",
                            "Portée (MAD)": f"{t['portee']:,.0f}",
                            "Reconst.": t.get("nb_reconstitutions","—"),
                            "AAL": f"{t['AAL']:,.0f}" if t.get("AAL") else "—",
                            "AAD": f"{t['AAD']:,.0f}" if t.get("AAD") else "—",
                            "Taux": f"{t.get('_taux',0):.4%}",
                        })
                tableau_resultats(rows_v)

                st.markdown("**Justifications actuarielles :**")
                for key, v in variantes.items():
                    st.markdown(f"**{v['label']}** — {v['description']}")

        # ── Journal des décisions ──
        with st.expander("Journal des décisions actuarielles", expanded=False):
            log_data = [{"Etape": e["etape"], "Décision": e["decision"],
                         "Détail": e["detail"]} for e in st.session_state.get("agent_py_log",[])]
            if log_data: tableau_resultats(log_data)

        # ── Rapport texte ──
        with st.expander("Rapport complet (format texte)", expanded=False):
            st.code(st.session_state.get("agent_py_rapport",""), language="text")

        st.markdown("")
        if st.button("Nouvelle tarification", key="relancer_py"):
            for k in ["agent_py_done","agent_py_log","agent_py_anomalies",
                      "agent_py_rapport","agent_py_variantes"]:
                st.session_state.pop(k, None)
            st.rerun()


# ════════════════════════════════════════════
# TAB PHASE 3 — AGENT COMPLET AUTONOME
# ════════════════════════════════════════════

with tab_full:
    section_header("Agent Complet LLM", "Fichiers bruts → Rapport final — Raisonnement LLM Claude (API requise)", "🚀")

    st.markdown("""
    <div style="background:linear-gradient(135deg,#0d0d1a,#1a1a1a);border-radius:12px;
        padding:20px 24px;margin-bottom:24px;border:1px solid rgba(59,130,246,0.4)">
        <div style="color:#3b82f6;font-weight:700;font-size:15px;margin-bottom:10px">
            ⚡ Agent Complet — LLM Claude (API Anthropic requise)
        </div>
        <div style="display:flex;gap:32px;flex-wrap:wrap">
            <div style="color:#ccc;font-size:13px;line-height:2">
                ✅ Uploade les fichiers bruts ici<br>
                ✅ Claude parse le triangle seul<br>
                ✅ Claude décide branche longue/courte<br>
                ✅ Claude calibre alpha et lambda
            </div>
            <div style="color:#ccc;font-size:13px;line-height:2">
                ✅ Claude lance BC + Simulation + Market Curve<br>
                ✅ Claude détecte et corrige les anomalies<br>
                ✅ Claude choisit la méthode par tranche<br>
                ✅ Claude produit le rapport final
            </div>
        </div>
        <div style="color:#888;font-size:12px;margin-top:10px">
            Seul un <b style="color:#f59e0b">seuil d'alerte critique</b> interrompt l'agent pour validation humaine.
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Uploads directs ──
    st.markdown("### 📁 Fichiers sources")
    c1, c2, c3, c4 = st.columns(4)
    with c1: f3_tri = st.file_uploader("Triangle développement", type=["xlsx","csv"], key="f3_tri")
    with c2: f3_gnp = st.file_uploader("Base GNPIs",             type=["xlsx","csv"], key="f3_gnp")
    with c3: f3_idx = st.file_uploader("Table indices",          type=["xlsx","csv"], key="f3_idx")
    with c4: f3_mkt = st.file_uploader("Données marché",         type=["xlsx","csv"], key="f3_mkt")

    # ── Config minimale ──
    st.markdown("### ⚙️ Configuration minimale")
    c1, c2, c3 = st.columns(3)
    with c1: gnpi3      = st.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000, key="gnpi3")
    with c2: annee3     = st.number_input("Année de cotation", value=2026, step=1, key="annee3")
    with c3: retour3    = st.number_input("Période de retour sinistres majeurs (ans)", value=20, step=5, key="retour3")

    # ── Contexte pour l'agent ──
    contexte3 = st.text_area("📌 Contexte pour l'agent (optionnel)",
        placeholder="Ex: Portefeuille automobile Maroc 2026, GNPI en hausse +8%, 3 tranches : Risk&Cat 13M xs 2M, Cat L1 10M xs 15M, Cat L2 15M xs 25M. Objectif prime < 14M MAD. Réassureur cible : Partner Re.",
        height=90, key="contexte3")

    seuil_alerte = st.slider(
        "🚨 Seuil d'alerte critique (interrompt l'agent)",
        min_value=10, max_value=60, value=35, step=5,
        help="Si écart BC/Simulation > ce seuil sur tranche travaillante → agent demande validation avant de continuer",
        key="seuil_alerte3")

    fichiers_ok = all([f3_tri, f3_gnp, f3_idx, f3_mkt, api_key])

    if not api_key:
        st.warning("⚠️ Clé API requise dans la sidebar")
    elif not fichiers_ok:
        manquants3 = [n for n, f in [("Triangle",f3_tri),("GNPIs",f3_gnp),("Indices",f3_idx),("Marché",f3_mkt)] if not f]
        st.warning(f"⚠️ Fichiers manquants : {', '.join(manquants3)}")

    lancer3 = st.button("🚀 Lancer l'Agent Complet", type="primary",
                        use_container_width=True, disabled=not fichiers_ok,
                        key="lancer3")

    # ════════════════════════════════
    # OUTILS PHASE 3 (étend phase 2)
    # ════════════════════════════════

    TOOLS_FULL = [
        {
            "name": "analyser_et_transformer_triangle",
            "description": """Parse et transforme le triangle de liquidation brut.
Détecte automatiquement le type de branche (long/court), applique As-If, stabilisation, Chain Ladder.
Estime alpha (MLE Hill), lambda Poisson, seuil p80×D, Pm proxy.
Retourne les statistiques clés et les paramètres calibrés.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "type_branche": {
                        "type": "string",
                        "enum": ["long", "court"],
                        "description": "Branche longue (As-If+Stab+CL) ou courte (As-If seul)"
                    },
                    "seuil_stabilisation": {
                        "type": "number",
                        "description": "Seuil de déclenchement clause stabilisation (0.0 = toujours, 0.1 = 10%)"
                    },
                    "pct_seuil_pareto": {
                        "type": "number",
                        "description": "Percentile pour le seuil Pareto (0.80 = p80 × D)"
                    },
                    "justification": {"type": "string"}
                },
                "required": ["type_branche", "seuil_stabilisation", "pct_seuil_pareto", "justification"]
            }
        },
        {
            "name": "definir_programme_tranches",
            "description": """Définit ou ajuste le programme de réassurance (tranches, conditions, frais).
Claude peut proposer les tranches basées sur le contexte fourni ou ajuster les valeurs par défaut.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tranches": {
                        "type": "array",
                        "description": "Liste des tranches avec leurs paramètres",
                        "items": {
                            "type": "object",
                            "properties": {
                                "nom"              : {"type": "string"},
                                "type"             : {"type": "string", "enum": ["travaillante","cat","non_travaillante"]},
                                "priorite"         : {"type": "number"},
                                "portee"           : {"type": "number"},
                                "nb_reconstitutions": {"type": "integer"},
                                "taux_reconstitution": {"type": "number"},
                                "brokage_pct"      : {"type": "number"},
                                "frais_pct"        : {"type": "number"},
                                "marge_pct"        : {"type": "number"}
                            }
                        }
                    },
                    "justification": {"type": "string"}
                },
                "required": ["tranches", "justification"]
            }
        },
        {
            "name": "calculer_burning_cost_complet",
            "description": "Calcule le BC sur les données transformées. Identique à l'outil Phase 2.",
            "input_schema": {
                "type": "object",
                "properties": {"justification": {"type": "string"}},
                "required": ["justification"]
            }
        },
        {
            "name": "lancer_simulation_complete",
            "description": "Lance la simulation avec les paramètres calibrés automatiquement.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "alpha"         : {"type": "number"},
                    "lambda_"       : {"type": "number"},
                    "seuil"         : {"type": "number"},
                    "n_sim"         : {"type": "integer"},
                    "justification" : {"type": "string"}
                },
                "required": ["alpha", "lambda_", "seuil", "n_sim", "justification"]
            }
        },
        {
            "name": "construire_market_curve_complete",
            "description": "Construit la market curve sur les données uploadées.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "rol_min"       : {"type": "number"},
                    "rol_max"       : {"type": "number"},
                    "r2_min"        : {"type": "number"},
                    "tolerance"     : {"type": "number"},
                    "filtre_branche": {"type": "string", "description": "Mot-clé colonne INT_BUSINESS (ex: EVENEMENT)"},
                    "justification" : {"type": "string"}
                },
                "required": ["rol_min", "rol_max", "r2_min", "tolerance", "filtre_branche", "justification"]
            }
        },
        {
            "name": "demander_validation_humaine",
            "description": """Interrompt l'agent pour demander une validation humaine sur un point critique.
À utiliser UNIQUEMENT si : anomalie grave, écart très élevé, paramètre hors norme, données suspectes.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "niveau"   : {"type": "string", "enum": ["avertissement", "critique", "bloquant"]},
                    "message"  : {"type": "string", "description": "Message clair pour l'humain"},
                    "question" : {"type": "string", "description": "Question précise à poser à l'humain"},
                    "choix"    : {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Options proposées à l'humain"
                    }
                },
                "required": ["niveau", "message", "question", "choix"]
            }
        },
        {
            "name": "generer_rapport_final_complet",
            "description": "Génère le rapport final complet avec recommandations.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "methode_travaillante": {"type": "string", "enum": ["bc","simulation","moyenne_bc_sim"]},
                    "methode_cat"         : {"type": "string", "enum": ["simulation","market_curve","max_sim_mkt"]},
                    "justification"       : {"type": "string"}
                },
                "required": ["methode_travaillante", "methode_cat", "justification"]
            }
        },
        {
            "name": "evaluer_pertinence_methodes",
            "description": """Analyse la pertinence statistique de chaque méthode de tarification
(BC, Simulation Pareto, Market Curve) pour chaque tranche du programme.
Utilise les résultats des tests KS/AD, la qualité du fit des distributions,
la suffisance des données historiques, et la cohérence entre méthodes.
Retourne un diagnostic structuré avec recommandation par tranche.
A appeler AVANT de générer le rapport final pour fonder le choix de méthode
sur des critères statistiques objectifs, pas seulement des règles fixes.""",
            "input_schema": {
                "type": "object",
                "properties": {
                    "inclure_tests_ks_ad":    {"type": "boolean", "description": "Inclure les résultats KS/AD"},
                    "inclure_stabilite_hill": {"type": "boolean", "description": "Inclure l'analyse Hill"},
                    "justification":          {"type": "string"}
                },
                "required": ["justification"]
            }
        }
    ]

    # ── Exécuteur evaluer_pertinence_methodes ──
    def _executer_evaluer_methodes(inclure_ks_ad=True, inclure_hill=True):
        """Analyse statistique de la pertinence de chaque méthode par tranche."""
        from scipy import stats as _sp_stats
        diag = {}
        has_bc   = "resultats_bc"  in st.session_state
        has_sim  = "resultats_sim" in st.session_state
        has_mkt  = bool(st.session_state.get("taux_mkt_final"))
        has_dist = "dist_fit_results" in st.session_state
        diag["disponibilite"] = {"bc":has_bc,"simulation":has_sim,"market_curve":has_mkt,"dist_fit":has_dist}
        dist_fit = st.session_state.get("dist_fit_results", {})
        sev_fits = dist_fit.get("severity", {})
        best_sev = None; best_pval = 0
        diag["distribution_fit"] = {}
        for nom_d, f in sev_fits.items():
            pval = f.get("pval",0)
            diag["distribution_fit"][nom_d] = {"ks":round(f.get("ks",1),4),"pval":round(pval,4),
                "adequation":"bon" if pval>0.05 else "acceptable" if pval>0.01 else "rejete"}
            if pval > best_pval: best_pval=pval; best_sev=nom_d
        diag["distribution_recommandee"] = best_sev or "Pareto"
        diag["n_exceedances"]  = dist_fit.get("n_exceedances",0)
        diag["overdispersion"] = dist_fit.get("overdispersion_ratio",1.0)
        bc_list  = st.session_state.get("resultats_bc", [])
        sim_list = st.session_state.get("resultats_sim",[])
        mkt_list = st.session_state.get("taux_mkt_final",[])
        tranches_analyse = []
        for t in tranches_input:
            nom_t = t["nom"]
            bc_r  = next((r for r in bc_list  if r["tranche"]==nom_t),{})
            sim_r = next((r for r in sim_list if r["tranche"]==nom_t),{})
            mkt_r = next((r for r in mkt_list if r["tranche"]==nom_t),{})
            bc_tt=bc_r.get("taux_technique",0); sim_tt=sim_r.get("taux_technique",0)
            mkt_tt=mkt_r.get("taux",0) if t["type"]!="travaillante" else 0
            n_nz=bc_r.get("n_ann_nonzero",0)
            ecart=abs(bc_tt-sim_tt)/bc_tt*100 if bc_tt>0 else 999
            bc_ok=n_nz>=5 and bc_tt>0; sim_ok=best_pval>0.01 and sim_tt>0
            mkt_ok=has_mkt and mkt_tt>0 and t["type"]!="travaillante"
            if t["type"]=="travaillante":
                if bc_ok and sim_ok and ecart<30: rec="max(BC,Simulation)"; raison=f"Coherent BC/Sim ({ecart:.0f}%)"
                elif bc_ok and sim_ok:            rec="Simulation (ecart eleve)"; raison=f"Ecart={ecart:.0f}%>30% — Sim prioritaire"
                elif bc_ok:                       rec="Burning Cost"; raison=f"{n_nz} ans — dist. faible"
                elif sim_ok:                      rec="Simulation"; raison=f"BC<5 ans non nuls"
                else:                             rec="Jugement expert"; raison="Donnees insuffisantes"
            else:
                if mkt_ok and sim_ok:  rec="max(Simulation,MarketCurve)"; raison="Cat: deux methodes disponibles"
                elif sim_ok:           rec="Simulation"; raison="Market curve absente/faible"
                elif mkt_ok:           rec="Market Curve"; raison="Historique cat limite"
                else:                  rec="Jugement expert"; raison="Donnees insuffisantes"
            tranches_analyse.append({"tranche":nom_t,"type":t["type"],"n_ann_bc":n_nz,
                "bc_fiable":bc_ok,"sim_fiable":sim_ok,"mkt_fiable":mkt_ok,
                "taux_bc":round(bc_tt,6),"taux_sim":round(sim_tt,6),"taux_mkt":round(mkt_tt,6),
                "ecart_bc_sim_pct":round(ecart,1),"methode_recommandee":rec,"raison":raison})
        diag["analyse_par_tranche"] = tranches_analyse
        diag["synthese"] = {
            "distribution_severite": best_sev or "Pareto",
            "adequation": "bonne" if best_pval>0.05 else "acceptable" if best_pval>0.01 else "faible",
            "frequence_modele": "BN" if diag["overdispersion"]>1.2 else "Poisson",
            "nb_bc_fiable":  sum(1 for t in tranches_analyse if t["bc_fiable"]),
            "nb_sim_fiable": sum(1 for t in tranches_analyse if t["sim_fiable"]),
            "nb_mkt_fiable": sum(1 for t in tranches_analyse if t["mkt_fiable"]),
        }
        return _json_safe(diag)

    # ── Exécuteur triangle complet ──
    def _executer_transformer_triangle_complet(type_branche, seuil_stab, pct_seuil_p,
                                                f_tri, f_gnp, f_idx, gnpi_val, annee_cot):
        try:
            import io as _io
            is_long_p3 = (type_branche == "long")
            # ── Seek & read files (Streamlit UploadedFile needs seek before each read) ──
            f_gnp.seek(0)
            df_gnpis_p3 = pd.read_excel(_io.BytesIO(f_gnp.read())) if f_gnp.name.endswith('xlsx') else pd.read_csv(f_gnp)
            f_idx.seek(0)
            df_idx_p3   = pd.read_excel(_io.BytesIO(f_idx.read())) if f_idx.name.endswith('xlsx') else pd.read_csv(f_idx)
            df_gnpis_p3.columns = [str(c).strip() for c in df_gnpis_p3.columns]
            df_idx_p3.columns   = [str(c).strip() for c in df_idx_p3.columns]

            df_idx_p3['Annee'] = pd.to_numeric(
                df_idx_p3['Annee'].astype(str).str.strip().str.replace('.0','',regex=False), errors='coerce')
            df_idx_p3['Coefficients'] = pd.to_numeric(
                df_idx_p3['Coefficients'].astype(str).str.replace(',','.',regex=False).str.replace(' ','',regex=False), errors='coerce')
            df_idx_p3 = df_idx_p3.dropna(subset=['Annee','Coefficients'])
            df_idx_p3['Annee'] = df_idx_p3['Annee'].astype(int)
            df_idx_p3 = df_idx_p3.sort_values('Annee')
            df_idx_set_p3 = df_idx_p3.set_index('Annee')['Coefficients']

            def get_idx(annee):
                annee = int(annee)
                ann = df_idx_set_p3.index.values.astype(int)
                val = df_idx_set_p3.values.astype(float)
                if annee in ann: return float(df_idx_set_p3.loc[annee])
                if annee < ann[0]:  return float(val[0] - (val[1]-val[0])*(ann[0]-annee))
                if annee > ann[-1]: return float(val[-1] + (val[-1]-val[-2])*(annee-ann[-1]))
                return float(np.interp(annee, ann, val))

            I_cot = get_idx(annee_cot)

            f_tri.seek(0)
            tri_bytes = f_tri.read()
            if f_tri.name.endswith('xlsx'):
                df_raw_p3 = pd.read_excel(_io.BytesIO(tri_bytes), header=None)
            else:
                df_raw_p3 = pd.read_csv(_io.BytesIO(tri_bytes), header=None)
            ligne_ann = df_raw_p3.iloc[0].tolist(); ligne_typ = df_raw_p3.iloc[1].tolist()
            annee_cur = None; col_info_p3 = []
            for i, (a, t) in enumerate(zip(ligne_ann, ligne_typ)):
                if i == 0: col_info_p3.append(('UW_YEAR','')); continue
                try:
                    av = int(float(str(a).strip().replace('.0','')))
                    if 2010 <= av <= 2050: annee_cur = av
                except: pass
                col_info_p3.append((annee_cur, str(t).strip().upper() if pd.notna(t) else ''))

            df_data_p3 = df_raw_p3.iloc[2:].reset_index(drop=True)
            df_data_p3.iloc[:, 0] = df_data_p3.iloc[:, 0].ffill()

            recs = []
            for idx_r, row in df_data_p3.iterrows():
                try:
                    as_ = int(float(str(row.iloc[0]).strip().replace('.0','')))
                    if not (2010 <= as_ <= 2050): continue
                except: continue
                sid = f"{as_}_{idx_r}"
                for ci, (ar, ty) in enumerate(col_info_p3):
                    if ty != 'TOTAL' or ar is None: continue
                    v = row.iloc[ci]
                    try:
                        if isinstance(v, str):
                            v = v.strip().replace(',','.').replace(' ','')
                            if any(c.isalpha() for c in v) or '#' in v: continue
                        v = float(v)
                        if v <= 0 or np.isnan(v): continue
                    except: continue
                    dv = ar - as_
                    if dv < 0 or dv > 9: continue
                    recs.append({'sinistre_id':sid,'annee_surv':as_,'annee_reg':ar,'dev':dv,'total':v})

            df_liq_p3 = pd.DataFrame(recs)
            df_liq_p3['annee_ultime'] = df_liq_p3['annee_surv'] + 9
            df_liq_p3 = df_liq_p3.sort_values(['sinistre_id', 'dev']).reset_index(drop=True)
            df_liq_p3['annee_ultime'] = df_liq_p3['annee_surv'] + 9
            df_liq_p3['I_ultime'] = df_liq_p3['annee_ultime'].apply(get_idx)
            df_liq_p3['I_reg']    = df_liq_p3['annee_reg'].apply(get_idx)
            df_liq_p3['I_surv']   = df_liq_p3['annee_surv'].apply(get_idx)

            # ── Décumul → As-If sur incréments → Recumul ──
            df_liq_p3['prev_total']  = df_liq_p3.groupby('sinistre_id')['total'].shift(1).fillna(0)
            df_liq_p3['increment']   = (df_liq_p3['total'] - df_liq_p3['prev_total']).clip(lower=0)
            df_liq_p3['inc_asif']    = df_liq_p3['increment'] * (I_cot / df_liq_p3['I_reg'])
            df_liq_p3['ratio_check'] = df_liq_p3['I_reg'] / df_liq_p3['I_surv']
            mask_s = df_liq_p3['ratio_check'] >= (1.0 + seuil_stab)
            df_liq_p3['inc_stab']   = np.where(mask_s,
                df_liq_p3['inc_asif'] * (df_liq_p3['I_surv'] / df_liq_p3['I_reg']),
                df_liq_p3['inc_asif'])
            df_liq_p3['Sk']        = df_liq_p3.groupby('sinistre_id')['inc_asif'].cumsum()
            df_liq_p3['S_prime_k'] = df_liq_p3.groupby('sinistre_id')['inc_stab'].cumsum()
            df_liq_p3['coeff_stab'] = np.where(df_liq_p3['S_prime_k']>0, df_liq_p3['Sk']/df_liq_p3['S_prime_k'], 1.0)

            if is_long_p3:
                facteurs_p3 = {k: [] for k in range(9)}
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            tk = grp.loc[k,'S_prime_k']; tk1 = grp.loc[k+1,'S_prime_k']
                            if tk > 0:
                                f = tk1/tk
                                if 0.9 <= f <= 2.5: facteurs_p3[k].append(f)
                f_moy_p3 = {k: np.mean(facteurs_p3[k]) if facteurs_p3[k] else 1.0 for k in range(9)}
                projs = []
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p = grp['annee_surv'].iloc[0]; dm = grp.index.max()
                    sp = grp.loc[dm,'S_prime_k']; cs = grp.loc[dm,'coeff_stab']
                    for k in range(dm,9): sp *= f_moy_p3[k]
                    projs.append({'sinistre_id':sid,'annee_surv':as_p,'dev_max':dm,
                                  'Sprime_ultime':sp,'Sk_ultime':sp*cs,'coeff_stab':cs})
            else:
                f_moy_p3 = {k:1.0 for k in range(9)}
                projs = []
                for sid, grp in df_liq_p3.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p = grp['annee_surv'].iloc[0]; dm = grp.index.max()
                    sk_ = grp.loc[dm,'Sk']
                    projs.append({'sinistre_id':sid,'annee_surv':as_p,'dev_max':dm,
                                  'Sprime_ultime':sk_,'Sk_ultime':sk_,'coeff_stab':1.0})

            df_proj_p3 = pd.DataFrame(projs)
            D_trav_p3  = next((t['priorite'] for t in st.session_state.get("tranches_p3", tranches_input) if t['type']=='travaillante'), 2_000_000)
            sm_p3      = pct_seuil_p * D_trav_p3
            X_p3       = df_proj_p3['Sprime_ultime'].values; X_p3 = X_p3[X_p3>0]
            Pm_p3      = np.percentile(X_p3, 99.5)
            Xm_p3      = X_p3[(X_p3>=sm_p3)&(X_p3<Pm_p3)]
            if len(Xm_p3)<5: Xm_p3 = X_p3[X_p3>=sm_p3]
            alpha_p3   = len(Xm_p3) / np.sum(np.log(Xm_p3/np.min(Xm_p3)))

            df_gi      = df_gnpis_p3.set_index(df_gnpis_p3.columns[0])
            gc_p3      = df_gnpis_p3.columns[1]
            dpm        = df_proj_p3[(df_proj_p3['Sprime_ultime']>=sm_p3)&(df_proj_p3['Sprime_ultime']<Pm_p3)]
            N_obs_p3   = dpm.groupby('annee_surv').size()
            lv = []
            for an, cn in N_obs_p3.items():
                try: lv.append(cn * gnpi_val / float(df_gi.loc[an, gc_p3]))
                except: lv.append(cn)
            lambda_p3  = float(np.mean(lv)) if lv else 5.0
            coeffs_p3  = df_proj_p3['coeff_stab'].values
            coeffs_p3  = coeffs_p3[(coeffs_p3>0)&np.isfinite(coeffs_p3)]

            # Stocker dans session
            st.session_state.update({
                "df_liq": df_liq_p3, "df_proj": df_proj_p3, "f_moyens": f_moy_p3,
                "alpha_est": float(alpha_p3), "lambda_est": float(lambda_p3),
                "seuil_est": float(sm_p3), "Pm_proxy": float(Pm_p3),
                "coeffs": coeffs_p3, "is_long": is_long_p3,
                "I_cotation": I_cot, "annee_cotation": annee_cot,
                "seuil_stabilisation": seuil_stab, "df_gnpis_df": df_gnpis_p3,
            })

            n_sins = df_proj_p3['sinistre_id'].nunique()
            n_ann  = df_proj_p3['annee_surv'].nunique()
            return {
                "status": "ok",
                "type_branche": type_branche,
                "nb_sinistres": int(n_sins), "nb_annees": int(n_ann),
                "nb_observations": len(df_liq_p3),
                "alpha_estime": round(float(alpha_p3), 4),
                "lambda_estime": round(float(lambda_p3), 4),
                "seuil_pareto_MAD": round(float(sm_p3), 0),
                "Pm_proxy_MAD": round(float(Pm_p3), 0),
                "I_cotation": round(float(I_cot), 4),
                "nb_obs_stabilisees": int(mask_s.sum()),
                "observations": f"{n_sins} sinistres sur {n_ann} années",
                "recommandation_alpha": "Cohérent" if 1.0 < alpha_p3 < 3.0 else "Vérifier — hors norme [1.0, 3.0]"
            }
        except Exception as e:
            return {"erreur": str(e)}


    def _executer_definir_programme(tranches_def):
        """Définit le programme depuis la décision de l'agent"""
        prog = []
        for t in tranches_def:
            prog.append({
                "numero": len(prog)+1,
                "nom": t.get("nom", f"Tranche {len(prog)+1}"),
                "type": t.get("type", "travaillante"),
                "priorite": float(t.get("priorite", 2_000_000)),
                "portee":   float(t.get("portee",   13_000_000)),
                "AAL": None, "AAD": None,
                "nb_reconstitutions":  int(t.get("nb_reconstitutions", 1)),
                "taux_reconstitution": float(t.get("taux_reconstitution", 100)),
                "indices": False,
                "brokage":      float(t.get("brokage_pct", 10)) / 100,
                "frais":        float(t.get("frais_pct",    5)) / 100,
                "marge":        float(t.get("marge_pct",   10)) / 100,
                "retrocession": 0.0
            })
        st.session_state["tranches_p3"] = prog
        return {"status": "ok", "programme": [{
            "nom": t["nom"], "type": t["type"],
            "priorite_MAD": t["priorite"], "portee_MAD": t["portee"],
            "reconstitutions": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
            "charges": f"Brokage {t['brokage']:.0%} | Frais {t['frais']:.0%} | Marge {t['marge']:.0%}"
        } for t in prog]}


    def _executer_market_curve_p3(rol_min, rol_max, r2_min, tolerance, filtre, f_mkt_file, gnpi_val):
        """Market curve sur fichier uploadé directement"""
        try:
            import io as _io
            f_mkt_file.seek(0)
            df_mkt_p3 = pd.read_excel(_io.BytesIO(f_mkt_file.read())) if f_mkt_file.name.endswith('xlsx') else pd.read_csv(f_mkt_file)
            df_mkt_p3.columns = [c.strip() for c in df_mkt_p3.columns]
            for col in ['ROLs','midpoints','Garantie en MAD']:
                if col in df_mkt_p3.columns and df_mkt_p3[col].dtype == object:
                    df_mkt_p3[col] = (df_mkt_p3[col].astype(str).str.replace('%','').str.replace(' ','').str.replace(',','.')
                        .apply(lambda x: float(x)/100 if x not in ['nan',''] and float(x)>1.5
                               else (float(x) if x not in ['nan',''] else np.nan)))
            df_mkt_p3 = df_mkt_p3.dropna(subset=['ROLs','midpoints'])
            if filtre.strip():
                col_b = next((c for c in df_mkt_p3.columns if 'BUSINESS' in c.upper()), None)
                if col_b:
                    df_mkt_p3 = df_mkt_p3[df_mkt_p3[col_b].astype(str).str.upper()
                                           .str.contains(filtre.upper(), regex=False, na=False)]
            mask_r = (df_mkt_p3['ROLs'] >= rol_min) & (df_mkt_p3['ROLs'] <= rol_max)
            df_mkt_p3 = df_mkt_p3[mask_r].copy()
            df_mkt_p3['diff_rel'] = np.where(df_mkt_p3['midpoints']!=0,
                np.abs(df_mkt_p3['ROLs']-df_mkt_p3['midpoints'])/np.abs(df_mkt_p3['midpoints']),1.0)
            df_mkt_p3 = df_mkt_p3[df_mkt_p3['diff_rel']>=tolerance].copy()
            df_mkt_p3 = df_mkt_p3[df_mkt_p3['midpoints']>0].copy()
            if len(df_mkt_p3) < 5: return {"erreur": f"Seulement {len(df_mkt_p3)} points — filtres trop restrictifs"}

            st.session_state["df_mkt_clean"] = df_mkt_p3
            prog_p3 = st.session_state.get("tranches_p3", tranches_input)

            def fit_p(x, y):
                lx=np.log(x); ly=np.log(y); c=np.polyfit(lx,ly,1)
                a=np.exp(c[1]); b=-c[0]; lyp=np.polyval(c,lx)
                r2=1-np.sum((ly-lyp)**2)/np.sum((ly-ly.mean())**2+1e-10)
                return a,b,r2

            def ctt(t, a, b):
                x=(t['priorite']+t['portee']/2)/gnpi_val
                rol=a*(x**(-b)); tp=rol*t['portee']/gnpi_val
                tr=tp*1.002; tt=tr/(1-t['brokage']-t['frais']-0.0021)
                L=t['portee']; t_r=t['taux_reconstitution']/100; n_r=t['nb_reconstitutions']
                Pr=sum(t_r*min(L,max(tp*gnpi_val-(r-1)*L,0)) for r in range(1,n_r+1))/(L or 1)
                Rec=Pr/(Pr+10)
                return {"tranche":t["nom"],"type":t["type"],"x_norm":round(x,6),
                        "rol":round(rol,6),"taux_pur":round(tp,6),"taux_tech":round(tt,6),
                        "chargement_majeurs":round(st.session_state.get("chargement_majeurs",0.0),6),"taux":round(tt,6)}

            resultats_p3_mkt = []
            for q in [0.20,0.40,0.60,0.80,1.0]:
                mq = np.quantile(df_mkt_p3['midpoints'],q)
                dq = df_mkt_p3[df_mkt_p3['midpoints']<=mq]
                if len(dq)<5: continue
                try:
                    a,b,r2=fit_p(dq['midpoints'].values,dq['ROLs'].values)
                    if b<=0: continue
                    tts=[ctt(t,a,b) for t in prog_p3]
                    if any(tt['taux']<=0 for tt in tts): continue
                    resultats_p3_mkt.append({"quantile":q,"n_points":len(dq),"a":round(a,6),
                        "b":round(b,4),"r2":round(r2,4),"r2_ok":r2>=r2_min,
                        "taux_tranches":tts,"score":r2-(0 if r2>=r2_min else 0.5)})
                except: continue

            if not resultats_p3_mkt: return {"erreur": "Aucun ajustement valide"}
            best = max(resultats_p3_mkt, key=lambda x: x["score"])
            st.session_state["resultats_mkt"]  = resultats_p3_mkt
            st.session_state["taux_mkt_final"] = best["taux_tranches"]
            return _json_safe({"status":"ok","a":best["a"],"b":best["b"],"r2":best["r2"],
                    "r2_ok":best["r2_ok"],"n_points":best["n_points"],
                    "taux_par_tranche":best["taux_tranches"],
                    "interpretation": "R² satisfaisant" if best["r2_ok"] else "R² faible — interpréter avec prudence"})
        except Exception as e:
            return {"erreur": str(e)}


    def executer_outil_full(nom, inputs, f_tri_f, f_gnp_f, f_idx_f, f_mkt_f, gnpi_v, annee_v):
        """Dispatcher Phase 3 — inclut les outils de parsing fichiers"""
        if nom == "analyser_et_transformer_triangle":
            return _executer_transformer_triangle_complet(
                inputs.get("type_branche", "long"), inputs.get("seuil_stabilisation", 0.0),
                inputs.get("pct_seuil_pareto", 0.80), f_tri_f, f_gnp_f, f_idx_f, gnpi_v, annee_v)
        elif nom == "definir_programme_tranches":
            return _executer_definir_programme(inputs.get("tranches", []))
        elif nom == "calculer_burning_cost_complet":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_burning_cost_p3(prog, gnpi_v)
        elif nom == "lancer_simulation_complete":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_simulation(inputs.get("alpha", st.session_state.get("alpha_est",1.5)), inputs.get("lambda_", st.session_state.get("lambda_est",5.0)), inputs.get("seuil", st.session_state.get("seuil_est",1_600_000)), int(inputs.get("n_sim", 10000)))
        elif nom == "construire_market_curve_complete":
            return _executer_market_curve_p3(
                inputs.get("rol_min", 0.05), inputs.get("rol_max", 1.0), inputs.get("r2_min", 0.30),
                inputs.get("tolerance", 0.50), inputs.get("filtre_branche", "EVENEMENT"), f_mkt_f, gnpi_v)
        elif nom == "demander_validation_humaine":
            return {"status": "validation_requise",
                    "niveau": inputs.get("niveau","avertissement"), "message": inputs.get("message",""),
                    "question": inputs.get("question",""), "choix": inputs.get("choix", ["Continuer", "Arrêter"])}
        elif nom == "generer_rapport_final_complet":
            prog = st.session_state.get("tranches_p3", tranches_input)
            return _executer_rapport_p3(inputs.get("methode_travaillante","simulation"), inputs.get("methode_cat","max_sim_mkt"), prog, gnpi_v)
        elif nom == "evaluer_pertinence_methodes":
            return _executer_evaluer_methodes(
                inclure_ks_ad=inputs.get("inclure_tests_ks_ad", True),
                inclure_hill=inputs.get("inclure_stabilite_hill", True))
        else:
            return {"erreur": f"Outil inconnu : {nom}"}


    def _executer_burning_cost_p3(prog, gnpi_v):
        if "df_proj" not in st.session_state: return {"erreur": "df_proj manquant"}
        df_proj = st.session_state["df_proj"].copy()
        resultats = []
        for t_info in prog:
            D=t_info["priorite"]; L=t_info["portee"]
            aal=t_info["AAL"]; aad=t_info["AAD"]
            n_rec=t_info["nb_reconstitutions"]; t_r=t_info["taux_reconstitution"]/100
            cap=(n_rec+1)*L
            df_proj["Ck"] = df_proj.apply(
                lambda row: min(max(row["Sprime_ultime"]-D,0),L)*row["coeff_stab"], axis=1)
            charges_ann = df_proj.groupby("annee_surv")["Ck"].sum()
            cfs = []
            for an, ch in charges_ann.items():
                if aad: ch=max(ch-aad,0)
                if aal: ch=min(ch,aal)
                cfs.append({"annee":int(an),"charge":round(float(min(ch,cap)),2)})
            df_ch=pd.DataFrame(cfs); N=len(df_ch)
            Pr=0.0
            for Cn in df_ch["charge"].values:
                for r in range(1,n_rec+1): Pr+=t_r*min(L,max(Cn-(r-1)*L,0))
            Pr/=L if L>0 else 1
            Rec=Pr/(Pr+N) if (Pr+N)>0 else 0.0
            cm = df_ch["charge"].mean()
            charges_nz = [c for c in df_ch["charge"].values if c > 0]
            n_nz = len(charges_nz)
            charg_maj_p3 = st.session_state.get("chargement_majeurs", 0.0)
            if n_nz < 3:
                tp = tr = tt = 0.0; sig_p3 = 0.0
            else:
                tp = cm / gnpi_v
                sig_p3 = float(np.std(charges_nz)) / gnpi_v
                tr = tp + sig_p3 * 0.20
                tt = (tr*(1-Rec))/(1-t_info["brokage"]-t_info["frais"]-t_info["marge"]-t_info["retrocession"])
            resultats.append({"tranche":t_info["nom"],"type":t_info["type"],
                "charge_moy":round(cm,2),"n_ann_nonzero":n_nz,"sigma_hist":round(sig_p3 if n_nz>=3 else 0.0,6),
                "Pr_Rec":round(Pr,6),"Rec":round(Rec,6),
                "taux_pur":round(tp,6),"taux_risque":round(tr,6),
                "taux_technique":round(tt,6),
                "chargement_majeurs":round(charg_maj_p3,6),
                "detail_annuel":cfs})
        st.session_state["resultats_bc"] = resultats
        return {"status":"ok","resultats":[{k:v for k,v in r.items() if k!="detail_annuel"} for r in resultats]}


    def _executer_rapport_p3(meth_trav, meth_cat, prog, gnpi_v):
        if not all(k in st.session_state for k in ["resultats_bc","resultats_sim","taux_mkt_final"]):
            return {"erreur": "Résultats intermédiaires manquants"}
        _bc_l = st.session_state["resultats_bc"]
        _si_l = st.session_state["resultats_sim"]
        _mk_l = st.session_state["taux_mkt_final"]
        rows=[]; pt=0
        for idx_t, t in enumerate(prog):
            n=t["nom"]
            bt  = _lookup_taux(_bc_l, n, idx_t, "taux_technique")
            st_ = _lookup_taux(_si_l, n, idx_t, "taux_technique")
            mk  = _lookup_taux(_mk_l, n, idx_t, "taux")
            if t["type"]=="travaillante":
                if meth_trav=="bc": tx=bt; me="BC"
                elif meth_trav=="moyenne_bc_sim": tx=(bt+st_)/2; me="Moy BC+Sim"
                else: tx=st_; me="Simulation"
            else:
                if meth_cat=="market_curve": tx=mk; me="Marché"
                elif meth_cat=="max_sim_mkt": tx=max(st_,mk); me="Max(Sim,Marché)"
                else: tx=st_; me="Simulation"
            pr=gnpi_v*tx; pt+=pr
            ec=abs(bt-st_)/bt*100 if bt>0 else 0
            rows.append({"tranche":n,"type":t["type"],
                "taux_bc":round(bt,6),"taux_sim":round(st_,6),"taux_mkt":round(mk,6),
                "taux_retenu":round(tx,6),"methode":me,"prime_MAD":round(pr,2),
                "ecart_bc_sim_pct":round(ec,1)})
        st.session_state["df_rapport"]=pd.DataFrame(rows); st.session_state["prime_totale"]=pt
        return {"status":"ok","synthese":rows,"prime_totale_MAD":round(pt,2),"taux_global":round(pt/gnpi_v,6)}


    # ════════════════════════════════
    # BOUCLE AGENTIQUE PHASE 3
    # ════════════════════════════════

    def run_agent_full(api_key, f_tri_f, f_gnp_f, f_idx_f, f_mkt_f,
                       gnpi_v, annee_v, contexte_v, seuil_al,
                       log_cont, result_cont, alert_cont):
        client = anthropic.Anthropic(api_key=api_key)

        system_p3 = f"""Tu es un agent actuariel autonome de niveau expert.
Tu as accès aux fichiers bruts d'Atlantic Re pour la tarification 2026.

CONTEXTE FOURNI PAR L'UTILISATEUR :
{contexte_v if contexte_v else "Portefeuille automobile Maroc, GNPI {gnpi_v:,} MAD, année cotation {annee_v}."}

GNPI : {gnpi_v:,} MAD | Année cotation : {annee_v}
Seuil d'alerte critique (écart BC/Sim) : {seuil_al}%
Période de retour sinistres majeurs : {retour3} ans

SÉQUENCE OBLIGATOIRE :
1. DÉFINIR le programme (tranches, priorités, portées, frais) depuis le contexte fourni
2. ANALYSER ET TRANSFORMER le triangle (choix branche longue/courte basé sur les données)
3. CALCULER le Burning Cost
4. LANCER la Simulation avec les paramètres calibrés
5. Si écart BC/Sim > {seuil_al}% → DEMANDER_VALIDATION_HUMAINE
6. CONSTRUIRE la Market Curve (filtre EVENEMENT par défaut)
7. Si R² < 0.25 → DEMANDER_VALIDATION_HUMAINE
8. GÉNÉRER le rapport final

RÈGLES DE DÉCISION AUTONOME :
- Branche longue si portefeuille > 5 ans d'historique avec développement > 3 ans
- Alpha suspect si < 0.8 ou > 4.0 → signaler mais continuer
- Pour tranches cat : méthode = max(simulation, market_curve)
- Pour tranches travaillantes : méthode = simulation sauf si BC/Sim < 15%
- Ne JAMAIS demander validation pour des décisions techniques mineures
- Justifie CHAQUE décision avec des chiffres

Agis de façon professionnelle et autonome."""

        messages = [{"role": "user", "content":
            f"Lance la tarification complète Atlantic Re 2026. GNPI={gnpi_v:,} MAD. Contexte : {contexte_v if contexte_v else 'Standard automobile Maroc'}. Go."}]

        tour=0; max_t=15; validation_en_attente=None

        while tour < max_t:
            tour+=1
            with log_cont:
                st.markdown(f"""<div style="background:#1a1a1a;border-radius:6px;padding:6px 12px;
                    margin:4px 0;font-size:11px;color:#888">Tour {tour}/{max_t}</div>""",
                    unsafe_allow_html=True)

            resp = client.messages.create(
                model="claude-opus-4-5", max_tokens=4096,
                system=system_p3, tools=TOOLS_FULL, messages=messages)

            for block in resp.content:
                if hasattr(block,'text') and block.text:
                    with log_cont:
                        st.markdown(f"""<div style="background:rgba(45,138,78,0.07);
                            border-left:3px solid #2d8a4e;border-radius:0 8px 8px 0;
                            padding:12px 16px;margin:6px 0;font-size:13px;line-height:1.6">
                            🧠 {block.text}</div>""", unsafe_allow_html=True)

                if block.type == "tool_use":
                    with log_cont:
                        just = block.input.get("justification","")
                        params_display = {k:v for k,v in block.input.items() if k not in ["justification","tranches"]}
                        st.markdown(f"""<div style="background:rgba(59,130,246,0.07);
                            border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
                            padding:12px 16px;margin:6px 0;font-size:13px">
                            ⚙️ <b style="color:#3b82f6">{block.name}</b><br>
                            <span style="color:#666;font-size:11px">{just}</span><br>
                            <code style="font-size:11px">{json.dumps(params_display,ensure_ascii=False)[:200]}</code>
                            </div>""", unsafe_allow_html=True)

            if resp.stop_reason == "end_turn": break

            if resp.stop_reason == "tool_use":
                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use": continue

                    with log_cont:
                        with st.spinner(f"⚙️ {block.name}..."):
                            result = executer_outil_full(
                                block.name, block.input,
                                f_tri_f, f_gnp_f, f_idx_f, f_mkt_f,
                                gnpi_v, annee_v)

                    # Gestion validation humaine
                    if result.get("status") == "validation_requise":
                        # ── Validation non-bloquante : affiche l'alerte et continue ──
                        niveau = result.get("niveau","avertissement")
                        color_map = {"avertissement":"#f59e0b","critique":"#ef4444","bloquant":"#7c3aed"}
                        col_a = color_map.get(niveau, "#f59e0b")
                        with alert_cont:
                            choix_defaut = result.get("choix", ["Continuer"])[0]
                            st.markdown(f"""<div style="background:rgba(245,158,11,0.08);
                                border:2px solid {col_a};border-radius:12px;
                                padding:16px 20px;margin:8px 0">
                                <div style="color:{col_a};font-weight:700;font-size:14px;margin-bottom:6px">
                                    🚨 {niveau.upper()} — {result.get('message','')}
                                </div>
                                <div style="color:#555;font-size:13px">
                                    {result.get('question','')}
                                </div>
                                <div style="color:#2d8a4e;font-size:12px;margin-top:8px">
                                    ✅ L'agent continue automatiquement avec : <b>{choix_defaut}</b>
                                </div></div>""", unsafe_allow_html=True)
                        result = {"status": "validation_confirmee",
                                  "choix_humain": choix_defaut,
                                  "message": f"Auto-continué : {choix_defaut}"}

                    erreur = result.get("erreur","")
                    with log_cont:
                        if erreur:
                            st.markdown(f"""<div style="background:rgba(239,68,68,0.08);
                                border-left:3px solid #ef4444;border-radius:0 8px 8px 0;
                                padding:10px 14px;margin:4px 0;font-size:12px">
                                ❌ <b>{block.name}</b> : {erreur}</div>""", unsafe_allow_html=True)
                        else:
                            status_txt = result.get("status","ok")
                            st.markdown(f"""<div style="background:rgba(45,138,78,0.06);
                                border-left:3px solid #2d8a4e;border-radius:0 8px 8px 0;
                                padding:10px 14px;margin:4px 0;font-size:12px">
                                ✅ <b>{block.name}</b> — {status_txt}</div>""", unsafe_allow_html=True)

                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": json.dumps(_json_safe(result), ensure_ascii=False)})

                messages.append({"role":"assistant","content":resp.content})
                messages.append({"role":"user","content":tool_results})
            else:
                break

        # Résultats finaux
        with result_cont:
            st.markdown("---")
            st.markdown("## 📊 Résultats Agent Complet")

            if "tranches_p3" in st.session_state:
                st.markdown("### 📋 Programme défini par l'agent")
                tableau_resultats([{
                    "Tranche": t["nom"], "Type": t["type"],
                    "Priorité": f"{t['priorite']:,.0f} MAD",
                    "Portée": f"{t['portee']:,.0f} MAD",
                    "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
                    "Charges": f"Brok {t['brokage']:.0%} | Frais {t['frais']:.0%} | Marge {t['marge']:.0%}"
                } for t in st.session_state["tranches_p3"]])

            if "df_proj" in st.session_state:
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Sinistres",  st.session_state["df_proj"]["sinistre_id"].nunique())
                c2.metric("Alpha",      f"{st.session_state.get('alpha_est',0):.4f}")
                c3.metric("Lambda",     f"{st.session_state.get('lambda_est',0):.4f}")
                c4.metric("Seuil MAD",  f"{st.session_state.get('seuil_est',0):,.0f}")

            if "resultats_bc" in st.session_state and "resultats_sim" in st.session_state:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("### 🔥 Burning Cost")
                    tableau_resultats([{
                        "Tranche": r["tranche"],
                        "Rec": f"{r['Rec']:.4%}",
                        "Taux pur": f"{r['taux_pur']:.4%}",
                        "Taux tech.": f"{r['taux_technique']:.4%}",
                    } for r in st.session_state["resultats_bc"]])
                with col_b:
                    st.markdown("### 🎲 Simulation")
                    tableau_resultats([{
                        "Tranche": r["tranche"],
                        "Taux pur": f"{r['taux_pur']:.4%}",
                        "Taux tech.": f"{r['taux_technique']:.4%}",
                        "Impact rec.": f"{r.get('impact_rec', 0):.4%}",
                    } for r in st.session_state["resultats_sim"]])

            if "taux_mkt_final" in st.session_state:
                st.markdown("### 📈 Market Curve")
                tableau_resultats([{
                    "Tranche": tt["tranche"],
                    "ROL": f"{tt['rol']:.4%}",
                    "Taux tech.": f"{tt['taux_tech']:.4%}",
                    "Taux final": f"{tt['taux']:.4%}",
                } for tt in st.session_state["taux_mkt_final"]])

            if "df_rapport" in st.session_state:
                st.markdown("### 📋 Rapport Final")
                tableau_resultats([{
                    "Tranche": row["tranche"], "Type": row["type"],
                    "Taux BC": f"{row['taux_bc']:.4%}",
                    "Taux Sim.": f"{row['taux_sim']:.4%}",
                    "Taux Marché": f"{row['taux_mkt']:.4%}",
                    "✅ Retenu": f"{row['taux_retenu']:.4%}",
                    "Prime (MAD)": f"{row['prime_MAD']:,.0f}",
                    "Méthode": row["methode"],
                    "Écart BC/Sim": f"{row['ecart_bc_sim_pct']:.0f}%",
                } for row in st.session_state["df_rapport"].to_dict("records")])

                pt = st.session_state.get("prime_totale", 0)
                c1,c2,c3 = st.columns(3)
                with c1: card("Prime totale", f"{pt:,.0f} MAD", icone="💰")
                with c2: card("Taux global",  f"{pt/gnpi_v:.4%}", couleur="#1a1a1a", icone="📊")
                with c3: card("Agent",        "Complet ✅", couleur="#3b82f6", icone="🚀")


    # ── Lancement Phase 3 ──
    if lancer3:
        st.markdown("---")
        st.markdown("### 🚀 Exécution Agent Complet")
        alert_cont  = st.container()
        log_cont    = st.container()
        result_cont = st.container()

        with log_cont:
            st.markdown("""<div style="background:linear-gradient(135deg,#0d0d1a,#1a1a1a);
                border-radius:10px;padding:14px 18px;margin-bottom:12px;
                border:1px solid rgba(59,130,246,0.4)">
                <span style="color:#3b82f6;font-weight:700">🚀 Agent Complet démarré</span>
                <span style="color:#888;font-size:12px;margin-left:8px">
                Traitement en cours ...</span>
                </div>""", unsafe_allow_html=True)
        try:
            run_agent_full(api_key, f3_tri, f3_gnp, f3_idx, f3_mkt,
                           gnpi3, annee3, contexte3, seuil_alerte,
                           log_cont, result_cont, alert_cont)
            with log_cont:
                st.success("✅ Agent Complet terminé — rapport disponible ci-dessus et dans tous les onglets")
        except Exception as e:
            st.error(f"❌ Erreur agent complet : {e}")

    elif not lancer3 and "df_rapport" in st.session_state:
        st.info("✅ Résultats de la dernière exécution disponibles dans les onglets.")
        if st.button("🔄 Relancer l'Agent Complet", key="relancer3"):
            for k in ["tranches_p3","df_proj","df_liq","resultats_bc","resultats_sim",
                      "resultats_mkt","taux_mkt_final","df_rapport"]:
                st.session_state.pop(k, None)
            st.rerun()



# ════════════════════════════════════════════
# TAB HISTORIQUE
# ════════════════════════════════════════════

with tab_hist:
    section_header("Historique des Sessions", "Consultez et rechargez vos tarifications passées", "📜")

    user_email_hist = st.session_state.get("user_email", "")
    if not user_email_hist:
        st.warning("⚠️ Connectez-vous pour accéder à l'historique")
    else:
        try:
            sessions = db_list_sessions(user_email_hist)
        except Exception as _e:
            sessions = []
            st.error(f"Erreur DB : {_e}")

        if not sessions:
            st.info("📭 Aucune session sauvegardée.")
            st.markdown("""
            <div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
                border-radius:0 8px 8px 0;padding:14px 18px;margin:8px 0;font-size:13px">
                <b>Comment créer une session ?</b><br>
                1. Définissez votre programme dans l'onglet 📋 Programme<br>
                2. Lancez au moins un calcul (BC, Simulation ou Market Curve)<br>
                3. Cliquez <b>💾 Sauvegarder maintenant</b> dans la sidebar<br>
                4. La session apparaîtra ici automatiquement
            </div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"**{len(sessions)} session(s) trouvée(s)** pour {user_email_hist}")

            # Tableau des sessions
            sess_data = []
            for sid, nom, gnpi_s, created, updated in sessions:
                is_current = (sid == st.session_state.get("db_session_id"))
                sess_data.append({
                    "ID": sid,
                    "Session": f"{'⭐ ' if is_current else ''}{nom or f'Session #{sid}'}",
                    "GNPI": f"{gnpi_s:,.0f} MAD" if gnpi_s else "—",
                    "Créée": created or "—",
                    "Modifiée": updated or "—",
                })
            tableau_resultats(sess_data)

            st.divider()
            st.markdown("### 🔄 Charger une session")
            c1, c2 = st.columns([3, 1])
            with c1:
                sess_options = {f"#{sid} — {nom or 'Sans nom'} ({updated})": sid
                                for sid, nom, _, _, updated in sessions}
                choix_sess = st.selectbox("Choisir une session à charger",
                    options=list(sess_options.keys()), key="hist_select")
            with c2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("📂 Charger", type="primary", use_container_width=True):
                    sid_choix = sess_options[choix_sess]
                    try:
                        nom_load = db_load_session(sid_choix)
                        # Résumé de ce qui a été chargé
                        chargé = []
                        if "resultats_bc"  in st.session_state: chargé.append("🔥 Burning Cost")
                        if "resultats_sim" in st.session_state: chargé.append("🎲 Simulation")
                        if "taux_mkt_final" in st.session_state and st.session_state["taux_mkt_final"]: chargé.append("📈 Market Curve")
                        if "df_rapport"    in st.session_state: chargé.append("📋 Rapport Final")
                        st.success(f"✅ Session restaurée : **{nom_load}**")
                        if chargé:
                            st.markdown(f"""<div style="background:rgba(45,138,78,0.08);
                                border-left:4px solid #2d8a4e;border-radius:0 8px 8px 0;
                                padding:14px 18px;margin:8px 0;font-size:13px">
                                <b>Données disponibles dans :</b><br>
                                {"  ·  ".join(chargé)}<br><br>
                                👉 Naviguez vers l'onglet souhaité pour consulter les résultats.<br>
                                👉 Allez dans <b>📋 Rapport Final</b> pour voir la synthèse complète.
                                </div>""", unsafe_allow_html=True)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Erreur chargement : {_e}")

            # Comparaison N-1
            st.divider()
            st.markdown("### 📊 Comparaison N-1")
            current_sid = st.session_state.get("db_session_id")
            if current_sid and st.session_state.get("df_rapport") is not None:
                try:
                    prev_rows = db_get_previous_session(user_email_hist, current_sid)
                    if prev_rows and st.session_state.get("df_rapport") is not None:
                        curr_rows = st.session_state["df_rapport"].to_dict("records")
                        prev_map = {r.get("Tranche","") or r.get("tranche",""): r for r in prev_rows}
                        comp = []
                        for r in curr_rows:
                            nom_t = r.get("Tranche","") or r.get("tranche","")
                            prev_r = prev_map.get(nom_t, {})
                            taux_curr = r.get("Taux retenu","") or r.get("taux_retenu","")
                            taux_prev = prev_r.get("Taux retenu","") or prev_r.get("taux_retenu","")
                            try:
                                tc = float(str(taux_curr).replace("%",""))
                                tp = float(str(taux_prev).replace("%",""))
                                delta = tc - tp
                                delta_str = f"{'▲' if delta>0 else '▼'} {abs(delta):.4f}%"
                            except:
                                delta_str = "—"
                            comp.append({
                                "Tranche": nom_t,
                                "Taux N (actuel)": taux_curr,
                                "Taux N-1": taux_prev or "—",
                                "Évolution": delta_str,
                            })
                        if comp:
                            st.caption("Comparaison entre la session courante et la précédente")
                            tableau_resultats(comp)
                    else:
                        st.info("Exécutez une tarification complète pour voir la comparaison N-1.")
                except Exception as _e:
                    st.info(f"Comparaison N-1 non disponible : {_e}")
            else:
                st.info("Chargez une session et complétez une tarification pour comparer.")

            # Suppression
            st.divider()
            st.markdown("### 🗑️ Supprimer une session")
            with st.expander("Supprimer (irréversible)", expanded=False):
                del_options = {f"#{sid} — {nom or 'Sans nom'}": sid
                               for sid, nom, _, _, _ in sessions}
                del_choix = st.selectbox("Session à supprimer", list(del_options.keys()),
                                          key="hist_del_select")
                if st.button("🗑️ Confirmer la suppression", key="hist_del_btn"):
                    try:
                        sid_del = del_options[del_choix]
                        db_delete_session(sid_del)
                        if st.session_state.get("db_session_id") == sid_del:
                            st.session_state.pop("db_session_id", None)
                        st.success("✅ Session supprimée")
                        st.rerun()
                    except Exception as _e:
                        st.error(str(_e))

# ════════════════════════════════════════════
# TAB ADMIN
# ════════════════════════════════════════════

with tab_admin:
    st.header("🔐 Interface Administrateur")
    admin_pwd = st.text_input("Mot de passe admin", type="password", key="admin_pwd")
    if admin_pwd == get_admin_password():
        st.success("✅ Accès accordé")
        users = get_users()
        st.markdown("#### 👥 Utilisateurs autorisés")
        st.dataframe(pd.DataFrame([{"Email": e, "Code": c, "Statut": "Actif"}
                                    for e, c in users.items()]), use_container_width=True)
        st.divider()
        st.markdown("#### ⚙️ Gérer les utilisateurs")
        st.info("Allez sur Streamlit Cloud -> Settings -> Secrets et ajoutez :\nadmin_password = 'VotreMDP'\n[users]\n'email@ex.com' = 'CODE'")
        st.divider()
        st.markdown("#### 🎲 Générateur de code")
        col1, col2 = st.columns(2)
        with col1:
            email_new = st.text_input("Email du nouvel utilisateur", key="new_email")
        with col2:
            if st.button("Générer un code"):
                st.session_state["generated_code"] = secrets_lib.token_hex(4).upper()
        if "generated_code" in st.session_state:
            st.success(f"Code généré : **{st.session_state['generated_code']}**")
            if email_new:
                st.code(f'"{email_new}" = "{st.session_state["generated_code"]}"')
    elif admin_pwd:
        st.error("❌ Mot de passe incorrect")
