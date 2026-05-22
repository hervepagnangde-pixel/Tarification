import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

st.set_page_config(page_title="Herve IA — Tarification XL", layout="wide", page_icon="🎯")

# ─── CSS PERSONNALISÉ ───
st.markdown("""
<style>
    /* Fond général */
    .stApp { background-color: #f0f2f6; }
    
    /* Header principal */
    h1 { color: #1a1a2e; font-size: 1.8rem !important; }
    h2 { color: #16213e; border-bottom: 2px solid #0f3460; padding-bottom: 8px; }
    h3 { color: #0f3460; }
    
    /* Boutons primaires */
    .stButton > button {
        background-color: #0f3460;
        color: white;
        border: none;
        border-radius: 8px;
        padding: 8px 20px;
        font-weight: 600;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background-color: #e94560;
        transform: translateY(-1px);
    }
    
    /* Cards */
    .metric-card {
        background: white;
        padding: 16px;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        border-left: 4px solid #0f3460;
        margin-bottom: 12px;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #1a1a2e;
        border-radius: 10px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        color: #aaa;
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
        background-color: #e94560 !important;
        color: white !important;
        border-radius: 8px;
    }
    
    /* Instruction box */
    .instruction-box {
        background: #fff8e1;
        border: 1px solid #ffc107;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
    }
    
    /* Sidebar */
    .css-1d391kg { background-color: #1a1a2e; }
    
    /* Success/warning */
    .stSuccess { border-radius: 8px; }
    .stWarning { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ─── HEADER ───
col_logo, col_title = st.columns([1, 8])
with col_title:
    st.title("🎯 Herve IA — Tarification Réassurance Non-Proportionnelle")
    st.caption("Burning Cost · Simulation · Market Curve · Recommandations IA")

st.divider()

# ─── SIDEBAR ───
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("🔑 Clé API Claude", type="password", placeholder="sk-ant-...")
    gnpi    = st.number_input("💰 GNPI (MAD)", value=183_000_000, step=1_000_000,
                               help="Gross Net Premium Income — assiette de tarification")
    st.divider()
    
    # Statut des étapes
    st.markdown("### 📊 Statut")
    etapes = [
        ("Programme",    "tranches_input" in st.session_state),
        ("Données",      "df_liq"         in st.session_state),
        ("Burning Cost", "resultats_bc"   in st.session_state),
        ("Simulation",   "resultats_sim"  in st.session_state),
        ("Market Curve", "resultats_mkt"  in st.session_state),
    ]
    for nom, done in etapes:
        icon = "✅" if done else "⬜"
        st.markdown(f"{icon} {nom}")
    
    st.divider()
    st.markdown("### 💡 Instructions globales")
    instructions_globales = st.text_area(
        "Contexte à donner à Claude",
        placeholder="Ex: Portefeuille automobile Maroc, forte croissance en 2023, changement de mix sinistres...",
        height=120,
        key="instructions_globales",
        help="Ces instructions seront incluses dans TOUS les prompts Claude"
    )

# ─── TABS ───
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📋 Programme",
    "📂 Données & Triangle",
    "🔥 Burning Cost",
    "🎲 Simulation",
    "📈 Market Curve",
    "📋 Rapport Final"
])

# ════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════
with tab1:
    st.header("Programme de Réassurance")
    st.caption("Définissez les tranches, conditions et paramètres de chargement")

    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)

    tranches_input = []
    for i in range(nb_tranches):
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i == 0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Identification**")
                nom      = st.text_input("Nom",       value=f"Tranche {i+1}", key=f"nom_{i}")
                type_t   = st.selectbox("Type",       ["travaillante","non_travaillante","cat"], key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)", value=2_000_000,  step=500_000, key=f"prio_{i}", format="%d")
                portee   = st.number_input("Portée (MAD)",   value=13_000_000, step=500_000, key=f"port_{i}", format="%d")
            with c2:
                st.markdown("**Conditions contractuelles**")
                has_aal = st.checkbox("AAL (Aggregate Annual Limit)", key=f"aal_{i}")
                aal_val = st.number_input("Montant AAL", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
                has_aad = st.checkbox("AAD (Annual Aggregate Deductible)", key=f"aad_{i}")
                aad_val = st.number_input("Montant AAD", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
                has_indices = st.checkbox("Clause d'indexation", key=f"idx_{i}")
            with c3:
                st.markdown("**Reconstitutions & Chargements**")
                nb_recon     = st.number_input("Nb reconstitutions",    value=1,   min_value=0, max_value=5,   key=f"recon_{i}")
                tx_recon     = st.number_input("Taux reconstitution %", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
                brokage      = st.number_input("Brokage %",        value=10, min_value=0, max_value=30, key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %", value=5,  min_value=0, max_value=20, key=f"frais_{i}")
                marge        = st.number_input("Marge %",          value=10, min_value=0, max_value=30, key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",   value=0,  min_value=0, max_value=50, key=f"retro_{i}")

        tranches_input.append({
            "numero": i+1, "nom": nom, "type": type_t,
            "priorite": priorite, "portee": portee,
            "AAL": aal_val if has_aal else None,
            "AAD": aad_val if has_aad else None,
            "nb_reconstitutions": nb_recon,
            "taux_reconstitution": tx_recon,
            "indices": has_indices,
            "brokage": brokage/100, "frais": frais/100,
            "marge": marge/100, "retrocession": retrocession/100
        })

    if st.button("💾 Valider le programme", type="primary"):
        st.session_state["tranches_input"] = tranches_input
        st.session_state["df_prog"] = pd.DataFrame([{
            "Tranche": t["nom"], "Type": t["type"],
            "Priorité": f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
            "AAL": f"{t['AAL']:,}" if t["AAL"] else "—",
            "AAD": f"{t['AAD']:,}" if t["AAD"] else "—",
            "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
            "Indices": "✅" if t["indices"] else "—",
            "Brokage": f"{t['brokage']:.0%}",
            "Frais": f"{t['frais']:.0%}",
            "Marge": f"{t['marge']:.0%}",
        } for t in tranches_input])
        st.success("✅ Programme validé !")

    if "df_prog" in st.session_state:
        st.dataframe(st.session_state["df_prog"], use_container_width=True)
        # Résumé visuel
        col1, col2, col3 = st.columns(3)
        trav  = sum(1 for t in tranches_input if t["type"] == "travaillante")
        cat   = sum(1 for t in tranches_input if t["type"] == "cat")
        other = sum(1 for t in tranches_input if t["type"] == "non_travaillante")
        col1.metric("Tranches travaillantes", trav)
        col2.metric("Tranches cat", cat)
        col3.metric("Tranches non-travaillantes", other)

# ════════════════════════════════
# TAB 2 — DONNÉES & TRIANGLE
# ════════════════════════════════
with tab2:
    st.header("Données de base & Transformation triangle")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Triangle de développement**")
        f_triangle = st.file_uploader("📁 Triangle (Excel/CSV)", type=["xlsx","csv"], key="f_tri")
    with c2:
        st.markdown("**Base GNPIs historiques**")
        f_gnpis = st.file_uploader("📁 GNPIs (Excel/CSV)", type=["xlsx","csv"], key="f_gnp")
    with c3:
        st.markdown("**Table d'indices**")
        f_indices = st.file_uploader("📁 Indices IPC/Salaires (Excel/CSV)", type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation", value=2026, step=1)

    if st.button("▶ Transformer le triangle", type="primary") and f_triangle and f_gnpis and f_indices:
        with st.spinner("🔄 Transformation en cours..."):
            progress = st.progress(0, text="Lecture des fichiers...")

            df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx')   else pd.read_csv(f_gnpis)
            df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
            df_gnpis_df.columns = [c.strip() for c in df_gnpis_df.columns]
            df_idx_df.columns   = [c.strip() for c in df_idx_df.columns]

            progress.progress(15, text="Parsing du triangle...")
            df_raw       = pd.read_excel(f_triangle, header=None)
            ligne_annees = df_raw.iloc[0].tolist()
            ligne_types  = df_raw.iloc[1].tolist()

            annee_courante = None
            col_info = []
            for i, (ann, typ) in enumerate(zip(ligne_annees, ligne_types)):
                if i == 0:
                    col_info.append(('UW_YEAR', ''))
                    continue
                try:
                    a = int(float(str(ann)))
                    if 2010 <= a <= 2035:
                        annee_courante = a
                except:
                    pass
                typ_clean = str(typ).strip().upper() if pd.notna(typ) else ''
                col_info.append((annee_courante, typ_clean))

            df_data = df_raw.iloc[2:].reset_index(drop=True)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            progress.progress(30, text="Extraction des TOTAL...")
            records = []
            for idx_row, row in df_data.iterrows():
                try:
                    annee_surv = int(float(str(row.iloc[0])))
                    if not (2010 <= annee_surv <= 2035): continue
                except:
                    continue
                sinistre_id = f"{annee_surv}_{idx_row}"
                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ != 'TOTAL' or annee_reg is None: continue
                    val = row.iloc[col_idx]
                    try:
                        if isinstance(val, str):
                            val = val.strip().replace(',','.').replace(' ','')
                            if any(c.isalpha() for c in val) or '#' in val: continue
                        val = float(val)
                        if val <= 0 or np.isnan(val): continue
                    except:
                        continue
                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 9: continue
                    records.append({
                        'sinistre_id': sinistre_id,
                        'annee_surv' : annee_surv,
                        'annee_reg'  : annee_reg,
                        'dev'        : dev,
                        'total'      : val
                    })

            df_liq = pd.DataFrame(records)

            progress.progress(45, text="Calcul As-If & Stabilisation...")
            df_idx_set = df_idx_df.set_index('Annee')['Coefficients']
            def get_indice(annee):
                try: return float(df_idx_set[annee])
                except: return 1.0

            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
            df_liq['total_asif']   = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])
            df_liq['ratio_stab']   = df_liq['I_reg'] / df_liq['I_surv']
            df_liq['total_stab']   = np.where(
                (df_liq['ratio_stab'] - 1) > 0.10,
                df_liq['total'] * (df_liq['I_surv'] / df_liq['I_reg']),
                df_liq['total']
            )

            progress.progress(60, text="Chain Ladder individuel...")
            facteurs = {k: [] for k in range(9)}
            for sin_id, grp in df_liq.groupby('sinistre_id'):
                grp = grp.sort_values('dev').set_index('dev')
                for k in range(9):
                    if k in grp.index and (k+1) in grp.index:
                        t_k  = grp.loc[k,   'total_stab']
                        t_k1 = grp.loc[k+1, 'total_stab']
                        if t_k > 0:
                            f = t_k1 / t_k
                            if 0.9 <= f <= 2.5:
                                facteurs[k].append(f)

            f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

            progress.progress(75, text="Projection à l'ultime...")
            projections = []
            for sin_id, grp in df_liq.groupby('sinistre_id'):
                grp = grp.sort_values('dev').set_index('dev')
                annee_surv        = grp['annee_surv'].iloc[0]
                dev_max           = grp.index.max()
                stab_actuel       = grp.loc[dev_max, 'total_stab']
                total_ultime_stab = stab_actuel
                for k in range(dev_max, 9):
                    total_ultime_stab *= f_moyens[k]
                projections.append({
                    'sinistre_id'      : sin_id,
                    'annee_surv'       : annee_surv,
                    'dev_max'          : dev_max,
                    'stab_actuel'      : stab_actuel,
                    'total_ultime_stab': total_ultime_stab
                })

            df_proj = pd.DataFrame(projections)

            progress.progress(88, text="Estimation alpha & lambda...")
            X       = df_proj['total_ultime_stab'].values
            X       = X[X > 0]
            seuil   = np.percentile(X, 85)
            X_above = X[X >= seuil]
            t_min   = np.min(X_above)
            n       = len(X_above)
            alpha_est = n / np.sum(np.log(X_above / t_min))

            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col     = df_gnpis_df.columns[1]
            N_obs        = df_proj[df_proj['total_ultime_stab'] >= seuil].groupby('annee_surv').size()
            N_asif_vals  = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except:
                    N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0

            coeffs_raw = df_liq['total_stab'].values / df_liq['total'].values
            coeffs     = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

            progress.progress(100, text="Terminé !")

            st.session_state.update({
                "df_liq"     : df_liq,
                "df_proj"    : df_proj,
                "f_moyens"   : f_moyens,
                "alpha_est"  : float(alpha_est),
                "lambda_est" : float(lambda_est),
                "seuil_est"  : float(seuil),
                "coeffs"     : coeffs,
                "df_gnpis_df": df_gnpis_df,
                "df_facteurs": pd.DataFrame({
                    'Dev.'           : [f"{k}→{k+1}" for k in range(9)],
                    'Facteur moyen'  : [round(f_moyens[k], 4) for k in range(9)],
                    'Nb observations': [len(facteurs[k]) for k in range(9)]
                })
            })

    if "df_liq" in st.session_state:
        col1, col2, col3 = st.columns(3)
        col1.metric("Observations extraites", len(st.session_state['df_liq']))
        col2.metric("Sinistres uniques", st.session_state['df_liq']['sinistre_id'].nunique())
        col3.metric("Années de survenance", st.session_state['df_liq']['annee_surv'].nunique())

        with st.expander("📊 Triangle de liquidation (As-If & Stab.)"):
            st.dataframe(st.session_state["df_liq"][
                ['sinistre_id','annee_surv','annee_reg','dev','total','total_asif','total_stab']
            ].head(30), use_container_width=True)

        with st.expander("📊 Facteurs Chain Ladder individuels"):
            st.dataframe(st.session_state["df_facteurs"], use_container_width=True)

        with st.expander("📊 Projections à l'ultime"):
            st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

        st.info(f"🔢 Paramètres estimés — Seuil P85: {st.session_state['seuil_est']:,.0f} MAD | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

# ════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════
with tab3:
    st.header("Burning Cost")
    st.caption("Calcul des charges historiques réassurance par tranche")

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle dans l'onglet 'Données & Triangle'")
    else:
        if st.button("▶ Calculer le Burning Cost", type="primary"):
            with st.spinner("Calcul en cours..."):
                df_proj      = st.session_state["df_proj"]
                resultats_bc = []

                for t_info in tranches_input:
                    D   = t_info["priorite"]
                    P   = t_info["portee"]
                    aal = t_info["AAL"]
                    aad = t_info["AAD"]
                    r   = t_info["nb_reconstitutions"]
                    cap = (r + 1) * P

                    df_proj['charge_sin'] = df_proj['total_ultime_stab'].apply(
                        lambda x: min(max(x - D, 0), P)
                    )
                    charges_ann     = df_proj.groupby('annee_surv')['charge_sin'].sum()
                    charges_finales = []
                    for ann, ch in charges_ann.items():
                        if aad: ch = max(ch - aad, 0)
                        if aal: ch = min(ch, aal)
                        ch = min(ch, cap)
                        charges_finales.append({'annee': ann, 'charge': ch})

                    df_ch          = pd.DataFrame(charges_finales)
                    charge_moy     = df_ch['charge'].mean()
                    taux_pur       = charge_moy / gnpi
                    taux_risque    = taux_pur * 1.20
                    taux_technique = taux_risque / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                    taux_final     = taux_technique * (1 + t_info["marge"] + t_info["retrocession"])

                    resultats_bc.append({
                        "tranche"       : t_info["nom"],
                        "type"          : t_info["type"],
                        "charge_moy"    : charge_moy,
                        "taux_pur"      : taux_pur,
                        "taux_risque"   : taux_risque,
                        "taux_technique": taux_technique,
                        "taux_final"    : taux_final,
                        "detail_annuel" : df_ch.to_dict('records')
                    })

                st.session_state["resultats_bc"] = resultats_bc

    if "resultats_bc" in st.session_state:
        st.subheader("📊 Résultats")
        st.dataframe(pd.DataFrame([{
            "Tranche"       : r["tranche"],
            "Type"          : r["type"],
            "Charge moy."   : f"{r['charge_moy']:,.0f} MAD",
            "Taux pur"      : f"{r['taux_pur']:.4%}",
            "Taux risque"   : f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final"    : f"{r['taux_final']:.4%}",
        } for r in st.session_state["resultats_bc"]]), use_container_width=True)

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Burning Cost")
        st.markdown('<div class="instruction-box">💡 <b>Instructions pour Claude</b> — Ajoutez du contexte spécifique à cette analyse</div>', unsafe_allow_html=True)
        instructions_bc = st.text_area(
            "Instructions supplémentaires",
            placeholder="Ex: Le portefeuille a connu une forte sinistralité en 2020 liée à la crise COVID. La tranche Risk & Cat a été touchée de manière exceptionnelle...",
            height=100,
            key="instructions_bc",
            label_visibility="collapsed"
        )

        if api_key and st.button("🤖 Obtenir les recommandations Claude — BC"):
            with st.spinner("Claude analyse..."):
                contexte_global = st.session_state.get("instructions_globales", "")
                prompt = f"""Tu es expert en réassurance non-proportionnelle automobile.
{f"CONTEXTE GÉNÉRAL : {contexte_global}" if contexte_global else ""}
{f"INSTRUCTIONS SPÉCIFIQUES : {instructions_bc}" if instructions_bc else ""}

Analyse ces résultats de Burning Cost par tranche.
Pour chaque tranche : commente le niveau du taux, signale les anomalies, vérifie la cohérence entre tranches, compare travaillante vs cat.

Résultats BC :
{json.dumps([{k:v for k,v in r.items() if k != 'detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}

Programme :
{json.dumps(tranches_input, indent=2)}

GNPI : {gnpi:,} MAD"""

                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(
                    model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role":"user","content":prompt}]
                )
                st.session_state["analyse_bc"] = analyse.content[0].text

        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])

# ════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════
with tab4:
    st.header("Simulation Pareto / Poisson")
    st.caption("Modélisation probabiliste des charges de réassurance")

    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle dans l'onglet 'Données & Triangle'")
    else:
        st.info(f"🔢 Estimations automatiques — Seuil P85: {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

        c1, c2, c3, c4 = st.columns(4)
        with c1: alpha_final  = st.number_input("Alpha (Pareto)",    value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
        with c2: lambda_final = st.number_input("Lambda (Poisson)",  value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
        with c3: seuil_final  = st.number_input("Seuil (MAD)",       value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
        with c4: n_sim        = st.number_input("Nb simulations",     value=10000, step=1000,               key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                alpha_final  = st.session_state["alpha_input"]
                lambda_final = st.session_state["lambda_input"]
                seuil_final  = st.session_state["seuil_input"]
                n_sim        = int(st.session_state["nsim_input"])
                coeffs       = st.session_state["coeffs"]
                np.random.seed(42)
                resultats_sim = []

                for idx_t, t_info in enumerate(tranches_input):
                    progress_sim.progress(int((idx_t/len(tranches_input))*100),
                                          text=f"Simulation tranche {t_info['nom']}...")
                    D   = t_info["priorite"]
                    P   = t_info["portee"]
                    r   = t_info["nb_reconstitutions"]
                    aal = t_info["AAL"]
                    aad = t_info["AAD"]
                    cap = (r + 1) * P

                    def simuler(avec_aal, avec_aad, avec_rec):
                        charges = []
                        for _ in range(n_sim):
                            N = np.random.poisson(lambda_final)
                            S_total = 0
                            if N > 0:
                                U          = np.random.uniform(size=N)
                                pareto_sim = seuil_final * (U ** (-1/alpha_final))
                                idx_c      = np.random.choice(len(coeffs), size=N, replace=True)
                                for i in range(N):
                                    S0 = pareto_sim[i]; c = coeffs[idx_c[i]]
                                    if   S0 <= D:     S_i = 0
                                    elif S0 <= D + P: S_i = c * (S0 - D)
                                    else:             S_i = c * P
                                    S_total += S_i
                            ch = S_total
                            if avec_aad and aad: ch = max(ch - aad, 0)
                            if avec_aal and aal: ch = min(ch, aal)
                            charges.append(min(ch, cap) if avec_rec else ch)
                        return np.array(charges)

                    def calc_taux(ch):
                        P0  = np.mean(ch); sig = np.std(ch)
                        tp  = P0 / gnpi
                        tr  = (P0 + 0.2 * sig) / gnpi
                        tt  = tr / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                        tf  = tt * (1 + t_info["marge"] + t_info["retrocession"])
                        return tp, tr, tt, tf

                    c_base     = simuler(True,  True,  True)
                    c_sans_aal = simuler(False, True,  True)
                    c_sans_aad = simuler(True,  False, True)
                    c_sans_rec = simuler(True,  True,  False)

                    tp,  tr,  tt,  tf  = calc_taux(c_base)
                    tp2, tr2, tt2, tf2 = calc_taux(c_sans_aal)
                    tp3, tr3, tt3, tf3 = calc_taux(c_sans_aad)
                    tp4, tr4, tt4, tf4 = calc_taux(c_sans_rec)

                    resultats_sim.append({
                        "tranche"       : t_info["nom"], "type": t_info["type"],
                        "taux_pur"      : tp,  "taux_risque"   : tr,
                        "taux_technique": tt,  "taux_final"    : tf,
                        "sans_aal"      : tt2, "sans_aad"      : tt3, "sans_rec": tt4,
                    })

                progress_sim.progress(100, text="Terminé !")
                st.session_state["resultats_sim"] = resultats_sim

    if "resultats_sim" in st.session_state:
        st.subheader("📊 Résultats")
        st.dataframe(pd.DataFrame([{
            "Tranche"       : r["tranche"],
            "Taux pur"      : f"{r['taux_pur']:.4%}",
            "Taux risque"   : f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final"    : f"{r['taux_final']:.4%}",
            "Sans AAL"      : f"{r['sans_aal']:.4%}",
            "Sans AAD"      : f"{r['sans_aad']:.4%}",
            "Sans reconst." : f"{r['sans_rec']:.4%}",
        } for r in st.session_state["resultats_sim"]]), use_container_width=True)

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Simulation & Conditions")
        st.markdown('<div class="instruction-box">💡 <b>Instructions pour Claude</b></div>', unsafe_allow_html=True)
        instructions_sim = st.text_area(
            "Instructions supplémentaires",
            placeholder="Ex: La clause AAL a été introduite pour la première fois cette année. Le réassureur est particulièrement sensible à la tranche Cat L1...",
            height=100,
            key="instructions_sim",
            label_visibility="collapsed"
        )

        if api_key and st.button("🤖 Obtenir les recommandations Claude — Simulation"):
            with st.spinner("Claude analyse..."):
                contexte_global = st.session_state.get("instructions_globales", "")
                prompt = f"""Tu es expert en réassurance non-proportionnelle automobile.
{f"CONTEXTE GÉNÉRAL : {contexte_global}" if contexte_global else ""}
{f"INSTRUCTIONS SPÉCIFIQUES : {instructions_sim}" if instructions_sim else ""}

Compare taux technique base vs sans AAL vs sans AAD vs sans reconstitution.
Règle : Écart < 5% → condition inutile | 5-15% → à ajuster | > 15% → nécessaire.
Pour chaque tranche donne : verdict par condition + justification actuarielle.

Résultats simulation :
{json.dumps(st.session_state['resultats_sim'], indent=2)}

Programme :
{json.dumps(tranches_input, indent=2)}"""

                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(
                    model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role":"user","content":prompt}]
                )
                st.session_state["analyse_sim"] = analyse.content[0].text

        if "analyse_sim" in st.session_state:
            st.markdown(st.session_state["analyse_sim"])

# ════════════════════════════════
# TAB 5 — MARKET CURVE
# ════════════════════════════════
with tab5:
    st.header("Market Curve")
    st.caption("Modèle log-log : log(ROL) = a × log(midpoints) + b")

    f_mkt = st.file_uploader("📁 Données marché (Excel/CSV)", type=["xlsx","csv"], key="f_mkt")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
            df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)

            for col in ['ROLs','midpoints','Garantie en MAD','Priorité en MAD']:
                if col in df_mkt.columns and df_mkt[col].dtype == object:
                    df_mkt[col] = df_mkt[col].str.replace('%','').str.replace(' ','').str.replace(',','.').astype(float)

            df_mkt = df_mkt[(df_mkt['ROLs'] > 0) & (df_mkt['ROLs'] <= 1)].copy()
            df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()

            def fit_log_log(x, y):
                log_x      = np.log(x)
                log_y      = np.log(y)
                coeffs     = np.polyfit(log_x, log_y, 1)
                a, b       = coeffs[0], coeffs[1]
                log_y_pred = np.polyval(coeffs, log_x)
                ss_res     = np.sum((log_y - log_y_pred)**2)
                ss_tot     = np.sum((log_y - np.mean(log_y))**2)
                r2         = 1 - ss_res/ss_tot
                return a, b, r2

            def predict_rol(midpoint, a, b):
                return np.exp(b) * (midpoint ** a)

            quantiles     = [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]
            resultats_mkt = []

            for q in quantiles:
                mid_max  = np.quantile(df_mkt['midpoints'],       q)
                port_max = np.quantile(df_mkt['Garantie en MAD'], q)
                df_q     = df_mkt[(df_mkt['midpoints'] <= mid_max) & (df_mkt['Garantie en MAD'] <= port_max)]
                if len(df_q) < 5: continue
                x = df_q['midpoints'].values
                y = df_q['ROLs'].values
                try:
                    a, b, r2  = fit_log_log(x, y)
                    taux_tranches = []
                    for t in tranches_input:
                        mid_t = t['priorite'] + t['portee'] / 2
                        rol   = predict_rol(mid_t, a, b)
                        taux  = rol * (t['portee'] / gnpi)
                        taux_tranches.append({"tranche":t["nom"],"type":t["type"],"rol":rol,"taux":taux})
                    taux_vals   = [tt["taux"] for tt in taux_tranches]
                    median_taux = np.median(taux_vals)
                    cv_taux     = np.std(taux_vals) / median_taux if median_taux > 0 else 99
                    resultats_mkt.append({
                        "quantile":q,"n_points":len(df_q),"a":a,"b":b,
                        "r2":r2,"cv_taux":cv_taux,"taux_tranches":taux_tranches
                    })
                except:
                    continue

            if resultats_mkt:
                all_taux       = [[tt["taux"] for tt in r["taux_tranches"]] for r in resultats_mkt]
                med_global     = np.median([t for sub in all_taux for t in sub])
                r2_vals        = [r["r2"] for r in resultats_mkt]
                r2_min, r2_max = min(r2_vals), max(r2_vals)
                for r in resultats_mkt:
                    taux_moy  = np.mean([tt["taux"] for tt in r["taux_tranches"]])
                    ecart_med = abs(taux_moy - med_global) / med_global if med_global > 0 else 0
                    r2_norm   = (r["r2"] - r2_min) / (r2_max - r2_min + 1e-10)
                    r["score"]= 0.5 * r2_norm - 0.3 * ecart_med - 0.2 * r["cv_taux"]
                resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)

            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt

    if "resultats_mkt" in st.session_state:
        resultats_mkt = st.session_state["resultats_mkt"]
        df_mkt_clean  = st.session_state["df_mkt_clean"]

        def predict_rol(midpoint, a, b):
            return np.exp(b) * (midpoint ** a)

        rows_recap = []
        for r in resultats_mkt:
            row = {
                "Quantile": f"Q{int(r['quantile']*100)}",
                "N pts"   : r["n_points"],
                "a"       : f"{r['a']:.4f}",
                "b"       : f"{r['b']:.4f}",
                "R²"      : f"{r['r2']:.4f}",
                "Score"   : f"{r['score']:.4f}",
            }
            for tt in r["taux_tranches"]:
                row[tt["tranche"]] = f"{tt['taux']:.4%}"
            rows_recap.append(row)

        st.subheader("📊 Comparaison des 10 ajustements")
        st.dataframe(pd.DataFrame(rows_recap), use_container_width=True)

        best = resultats_mkt[0]
        st.success(f"✅ Meilleur score : Q{int(best['quantile']*100)} — R²={best['r2']:.4f} | Score={best['score']:.4f}")

        choix_q   = st.selectbox(
            "Choisir la combinaison à retenir",
            options=[f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in resultats_mkt],
            index=0
        )
        idx_choix = [f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in resultats_mkt].index(choix_q)
        choix     = resultats_mkt[idx_choix]

        x_all   = df_mkt_clean['midpoints'].values
        y_all   = df_mkt_clean['ROLs'].values
        x_range = np.linspace(min(x_all), max(x_all), 300)
        y_fit   = np.exp(choix['b']) * (x_range ** choix['a'])

        fig, ax = plt.subplots(figsize=(10,5))
        fig.patch.set_facecolor('#f0f2f6')
        ax.set_facecolor('#f8f9fa')
        ax.scatter(x_all, y_all, color='#e94560', s=60, zorder=5, alpha=0.7, label='Données marché')
        ax.plot(x_range, y_fit, color='#0f3460', lw=2.5,
                label=f"log(ROL)={choix['a']:.3f}×log(mid)+{choix['b']:.3f} | R²={choix['r2']:.4f}")
        ax.set_xlabel('Midpoints', fontsize=11)
        ax.set_ylabel('ROL', fontsize=11)
        ax.set_title('Market Curve — Modèle log-log', fontsize=13, fontweight='bold')
        ax.legend(fontsize=10); ax.grid(alpha=0.3, linestyle='--')
        st.pyplot(fig)

        st.subheader("📊 Taux marché retenus")
        st.dataframe(pd.DataFrame([{
            "Tranche"    : tt["tranche"],
            "Type"       : tt["type"],
            "ROL estimé" : f"{tt['rol']:.4%}",
            "Taux marché": f"{tt['taux']:.4%}"
        } for tt in choix["taux_tranches"]]), use_container_width=True)

        st.session_state["taux_mkt_final"] = choix["taux_tranches"]

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Market Curve")
        st.markdown('<div class="instruction-box">💡 <b>Instructions pour Claude</b></div>', unsafe_allow_html=True)
        instructions_mkt = st.text_area(
            "Instructions supplémentaires",
            placeholder="Ex: Le marché est actuellement en phase de durcissement. Les taux observés sont en hausse de 15% par rapport à l'an dernier...",
            height=100,
            key="instructions_mkt",
            label_visibility="collapsed"
        )

        if api_key and st.button("🤖 Obtenir les recommandations Claude — Market Curve"):
            with st.spinner("Claude analyse..."):
                contexte_global = st.session_state.get("instructions_globales", "")
                prompt = f"""Tu es expert en réassurance catastrophe et market curve.
{f"CONTEXTE GÉNÉRAL : {contexte_global}" if contexte_global else ""}
{f"INSTRUCTIONS SPÉCIFIQUES : {instructions_mkt}" if instructions_mkt else ""}

Analyse ces ajustements de market curve et recommande le meilleur.
Modèle : log(ROL) = a × log(midpoints) + b
Tiens compte du R², score optimal, nombre de points, cohérence des taux et contexte marché.

Ajustements :
{json.dumps(rows_recap, indent=2)}

Programme :
{json.dumps(tranches_input, indent=2)}"""

                client = anthropic.Anthropic(api_key=api_key)
                reco   = client.messages.create(
                    model="claude-opus-4-5", max_tokens=1000,
                    messages=[{"role":"user","content":prompt}]
                )
                st.session_state["analyse_mkt"] = reco.content[0].text

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])

# ════════════════════════════════
# TAB 6 — RAPPORT FINAL
# ════════════════════════════════
with tab6:
    st.header("Rapport Final de Tarification")

    manquants = []
    if "resultats_bc"  not in st.session_state: manquants.append("Burning Cost")
    if "resultats_sim" not in st.session_state: manquants.append("Simulation")
    if "taux_mkt_final"not in st.session_state: manquants.append("Market Curve")

    if manquants:
        st.warning(f"⚠️ Complétez d'abord : {', '.join(manquants)}")
    else:
        st.divider()
        st.markdown("### 🤖 Instructions pour le rapport final")
        st.markdown('<div class="instruction-box">💡 Ces instructions guideront Claude dans la rédaction du rapport final</div>', unsafe_allow_html=True)
        instructions_rapport = st.text_area(
            "Instructions finales",
            placeholder="Ex: Focus particulier sur la cohérence entre méthodes. Le cedant souhaite minimiser la prime totale tout en maintenant une protection adéquate. Comparer avec les taux de l'année précédente si pertinent...",
            height=120,
            key="instructions_rapport"
        )

        if st.button("▶ Générer le rapport final", type="primary"):
            bc_map  = {r["tranche"]: r for r in st.session_state["resultats_bc"]}
            sim_map = {r["tranche"]: r for r in st.session_state["resultats_sim"]}
            mkt_map = {r["tranche"]: r["taux"] for r in st.session_state["taux_mkt_final"]}

            rows_rapport = []
            prime_totale = 0

            for t in tranches_input:
                nom    = t["nom"]
                bc     = bc_map.get(nom, {})
                sim    = sim_map.get(nom, {})
                mkt    = mkt_map.get(nom, 0)
                bc_tt  = bc.get("taux_technique", 0)
                sim_tt = sim.get("taux_technique", 0)

                if t["type"] == "travaillante":
                    ecart       = abs(bc_tt - sim_tt) / bc_tt * 100 if bc_tt > 0 else 0
                    taux_retenu = sim_tt
                    alerte      = "⚠️" if ecart > 25 else "✅"
                    methode     = f"Simulation (écart BC/Sim: {ecart:.0f}%) {alerte}"
                else:
                    taux_retenu = max(sim_tt, mkt)
                    methode     = "Simulation" if sim_tt >= mkt else "Marché"

                prime         = gnpi * taux_retenu
                prime_totale += prime

                rows_rapport.append({
                    "Tranche"    : nom,
                    "Type"       : t["type"],
                    "Taux BC"    : f"{bc_tt:.4%}",
                    "Taux Sim."  : f"{sim_tt:.4%}",
                    "Taux Marché": f"{mkt:.4%}",
                    "Taux retenu": f"{taux_retenu:.4%}",
                    "Prime (MAD)": f"{prime:,.0f}",
                    "Méthode"    : methode
                })

            st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
            st.session_state["prime_totale"] = prime_totale

            if api_key:
                with st.spinner("Claude rédige le rapport final..."):
                    contexte_global = st.session_state.get("instructions_globales", "")
                    prompt = f"""Tu es expert senior en tarification réassurance non-proportionnelle automobile.
{f"CONTEXTE GÉNÉRAL : {contexte_global}" if contexte_global else ""}
{f"INSTRUCTIONS SPÉCIFIQUES : {instructions_rapport}" if instructions_rapport else ""}

Rédige un rapport de tarification structuré et professionnel.
Pour chaque tranche :
1. Valide ou questionne le taux retenu
2. Compare les 3 méthodes (BC, Simulation, Marché)
3. Signale les anomalies ou incohérences
4. Donne une recommandation finale motivée

Termine par une synthèse globale avec avis sur la structure du programme.

Rapport de tarification :
{json.dumps(rows_rapport, indent=2)}

GNPI : {gnpi:,} MAD
Prime totale : {prime_totale:,.0f} MAD
Taux global : {prime_totale/gnpi:.4%}"""

                    client      = anthropic.Anthropic(api_key=api_key)
                    reco_finale = client.messages.create(
                        model="claude-opus-4-5", max_tokens=2000,
                        messages=[{"role":"user","content":prompt}]
                    )
                    st.session_state["reco_finale"] = reco_finale.content[0].text

    if "df_rapport" in st.session_state:
        st.subheader("📊 Synthèse de tarification")
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)

        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Prime totale", f"{st.session_state['prime_totale']:,.0f} MAD")
        c2.metric("📊 Taux global",  f"{st.session_state['prime_totale']/gnpi:.4%}")
        c3.metric("📋 Nb tranches",  len(tranches_input))

    if "reco_finale" in st.session_state:
        st.divider()
        st.subheader("🤖 Rapport Claude")
        st.markdown(st.session_state["reco_finale"])
