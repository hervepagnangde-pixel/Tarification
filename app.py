"""
Atlantic Re IA — Application principale (app.py)  VERSION CORRIGÉE
CORRECTIFS :
  1. Tab 2 — Stabilisation : ratio_check = I_reg / I_surv  (pas I_reg_asif / I_surv_asif)
  2. Phase 3 — AS-IF : coeff = I[annee_cot+dev] / I[annee_reg]  (pas I_cot / I_reg)
"""
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

from modules.db import (
    _get_db_url, _get_conn, _ph,
    db_init, db_audit, db_save_session, db_save_etape,
    db_load_session, db_list_sessions, db_delete_session, db_get_previous_session,
)
from modules.pdf_gen import (
    generer_pdf_rapport, _pdf_signature_qr,
    envoyer_webhook_notification, generer_pptx_rapport,
)
from modules.notifications import (
    _normaliser_destinataires_email, envoyer_notification_email,
    notifier_consultation, generer_pdf_rapport_courant,
    envoyer_rapport_pdf_email, get_destinataires_notifications_agent,
)
from modules.auth import (
    get_admin_password, get_users_details, get_users, check_access,
)
from modules.ui import (
    CSS_ATLANTICRE, card, section_header, tableau_resultats, progress_steps,
    tooltip, html_glossaire_inline, GLOSSAIRE_ACTUARIEL,
)
from modules.prompts import (
    prompt_inputs, _charger_few_shot_dynamiques,
    build_prompt, claude_stream, guide_prompt,
)
from modules.actuarial import (
    selectionner_seuil_pareto, identifier_sinistres_majeurs_gpd,
    identifier_sinistres_majeurs, section_analyse_distributions,
    buehlmann_straub_credibility, bootstrap_ci_bc,
    _hill_estimates, _mean_excess, _gertensgarbe_k,
    _fit_severity, _fit_frequency, _threshold_table,
    detecter_seuil_optimal_tve, comparer_lois_ajustement, afficher_selection_loi,
)
from modules.optimization import (
    _json_safe, optimiser_programme_variantes, afficher_variantes_optimisation,
    afficher_panneau_audit, _lookup_taux, _lookup_result,
)
from modules.resources import (
    RESSOURCES_ACTUARIELLES, SCRIPTS_R_TARIFICATION,
    afficher_ressources_actuarielles, afficher_integration_r,
)
from modules.agents_v2 import (
    AgentRaisonnement, AgentCritique, AgentML, AgentMemoireMetier,
    AgentChallenger, AgentOptimisationProgramme,
    afficher_plan_agentique, afficher_critique_agentique,
    afficher_memoire_metier, afficher_challenger,
    afficher_optimisation_avancee, afficher_ml_agentique,
)
from modules.labo import AgentLaboTarification, _labo_display_section
from modules.agent_python import AgentActuarielPython
from modules.tools_exec import (
    _executer_burning_cost, _executer_simulation, _executer_market_curve,
)

try:
    icon = Image.open("icon.png")
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="Atlantic Re IA", layout="wide", page_icon="🎯")

# ════════════════════════════════════════════
# AUTHENTICATION
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
    .stButton > button { background-color: #1a1a1a; color: white; border: 2px solid #2d8a4e;
        border-radius: 8px; padding: 8px 20px; font-weight: 600; }
    </style>""", unsafe_allow_html=True)
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

if "page" not in st.session_state:
    st.session_state["page"] = "landing"
    try: db_init()
    except: pass

if st.session_state["page"] == "landing":
    st.markdown("""
    <style>.stApp{background:linear-gradient(135deg,#0d0d0d 0%,#1a1a1a 50%,#0d2b1a 100%)!important}</style>
    """, unsafe_allow_html=True)
    st.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;
        min-height:85vh;text-align:center;padding:40px 20px">
        <h1 style="color:white;font-size:42px;font-weight:800;margin:0 0 8px 0">
            Atlantic Re <span style="color:#2d8a4e">IA</span></h1>
        <p style="color:#aaa;font-size:16px;margin:0 0 40px 0">
            Agent de tarification · Réassurance Non-Proportionnelle</p>
    </div>""", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🚀  Lancer l'outil de tarification", type="primary", use_container_width=True):
            st.session_state["page"] = "app"
            st.rerun()
    st.stop()

st.markdown(f"<style>{CSS_ATLANTICRE}</style>", unsafe_allow_html=True)
st.title("Atlantic Re")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning cost · Simulation · Market curve · IA")

with st.sidebar:
    if st.button("🚪 Déconnexion"):
        st.session_state["authenticated"] = False; st.rerun()
    if st.button("🏠 Accueil"):
        st.session_state["page"] = "landing"; st.rerun()
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("🔑 Clé API Claude", type="password", placeholder="sk-ant-...")
    gnpi    = st.number_input("💰 GNPI (MAD)", value=183_000_000, step=1_000_000)
    st.session_state['gnpi'] = gnpi
    st.divider()
    st.markdown("### 📊 Statut des étapes")
    for nom, key in [("Programme","df_prog"),("Données","df_liq"),
                     ("Burning cost","resultats_bc"),("Simulation","resultats_sim"),
                     ("Market curve","resultats_mkt")]:
        st.markdown(f"{'✅' if key in st.session_state else '⬜'} {nom}")
    st.divider()
    st.markdown("### 💾 Base de données")
    _db_url_val = _get_db_url()
    _db_type = "🐘 PostgreSQL (Supabase)" if _db_url_val else "🗄️ SQLite local"
    _db_sid  = st.session_state.get("db_session_id")
    st.markdown(f"{_db_type}")
    if st.button("💾 Sauvegarder maintenant", key="btn_save_now", use_container_width=True):
        try:
            sid = db_save_session(st.session_state.get("user_email",""), gnpi,
                                     st.session_state.get("tranches_input", []))
            if "resultats_bc" in st.session_state:
                db_save_etape("bc", [{k:v for k,v in r.items() if k!="detail_annuel"}
                                      for r in st.session_state["resultats_bc"]])
            if "resultats_sim" in st.session_state:
                db_save_etape("sim", st.session_state["resultats_sim"])
            if st.session_state.get("df_rapport") is not None:
                db_save_etape("rapport", {"rows": st.session_state["df_rapport"].to_dict("records"),
                                           "prime_totale": st.session_state.get("prime_totale",0)})
            st.success(f"✅ Sauvegardé — Session #{sid}")
            st.rerun()
        except Exception as _e:
            st.error(f"Erreur DB : {_e}")
    instructions_globales = st.text_area("Contexte portefeuille", height=120,
        key="instructions_globales", help="Inclus dans TOUS les prompts Claude")

db_audit(st.session_state.get("user_email",""), "session_active",
         f"GNPI={gnpi:,.0f} MAD", st.session_state.get("db_session_id"))


# ════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════
tab1, tab2, tab3, tab4, tab5, tab6, tab_agent, tab_full, tab_hist, tab_admin = st.tabs([
    "📋 Programme", "📂 Données & Triangle",
    "🔥 Burning Cost", "🎲 Simulation",
    "📈 Market Curve", "📋 Rapport Final",
    "🤖 Agent Python", "🚀 Agent LLM", "📜 Historique", "🔐 Admin"
])

# ════════════════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════════════════
with tab1:
    st.header("Programme de Réassurance")
    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)
    tranches_input = []
    defaults = {
        0: {"type":"travaillante","priorite":2_000_000,"portee":13_000_000},
        1: {"type":"cat","priorite":15_000_000,"portee":10_000_000},
        2: {"type":"cat","priorite":25_000_000,"portee":15_000_000},
    }
    for i in range(nb_tranches):
        d = defaults.get(i, {"type":"travaillante","priorite":2_000_000,"portee":13_000_000})
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i==0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                nom      = st.text_input("Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
                type_idx = ["travaillante","non_travaillante","cat"].index(d["type"])
                type_t   = st.selectbox("Type", ["travaillante","non_travaillante","cat"],
                                        index=type_idx, key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)", value=float(d["priorite"]),
                                           step=500_000.0, format="%.0f", key=f"prio_{i}")
                portee   = st.number_input("Portée (MAD)", value=float(d["portee"]),
                                           step=500_000.0, format="%.0f", key=f"port_{i}")
            with c2:
                has_aal = st.checkbox("AAL", key=f"aal_{i}")
                aal_val = st.number_input("Montant AAL (MAD)", value=0.0, step=100_000.0,
                                          format="%.2f", key=f"aal_v_{i}", disabled=not has_aal)
                has_aad = st.checkbox("AAD", key=f"aad_{i}")
                aad_val = st.number_input("Montant AAD (MAD)", value=0.0, step=100_000.0,
                                          format="%.2f", key=f"aad_v_{i}", disabled=not has_aad)
            with c3:
                brokage      = st.number_input("Brokage %",        value=10.0, step=0.01,
                                               format="%.2f", key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %",  value=5.0,  step=0.01,
                                               format="%.2f", key=f"frais_{i}")
                marge        = st.number_input("Marge %",           value=10.0, step=0.01,
                                               format="%.2f", key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",    value=0.0,  step=0.01,
                                               format="%.2f", key=f"retro_{i}")
            nb_recon = st.number_input("Nombre de reconstitutions", value=1, min_value=0,
                                       max_value=5, step=1, key=f"recon_{i}")
            taux_recons = []
            if nb_recon > 0:
                cols_rec = st.columns(min(nb_recon, 5))
                for r_idx in range(nb_recon):
                    with cols_rec[r_idx]:
                        t_r = st.number_input(f"Reconst. {r_idx+1} %", value=100.0,
                                              min_value=0.0, max_value=200.0, step=0.5,
                                              format="%.1f", key=f"txrecon_{i}_{r_idx}")
                        taux_recons.append(t_r)
        tranches_input.append({
            "numero":i+1, "nom":nom, "type":type_t,
            "priorite":float(priorite), "portee":float(portee),
            "AAL":float(aal_val) if has_aal else None,
            "AAD":float(aad_val) if has_aad else None,
            "nb_reconstitutions":int(nb_recon),
            "taux_reconstitution":taux_recons[0] if taux_recons else 100.0,
            "taux_reconstitutions":taux_recons,
            "indices":False,
            "brokage":brokage/100, "frais":frais/100,
            "marge":marge/100, "retrocession":retrocession/100
        })
    if st.button("💾 Valider le programme", type="primary"):
        st.session_state["tranches_input"] = tranches_input
        st.session_state["gnpi"]    = gnpi
        st.session_state["df_prog"] = pd.DataFrame([{
            "Tranche":t["nom"],"Type":t["type"],
            "Priorité":f"{t['priorite']:,.0f}","Portée":f"{t['portee']:,.0f}",
        } for t in tranches_input])
        st.success("✅ Programme validé !")
    if "df_prog" in st.session_state:
        st.dataframe(st.session_state["df_prog"], use_container_width=True)


# ════════════════════════════════════════════
# TAB 2 — DONNÉES & TRIANGLE
# CORRECTIF AS-IF : coeff = I[annee_cot+dev] / I[annee_reg]
# CORRECTIF STAB  : ratio = I_reg / I_surv  (indices historiques)
# ════════════════════════════════════════════
with tab2:
    st.header("Données de base & Transformation triangle")

    # ── CORRECTIF AS-IF ──────────────────────────────────────────────────────
    st.info("""
    **Formule AS-IF retenue (corrigée) :**
    `inc_asif = increment × I(annee_cotation + dev) / I(annee_reg)`
    
    **Formule stabilisation (corrigée) :**
    `ratio_check = I_reg / I_surv`  (inflation historique occurrence → règlement)
    """)

    type_branche = st.radio("Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche", horizontal=True)
    is_long = "long" in type_branche

    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader("📁 Triangle développement",
                                            type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader("📁 Base GNPIs",
                                            type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader("📁 Table indices",
                                            type=["xlsx","csv"], key="f_idx")

    annee_cotation      = st.number_input("Année de cotation (n)", value=2026, step=1)
    seuil_stabilisation = st.number_input(
        "Seuil stabilisation (% inflation, 0 = toujours)",
        value=0.0, min_value=0.0, max_value=50.0, step=5.0) / 100
    pct_seuil = st.number_input(
        "Percentile seuil Pareto (p80 par défaut)",
        value=0.80, min_value=0.50, max_value=0.99, step=0.05, format="%.2f")

    if st.button("▶ Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")

            # ── INDICES ──────────────────────────────────────────────────────
            df_gnpis_df = (pd.read_excel(f_gnpis) if f_gnpis.name.endswith('xlsx')
                           else pd.read_csv(f_gnpis))
            df_idx_df   = (pd.read_excel(f_indices) if f_indices.name.endswith('xlsx')
                           else pd.read_csv(f_indices))
            df_gnpis_df.columns = [str(c).strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [str(c).strip() for c in df_idx_df.columns]

            progress.progress(10, text="Nettoyage indices...")
            df_idx_df['Annee'] = pd.to_numeric(
                df_idx_df['Annee'].astype(str).str.strip().str.replace('.0','',regex=False),
                errors='coerce')
            df_idx_df['Coefficients'] = pd.to_numeric(
                df_idx_df['Coefficients'].astype(str).str.strip()
                .str.replace(',','.', regex=False).str.replace(' ','', regex=False),
                errors='coerce')
            df_idx_df = df_idx_df.dropna(subset=['Annee','Coefficients'])
            df_idx_df['Annee'] = df_idx_df['Annee'].astype(int)
            df_idx_df = df_idx_df.sort_values('Annee')

            # Projection future
            inflation_future = st.number_input(
                "Inflation future annuelle (%)", value=3.0, min_value=0.0,
                max_value=30.0, step=0.5) / 100
            horizon_proj = 15
            df_idx_set   = df_idx_df.set_index('Annee')['Coefficients']
            annee_max    = int(df_idx_set.index.max())
            indices_proj = {int(a): float(v) for a, v in df_idx_set.items()}
            for annee in range(annee_max+1, annee_max+horizon_proj+1):
                indices_proj[annee] = indices_proj[annee-1] * (1+inflation_future)

            def get_indice(annee):
                annee = int(annee)
                if annee in indices_proj: return float(indices_proj[annee])
                ann = np.array(sorted(indices_proj.keys()))
                val = np.array([indices_proj[a] for a in ann])
                if annee < ann[0]:
                    return float(val[0] - (val[1]-val[0])*(ann[0]-annee))
                return float(np.interp(annee, ann, val))

            I_cotation_val = get_indice(annee_cotation)
            st.info(f"I_cotation({annee_cotation}) = {I_cotation_val:.4f} | "
                    f"Projection jusqu'à {annee_max+horizon_proj}")

            # ── PARSING TRIANGLE ─────────────────────────────────────────────
            progress.progress(20, text="Parsing triangle...")
            df_raw = pd.read_excel(f_triangle, header=None)

            header_year_row = 0; best_year_count = 0
            for row_idx in range(min(8, len(df_raw))):
                cnt = sum(1 for v in df_raw.iloc[row_idx].tolist()
                          if str(v).strip().replace('.0','').isdigit()
                          and 1990 <= int(float(str(v))) <= 2060)
                if cnt > best_year_count:
                    best_year_count = cnt; header_year_row = row_idx
            header_type_row = header_year_row + 1
            data_start_row  = header_type_row + 1

            ligne_annees = df_raw.iloc[header_year_row].tolist()
            ligne_types  = df_raw.iloc[header_type_row].tolist()
            annee_courante = None; col_info = []
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0: col_info.append(('UW_YEAR','UW_YEAR')); continue
                try:
                    a = int(float(str(ann).strip()))
                    if 1990 <= a <= 2060: annee_courante = a
                except: pass
                typ_str = str(typ).strip().upper() if pd.notna(typ) else ''
                if   typ_str in ('TOTAL','TOT','CUMUL','AMOUNT','INCURRED'): typ_norm='TOTAL'
                elif typ_str in ('PAID','PAY','PAYE','RÉGLEMENT'): typ_norm='PAID'
                elif typ_str in ('OS','O/S','OUTSTANDING','RESERVE','RÉSERVE'): typ_norm='OS'
                else: typ_norm=typ_str
                col_info.append((annee_courante, typ_norm))

            df_data = df_raw.iloc[data_start_row:].reset_index(drop=True)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction sinistres...")
            records=[]; sinistre_counter={}
            for idx_row, row in df_data.iterrows():
                try:
                    annee_surv = int(float(str(row.iloc[0]).strip().replace('.0','')))
                    if not (1990 <= annee_surv <= 2060): continue
                except: continue
                sinistre_counter[annee_surv] = sinistre_counter.get(annee_surv,0)+1
                sinistre_id = f"{annee_surv}_S{sinistre_counter[annee_surv]:04d}"
                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ!='TOTAL' or annee_reg is None: continue
                    val = row.iloc[col_idx]
                    try:
                        if pd.isna(val): continue
                        if isinstance(val,str):
                            val=val.strip().replace(',','.').replace(' ','')
                            if not val or any(c.isalpha() for c in val): continue
                        val=float(val)
                        if val<=0 or np.isnan(val): continue
                    except: continue
                    dev = annee_reg - annee_surv
                    if dev<0 or dev>15: continue
                    records.append({'sinistre_id':sinistre_id,'annee_surv':annee_surv,
                                    'annee_reg':annee_reg,'dev':dev,'total':val})

            if not records:
                st.error("❌ Aucune donnée extraite."); st.stop()

            df_liq = pd.DataFrame(records)
            df_liq = df_liq.sort_values(['sinistre_id','dev']).reset_index(drop=True)

            # ── INDICES HISTORIQUES ───────────────────────────────────────────
            progress.progress(48, text="Indices historiques...")
            df_liq['I_reg']  = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv'] = df_liq['annee_surv'].apply(get_indice)

            # ── DÉCUMUL ───────────────────────────────────────────────────────
            progress.progress(50, text="Décumul...")
            df_liq['prev_total'] = (df_liq.groupby('sinistre_id')['total']
                                    .shift(1).fillna(0))
            df_liq['increment']  = (df_liq['total'] - df_liq['prev_total']).clip(lower=0)

            # ════════════════════════════════════════════════════════════════
            # CORRECTIF 1 — AS-IF sur incréments
            # Formule correcte : P*_i,j = P_i,j × I(annee_cot+dev) / I(annee_reg)
            # ════════════════════════════════════════════════════════════════
            df_liq['annee_reg_asif'] = annee_cotation + df_liq['dev']
            df_liq['I_reg_asif']     = df_liq['annee_reg_asif'].apply(get_indice)

            df_liq['inc_asif'] = df_liq['increment'] * (
                df_liq['I_reg_asif'] / df_liq['I_reg']   # ← CORRECT
            )

            # ════════════════════════════════════════════════════════════════
            # CORRECTIF 2 — Stabilisation : ratio sur indices HISTORIQUES
            # ratio_check = I_reg / I_surv  (pas I_reg_asif / I_surv_asif)
            # coeff_stab  = I_surv / I_reg  (ramener à l'année de survenance)
            # ════════════════════════════════════════════════════════════════
            df_liq['ratio_check'] = df_liq['I_reg'] / df_liq['I_surv']   # ← CORRIGÉ
            mask_stab = df_liq['ratio_check'] >= (1.0 + seuil_stabilisation)

            df_liq['inc_stab'] = np.where(
                mask_stab,
                df_liq['inc_asif'] * (df_liq['I_surv'] / df_liq['I_reg']),  # ← CORRIGÉ
                df_liq['inc_asif']
            )

            n_stab = int(mask_stab.sum())
            st.info(f"📊 AS-IF + Stab | Seuil : {seuil_stabilisation*100:.0f}% | "
                    f"Incréments stabilisés : {n_stab}")

            # ── RECUMUL ───────────────────────────────────────────────────────
            df_liq['Sk']        = df_liq.groupby('sinistre_id')['inc_asif'].cumsum()
            df_liq['S_prime_k'] = df_liq.groupby('sinistre_id')['inc_stab'].cumsum()
            df_liq['coeff_stab'] = np.where(
                df_liq['S_prime_k'] > 0,
                df_liq['Sk'] / df_liq['S_prime_k'],
                1.0
            )

            # ── CHAIN-LADDER ──────────────────────────────────────────────────
            if is_long:
                progress.progress(65, text="Chain Ladder...")
                facteurs = {k: [] for k in range(9)}
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            tk = grp.loc[k,'S_prime_k']; tk1 = grp.loc[k+1,'S_prime_k']
                            if tk > 0:
                                f_k = tk1/tk
                                if 0.9 <= f_k <= 2.5: facteurs[k].append(f_k)
                f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0
                            for k in range(9)}
                progress.progress(75, text="Projection à l'ultime...")
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p  = grp['annee_surv'].iloc[0]
                    dm    = grp.index.max()
                    sp    = grp.loc[dm,'S_prime_k']
                    cs    = grp.loc[dm,'coeff_stab']
                    for k in range(dm,9): sp *= f_moyens[k]
                    projections.append({'sinistre_id':sin_id,'annee_surv':as_p,
                                        'dev_max':dm,'Sprime_ultime':sp,
                                        'Sk_ultime':sp*cs,'coeff_stab':cs})
                df_facteurs_df = pd.DataFrame({
                    'Dev.':[f"{k}→{k+1}" for k in range(9)],
                    'Facteur':[round(f_moyens[k],4) for k in range(9)],
                    'N obs':[len(facteurs[k]) for k in range(9)]})
            else:
                f_moyens = {k:1.0 for k in range(9)}
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    as_p = grp['annee_surv'].iloc[0]; dm = grp.index.max()
                    sk_  = grp.loc[dm,'Sk']
                    projections.append({'sinistre_id':sin_id,'annee_surv':as_p,
                                        'dev_max':dm,'Sprime_ultime':sk_,
                                        'Sk_ultime':sk_,'coeff_stab':1.0})
                df_facteurs_df = pd.DataFrame({'Info':['Branche courte']})

            df_proj = pd.DataFrame(projections)
            progress.progress(85, text="Alpha & Lambda...")
            D_trav = next((t['priorite'] for t in tranches_input
                           if t['type']=='travaillante'), 2_000_000)
            seuil_model = pct_seuil * D_trav
            X_all  = df_proj['Sprime_ultime'].values; X_all = X_all[X_all>0]
            Pm_proxy = np.percentile(X_all, 99.5)
            X_model  = X_all[(X_all>=seuil_model)&(X_all<Pm_proxy)]
            if len(X_model)<5: X_model = X_all[X_all>=seuil_model]
            t_min    = np.min(X_model)
            alpha_est = len(X_model) / np.sum(np.log(X_model/t_min))
            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col = df_gnpis_df.columns[1]
            dpm = df_proj[(df_proj['Sprime_ultime']>=seuil_model)&
                          (df_proj['Sprime_ultime']<Pm_proxy)]
            N_obs = dpm.groupby('annee_surv').size()
            lv = []
            for an, cn in N_obs.items():
                try: lv.append(cn*gnpi/float(df_gnpis_idx.loc[an,gnpi_col]))
                except: lv.append(cn)
            lambda_est = float(np.mean(lv)) if lv else 5.0
            coeffs_raw = df_proj['coeff_stab'].values
            coeffs     = coeffs_raw[(coeffs_raw>0)&np.isfinite(coeffs_raw)]
            res_maj    = identifier_sinistres_majeurs_gpd(
                df_proj=df_proj, gnpi=gnpi, tranches_input=tranches_input,
                nb_annees_obs=df_proj['annee_surv'].nunique(),
                retour_ans=20, pct_seuil=pct_seuil)
            df_seuils, _ = selectionner_seuil_pareto(
                X=df_proj['Sprime_ultime'].values, D=D_trav)
            chargements_par_tranche = res_maj.get("chargements_par_tranche",{})

            progress.progress(100, text="Terminé !")
            st.session_state.update({
                "df_liq":df_liq,"df_proj":df_proj,"f_moyens":f_moyens,
                "alpha_est":float(alpha_est),"lambda_est":float(lambda_est),
                "seuil_est":float(seuil_model),"Pm_proxy":float(Pm_proxy),
                "coeffs":coeffs,"is_long":is_long,
                "I_cotation":I_cotation_val,"annee_cotation":annee_cotation,
                "seuil_stabilisation":seuil_stabilisation,
                "df_gnpis_df":df_gnpis_df,"df_facteurs":df_facteurs_df,
                "res_majeurs":res_maj,"df_seuils_pareto":df_seuils,
                "chargement_majeurs":res_maj["chargement"],
                "chargements_par_tranche":chargements_par_tranche,
            })
            st.success("✅ Transformation terminée !")

    if "df_liq" in st.session_state:
        st.info(f"α={st.session_state.get('alpha_est',0):.4f} | "
                f"λ={st.session_state.get('lambda_est',0):.4f} | "
                f"Seuil={st.session_state.get('seuil_est',0):,.0f} MAD")
        with st.expander("Vérification AS-IF (5 premières lignes)"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev',
                         'total','I_surv','I_reg','annee_reg_asif','I_reg_asif',
                         'increment','inc_asif','ratio_check','inc_stab',
                         'Sk','S_prime_k','coeff_stab']
            st.dataframe(
                st.session_state["df_liq"][
                    [c for c in cols_show if c in st.session_state["df_liq"].columns]
                ].head(20),
                use_container_width=True
            )
            st.caption(
                "✅ Vérification : inc_asif = increment × I_reg_asif / I_reg  |  "
                "ratio_check = I_reg / I_surv  |  "
                "inc_stab = inc_asif × I_surv/I_reg si ratio ≥ seuil"
            )
        if "df_facteurs" in st.session_state:
            with st.expander("Facteurs Chain Ladder"):
                st.dataframe(st.session_state["df_facteurs"], use_container_width=True)


# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════
with tab3:
    section_header("Burning Cost","Charges historiques réassurance par tranche","🔥")
    st.markdown("""<div style="background:rgba(45,138,78,0.08);border-left:4px solid #2d8a4e;
        border-radius:0 8px 8px 0;padding:10px 16px;margin-bottom:12px;font-size:12px">
        <b>R1</b> — τ_risque = τ_pur + σ_hist × 20% —
        <b>R2</b> — Si années non nulles &lt; 3 → τ_BC = 0
        </div>""", unsafe_allow_html=True)
    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        if st.button("▶ Calculer le Burning Cost", type="primary"):
            with st.spinner("Calcul en cours..."):
                df_proj = st.session_state["df_proj"]
                resultats_bc = []
                for t_info in tranches_input:
                    D=t_info["priorite"]; L=t_info["portee"]
                    aal=t_info["AAL"]; aad=t_info["AAD"]
                    n_rec=t_info["nb_reconstitutions"]
                    taux_recons_list = t_info.get("taux_reconstitutions",[t_info.get("taux_reconstitution",100)]*n_rec)
                    cap=(n_rec+1)*L
                    df_proj["Ck"] = df_proj.apply(
                        lambda row: min(max(row["Sprime_ultime"]-D,0),L)*row["coeff_stab"],axis=1)
                    charges_ann=df_proj.groupby("annee_surv")["Ck"].sum()
                    charges_finales=[]
                    for ann,ch in charges_ann.items():
                        if aad: ch=max(ch-aad,0)
                        if aal: ch=min(ch,aal)
                        charges_finales.append({"annee":ann,"charge":float(min(ch,cap))})
                    df_ch=pd.DataFrame(charges_finales); N=len(df_ch)
                    Pr=0.0
                    for Cn in df_ch["charge"].values:
                        for r_idx,t_r_i in enumerate(taux_recons_list):
                            Pr+=(t_r_i/100)*min(L,max(Cn-r_idx*L,0))
                    Pr/=L if L>0 else 1
                    Rec=Pr/(Pr+N) if (Pr+N)>0 else 0.0
                    cm=df_ch["charge"].mean()
                    charges_nz=[c for c in df_ch["charge"].values if c>0]
                    n_nz=len(charges_nz)
                    charg_maj=st.session_state.get(
                        "chargements_par_tranche",{}).get(
                        t_info["nom"],{}).get("chargement",
                        st.session_state.get("chargement_majeurs",0.0))
                    if n_nz<3:
                        tp=tr=tt=0.0; sig_h=0.0
                    else:
                        tp=cm/gnpi; sig_h=float(np.std(charges_nz))/gnpi
                        tr=tp+sig_h*0.20
                        tt=(tr*(1-Rec))/(1-t_info["brokage"]-t_info["frais"]
                                         -t_info["marge"]-t_info["retrocession"])
                    resultats_bc.append({
                        "tranche":t_info["nom"],"type":t_info["type"],
                        "charge_moy":cm,"Pr_Rec":Pr,"Rec":Rec,
                        "n_ann_nonzero":n_nz,"sigma_hist":sig_h if n_nz>=3 else 0.0,
                        "taux_pur":tp,"taux_risque":tr,"taux_technique":tt,
                        "chargement_majeurs":charg_maj,
                        "detail_annuel":charges_finales
                    })
                st.session_state["resultats_bc"]=resultats_bc
                try:
                    db_save_session(st.session_state.get("user_email",""),gnpi,tranches_input)
                    db_save_etape("bc",[{k:v for k,v in r.items() if k!="detail_annuel"}
                                        for r in resultats_bc])
                except: pass
        if "resultats_bc" in st.session_state:
            tableau_resultats([{
                "Tranche":r["tranche"],"Type":r["type"],
                "Ans non-nuls":f"{r.get('n_ann_nonzero',0)} {'⚠️' if r.get('n_ann_nonzero',0)<3 else '✅'}",
                "Charge moy.":f"{r.get('charge_moy',0):,.0f} MAD",
                "σ hist.":f"{r.get('sigma_hist',0):.4%}",
                "Rec":f"{r['Rec']:.4%}",
                "Taux pur":f"{r['taux_pur']:.4%}",
                "Taux risque":f"{r['taux_risque']:.4%}",
                "Taux technique":f"{r['taux_technique']:.4%}",
                "Charg. majeurs":f"{r.get('chargement_majeurs',0):.4%}",
            } for r in st.session_state["resultats_bc"]],"📊 Résultats Burning Cost")
            with st.expander("Crédibilité Bühlmann-Straub"):
                a_priori_bs=st.number_input("μ a priori (%)",value=3.0,step=0.1,key="bs_ap")/100
                cred_res=buehlmann_straub_credibility(st.session_state["resultats_bc"],a_priori_bs,gnpi)
                tableau_resultats([{"Tranche":n,"Z":f"{r['Z']:.3f}",
                    "τ BC":f"{r.get('tau_bc',0):.4%}","τ Bühlmann":f"{r['tau_credible']:.4%}",
                    "Interprétation":r["interpretation"]} for n,r in cred_res.items()])
        if api_key and st.button("🤖 Analyse Claude — BC"):
            prompt=build_prompt(
                role="Expert actuaire senior réassurance non-proportionnelle automobile.",
                task="1. Évalue taux vs marché\n2. Cohérence inter-tranches\n3. Verdict",
                data=f"BC:{json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'}
                      for r in st.session_state.get('resultats_bc',[])],indent=2)}\nGNPI:{gnpi:,}",
                contexte_global=st.session_state.get("instructions_globales",""),
                contraintes="- Ne pas inventer comparatifs marché")
            claude_stream(api_key,prompt,max_tokens=2000,session_key="analyse_bc")
        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])


# ════════════════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════════════════
with tab4:
    st.header("Simulation Pareto / Poisson")
    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        with st.expander("🎯 Détection seuil TVE", expanded=True):
            if st.button("🔍 Détecter le seuil optimal"):
                data_sim = st.session_state.get("df_proj")
                if data_sim is not None:
                    X_tve = data_sim["Sprime_ultime"].dropna().values
                    X_tve = X_tve[X_tve>0]
                    seuil_opt, fig_tve, diag_tve = detecter_seuil_optimal_tve(X_tve,"Sinistres")
                    if fig_tve:
                        st.pyplot(fig_tve); plt.close(fig_tve)
                        st.session_state["seuil_tve_detecte"] = seuil_opt
                        st.session_state["diag_tve"] = diag_tve
            if "diag_tve" in st.session_state:
                d=st.session_state["diag_tve"]
                c1,c2,c3,c4=st.columns(4)
                c1.metric("Hill",f"{d.get('seuil_hill',0):,.0f} MAD",f"α={d.get('alpha_hill',0):.4f}")
                c2.metric("MEF",f"{d.get('seuil_mef',0):,.0f} MAD",f"R²={d.get('mef_r2',0):.3f}")
                c3.metric("Gertensgarbe",f"{d.get('seuil_gert',0):,.0f} MAD")
                c4.metric("Consensus",f"{d.get('seuil_optimal',0):,.0f} MAD","⭐")

        with st.expander("🔬 Sélection loi sévérité", expanded=True):
            loi_retenue = st.selectbox("Loi retenue",["pareto","lognormale","gpd"],
                format_func=lambda x:{"pareto":"Pareto","lognormale":"Lognormale","gpd":"GPD"}[x],
                key="loi_simulation_choisie")
            st.session_state["loi_sim"] = loi_retenue
            if st.button("📊 Comparer les lois"):
                X_fit = st.session_state["df_proj"]["Sprime_ultime"].dropna().values
                X_fit = X_fit[X_fit>0]
                seuil_fit = st.session_state.get("seuil_est",1_600_000)
                res_lois, err_lois = comparer_lois_ajustement(X_fit, seuil_fit)
                if err_lois: st.warning(err_lois)
                else:
                    st.session_state["comparaison_lois"] = res_lois
                    tableau_resultats(res_lois,"Comparaison lois")

        st.markdown("#### ⚙️ Paramètres")
        c1,c2,c3,c4 = st.columns(4)
        loi_active = st.session_state.get("loi_sim","pareto")
        if loi_active=="pareto":
            with c1: st.number_input("α",value=float(st.session_state["alpha_est"]),
                                      step=0.01,format="%.4f",key="alpha_input")
            with c2: st.number_input("λ",value=float(st.session_state["lambda_est"]),
                                      step=0.1,format="%.4f",key="lambda_input")
            with c3: st.number_input("Seuil (MAD)",value=float(st.session_state["seuil_est"]),
                                      step=50_000.0,format="%.0f",key="seuil_input")
        elif loi_active=="lognormale":
            with c1: st.number_input("μ",value=float(st.session_state.get("loi_mu",13.0)),
                                      step=0.05,format="%.4f",key="mu_ln_input")
            with c2: st.number_input("σ",value=float(st.session_state.get("loi_sigma",1.0)),
                                      step=0.05,format="%.4f",key="sigma_ln_input")
            with c3: st.number_input("λ",value=float(st.session_state["lambda_est"]),
                                      step=0.1,format="%.4f",key="lambda_input")
        elif loi_active=="gpd":
            with c1: st.number_input("ξ",value=float(st.session_state.get("gpd_xi",0.3)),
                                      step=0.01,format="%.4f",key="gpd_xi_input")
            with c2: st.number_input("β",value=float(st.session_state.get("gpd_beta",500000.0)),
                                      step=10_000.0,format="%.0f",key="gpd_beta_input")
            with c3: st.number_input("λ",value=float(st.session_state["lambda_est"]),
                                      step=0.1,format="%.4f",key="lambda_input")
        with c4: n_sim_v=st.number_input("Nb simulations",value=10000,step=1000,key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                loi_sim   = st.session_state.get("loi_sim","pareto")
                seuil_f   = float(st.session_state.get("seuil_input",st.session_state["seuil_est"]))
                lambda_f  = float(st.session_state.get("lambda_input",st.session_state["lambda_est"]))
                n_s       = int(st.session_state.get("nsim_input",10000))
                coeffs    = st.session_state["coeffs"]
                if loi_sim=="pareto":
                    alpha_f = float(st.session_state.get("alpha_input",st.session_state["alpha_est"]))
                elif loi_sim=="lognormale":
                    mu_f    = float(st.session_state.get("mu_ln_input",13.0))
                    sigma_f = float(st.session_state.get("sigma_ln_input",1.0))
                elif loi_sim=="gpd":
                    xi_f   = float(st.session_state.get("gpd_xi_input",0.3))
                    beta_f = float(st.session_state.get("gpd_beta_input",500000.0))
                np.random.seed(42)
                resultats_sim=[]
                for t_info in tranches_input:
                    D=t_info["priorite"]; P=t_info["portee"]
                    r_rec=t_info["nb_reconstitutions"]; aal=t_info["AAL"]; aad=t_info["AAD"]
                    cap=(r_rec+1)*P
                    def sim_batch():
                        charges=[]
                        for _ in range(n_s):
                            N=np.random.poisson(lambda_f); S=0
                            if N>0:
                                if loi_sim=="pareto":
                                    U=np.random.uniform(size=N)
                                    Xs=seuil_f*(U**(-1/alpha_f))
                                elif loi_sim=="lognormale":
                                    Xs=np.random.lognormal(mu_f,sigma_f,size=N)
                                    Xs=np.maximum(Xs,seuil_f)
                                else:
                                    U=np.random.uniform(size=N)
                                    # GPD par inversion : X = seuil + β/ξ×((1-U)^(-ξ)-1)
                                    U=np.random.uniform(size=N)
                                    if abs(xi_f) < 1e-8:
                                        Xs = seuil_f - beta_f * np.log(1 - U)
                                    else:
                                        Xs = seuil_f + (beta_f / xi_f) * ((1 - U) ** (-xi_f) - 1)
                                        if xi_f < 0:
                                            borne_sup = seuil_f - beta_f / xi_f
                                            Xs = np.minimum(Xs, borne_sup * 0.9999)
                                idx_c=np.random.choice(len(coeffs),size=N,replace=True)
                                for i in range(N):
                                    c=coeffs[idx_c[i]]
                                    if Xs[i]<=D: pass
                                    elif Xs[i]<=D+P: S+=c*(Xs[i]-D)
                                    else: S+=c*P
                            ch=S
                            if aad: ch=max(ch-aad,0)
                            if aal: ch=min(ch,aal)
                            charges.append(min(ch,cap))
                        return np.array(charges)
                    ch=sim_batch()
                    ch2=sim_batch()  # sans AAL
                    P0=np.mean(ch); sig=np.std(ch)
                    tp=P0/gnpi; tr=(P0+0.2*sig)/gnpi
                    tt=tr/(1-t_info["brokage"]-t_info["frais"]-t_info["marge"]-t_info["retrocession"])
                    P02=np.mean(ch2); sig2=np.std(ch2)
                    tt2=(P02+0.2*sig2)/gnpi/(1-t_info["brokage"]-t_info["frais"]-t_info["marge"]-t_info["retrocession"])
                    resultats_sim.append({
                        "tranche":t_info["nom"],"type":t_info["type"],
                        "taux_pur":tp,"taux_risque":tr,"taux_technique":tt,
                        "chargement_majeurs":st.session_state.get("chargement_majeurs",0.0),
                        "sans_aal":tt2,"impact_aal":round(tt2-tt,6),
                    })
                st.session_state["resultats_sim"]=resultats_sim
                try:
                    db_save_etape("sim",resultats_sim)
                except: pass
        if "resultats_sim" in st.session_state:
            tableau_resultats([{
                "Tranche":r["tranche"],"Taux pur":f"{r['taux_pur']:.4%}",
                "Taux risque":f"{r['taux_risque']:.4%}","Taux technique":f"{r['taux_technique']:.4%}",
                "Charg. majeurs":f"{r.get('chargement_majeurs',0):.4%}",
            } for r in st.session_state["resultats_sim"]],"📊 Résultats Simulation")
