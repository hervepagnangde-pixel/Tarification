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
    "🤖 Mode Agent", "🚀 Agent Complet", "📜 Historique", "🔐 Admin"
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
            progress.progress(50, text="As-If...")
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
            df_liq['Sk']           = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

            progress.progress(55, text="Stabilisation...")
            df_liq['ratio_check'] = df_liq['I_reg'] / df_liq['I_surv']
            mask_stab = df_liq['ratio_check'] >= (1.0 + seuil_stabilisation)
            df_liq['S_prime_k'] = np.where(mask_stab, df_liq['Sk'] * (df_liq['I_surv'] / df_liq['I_reg']), df_liq['Sk'])
            df_liq['coeff_stab'] = np.where(df_liq['S_prime_k'] > 0, df_liq['Sk'] / df_liq['S_prime_k'], 1.0)
            n_stab = mask_stab.sum()
            annees_reg_stab = sorted(df_liq[mask_stab]['annee_reg'].unique().tolist())
            st.info(f"📊 Stabilisation | Seuil : {seuil_stabilisation*100:.0f}% | Obs. : {n_stab} | Années règlement : {annees_reg_stab}")

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
        rmt = st.session_state["resultats_mkt"]
        dmc = st.session_state["df_mkt_clean"]
        def predict_rol(x_norm, a, b): return a * (x_norm ** (-b))
        rows_recap = []
        for r in rmt:
            row = {"Q": f"Q{int(r['quantile']*100)}", "N": r["n_points"],
                   "a": f"{r['a']:.5f}", "b": f"{r['b']:.4f}",
                   "R2": f"{r['r2']:.4f}", "R2ok": "OK" if r["r2_ok"] else "faible",
                   "Score": f"{r['score']:.4f}"}
            for tt in r.get("taux_tranches",[]):
                row[tt["tranche"]] = f"{tt['taux']:.4%}" if tt["taux"] > 0 else "NUL"
            rows_recap.append(row)
        st.subheader("📊 Comparaison ajustements — ROL = a x x^(-b)  |  x = (D+C/2)/GNPI")
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

        st.subheader("📊 Taux marché retenus")
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
    # GÉNÉRATION DU RAPPORT TEXTE (sans LLM)
    # ────────────────────────────────────────────
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
        return self.generer_rapport_texte()


# ════════════════════════════════════════════
# TAB AGENT — AGENT PYTHON PUR (HORS LIGNE)
# ════════════════════════════════════════════

with tab_agent:
    section_header("Agent Autonome Python", "Pipeline complet — logique codée, 0 API, fonctionne hors ligne", "🤖")

    st.markdown("""<div style="background:linear-gradient(135deg,#0d2b1a,#1a1a1a);border-radius:12px;
        padding:18px 24px;margin-bottom:16px;border:1px solid rgba(45,138,78,0.4)">
        <div style="color:#2d8a4e;font-weight:700;font-size:15px;margin-bottom:8px">
            ⚡ Agent Python pur — Aucune API, aucun coût, fonctionne hors ligne
        </div>
        <div style="color:#ccc;font-size:13px;line-height:1.9">
            1. Valide les paramètres (alpha, lambda) →
            2. Calcule le BC (R1/R2) →
            3. Lance la simulation →
            4. Contrôle BC vs Sim →
            5. Construit la market curve cat →
            6. Génère le rapport avec sélection conservative
        </div>
        <div style="color:#888;font-size:12px;margin-top:8px">
            La logique de décision est entièrement codée en Python — chaque règle est visible et auditable.
        </div></div>""", unsafe_allow_html=True)

    # Prérequis
    prereqs = {
        "Programme validé"   : "tranches_input" in st.session_state or True,
        "Triangle transformé": "df_proj"         in st.session_state,
        "Alpha/Lambda calibrés":"alpha_est"      in st.session_state,
    }
    c1, c2, c3 = st.columns(3)
    for col, (nom_p, ok) in zip([c1,c2,c3], prereqs.items()):
        col.markdown(f"""<div style="background:{'rgba(45,138,78,0.12)' if ok else 'rgba(239,68,68,0.08)'};
            border:1px solid {'#2d8a4e' if ok else '#ef4444'};border-radius:10px;
            padding:12px;text-align:center">
            <div style="font-size:20px">{'✅' if ok else '❌'}</div>
            <div style="font-size:11px;font-weight:600;color:{'#2d8a4e' if ok else '#ef4444'};margin-top:4px">{nom_p}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("")
    c_left, c_right = st.columns([2, 1])
    with c_left:
        n_sim_py = st.number_input("Nb simulations", value=10000, step=5000, min_value=1000, key="nsim_py")
    with c_right:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        lancer_py = st.button("▶ Lancer l'agent", type="primary", use_container_width=True,
                              disabled=not st.session_state.get("df_proj") is not None or
                                       "df_proj" not in st.session_state)

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle dans l'onglet Données & Triangle")

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
            rapport_txt = agent.generer_rapport_texte()
            prog_bar.progress(100, "Terminé !")

            # Stocker dans session_state
            st.session_state["resultats_bc"]   = agent.resultats_bc
            st.session_state["resultats_sim"]  = agent.resultats_sim
            st.session_state["taux_mkt_final"] = agent.resultats_mkt
            st.session_state["df_rapport"]     = pd.DataFrame(agent.rapport_rows)
            st.session_state["prime_totale"]   = agent.prime_totale
            st.session_state["agent_py_log"]   = agent.log
            st.session_state["agent_py_anomalies"] = agent.anomalies
            st.session_state["agent_py_rapport"]   = rapport_txt
            st.session_state["agent_py_done"]      = True

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

        # Alertes
        anomalies = st.session_state.get("agent_py_anomalies", [])
        if anomalies:
            st.markdown("### 🚨 Alertes détectées")
            for a in anomalies:
                color = {"CRITIQUE":"#ef4444","WARN":"#f59e0b","INFO":"#3b82f6"}.get(a["niveau"],"#888")
                st.markdown(f"""<div style="background:rgba(0,0,0,0.04);border-left:4px solid {color};
                    border-radius:0 8px 8px 0;padding:10px 14px;margin:4px 0;font-size:13px">
                    {a['icone']} <b>[{a['niveau']}]</b> {a['message']}</div>""",
                    unsafe_allow_html=True)

        # Résultats tabulaires
        if st.session_state.get("resultats_bc"):
            st.markdown("### 📊 Résultats par méthode")
            c_bc, c_sim = st.columns(2)
            with c_bc:
                st.markdown("**🔥 Burning Cost**")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "Ans non-nuls": f"{r.get('n_ann_nonzero',0)} {'⚠️' if r.get('n_ann_nonzero',0)<3 else '✅'}",
                    "τ pur": f"{r['taux_pur']:.4%}",
                    "σ": f"{r.get('sigma_hist',0):.4%}",
                    "τ tech.": f"{r['taux_technique']:.4%}",
                } for r in st.session_state["resultats_bc"]])
            with c_sim:
                st.markdown("**🎲 Simulation**")
                tableau_resultats([{
                    "Tranche": r["tranche"],
                    "τ pur": f"{r['taux_pur']:.4%}",
                    "τ tech.": f"{r['taux_technique']:.4%}",
                    "Impact rec.": f"{r.get('impact_rec',0):.4%}",
                } for r in st.session_state["resultats_sim"]])

        if st.session_state.get("df_rapport") is not None:
            st.markdown("### 📋 Rapport final")
            tableau_resultats([{
                "Tranche": row["tranche"], "Type": row["type"],
                "BC": f"{row['taux_bc']:.4%}",
                "Sim.": f"{row['taux_sim']:.4%}",
                "Mkt": f"{row['taux_mkt']:.4%}",
                "✅ Retenu": f"{row['taux_retenu']:.4%}",
                "Prime (MAD)": f"{row['prime_MAD']:,.0f}",
                "Méthode": row["methode"],
                "Écart BC/Sim": f"{row['ecart_bc_sim_pct']:.0f}%",
            } for row in st.session_state["df_rapport"].to_dict("records")])
            pt = st.session_state.get("prime_totale",0)
            c1,c2,c3 = st.columns(3)
            with c1: card("Prime totale", f"{pt:,.0f} MAD", icone="💰")
            with c2: card("Taux global",  f"{pt/gnpi:.4%}", couleur="#1a1a1a", icone="📊")
            with c3: card("Mode",         "Python pur ✅", couleur="#2d8a4e", icone="⚡")

        # Journal des décisions
        with st.expander("📋 Journal des décisions de l'agent", expanded=False):
            st.caption("Chaque décision est tracée avec son étape et sa justification — aucune boîte noire")
            log_data = [{"Étape": e["etape"], "Décision": e["decision"],
                         "Détail": e["detail"]} for e in st.session_state.get("agent_py_log",[])]
            if log_data: tableau_resultats(log_data)

        # Rapport texte complet
        with st.expander("📄 Rapport texte complet (exportable)", expanded=False):
            st.code(st.session_state.get("agent_py_rapport",""), language="text")

        if st.button("🔄 Relancer l'agent", key="relancer_py"):
            for k in ["agent_py_done","agent_py_log","agent_py_anomalies","agent_py_rapport"]:
                st.session_state.pop(k, None)
            st.rerun()


# ════════════════════════════════════════════
# TAB FULL — Redirige vers Agent Python
# ════════════════════════════════════════════

with tab_full:
    section_header("Agent Complet", "Même pipeline que l'onglet Agent — uploadez les fichiers dans Données & Triangle", "🚀")
    st.info("✅ L'agent autonome Python est dans l'onglet **🤖 Mode Agent**. Uploadez vos fichiers dans **📂 Données & Triangle**, puis lancez l'agent.")
    if st.session_state.get("agent_py_done"):
        st.success("✅ Dernière exécution disponible — résultats synchronisés dans tous les onglets.")




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
