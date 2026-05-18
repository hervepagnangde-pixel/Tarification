import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.stats import pareto
import json

st.set_page_config(page_title="Agent Tarification Réassurance", layout="wide")
st.title("🎯 Agent Tarification Réassurance Non-Proportionnelle")

# ─── SIDEBAR ───
st.sidebar.header("⚙️ Configuration")
api_key = st.sidebar.text_input("Clé API Claude", type="password")
gnpi = st.sidebar.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000)

# ─── FORMULAIRE PROGRAMME ───
st.header("📋 Programme de Réassurance")
nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)

tranches_input = []
for i in range(nb_tranches):
    st.markdown(f"**Tranche {i+1}**")
    col1, col2, col3 = st.columns(3)
    with col1:
        nom      = st.text_input("Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
        type_t   = st.selectbox("Type", ["travaillante","non_travaillante","cat"], key=f"type_{i}")
        priorite = st.number_input("Priorité (MAD)", value=2_000_000, step=500_000, key=f"prio_{i}")
        portee   = st.number_input("Portée/Limite (MAD)", value=13_000_000, step=500_000, key=f"port_{i}")
    with col2:
        st.markdown("**Conditions**")
        has_aal = st.checkbox("AAL", key=f"aal_{i}")
        aal_val = st.number_input("Montant AAL (MAD)", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
        has_aad = st.checkbox("AAD", key=f"aad_{i}")
        aad_val = st.number_input("Montant AAD (MAD)", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
    with col3:
        st.markdown("**Reconstitutions & Frais**")
        nb_recon    = st.number_input("Nb reconstitutions", value=1, min_value=0, max_value=5, key=f"recon_{i}")
        tx_recon    = st.number_input("Taux reconstitution (%)", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
        has_indices = st.checkbox("Indices", key=f"idx_{i}")
        brokage     = st.number_input("Brokage (%)", value=10, min_value=0, max_value=30, key=f"brok_{i}")
        frais       = st.number_input("Frais généraux (%)", value=5, min_value=0, max_value=20, key=f"frais_{i}")
        marge       = st.number_input("Marge (%)", value=10, min_value=0, max_value=30, key=f"marge_{i}")
        retrocession = st.number_input("Rétrocession (%)", value=0, min_value=0, max_value=50, key=f"retro_{i}")

    tranches_input.append({
        "numero": i+1, "nom": nom, "type": type_t,
        "priorite": priorite, "portee": portee,
        "AAL": aal_val if has_aal else None,
        "AAD": aad_val if has_aad else None,
        "nb_reconstitutions": nb_recon,
        "taux_reconstitution": tx_recon,
        "indices": has_indices,
        "brokage": brokage/100,
        "frais": frais/100,
        "marge": marge/100,
        "retrocession": retrocession/100
    })
    st.divider()

if st.button("📊 Voir résumé du programme"):
    df_prog = pd.DataFrame([{
        "Tranche": t["nom"], "Type": t["type"],
        "Priorité": f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
        "AAL": t["AAL"] or "—", "AAD": t["AAD"] or "—",
        "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
        "Indices": "✅" if t["indices"] else "—",
        "Brokage": f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}"
    } for t in tranches_input])
    st.dataframe(df_prog, use_container_width=True)

# ─── SIMULATION ───
st.header("🎲 Simulation")

st.subheader("📂 Données de base")
col1, col2, col3 = st.columns(3)
with col1:
    f_triangle = st.file_uploader("Triangle de développement", type=["xlsx","csv"])
with col2:
    f_gnpis = st.file_uploader("Base GNPIs (Annee, GNPI)", type=["xlsx","csv"])
with col3:
    f_indices = st.file_uploader("Table indices (Annee, Coefficients)", type=["xlsx","csv"])

annee_cotation = st.number_input("Année de cotation", value=2026, step=1)

if f_triangle and f_gnpis and f_indices:

    df_gnpis = pd.read_excel(f_gnpis) if f_gnpis.name.endswith('xlsx') else pd.read_csv(f_gnpis)
    df_idx   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
    df_gnpis.columns = [c.strip() for c in df_gnpis.columns]
    df_idx.columns   = [c.strip() for c in df_idx.columns]

    # Nettoyer virgules
    for col in df_gnpis.columns:
        if df_gnpis[col].dtype == object:
            df_gnpis[col] = df_gnpis[col].str.replace(',','.').astype(float)

    st.success("✅ Fichiers chargés")

    st.subheader("🔄 Transformation en triangle de liquidation")

    if st.button("▶ Transformer le triangle"):
        with st.spinner("Transformation en cours..."):

            # ── 1. Lire le triangle brut ──
            df_raw = pd.read_excel(f_triangle, header=None)
            ligne_annees = df_raw.iloc[0].tolist()
            ligne_types  = df_raw.iloc[1].tolist()

            # Construire col_info : (annee_reglement, type) par colonne
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

            # Données sinistres à partir ligne 2
            df_data = df_raw.iloc[2:].reset_index(drop=True)
            df_data.iloc[:, 0] = df_data.iloc[:, 0].ffill()

            # ── 2. Extraire TOTAL par sinistre × année règlement ──
            records = []
            for idx_row, row in df_data.iterrows():
                try:
                    annee_surv = int(float(str(row.iloc[0])))
                    if not (2010 <= annee_surv <= 2035):
                        continue
                except:
                    continue

                sinistre_id = f"{annee_surv}_{idx_row}"

                for col_idx, (annee_reg, typ) in enumerate(col_info):
                    if typ != 'TOTAL':
                        continue
                    if annee_reg is None:
                        continue
                    val = row.iloc[col_idx]
                    try:
                        if isinstance(val, str):
                            val = val.strip().replace(',','.').replace(' ','')
                            if any(c.isalpha() for c in val) or '#' in val:
                                continue
                        val = float(val)
                        if val <= 0 or np.isnan(val):
                            continue
                    except:
                        continue

                    dev = annee_reg - annee_surv
                    if dev < 0 or dev > 9:
                        continue

                    records.append({
                        'sinistre_id': sinistre_id,
                        'annee_surv' : annee_surv,
                        'annee_reg'  : annee_reg,
                        'dev'        : dev,
                        'total'      : val
                    })

            df_liq = pd.DataFrame(records)

            if df_liq.empty:
                st.error("❌ Triangle vide. Vérifiez le format.")
                st.stop()

            st.success(f"✅ {len(df_liq)} observations — {df_liq['sinistre_id'].nunique()} sinistres")
            with st.expander("Aperçu triangle de liquidation"):
                st.dataframe(df_liq.head(30))

            # ── 3. As-If sur chaque paiement ──
            st.write("**Calcul As-If par paiement...**")

            df_idx_set = df_idx.set_index('Annee')['Coefficients']

            def get_indice(annee):
                try:
                    return float(df_idx_set[annee])
                except:
                    return 1.0

            df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
            df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
            df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
            df_liq['total_asif']   = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

            with st.expander("Aperçu As-If par paiement"):
                st.dataframe(df_liq[['sinistre_id','annee_surv','annee_reg',
                                     'dev','total','I_ultime','I_reg','total_asif']].head(20))

            # ── 4. Chain Ladder individuel sur total_asif ──
            st.write("**Calcul coefficients Chain Ladder individuels (As-If)...**")

            facteurs = {k: [] for k in range(9)}
            for sin_id, grp in df_liq.groupby('sinistre_id'):
                grp = grp.sort_values('dev').set_index('dev')
                for k in range(9):
                    if k in grp.index and (k+1) in grp.index:
                        t_k  = grp.loc[k,   'total_asif']
                        t_k1 = grp.loc[k+1, 'total_asif']
                        if t_k > 0:
                            f = t_k1 / t_k
                            if 0.9 <= f <= 2.5:
                                facteurs[k].append(f)

            f_moyens = {k: np.mean(facteurs[k]) if facteurs[k] else 1.0 for k in range(9)}

            df_facteurs = pd.DataFrame({
                'Développement'  : [f"{k}→{k+1}" for k in range(9)],
                'Facteur moyen'  : [round(f_moyens[k], 4) for k in range(9)],
                'Nb observations': [len(facteurs[k]) for k in range(9)]
            })
            st.dataframe(df_facteurs, use_container_width=True)

            # ── 5. Projection jusqu'à dev 9 ──
            st.write("**Projection As-If jusqu'à dev 9...**")

            projections = []
            for sin_id, grp in df_liq.groupby('sinistre_id'):
                grp = grp.sort_values('dev').set_index('dev')
                annee_surv        = grp['annee_surv'].iloc[0]
                dev_max           = grp.index.max()
                asif_actuel       = grp.loc[dev_max, 'total_asif']
                total_ultime_asif = asif_actuel
                for k in range(dev_max, 9):
                    total_ultime_asif *= f_moyens[k]

                projections.append({
                    'sinistre_id'      : sin_id,
                    'annee_surv'       : annee_surv,
                    'dev_max'          : dev_max,
                    'asif_actuel'      : asif_actuel,
                    'total_ultime_asif': total_ultime_asif
                })

            df_proj = pd.DataFrame(projections)
            st.success(f"✅ {len(df_proj)} sinistres projetés")

            with st.expander("Aperçu projections finales"):
                st.dataframe(df_proj.head(20))

            # ── 6. Estimation alpha et lambda ──
            st.subheader("📐 Estimation des paramètres")

            X = df_proj['total_ultime_asif'].values
            X = X[X > 0]

            seuil = np.percentile(X, 85)
            X_above = X[X >= seuil]
            t_min = np.min(X_above)
            n = len(X_above)
            alpha_est = n / np.sum(np.log(X_above / t_min))

            # Lambda As-If
            df_proj_ann = df_proj[df_proj['total_ultime_asif'] >= seuil].copy()
            N_obs = df_proj_ann.groupby('annee_surv').size()
            df_gnpis_idx = df_gnpis.set_index(df_gnpis.columns[0])
            gnpi_col = df_gnpis.columns[1]
            N_asif_vals = []
            for ann, cnt in N_obs.items():
                try:
                    gnpi_ann = float(df_gnpis_idx.loc[ann, gnpi_col])
                    N_asif_vals.append(cnt * gnpi / gnpi_ann)
                except:
                    N_asif_vals.append(cnt)
            lambda_est = float(np.mean(N_asif_vals)) if N_asif_vals else 5.0

            st.info(f"Seuil P85 : {seuil:,.0f} MAD | N sinistres : {n} | Alpha estimé : {alpha_est:.4f} | Lambda estimé : {lambda_est:.4f}")

            col1, col2, col3 = st.columns(3)
            with col1:
                alpha_final  = st.number_input("Alpha (Pareto)", value=round(float(alpha_est),4), step=0.01, format="%.4f")
            with col2:
                lambda_final = st.number_input("Lambda (Poisson)", value=round(float(lambda_est),4), step=0.1, format="%.4f")
            with col3:
                seuil_final  = st.number_input("Seuil (MAD)", value=round(float(seuil),0), step=50_000.0)

            # Coefficients stabilisation
            coeffs = (df_proj['total_ultime_asif'] / df_proj['asif_actuel']).dropna().values
            coeffs = coeffs[coeffs > 0]

            # ── 7. Simulation ──
            st.session_state["alpha_final"]  = alpha_final
            st.session_state["lambda_final"] = lambda_final
            st.session_state["seuil_final"]  = seuil_final
            st.session_state["coeffs"]       = coeffs

            if st.button("▶ Lancer la simulation"):
                alpha_final  = st.session_state.get("alpha_final", 1.5)
                lambda_final = st.session_state.get("lambda_final", 5.0)
                seuil_final  = st.session_state.get("seuil_final", 1_000_000)
                coeffs       = st.session_state.get("coeffs", np.array([1.0]))
                with st.spinner("Simulation en cours..."):
                    np.random.seed(42)
                    resultats_sim = []

                    for t_info in tranches_input:
                        D   = t_info["priorite"]
                        P   = t_info["portee"]
                        r   = t_info["nb_reconstitutions"]
                        aal = t_info["AAL"]
                        aad = t_info["AAD"]
                        cap = (r + 1) * P

                        def simuler(avec_aal, avec_aad, avec_rec):
                            charges = []
                            for _ in range(int(n_sim)):
                                N = np.random.poisson(lambda_final)
                                S_total = 0
                                if N > 0:
                                    pareto_sim = seuil_final * (np.random.uniform(size=N) ** (-1/alpha_final))
                                    idx_c = np.random.choice(len(coeffs), size=N, replace=True)
                                    for i in range(N):
                                        S0 = pareto_sim[i]
                                        c  = coeffs[idx_c[i]]
                                        if S0 <= D:         S_i = 0
                                        elif S0 <= D + P:   S_i = c * (S0 - D)
                                        else:               S_i = c * P
                                        S_total += S_i
                                ch = S_total
                                if avec_aad and aad: ch = max(ch - aad, 0)
                                if avec_aal and aal: ch = min(ch, aal)
                                charges.append(min(ch, cap) if avec_rec else ch)
                            return np.array(charges)

                        def taux(ch):
                            P0  = np.mean(ch)
                            sig = np.std(ch)
                            tp  = P0 / gnpi
                            tr  = (P0 + 0.2 * sig) / gnpi
                            tt  = tr / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                            tf  = tt * (1 + t_info["marge"] + t_info["retrocession"])
                            return tp, tr, tt, tf

                        c_base     = simuler(True,  True,  True)
                        c_sans_aal = simuler(False, True,  True)
                        c_sans_aad = simuler(True,  False, True)
                        c_sans_rec = simuler(True,  True,  False)

                        tp,  tr,  tt,  tf  = taux(c_base)
                        tp2, tr2, tt2, tf2 = taux(c_sans_aal)
                        tp3, tr3, tt3, tf3 = taux(c_sans_aad)
                        tp4, tr4, tt4, tf4 = taux(c_sans_rec)

                        resultats_sim.append({
                            "tranche"        : t_info["nom"],
                            "type"           : t_info["type"],
                            "taux_pur"       : tp,
                            "taux_risque"    : tr,
                            "taux_technique" : tt,
                            "taux_final"     : tf,
                            "sans_aal"       : tt2,
                            "sans_aad"       : tt3,
                            "sans_rec"       : tt4,
                        })

                    st.subheader("📊 Résultats simulation")
                    df_res = pd.DataFrame([{
                        "Tranche"        : r["tranche"],
                        "Taux pur"       : f"{r['taux_pur']:.4%}",
                        "Taux risque"    : f"{r['taux_risque']:.4%}",
                        "Taux technique" : f"{r['taux_technique']:.4%}",
                        "Taux final"     : f"{r['taux_final']:.4%}",
                        "Sans AAL"       : f"{r['sans_aal']:.4%}",
                        "Sans AAD"       : f"{r['sans_aad']:.4%}",
                        "Sans reconst."  : f"{r['sans_rec']:.4%}",
                    } for r in resultats_sim])
                    st.dataframe(df_res, use_container_width=True)

                    if api_key:
                        with st.spinner("Claude analyse les conditions..."):
                            client = anthropic.Anthropic(api_key=api_key)
                            analyse = client.messages.create(
                                model="claude-opus-4-5", max_tokens=1500,
                                messages=[{"role":"user","content":f"""Tu es expert en réassurance non-proportionnelle.
Pour chaque tranche compare taux technique de base vs sans AAL vs sans AAD vs sans reconstitution.
Si écart faible → condition inutile. Si écart significatif → nécessaire. Sinon → à ajuster.
Résultats : {json.dumps(resultats_sim, indent=2)}
Tranches : {json.dumps(tranches_input, indent=2)}"""}]
                            )
                            st.subheader("🤖 Analyse Claude des conditions")
                            st.markdown(analyse.content[0].text)

                    st.session_state["resultats_sim"] = resultats_sim
                    st.session_state["tranches"]      = tranches_input
                    st.success("✅ Simulation terminée !")

# ─── MARKET CURVE ───
st.header("📈 Market Curve")

f_mkt = st.file_uploader("Données marché (Excel)", type=["xlsx","csv"])

if f_mkt:
    df_mkt   = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)
    df_curve = df_mkt[['Priorité en MAD','ROLs']].dropna().copy()
    if df_curve['ROLs'].dtype == object:
        df_curve['ROLs'] = df_curve['ROLs'].str.replace('%','').astype(float)/100

    x = df_curve['Priorité en MAD'].values
    y = df_curve['ROLs'].values

    def power_model(x, a, b):
        return a * np.power(x, -b)

    params, _ = curve_fit(power_model, x, y, p0=[1, 0.5], maxfev=5000)
    a, b = params

    y_pred = power_model(x, a, b)
    residus = y - y_pred
    p25 = np.percentile(residus, 25)
    p75 = np.percentile(residus, 75)

    st.write(f"Modèle : y = {a:.5f} × x^(-{b:.4f})")

    fig, ax = plt.subplots(figsize=(10,5))
    ax.scatter(x, y, color='orange', s=60, zorder=5, label='Données marché')
    x_range = np.linspace(min(x), max(x), 300)
    ax.plot(x_range, power_model(x_range,a,b),         color='red',   lw=2,   label='Courbe centrale')
    ax.plot(x_range, power_model(x_range,a,b)+p25,     color='green', lw=1.5, linestyle='--', label='P25')
    ax.plot(x_range, power_model(x_range,a,b)+p75,     color='blue',  lw=1.5, linestyle='--', label='P75')
    ax.set_xlabel('Priorité (MAD)'); ax.set_ylabel('ROL')
    ax.set_title('Market Curve — P25 / Médiane / P75')
    ax.legend(); ax.grid(alpha=0.3)
    st.pyplot(fig)

    st.subheader("📊 Taux marché par tranche")
    rows_mkt = []
    for t in tranches_input:
        rol_c = power_model(t['priorite'], a, b)
        rol_b = max(rol_c + p25, 0)
        rol_h = rol_c + p75

        rows_mkt.append({
            "Tranche"        : t["nom"],
            "Type"           : t["type"],
            "Taux P25 (bas)" : f"{rol_b*(t['portee']/gnpi):.4%}",
            "Taux médian"    : f"{rol_c*(t['portee']/gnpi):.4%}",
            "Taux P75 (haut)": f"{rol_h*(t['portee']/gnpi):.4%}",
        })

    st.dataframe(pd.DataFrame(rows_mkt), use_container_width=True)

    if api_key:
        with st.spinner("Claude analyse la market curve..."):
            client = anthropic.Anthropic(api_key=api_key)
            analyse_mkt = client.messages.create(
                model="claude-opus-4-5", max_tokens=1000,
                messages=[{"role":"user","content":f"""Expert réassurance.
Pour chaque tranche recommande quel taux marché retenir (P25, médian ou P75) et pourquoi.
Taux marché : {json.dumps(rows_mkt, indent=2)}
Tranches : {json.dumps(tranches_input, indent=2)}"""}]
            )
            st.subheader("🤖 Recommandation Claude")
            st.markdown(analyse_mkt.content[0].text)

    st.session_state["rows_mkt"] = rows_mkt
    st.success("✅ Market curve construite !")
