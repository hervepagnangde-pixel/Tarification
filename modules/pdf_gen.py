"""
Atlantic Re IA — PDF & PPTX generation module
ReportLab pour les rapports PDF, PptxGenJS (Node.js) pour le PowerPoint.
"""
import io as _io_db
import streamlit as st
import os, json, subprocess, tempfile
from datetime import datetime
import numpy as np
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, PageBreak, HRFlowable)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

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
import streamlit as st

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
    pdf_data = buf.getvalue()
    # ── Signature SHA-256 ────────────────────────────────────────
    sig = _pdf_signature_qr(pdf_data)
    return pdf_data


def _pdf_signature_qr(pdf_bytes):
    """Génère un hash SHA-256 du contenu PDF pour la traçabilité."""
    import hashlib
    h = hashlib.sha256(pdf_bytes).hexdigest()
    return h


def envoyer_webhook_notification(sujet, corps_texte, niveau="info"):
    """
    Envoie une notification via webhook Slack ou Microsoft Teams.
    Configurer dans Secrets : SLACK_WEBHOOK_URL ou TEAMS_WEBHOOK_URL
    """
    import urllib.request, urllib.error
    slack_url  = ""
    teams_url  = ""
    try:
        slack_url  = st.secrets.get("SLACK_WEBHOOK_URL", "")
        teams_url  = st.secrets.get("TEAMS_WEBHOOK_URL", "")
    except Exception:
        pass

    icone = {"info":"ℹ️","alerte":"⚠️","rapport_final":"📋","succes":"✅"}.get(niveau,"📊")
    resultats = []

    # ── Slack ──────────────────────────────────────────────────────
    if slack_url:
        payload = json.dumps({
            "text": f"{icone} *[Atlantic Re IA]* {sujet}",
            "blocks": [
                {"type":"section","text":{"type":"mrkdwn",
                    "text":f"{icone} *{sujet}*\n{corps_texte[:500]}"}},
                {"type":"context","elements":[
                    {"type":"mrkdwn","text":f"Atlantic Re IA · {datetime.now().strftime('%d/%m/%Y %H:%M')}"}]}
            ]
        }).encode()
        try:
            req = urllib.request.Request(slack_url, data=payload,
                headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=5)
            resultats.append(("Slack", True, "OK"))
        except Exception as e:
            resultats.append(("Slack", False, str(e)[:80]))

    # ── Teams ──────────────────────────────────────────────────────
    if teams_url:
        color_map = {"info":"0076D7","alerte":"FF8C00","rapport_final":"107C10","succes":"107C10"}
        payload = json.dumps({
            "@type":"MessageCard","@context":"http://schema.org/extensions",
            "themeColor": color_map.get(niveau,"0076D7"),
            "summary": sujet,
            "sections":[{"activityTitle": f"{icone} {sujet}",
                          "activitySubtitle": "Atlantic Re IA",
                          "text": corps_texte[:500]}]
        }).encode()
        try:
            req = urllib.request.Request(teams_url, data=payload,
                headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=5)
            resultats.append(("Teams", True, "OK"))
        except Exception as e:
            resultats.append(("Teams", False, str(e)[:80]))

    return resultats
