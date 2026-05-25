import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json
import secrets as secrets_lib
from PIL import Image

# ════════════════════════════════════════════
# ACCESS CONTROL
# ════════════════════════════════════════════

def get_admin_password():
    try: return st.secrets["admin_password"]
    except: return "Admin@HerveIA2026"

def get_users():
    try: return dict(st.secrets["users"])
    except: return {"demo@herve.ia": "DEMO2026"}

def check_access(email, code):
    return get_users().get(email.lower().strip()) == code.strip()

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    try:
        icon = Image.open("icon.jpg")
        st.set_page_config(page_title="Herve IA", layout="centered", page_icon=icon)
    except:
        st.set_page_config(page_title="Herve IA", layout="centered", page_icon="🎯")

    st.markdown("""
    <style>
    .stApp { background: linear-gradient(135deg, #0f3460 0%, #16213e 100%); }
    .login-card {
        background: white; border-radius: 20px;
        padding: 40px; margin: 60px auto;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        max-width: 420px;
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-card">', unsafe_allow_html=True)
        st.markdown("<div style='text-align:center'>", unsafe_allow_html=True)
        st.markdown("# 🎯")
        st.markdown("### Herve IA")
        st.caption("Tarification Réassurance Non-Proportionnelle")
        st.markdown("</div>", unsafe_allow_html=True)
        st.divider()
        email = st.text_input("📧 Adresse email", placeholder="votre@email.com",  key="login_email")
        code  = st.text_input("🔑 Code d'accès",  type="password", placeholder="CODE123", key="login_code")
        if st.button("Se connecter", type="primary", use_container_width=True):
            if check_access(email, code):
                st.session_state["authenticated"] = True
                st.session_state["user_email"]    = email
                st.rerun()
            else:
                st.error("❌ Email ou code d'accès incorrect")
        st.caption("Accès réservé. Contactez l'administrateur.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ════════════════════════════════════════════
# APP CONFIG (après auth)
# ════════════════════════════════════════════
try:
    icon = Image.open("icon.jpg")
    st.set_page_config(page_title="Herve IA — Tarification XL", layout="wide", page_icon=icon)
except:
    st.set_page_config(page_title="Herve IA — Tarification XL", layout="wide", page_icon="🎯")

st.markdown("""
<style>
.stApp { background-color: #f0f2f6; }
h1 { color: #1a1a2e; }
h2 { color: #16213e; border-bottom: 2px solid #0f3460; padding-bottom: 8px; }
h3 { color: #0f3460; }
.stButton > button {
    background-color: #0f3460; color: white;
    border: none; border-radius: 8px;
    padding: 8px 20px; font-weight: 600; transition: all 0.3s;
}
.stButton > button:hover { background-color: #e94560; transform: translateY(-1px); }
.stTabs [data-baseweb="tab-list"] { background-color: #1a1a2e; border-radius: 10px; padding: 4px; }
.stTabs [data-baseweb="tab"] { color: #aaa; font-weight: 500; }
.stTabs [aria-selected="true"] { background-color: #e94560 !important; color: white !important; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════
# PROMPT ENGINEERING
# ════════════════════════════════════════════

def prompt_inputs(key_prefix, placeholder_contexte="", placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    with st.expander("✏️ Personnaliser le prompt Claude", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area("📌 Contexte",
                placeholder=placeholder_contexte, height=80, key=f"{key_prefix}_contexte")
            instructions = st.text_area("📋 Instructions spécifiques",
                placeholder=placeholder_instructions, height=80, key=f"{key_prefix}_instructions")
        with c2:
            input_data = st.text_area("📥 Données supplémentaires",
                placeholder=placeholder_input, height=80, key=f"{key_prefix}_input")
            output_instructions = st.text_area("📤 Format de sortie",
                placeholder=placeholder_output, height=80, key=f"{key_prefix}_output")
    return contexte, instructions, input_data, output_instructions


def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    return f"""
════════════════════════════════════════════
RÔLE
════════════════════════════════════════════
{role}

════════════════════════════════════════════
RÈGLES ABSOLUES
════════════════════════════════════════════
1. ANTI-HALLUCINATION : Ne jamais inventer de chiffres.
   Si incertain → écrire : "Information insuffisante pour conclure."
2. RAISONNEMENT : Format obligatoire [Observation] → [Analyse] → [Conclusion]
3. CONTRAINTES MÉTIER :
{contraintes if contraintes else "   - Taux techniques positifs < 50% | Écart BC/Sim > 25% → ⚠️ | BC=0 tranche cat = NORMAL"}
4. VÉRIFICATION avant réponse :
   ✓ Chiffres présents dans les données ? ✓ Cohérence entre tranches ?
   ✓ Hiérarchie taux_pur < taux_risque < taux_technique ?
5. EXEMPLES :
{exemples if exemples else '   Bon : "Écart 35% [Obs] → sous-estimation BC [Anal] → retenir simulation [Concl]"\n   Mauvais : "Le taux semble acceptable."'}

════════════════════════════════════════════
CONTEXTE GÉNÉRAL
════════════════════════════════════════════
{contexte_global if contexte_global else "Non fourni."}

════════════════════════════════════════════
CONTEXTE SPÉCIFIQUE
════════════════════════════════════════════
{contexte if contexte else "Aucun."}

════════════════════════════════════════════
TÂCHE
════════════════════════════════════════════
{task}

════════════════════════════════════════════
DONNÉES
════════════════════════════════════════════
{data}
{f"DONNÉES SUPPLÉMENTAIRES : {input_data}" if input_data else ""}

════════════════════════════════════════════
INSTRUCTIONS SPÉCIFIQUES
════════════════════════════════════════════
{instructions if instructions else "Suivre la tâche décrite."}

════════════════════════════════════════════
FORMAT DE SORTIE
════════════════════════════════════════════
{output_instructions if output_instructions else "1. SYNTHÈSE (2-3 phrases)\n2. ANALYSE PAR TRANCHE\n3. POINTS D'ATTENTION\n4. CONCLUSION"}
════════════════════════════════════════════
""".strip()


# ════════════════════════════════════════════
# HEADER + SIDEBAR
# ════════════════════════════════════════════

st.title("🎯 Herve IA — Tarification Réassurance Non-Proportionnelle")
st.caption(f"Connecté : {st.session_state.get('user_email','')} | Burning Cost · Simulation · Market Curve · IA")

if st.sidebar.button("🚪 Déconnexion"):
    st.session_state["authenticated"] = False
    st.rerun()

with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    api_key = st.text_input("🔑 Clé API Claude", type="password", placeholder="sk-ant-...")
    gnpi    = st.number_input("💰 GNPI (MAD)", value=183_000_000, step=1_000_000)
    st.divider()
    st.markdown("### 📊 Statut")
    for nom, key in [("Programme","df_prog"),("Données","df_liq"),
                     ("Burning Cost","resultats_bc"),("Simulation","resultats_sim"),
                     ("Market Curve","resultats_mkt")]:
        st.markdown(f"{'✅' if key in st.session_state else '⬜'} {nom}")
    st.divider()
    st.markdown("### 🌍 Contexte global")
    instructions_globales = st.text_area("Contexte portefeuille",
        placeholder="Ex: Portefeuille automobile Maroc...", height=100, key="instructions_globales")


# ════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════

tab1, tab2, tab3, tab4, tab5, tab6, tab_admin = st.tabs([
    "📋 Programme", "📂 Données & Triangle",
    "🔥 Burning Cost", "🎲 Simulation",
    "📈 Market Curve", "📋 Rapport Final", "🔐 Admin"
])

# ════════════════════════════════════════════
# TAB 1 — PROGRAMME
# ════════════════════════════════════════════

with tab1:
    st.header("Programme de Réassurance")
    nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)
    tranches_input = []

    for i in range(nb_tranches):
        with st.expander(f"🔷 Tranche {i+1}", expanded=(i==0)):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("**Identification**")
                nom      = st.text_input("Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
                type_t   = st.selectbox("Type", ["travaillante","non_travaillante","cat"], key=f"type_{i}")
                priorite = st.number_input("Priorité (MAD)", value=2_000_000,  step=500_000, key=f"prio_{i}", format="%d")
                portee   = st.number_input("Portée (MAD)",   value=13_000_000, step=500_000, key=f"port_{i}", format="%d")
            with c2:
                st.markdown("**Conditions**")
                has_aal     = st.checkbox("AAL", key=f"aal_{i}")
                aal_val     = st.number_input("Montant AAL", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
                has_aad     = st.checkbox("AAD", key=f"aad_{i}")
                aad_val     = st.number_input("Montant AAD", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
                has_indices = st.checkbox("Clause d'indexation", key=f"idx_{i}")
            with c3:
                st.markdown("**Frais & Reconstitutions**")
                nb_recon     = st.number_input("Nb reconstitutions",    value=1,   min_value=0, max_value=5,   key=f"recon_{i}")
                tx_recon     = st.number_input("Taux reconstitution %", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
                brokage      = st.number_input("Brokage %",             value=10,  min_value=0, max_value=30,  key=f"brok_{i}")
                frais        = st.number_input("Frais généraux %",      value=5,   min_value=0, max_value=20,  key=f"frais_{i}")
                marge        = st.number_input("Marge %",               value=10,  min_value=0, max_value=30,  key=f"marge_{i}")
                retrocession = st.number_input("Rétrocession %",        value=0,   min_value=0, max_value=50,  key=f"retro_{i}")
        tranches_input.append({
            "numero": i+1, "nom": nom, "type": type_t,
            "priorite": priorite, "portee": portee,
            "AAL": aal_val if has_aal else None,
            "AAD": aad_val if has_aad else None,
            "nb_reconstitutions": nb_recon, "taux_reconstitution": tx_recon,
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
            "Brokage": f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}",
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

    # ── Type de branche ──
    type_branche = st.radio(
        "Type de branche",
        ["Développement long (As-If + Stabilisation + Projection CL)",
         "Développement court (As-If uniquement, pas de projection)"],
        key="type_branche",
        horizontal=True
    )
    is_long = "long" in type_branche

    c1, c2, c3 = st.columns(3)
    with c1: f_triangle = st.file_uploader("📁 Triangle développement", type=["xlsx","csv"], key="f_tri")
    with c2: f_gnpis    = st.file_uploader("📁 Base GNPIs",             type=["xlsx","csv"], key="f_gnp")
    with c3: f_indices  = st.file_uploader("📁 Table indices",          type=["xlsx","csv"], key="f_idx")

    annee_cotation = st.number_input("Année de cotation (n)", value=2026, step=1,
                                      help="Année fixe utilisée pour la stabilisation : I_surv/I_cotation")

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
                if i == 0: col_info.append(('UW_YEAR', '')); continue
                try:
                    a = int(float(str(ann)))
                    if 2010 <= a <= 2035: annee_courante = a
                except: pass
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
                except: continue
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
                    except: continue
                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 9: continue
                    records.append({'sinistre_id': sinistre_id, 'annee_surv': annee_surv,
                                    'annee_reg': annee_reg, 'dev': dev, 'total': val})

            df_liq = pd.DataFrame(records)

            progress.progress(45, text="Calcul As-If...")
            df_idx_set    = df_idx_df.set_index('Annee')['Coefficients']
            I_cotation_val = float(df_idx_set.get(annee_cotation, 1.0))

            def get_indice(annee):
                try: return float(df_idx_set[annee])
                except: return 1.0

            # ── As-If : Sk = total × (I_ultime / I_reg) ──
            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
            df_liq['Sk']           = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

            if is_long:
                progress.progress(50, text="Stabilisation...")
                # ── Stabilisation : S'k = Sk × (I_surv / I_cotation) ──
                # Condition : (I_cotation / I_surv - 1) > 10%
                df_liq['ratio_check'] = I_cotation_val / df_liq['I_surv']
                df_liq['S_prime_k']   = np.where(
                    (df_liq['ratio_check'] - 1) > 0.10,
                    df_liq['Sk'] * (df_liq['I_surv'] / I_cotation_val),
                    df_liq['Sk']
                )
                # coeff = Sk / S'k (déterministe par sinistre)
                df_liq['coeff_stab'] = np.where(
                    df_liq['S_prime_k'] > 0,
                    df_liq['Sk'] / df_liq['S_prime_k'],
                    1.0
                )

                progress.progress(60, text="Chain Ladder individuel sur S'k...")
                facteurs = {k: [] for k in range(9)}
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    for k in range(9):
                        if k in grp.index and (k+1) in grp.index:
                            t_k  = grp.loc[k,   'S_prime_k']
                            t_k1 = grp.loc[k+1, 'S_prime_k']
                            if t_k > 0:
                                f = t_k1 / t_k
                                if 0.9 <= f <= 2.5: facteurs[k].append(f)

                f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

                progress.progress(75, text="Projection S'k à l'ultime...")
                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv          = grp['annee_surv'].iloc[0]
                    dev_max             = grp.index.max()
                    Sprime_actuel       = grp.loc[dev_max, 'S_prime_k']
                    coeff_sin           = grp.loc[dev_max, 'coeff_stab']
                    Sprime_ultime       = Sprime_actuel
                    for k in range(dev_max, 9):
                        Sprime_ultime  *= f_moyens[k]
                    # Sk_ultime = S'k_ultime × coeff (coeff = I_cotation/I_surv, constant)
                    Sk_ultime = Sprime_ultime * coeff_sin
                    projections.append({
                        'sinistre_id'   : sin_id,
                        'annee_surv'    : annee_surv,
                        'dev_max'       : dev_max,
                        'Sprime_ultime' : Sprime_ultime,   # S'k projeté (stabilisé)
                        'Sk_ultime'     : Sk_ultime,        # Sk projeté (as-if)
                        'coeff_stab'    : coeff_sin         # Sk/S'k
                    })

            else:
                # Branche courte : pas de stabilisation, pas de projection
                progress.progress(60, text="Branche courte — As-If direct...")
                df_liq['S_prime_k']  = df_liq['Sk']
                df_liq['coeff_stab'] = 1.0
                f_moyens = {k: 1.0 for k in range(9)}

                projections = []
                for sin_id, grp in df_liq.groupby('sinistre_id'):
                    grp = grp.sort_values('dev').set_index('dev')
                    annee_surv    = grp['annee_surv'].iloc[0]
                    dev_max       = grp.index.max()
                    Sk_actuel     = grp.loc[dev_max, 'Sk']
                    projections.append({
                        'sinistre_id'   : sin_id,
                        'annee_surv'    : annee_surv,
                        'dev_max'       : dev_max,
                        'Sprime_ultime' : Sk_actuel,   # = Sk (pas de stab)
                        'Sk_ultime'     : Sk_actuel,
                        'coeff_stab'    : 1.0
                    })

            df_proj = pd.DataFrame(projections)

            progress.progress(88, text="Estimation alpha & lambda...")
            # Alpha estimé sur S'k (stabilisé) pour branche longue, Sk pour courte
            X       = df_proj['Sprime_ultime'].values
            X       = X[X > 0]
            seuil   = np.percentile(X, 85)
            X_above = X[X >= seuil]
            t_min   = np.min(X_above)
            n_above = len(X_above)
            alpha_est = n_above / np.sum(np.log(X_above / t_min))

            df_gnpis_idx = df_gnpis_df.set_index(df_gnpis_df.columns[0])
            gnpi_col     = df_gnpis_df.columns[1]
            N_obs        = df_proj[df_proj['Sprime_ultime'] >= seuil].groupby('annee_surv').size()
            N_asif_vals  = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except: N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0

            # Coefficients pour simulation (Sk/S'k par sinistre)
            coeffs_raw = df_proj['coeff_stab'].values
            coeffs     = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

            progress.progress(100, text="Terminé !")

            st.session_state.update({
                "df_liq"        : df_liq,
                "df_proj"       : df_proj,
                "f_moyens"      : f_moyens,
                "alpha_est"     : float(alpha_est),
                "lambda_est"    : float(lambda_est),
                "seuil_est"     : float(seuil),
                "coeffs"        : coeffs,
                "is_long"       : is_long,
                "I_cotation"    : I_cotation_val,
                "annee_cotation": annee_cotation,
                "df_gnpis_df"   : df_gnpis_df,
                "df_facteurs"   : pd.DataFrame({
                    'Dev.'           : [f"{k}→{k+1}" for k in range(9)],
                    'Facteur moyen'  : [round(f_moyens[k], 4) for k in range(9)],
                    'Nb observations': [len(facteurs[k]) if is_long else 0 for k in range(9)]
                }) if is_long else pd.DataFrame({'Info': ['Branche courte — pas de projection CL']})
            })

    if "df_liq" in st.session_state:
        c1, c2, c3 = st.columns(3)
        c1.metric("Observations", len(st.session_state['df_liq']))
        c2.metric("Sinistres",    st.session_state['df_liq']['sinistre_id'].nunique())
        c3.metric("Années",       st.session_state['df_liq']['annee_surv'].nunique())

        branch_label = "Longue (As-If + Stab + CL)" if st.session_state.get("is_long") else "Courte (As-If uniquement)"
        st.info(f"🌿 Branche : **{branch_label}** | I_cotation({st.session_state.get('annee_cotation')}) = {st.session_state.get('I_cotation',1):.4f}")
        st.info(f"🔢 Seuil P85: {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

        with st.expander("📊 Triangle de liquidation (Sk & S'k)"):
            cols_show = ['sinistre_id','annee_surv','annee_reg','dev','total','Sk','S_prime_k','coeff_stab']
            st.dataframe(st.session_state["df_liq"][[c for c in cols_show if c in st.session_state["df_liq"].columns]].head(30), use_container_width=True)
        with st.expander("📊 Facteurs Chain Ladder"):
            st.dataframe(st.session_state["df_facteurs"], use_container_width=True)
        with st.expander("📊 Projections (S'k & Sk à l'ultime)"):
            st.dataframe(st.session_state["df_proj"].head(20), use_container_width=True)

# ════════════════════════════════════════════
# TAB 3 — BURNING COST
# ════════════════════════════════════════════

with tab3:
    st.header("Burning Cost")
    st.caption("Ck = min(max(S'k_ultime − D, 0), L) × (Sk/S'k)")

    if "df_proj" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
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

                    # Ck = min(max(S'k_ultime − D, 0), L) × coeff_stab
                    df_proj['Ck'] = df_proj.apply(
                        lambda row: min(max(row['Sprime_ultime'] - D, 0), P) * row['coeff_stab'],
                        axis=1
                    )

                    charges_ann     = df_proj.groupby('annee_surv')['Ck'].sum()
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
                        "tranche"       : t_info["nom"], "type": t_info["type"],
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
            "Tranche"       : r["tranche"], "Type": r["type"],
            "Charge moy."   : f"{r['charge_moy']:,.0f} MAD",
            "Taux pur"      : f"{r['taux_pur']:.4%}",
            "Taux risque"   : f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final"    : f"{r['taux_final']:.4%}",
        } for r in st.session_state["resultats_bc"]]), use_container_width=True)

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Burning Cost")
        ctx_bc, inst_bc, inp_bc, out_bc = prompt_inputs("bc",
            placeholder_contexte="Ex: Sinistralité exceptionnelle 2020...",
            placeholder_instructions="Ex: Comparer avec taux marché 3-4%...",
            placeholder_input="Ex: Taux BC N-1 : R&C=2.5%",
            placeholder_output="Ex: Tableau + verdict OK/ALERTE/RÉVISER")

        if api_key and st.button("🤖 Recommandations Claude — BC"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert actuaire senior réassurance non-proportionnelle automobile.",
                    task="""Analyse les résultats de Burning Cost.
Pour chaque tranche : niveau du taux, cohérence, anomalies, verdict ✅/⚠️/❌""",
                    data=f"""BC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}
Programme : {json.dumps(tranches_input, indent=2)}
GNPI : {gnpi:,} MAD
Formule utilisée : Ck = min(max(S'k_ultime−D,0),L) × (Sk/S'k)""",
                    contexte=ctx_bc, instructions=inst_bc,
                    input_data=inp_bc, output_instructions=out_bc,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="- BC=0 tranche cat = NORMAL\n- Vérifier hiérarchie taux\n- Ne pas inventer de comparatifs"
                )
                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(model="claude-opus-4-5", max_tokens=2000,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_bc"] = analyse.content[0].text

        if "analyse_bc" in st.session_state:
            st.markdown(st.session_state["analyse_bc"])

# ════════════════════════════════════════════
# TAB 4 — SIMULATION
# ════════════════════════════════════════════

with tab4:
    st.header("Simulation Pareto / Poisson")
    st.caption("Simule S'0 (stabilisé) sur Pareto — applique coeff Sk/S'k pour charge réassurance")

    if "alpha_est" not in st.session_state:
        st.warning("⚠️ Transformez d'abord le triangle")
    else:
        is_long_sim = st.session_state.get("is_long", True)
        st.info(f"🌿 Branche {'longue' if is_long_sim else 'courte'} | Seuil P85: {st.session_state['seuil_est']:,.0f} | Alpha: {st.session_state['alpha_est']:.4f} | Lambda: {st.session_state['lambda_est']:.4f}")

        c1, c2, c3, c4 = st.columns(4)
        with c1: alpha_final  = st.number_input("Alpha",         value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
        with c2: lambda_final = st.number_input("Lambda",        value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
        with c3: seuil_final  = st.number_input("Seuil (MAD)",   value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
        with c4: n_sim        = st.number_input("Nb simulations", value=10000, step=1000,               key="nsim_input")

        if st.button("▶ Lancer la simulation", type="primary"):
            with st.spinner("🎲 Simulation en cours..."):
                progress_sim = st.progress(0, text="Initialisation...")
                alpha_f  = st.session_state["alpha_input"]
                lambda_f = st.session_state["lambda_input"]
                seuil_f  = st.session_state["seuil_input"]
                n_s      = int(st.session_state["nsim_input"])
                coeffs   = st.session_state["coeffs"]
                np.random.seed(42)
                resultats_sim = []

                for idx_t, t_info in enumerate(tranches_input):
                    progress_sim.progress(int((idx_t/len(tranches_input))*100),
                                          text=f"Simulation {t_info['nom']}...")
                    D   = t_info["priorite"]
                    P   = t_info["portee"]
                    r   = t_info["nb_reconstitutions"]
                    aal = t_info["AAL"]
                    aad = t_info["AAD"]
                    cap = (r + 1) * P

                    def simuler(avec_aal, avec_aad, avec_rec):
                        charges = []
                        for _ in range(n_s):
                            N = np.random.poisson(lambda_f)
                            S_total = 0
                            if N > 0:
                                U = np.random.uniform(size=N)
                                # Simule S'0 (montants stabilisés) sur Pareto
                                Sprime_sim = seuil_f * (U ** (-1/alpha_f))
                                # coeff déterministe tiré aléatoirement parmi les historiques
                                idx_c = np.random.choice(len(coeffs), size=N, replace=True)
                                for i in range(N):
                                    S_prime = Sprime_sim[i]
                                    c       = coeffs[idx_c[i]]  # Sk/S'k
                                    # Ck = min(max(S'0 - D, 0), L) × coeff
                                    if   S_prime <= D:       S_i = 0
                                    elif S_prime <= D + P:   S_i = c * (S_prime - D)
                                    else:                    S_i = c * P
                                    S_total += S_i
                            ch = S_total
                            if avec_aad and aad: ch = max(ch - aad, 0)
                            if avec_aal and aal: ch = min(ch, aal)
                            charges.append(min(ch, cap) if avec_rec else ch)
                        return np.array(charges)

                    def calc_taux(ch):
                        P0 = np.mean(ch); sig = np.std(ch)
                        tp = P0 / gnpi
                        tr = (P0 + 0.2 * sig) / gnpi
                        tt = tr / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                        tf = tt * (1 + t_info["marge"] + t_info["retrocession"])
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
                        "taux_pur"      : tp,  "taux_risque": tr,
                        "taux_technique": tt,  "taux_final" : tf,
                        "sans_aal"      : tt2, "sans_aad"   : tt3, "sans_rec": tt4,
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
        st.markdown("### 🤖 Analyse Claude — Simulation")
        ctx_sim, inst_sim, inp_sim, out_sim = prompt_inputs("sim",
            placeholder_contexte="Ex: Nouveau modèle cat, lambda revu...",
            placeholder_instructions="Ex: Seuil alerte = 20%...",
            placeholder_input="Ex: Résultats sim N-1...",
            placeholder_output="Ex: Verdict par condition + impact en pts de taux")

        if api_key and st.button("🤖 Recommandations Claude — Simulation"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert modélisation catastrophe et simulation stochastique réassurance.",
                    task="""Analyse simulation et impact des conditions contractuelles.
Pour chaque tranche/condition : impact en pts de taux, verdict NÉCESSAIRE/À AJUSTER/INUTILE, montant optimal.""",
                    data=f"Simulation : {json.dumps(st.session_state['resultats_sim'], indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}",
                    contexte=ctx_sim, instructions=inst_sim,
                    input_data=inp_sim, output_instructions=out_sim,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="- Ne pas supprimer AAL sur tranche cat\n- AAD trop élevé = tranche inutile\n- Écart BC/Sim > 50% = anomalie majeure"
                )
                client  = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(model="claude-opus-4-5", max_tokens=2000,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_sim"] = analyse.content[0].text

        if "analyse_sim" in st.session_state:
            st.markdown(st.session_state["analyse_sim"])

# ════════════════════════════════════════════
# TAB 5 — MARKET CURVE
# ════════════════════════════════════════════

with tab5:
    st.header("Market Curve")
    st.caption("Modèle log-log : log(ROL) = a × log(midpoints) + b")

    f_mkt = st.file_uploader("📁 Données marché", type=["xlsx","csv"], key="f_mkt")

    if f_mkt and st.button("▶ Construire la market curve", type="primary"):
        with st.spinner("📈 Construction en cours..."):
            df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)

            for col in ['ROLs','midpoints','Garantie en MAD','Priorité en MAD']:
                if col in df_mkt.columns and df_mkt[col].dtype == object:
                    df_mkt[col] = df_mkt[col].str.replace('%','').str.replace(' ','').str.replace(',','.').astype(float)

            df_mkt = df_mkt[(df_mkt['ROLs'] > 0) & (df_mkt['ROLs'] <= 1)].copy()
            df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()

            def fit_log_log(x, y):
                log_x = np.log(x); log_y = np.log(y)
                c     = np.polyfit(log_x, log_y, 1)
                a, b  = c[0], c[1]
                r2    = 1 - np.sum((log_y - np.polyval(c, log_x))**2) / np.sum((log_y - log_y.mean())**2)
                return a, b, r2

            def predict_rol(mid, a, b):
                return np.exp(b) * (mid ** a)

            resultats_mkt = []
            for q in [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]:
                mid_max  = np.quantile(df_mkt['midpoints'],       q)
                port_max = np.quantile(df_mkt['Garantie en MAD'], q)
                df_q     = df_mkt[(df_mkt['midpoints'] <= mid_max) & (df_mkt['Garantie en MAD'] <= port_max)]
                if len(df_q) < 5: continue
                try:
                    a, b, r2 = fit_log_log(df_q['midpoints'].values, df_q['ROLs'].values)
                    taux_tranches = [{"tranche":t["nom"],"type":t["type"],
                        "rol": predict_rol(t['priorite']+t['portee']/2, a, b),
                        "taux": predict_rol(t['priorite']+t['portee']/2, a, b) * (t['portee']/gnpi)}
                        for t in tranches_input]
                    taux_vals   = [tt["taux"] for tt in taux_tranches]
                    median_taux = np.median(taux_vals)
                    cv_taux     = np.std(taux_vals)/median_taux if median_taux > 0 else 99
                    resultats_mkt.append({"quantile":q,"n_points":len(df_q),"a":a,"b":b,
                        "r2":r2,"cv_taux":cv_taux,"taux_tranches":taux_tranches})
                except: continue

            if resultats_mkt:
                all_t = [tt["taux"] for r in resultats_mkt for tt in r["taux_tranches"]]
                med_g = np.median(all_t)
                r2v   = [r["r2"] for r in resultats_mkt]
                r2min, r2max = min(r2v), max(r2v)
                for r in resultats_mkt:
                    tm = np.mean([tt["taux"] for tt in r["taux_tranches"]])
                    r["score"] = 0.5*(r["r2"]-r2min)/(r2max-r2min+1e-10) - 0.3*abs(tm-med_g)/(med_g+1e-10) - 0.2*r["cv_taux"]
                resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)

            st.session_state["resultats_mkt"] = resultats_mkt
            st.session_state["df_mkt_clean"]  = df_mkt

    if "resultats_mkt" in st.session_state:
        rmt = st.session_state["resultats_mkt"]
        dmc = st.session_state["df_mkt_clean"]

        def predict_rol(mid, a, b): return np.exp(b) * (mid ** a)

        rows_recap = []
        for r in rmt:
            row = {"Q":f"Q{int(r['quantile']*100)}","N":r["n_points"],
                   "a":f"{r['a']:.4f}","b":f"{r['b']:.4f}","R²":f"{r['r2']:.4f}","Score":f"{r['score']:.4f}"}
            for tt in r["taux_tranches"]: row[tt["tranche"]] = f"{tt['taux']:.4%}"
            rows_recap.append(row)

        st.dataframe(pd.DataFrame(rows_recap), use_container_width=True)
        best = rmt[0]
        st.success(f"✅ Meilleur : Q{int(best['quantile']*100)} — R²={best['r2']:.4f} | Score={best['score']:.4f}")

        choix_q   = st.selectbox("Choisir",
            options=[f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in rmt], index=0)
        idx_choix = [f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in rmt].index(choix_q)
        choix     = rmt[idx_choix]

        x_all   = dmc['midpoints'].values; y_all = dmc['ROLs'].values
        x_range = np.linspace(min(x_all), max(x_all), 300)

        fig, ax = plt.subplots(figsize=(10,5))
        fig.patch.set_facecolor('#f0f2f6'); ax.set_facecolor('#f8f9fa')
        ax.scatter(x_all, y_all, color='#e94560', s=60, zorder=5, alpha=0.7, label='Données marché')
        ax.plot(x_range, np.exp(choix['b'])*(x_range**choix['a']), color='#0f3460', lw=2.5,
                label=f"log(ROL)={choix['a']:.3f}×log(mid)+{choix['b']:.3f} | R²={choix['r2']:.4f}")
        ax.set_xlabel('Midpoints'); ax.set_ylabel('ROL')
        ax.set_title('Market Curve — Modèle log-log', fontweight='bold')
        ax.legend(); ax.grid(alpha=0.3, linestyle='--')
        st.pyplot(fig)

        st.dataframe(pd.DataFrame([{"Tranche":tt["tranche"],"Type":tt["type"],
            "ROL estimé":f"{tt['rol']:.4%}","Taux marché":f"{tt['taux']:.4%}"}
            for tt in choix["taux_tranches"]]), use_container_width=True)
        st.session_state["taux_mkt_final"] = choix["taux_tranches"]

        st.divider()
        st.markdown("### 🤖 Analyse Claude — Market Curve")
        ctx_mkt, inst_mkt, inp_mkt, out_mkt = prompt_inputs("mkt",
            placeholder_contexte="Ex: Marché en durcissement +15%...",
            placeholder_instructions="Ex: Privilégier N > 20 points...",
            placeholder_input="Ex: Taux marché référence Cat L1=1.5%",
            placeholder_output="Ex: Recommandation unique avec justification")

        if api_key and st.button("🤖 Recommandations Claude — Market Curve"):
            with st.spinner("Claude analyse..."):
                prompt = build_prompt(
                    role="Expert réassurance catastrophe et market curve.",
                    task="Analyse les ajustements log-log et recommande UN seul. Justifie avec R², score, N points, cohérence taux.",
                    data=f"Ajustements : {json.dumps(rows_recap, indent=2)}\nProgramme : {json.dumps(tranches_input, indent=2)}",
                    contexte=ctx_mkt, instructions=inst_mkt,
                    input_data=inp_mkt, output_instructions=out_mkt,
                    contexte_global=st.session_state.get("instructions_globales",""),
                    contraintes="- R²<0.3 = médiocre\n- N<10 = faible robustesse\n- Taux>3×simulation = suspect"
                )
                client = anthropic.Anthropic(api_key=api_key)
                reco   = client.messages.create(model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role":"user","content":prompt}])
                st.session_state["analyse_mkt"] = reco.content[0].text

        if "analyse_mkt" in st.session_state:
            st.markdown(st.session_state["analyse_mkt"])

# ════════════════════════════════════════════
# TAB 6 — RAPPORT FINAL
# ════════════════════════════════════════════

with tab6:
    st.header("Rapport Final de Tarification")

    manquants = [n for n, k in [("BC","resultats_bc"),("Simulation","resultats_sim"),("Market Curve","taux_mkt_final")]
                 if k not in st.session_state]
    if manquants:
        st.warning(f"⚠️ Complétez d'abord : {', '.join(manquants)}")
    else:
        ctx_r, inst_r, inp_r, out_r = prompt_inputs("rapport",
            placeholder_contexte="Ex: Négociation XYZ, objectif prime < 14M...",
            placeholder_instructions="Ex: Justifier chaque taux, comparer N-1...",
            placeholder_input="Ex: Taux N-1 : R&C=3.1%, CatL1=1.2%",
            placeholder_output="Ex: Rapport 1 page, tableau synthèse obligatoire")

        if st.button("▶ Générer le rapport final", type="primary"):
            bc_map  = {r["tranche"]: r for r in st.session_state["resultats_bc"]}
            sim_map = {r["tranche"]: r for r in st.session_state["resultats_sim"]}
            mkt_map = {r["tranche"]: r["taux"] for r in st.session_state["taux_mkt_final"]}

            rows_rapport = []; prime_totale = 0
            for t in tranches_input:
                nom = t["nom"]
                bc_tt  = bc_map.get(nom,{}).get("taux_technique",0)
                sim_tt = sim_map.get(nom,{}).get("taux_technique",0)
                mkt    = mkt_map.get(nom, 0)
                if t["type"] == "travaillante":
                    ecart = abs(bc_tt-sim_tt)/bc_tt*100 if bc_tt > 0 else 0
                    taux_retenu = sim_tt
                    methode = f"Simulation (écart BC/Sim: {ecart:.0f}%) {'⚠️' if ecart>25 else '✅'}"
                else:
                    taux_retenu = max(sim_tt, mkt)
                    methode = "Simulation" if sim_tt >= mkt else "Marché"
                prime = gnpi * taux_retenu; prime_totale += prime
                rows_rapport.append({"Tranche":nom,"Type":t["type"],
                    "Taux BC":f"{bc_tt:.4%}","Taux Sim.":f"{sim_tt:.4%}","Taux Marché":f"{mkt:.4%}",
                    "Taux retenu":f"{taux_retenu:.4%}","Prime (MAD)":f"{prime:,.0f}","Méthode":methode})

            st.session_state["df_rapport"]   = pd.DataFrame(rows_rapport)
            st.session_state["prime_totale"] = prime_totale

            if api_key:
                with st.spinner("Claude rédige le rapport..."):
                    prompt = build_prompt(
                        role="Expert senior tarification réassurance XL, marchés émergents automobile.",
                        task="""Rapport professionnel :
1. SYNTHÈSE EXÉCUTIVE (5 lignes)
2. ANALYSE PAR TRANCHE [Obs→Anal→Concl]
3. COHÉRENCE INTER-MÉTHODES
4. ANOMALIES & POINTS D'ATTENTION
5. TABLEAU RÉCAPITULATIF
6. RECOMMANDATION GLOBALE""",
                        data=f"""Rapport : {json.dumps(rows_rapport, indent=2)}
BC : {json.dumps([{k:v for k,v in r.items() if k!='detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}
Simulation : {json.dumps(st.session_state['resultats_sim'], indent=2)}
GNPI : {gnpi:,} MAD | Prime totale : {prime_totale:,.0f} MAD | Taux global : {prime_totale/gnpi:.4%}""",
                        contexte=ctx_r, instructions=inst_r,
                        input_data=inp_r, output_instructions=out_r,
                        contexte_global=st.session_state.get("instructions_globales",""),
                        contraintes="- Ne pas recommander taux < taux pur\n- BC=0 cat = normal\n- Ne pas inventer comparatifs"
                    )
                    client = anthropic.Anthropic(api_key=api_key)
                    reco   = client.messages.create(model="claude-opus-4-5", max_tokens=2500,
                        messages=[{"role":"user","content":prompt}])
                    st.session_state["reco_finale"] = reco.content[0].text

    if "df_rapport" in st.session_state:
        st.dataframe(st.session_state["df_rapport"], use_container_width=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Prime totale", f"{st.session_state['prime_totale']:,.0f} MAD")
        c2.metric("📊 Taux global",  f"{st.session_state['prime_totale']/gnpi:.4%}")
        c3.metric("📋 Tranches",     len(tranches_input))

    if "reco_finale" in st.session_state:
        st.divider()
        st.subheader("🤖 Rapport Claude")
        st.markdown(st.session_state["reco_finale"])

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
        st.dataframe(pd.DataFrame([
            {"Email": e, "Code": c, "Statut": "✅ Actif"}
            for e, c in users.items()
        ]), use_container_width=True)

        st.divider()
        st.markdown("#### ➕ Gérer les utilisateurs")
        st.info("""**Pour ajouter/modifier des utilisateurs :**

1. Allez sur **Streamlit Cloud** → votre app → **Settings** → **Secrets**
2. Ajoutez dans la section `[users]` :
```toml
[users]
"email@exemple.com" = "CODE_UNIQUE"
"autre@email.com"   = "AUTRE_CODE"
```
3. Pour le mot de passe admin :
```toml
admin_password = "VotreMotDePasseAdmin"
```
4. Sauvegardez — l'app se recharge automatiquement.""")

        st.divider()
        st.markdown("#### 🎲 Générateur de code aléatoire")
        col1, col2 = st.columns(2)
        with col1:
            email_new = st.text_input("Email du nouvel utilisateur", key="new_email")
        with col2:
            if st.button("Générer un code"):
                code_gen = secrets_lib.token_hex(4).upper()
                st.session_state["generated_code"] = code_gen

        if "generated_code" in st.session_state:
            st.success(f"Code généré : **{st.session_state['generated_code']}**")
            if email_new:
                st.code(f'"{email_new}" = "{st.session_state["generated_code"]}"')
                st.caption("Copiez cette ligne dans vos Secrets Streamlit et communiquez le code à l'utilisateur.")

    elif admin_pwd:
        st.error("❌ Mot de passe incorrect")
