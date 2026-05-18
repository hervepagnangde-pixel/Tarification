import streamlit as st
import anthropic
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import json

st.set_page_config(page_title="Agent Tarification Réassurance", layout="wide")
st.title("Atarificatairé")

# ─── SIDEBAR ───
st.sidebar.header("⚙️ Configuration")
api_key = st.sidebar.text_input("Clé API Claude", type="password")
gnpi    = st.sidebar.number_input("GNPI (MAD)", value=183_000_000, step=1_000_000)

# ─── PROGRAMME ───
st.header("📋 Programme de Réassurance")
nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)

tranches_input = []
for i in range(nb_tranches):
    st.markdown(f"**Tranche {i+1}**")
    c1, c2, c3 = st.columns(3)
    with c1:
        nom      = st.text_input("Nom",       value=f"Tranche {i+1}", key=f"nom_{i}")
        type_t   = st.selectbox("Type",       ["travaillante","non_travaillante","cat"], key=f"type_{i}")
        priorite = st.number_input("Priorité",value=2_000_000,  step=500_000, key=f"prio_{i}")
        portee   = st.number_input("Portée",  value=13_000_000, step=500_000, key=f"port_{i}")
    with c2:
        st.markdown("**Conditions**")
        has_aal = st.checkbox("AAL", key=f"aal_{i}")
        aal_val = st.number_input("Montant AAL", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
        has_aad = st.checkbox("AAD", key=f"aad_{i}")
        aad_val = st.number_input("Montant AAD", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
    with c3:
        st.markdown("**Frais & Reconstitutions**")
        nb_recon     = st.number_input("Nb reconstitutions",    value=1,   min_value=0, max_value=5,   key=f"recon_{i}")
        tx_recon     = st.number_input("Taux reconstitution %", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
        has_indices  = st.checkbox("Indices", key=f"idx_{i}")
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
    st.divider()

if st.button("📊 Résumé programme"):
    st.session_state["tranches_input"] = tranches_input
    st.session_state["df_prog"] = pd.DataFrame([{
        "Tranche": t["nom"], "Type": t["type"],
        "Priorité": f"{t['priorite']:,}", "Portée": f"{t['portee']:,}",
        "AAL": t["AAL"] or "—", "AAD": t["AAD"] or "—",
        "Reconst.": f"{t['nb_reconstitutions']} x {t['taux_reconstitution']}%",
        "Brokage": f"{t['brokage']:.0%}", "Marge": f"{t['marge']:.0%}"
    } for t in tranches_input])

if "df_prog" in st.session_state:
    st.dataframe(st.session_state["df_prog"], use_container_width=True)

# ─── DONNÉES DE BASE ───
st.header("📂 Données de base")
c1, c2, c3 = st.columns(3)
with c1: f_triangle = st.file_uploader("Triangle développement", type=["xlsx","csv"])
with c2: f_gnpis    = st.file_uploader("Base GNPIs",             type=["xlsx","csv"])
with c3: f_indices  = st.file_uploader("Table indices",          type=["xlsx","csv"])

annee_cotation = st.number_input("Année de cotation", value=2026, step=1)

if st.button("▶ Transformer le triangle") and f_triangle and f_gnpis and f_indices:
    with st.spinner("Transformation en cours..."):

        df_gnpis_df = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx')   else pd.read_csv(f_gnpis)
        df_idx_df   = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)
        df_gnpis_df.columns = [c.strip() for c in df_gnpis_df.columns]
        df_idx_df.columns   = [c.strip() for c in df_idx_df.columns]

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

        # ── Indices ──
        df_idx_set = df_idx_df.set_index('Annee')['Coefficients']
        def get_indice(annee):
            try: return float(df_idx_set[annee])
            except: return 1.0

        # ── As-If ──
        df_liq['annee_ultime'] = df_liq['annee_surv'] + 9
        df_liq['I_ultime']     = df_liq['annee_ultime'].apply(get_indice)
        df_liq['I_reg']        = df_liq['annee_reg'].apply(get_indice)
        df_liq['I_surv']       = df_liq['annee_surv'].apply(get_indice)
        df_liq['total_asif']   = df_liq['total'] * (df_liq['I_ultime'] / df_liq['I_reg'])

        # ── Stabilisation ──
        df_liq['ratio_stab'] = df_liq['I_reg'] / df_liq['I_surv']
        df_liq['total_stab'] = np.where(
            (df_liq['ratio_stab'] - 1) > 0.10,
            df_liq['total'] * (df_liq['I_surv'] / df_liq['I_reg']),
            df_liq['total']
        )

        # ── Chain Ladder sur total_stab ──
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

        # ── Projection sur total_stab ──
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

        # ── Estimation alpha & lambda ──
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

        # ── Coefficients stabilisation ──
        coeffs_raw = df_liq['total_stab'].values / df_liq['total'].values
        coeffs     = coeffs_raw[(coeffs_raw > 0) & np.isfinite(coeffs_raw)]

        # ── Sauvegarder ──
        st.session_state["df_liq"]      = df_liq
        st.session_state["df_proj"]     = df_proj
        st.session_state["f_moyens"]    = f_moyens
        st.session_state["alpha_est"]   = float(alpha_est)
        st.session_state["lambda_est"]  = float(lambda_est)
        st.session_state["seuil_est"]   = float(seuil)
        st.session_state["coeffs"]      = coeffs
        st.session_state["df_gnpis_df"] = df_gnpis_df
        st.session_state["df_facteurs"] = pd.DataFrame({
            'Développement'  : [f"{k}→{k+1}" for k in range(9)],
            'Facteur moyen'  : [round(f_moyens[k], 4) for k in range(9)],
            'Nb observations': [len(facteurs[k]) for k in range(9)]
        })

if "df_liq" in st.session_state:
    st.success(f"✅ {len(st.session_state['df_liq'])} observations — {st.session_state['df_liq']['sinistre_id'].nunique()} sinistres")
    with st.expander("Triangle de liquidation"):
        st.dataframe(st.session_state["df_liq"][['sinistre_id','annee_surv','annee_reg','dev','total','total_asif','total_stab']].head(30))
    with st.expander("Facteurs Chain Ladder"):
        st.dataframe(st.session_state["df_facteurs"])
    with st.expander("Projections"):
        st.dataframe(st.session_state["df_proj"].head(20))

# ─── BURNING COST ───
st.header("🔥 Burning Cost")

if "df_proj" in st.session_state and st.button("▶ Calculer le Burning Cost"):
    with st.spinner("Calcul BC en cours..."):
        df_proj     = st.session_state["df_proj"]
        resultats_bc = []

        for t_info in tranches_input:
            D   = t_info["priorite"]
            P   = t_info["portee"]
            aal = t_info["AAL"]
            aad = t_info["AAD"]
            r   = t_info["nb_reconstitutions"]
            cap = (r + 1) * P

            # Charge par sinistre
            df_proj['charge_sin'] = df_proj['total_ultime_stab'].apply(
                lambda x: min(max(x - D, 0), P)
            )

            # Charge annuelle
            charges_ann = df_proj.groupby('annee_surv')['charge_sin'].sum()
            charges_finales = []
            for ann, ch in charges_ann.items():
                if aad: ch = max(ch - aad, 0)
                if aal: ch = min(ch, aal)
                ch = min(ch, cap)
                charges_finales.append({'annee': ann, 'charge': ch})

            df_ch      = pd.DataFrame(charges_finales)
            charge_moy = df_ch['charge'].mean()
            taux_pur   = charge_moy / gnpi
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
    st.subheader("📊 Résultats Burning Cost")
    st.dataframe(pd.DataFrame([{
        "Tranche"       : r["tranche"],
        "Charge moy."   : f"{r['charge_moy']:,.0f}",
        "Taux pur"      : f"{r['taux_pur']:.4%}",
        "Taux risque"   : f"{r['taux_risque']:.4%}",
        "Taux technique": f"{r['taux_technique']:.4%}",
        "Taux final"    : f"{r['taux_final']:.4%}",
    } for r in st.session_state["resultats_bc"]]), use_container_width=True)

    if api_key and st.button("🤖 Recommandations Claude — Burning Cost"):
        with st.spinner("Claude analyse le BC..."):
            client  = anthropic.Anthropic(api_key=api_key)
            analyse = client.messages.create(
                model="claude-opus-4-5", max_tokens=1500,
                messages=[{"role":"user","content":f"""Expert réassurance non-proportionnelle.
Analyse ces résultats de Burning Cost par tranche.
Pour chaque tranche : commente le niveau du taux, signale les anomalies,
vérifie la cohérence entre tranches.
Résultats BC : {json.dumps([{k:v for k,v in r.items() if k != 'detail_annuel'} for r in st.session_state['resultats_bc']], indent=2)}
Tranches : {json.dumps(tranches_input, indent=2)}"""}]
            )
            st.session_state["analyse_bc"] = analyse.content[0].text

    if "analyse_bc" in st.session_state:
        st.subheader("🤖 Analyse Claude — Burning Cost")
        st.markdown(st.session_state["analyse_bc"])

# ─── SIMULATION ───
st.header("🎲 Simulation")

if "alpha_est" in st.session_state:
    st.info(f"Seuil P85 : {st.session_state['seuil_est']:,.0f} | Alpha : {st.session_state['alpha_est']:.4f} | Lambda : {st.session_state['lambda_est']:.4f}")
    c1, c2, c3, c4 = st.columns(4)
    with c1: alpha_final  = st.number_input("Alpha",          value=st.session_state["alpha_est"],  step=0.01,     format="%.4f", key="alpha_input")
    with c2: lambda_final = st.number_input("Lambda",         value=st.session_state["lambda_est"], step=0.1,      format="%.4f", key="lambda_input")
    with c3: seuil_final  = st.number_input("Seuil",          value=st.session_state["seuil_est"],  step=50_000.0, format="%.0f", key="seuil_input")
    with c4: n_sim        = st.number_input("Nb simulations", value=10000, step=1000,                               key="nsim_input")

if "coeffs" in st.session_state and st.button("▶ Lancer la simulation"):
    with st.spinner("Simulation en cours..."):

        alpha_final  = st.session_state["alpha_input"]
        lambda_final = st.session_state["lambda_input"]
        seuil_final  = st.session_state["seuil_input"]
        n_sim        = int(st.session_state["nsim_input"])
        coeffs       = st.session_state["coeffs"]
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
                "tranche"       : t_info["nom"],  "type": t_info["type"],
                "taux_pur"      : tp,  "taux_risque"   : tr,
                "taux_technique": tt,  "taux_final"    : tf,
                "sans_aal"      : tt2, "sans_aad"      : tt3, "sans_rec": tt4,
            })

        st.session_state["resultats_sim"] = resultats_sim

if "resultats_sim" in st.session_state:
    st.subheader("📊 Résultats simulation")
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

    if api_key and st.button("🤖 Analyser conditions avec Claude"):
        with st.spinner("Claude analyse..."):
            client  = anthropic.Anthropic(api_key=api_key)
            analyse = client.messages.create(
                model="claude-opus-4-5", max_tokens=1500,
                messages=[{"role":"user","content":f"""Expert réassurance non-proportionnelle.
Compare taux technique base vs sans AAL vs sans AAD vs sans reconstitution.
Écart faible → inutile. Significatif → nécessaire. Intermédiaire → à ajuster.
Résultats : {json.dumps(st.session_state['resultats_sim'], indent=2)}
Tranches : {json.dumps(tranches_input, indent=2)}"""}]
            )
            st.session_state["analyse_sim"] = analyse.content[0].text

    if "analyse_sim" in st.session_state:
        st.subheader("🤖 Analyse Claude des conditions")
        st.markdown(st.session_state["analyse_sim"])

# ─── MARKET CURVE ───
st.header("📈 Market Curve")
f_mkt = st.file_uploader("Données marché", type=["xlsx","csv"])

if f_mkt and st.button("▶ Construire la market curve"):
    df_mkt = pd.read_excel(f_mkt) if f_mkt.name.endswith('xlsx') else pd.read_csv(f_mkt)

    # Nettoyage
    for col in ['ROLs','midpoints','Garantie en MAD','Priorité en MAD']:
        if col in df_mkt.columns and df_mkt[col].dtype == object:
            df_mkt[col] = df_mkt[col].str.replace('%','').str.replace(' ','').str.replace(',','.').astype(float)

    # Filtrer atypiques
    df_mkt = df_mkt[(df_mkt['ROLs'] > 0) & (df_mkt['ROLs'] <= 1)].copy()
    df_mkt = df_mkt[df_mkt['midpoints'] > 0].copy()

    def fit_log_log(x, y):
        """Régression log(ROL) = a*log(midpoints) + b"""
        log_x  = np.log(x)
        log_y  = np.log(y)
        coeffs = np.polyfit(log_x, log_y, 1)
        a, b   = coeffs[0], coeffs[1]
        log_y_pred = np.polyval(coeffs, log_x)
        ss_res = np.sum((log_y - log_y_pred)**2)
        ss_tot = np.sum((log_y - np.mean(log_y))**2)
        r2     = 1 - ss_res/ss_tot
        return a, b, r2

    def predict_rol(midpoint, a, b):
        return np.exp(b) * (midpoint ** a)

    # 10 combinaisons de quantiles
    quantiles     = [0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,1.0]
    resultats_mkt = []

    for q in quantiles:
        mid_max  = np.quantile(df_mkt['midpoints'],      q)
        port_max = np.quantile(df_mkt['Garantie en MAD'], q)
        df_q     = df_mkt[(df_mkt['midpoints'] <= mid_max) & (df_mkt['Garantie en MAD'] <= port_max)]

        if len(df_q) < 5: continue

        x = df_q['midpoints'].values
        y = df_q['ROLs'].values

        try:
            a, b, r2 = fit_log_log(x, y)

            # Taux pour nos tranches
            taux_tranches = []
            for t in tranches_input:
                # midpoint de la tranche = priorité + portée/2
                mid_t = t['priorite'] + t['portee'] / 2
                rol   = predict_rol(mid_t, a, b)
                taux  = rol * (t['portee'] / gnpi)
                taux_tranches.append({
                    "tranche": t["nom"],
                    "type"   : t["type"],
                    "rol"    : rol,
                    "taux"   : taux
                })

            # Score optimal : R² élevé + taux pas trop extrêmes
            taux_vals   = [tt["taux"] for tt in taux_tranches]
            median_taux = np.median(taux_vals)
            cv_taux     = np.std(taux_vals) / median_taux if median_taux > 0 else 99

            # Taux médian de toutes les combinaisons (sera mis à jour après)
            resultats_mkt.append({
                "quantile"     : q,
                "n_points"     : len(df_q),
                "a"            : a,
                "b"            : b,
                "r2"           : r2,
                "cv_taux"      : cv_taux,
                "taux_tranches": taux_tranches
            })
        except:
            continue

    # Score optimal : R² normalisé - écart vs médiane normalisé
    if resultats_mkt:
        all_taux   = [[tt["taux"] for tt in r["taux_tranches"]] for r in resultats_mkt]
        med_global = np.median([t for sublist in all_taux for t in sublist])
        r2_vals    = [r["r2"] for r in resultats_mkt]
        r2_min, r2_max = min(r2_vals), max(r2_vals)

        for r in resultats_mkt:
            taux_moy   = np.mean([tt["taux"] for tt in r["taux_tranches"]])
            ecart_med  = abs(taux_moy - med_global) / med_global if med_global > 0 else 0
            r2_norm    = (r["r2"] - r2_min) / (r2_max - r2_min + 1e-10)
            r["score"] = 0.5 * r2_norm - 0.3 * ecart_med - 0.2 * r["cv_taux"]

        resultats_mkt = sorted(resultats_mkt, key=lambda x: x['score'], reverse=True)

    st.session_state["resultats_mkt"] = resultats_mkt
    st.session_state["df_mkt_clean"]  = df_mkt

if "resultats_mkt" in st.session_state:
    resultats_mkt = st.session_state["resultats_mkt"]
    df_mkt_clean  = st.session_state["df_mkt_clean"]

    # Tableau récapitulatif
    rows_recap = []
    for r in resultats_mkt:
        row = {
            "Quantile" : f"Q{int(r['quantile']*100)}",
            "N pts"    : r["n_points"],
            "a"        : f"{r['a']:.4f}",
            "b"        : f"{r['b']:.4f}",
            "R²"       : f"{r['r2']:.4f}",
            "Score"    : f"{r['score']:.4f}",
        }
        for tt in r["taux_tranches"]:
            row[tt["tranche"]] = f"{tt['taux']:.4%}"
        rows_recap.append(row)

    st.subheader("📊 Comparaison des ajustements")
    st.dataframe(pd.DataFrame(rows_recap), use_container_width=True)

    best = resultats_mkt[0]
    st.success(f"✅ Meilleur score : Q{int(best['quantile']*100)} — R²={best['r2']:.4f} | Score={best['score']:.4f}")

    choix_q   = st.selectbox(
        "Choisir la combinaison",
        options=[f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in resultats_mkt],
        index=0
    )
    idx_choix = [f"Q{int(r['quantile']*100)} — R²={r['r2']:.4f} | Score={r['score']:.4f}" for r in resultats_mkt].index(choix_q)
    choix     = resultats_mkt[idx_choix]

    # Graphique
    x_all   = df_mkt_clean['midpoints'].values
    y_all   = df_mkt_clean['ROLs'].values
    x_range = np.linspace(min(x_all), max(x_all), 300)
    y_fit   = np.exp(choix['b']) * (x_range ** choix['a'])

    fig, ax = plt.subplots(figsize=(10,5))
    ax.scatter(x_all, y_all, color='orange', s=60, zorder=5, label='Données marché')
    ax.plot(x_range, y_fit, color='red', lw=2,
            label=f"log(ROL)={choix['a']:.3f}×log(mid)+{choix['b']:.3f} | R²={choix['r2']:.4f}")
    ax.set_xlabel('Midpoints'); ax.set_ylabel('ROL')
    ax.set_title('Market Curve — Modèle log-log')
    ax.legend(); ax.grid(alpha=0.3)
    st.pyplot(fig)

    st.subheader("📊 Taux marché retenus")
    st.dataframe(pd.DataFrame([{
        "Tranche"    : tt["tranche"],
        "Type"       : tt["type"],
        "ROL estimé" : f"{tt['rol']:.4%}",
        "Taux marché": f"{tt['taux']:.4%}"
    } for tt in choix["taux_tranches"]]), use_container_width=True)

    st.session_state["taux_mkt_final"] = choix["taux_tranches"]

    if api_key and st.button("🤖 Analyse Claude market curve"):
        client = anthropic.Anthropic(api_key=api_key)
        reco   = client.messages.create(
            model="claude-opus-4-5", max_tokens=1000,
            messages=[{"role":"user","content":f"""Expert réassurance.
Analyse ces ajustements market curve et recommande le meilleur.
Tiens compte du R², score optimal, nombre de points et cohérence des taux.
Modèle : log(ROL) = a×log(midpoints) + b
Ajustements : {json.dumps(rows_recap, indent=2)}
Tranches : {json.dumps(tranches_input, indent=2)}"""}]
        )
        st.session_state["analyse_mkt"] = reco.content[0].text

    if "analyse_mkt" in st.session_state:
        st.subheader("🤖 Recommandation Claude")
        st.markdown(st.session_state["analyse_mkt"])

# ─── RAPPORT FINAL ───
st.header("📋 Rapport Final")

if all(k in st.session_state for k in ["resultats_bc","resultats_sim","taux_mkt_final"]):
    if st.button("▶ Générer le rapport final"):
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
            with st.spinner("Claude génère les recommandations finales..."):
                client      = anthropic.Anthropic(api_key=api_key)
                reco_finale = client.messages.create(
                    model="claude-opus-4-5", max_tokens=2000,
                    messages=[{"role":"user","content":f"""Expert réassurance non-proportionnelle automobile.
Analyse ce rapport de tarification final.
Pour chaque tranche : valide ou questionne le taux retenu, signale les anomalies,
compare les méthodes, donne une recommandation finale.
Rapport : {json.dumps(rows_rapport, indent=2)}
GNPI : {gnpi:,} MAD"""}]
                )
                st.session_state["reco_finale"] = reco_finale.content[0].text

if "df_rapport" in st.session_state:
    st.subheader("📊 Synthèse de tarification")
    st.dataframe(st.session_state["df_rapport"], use_container_width=True)
    c1, c2 = st.columns(2)
    with c1: st.metric("Prime totale", f"{st.session_state['prime_totale']:,.0f} MAD")
    with c2: st.metric("Taux global",  f"{st.session_state['prime_totale']/gnpi:.4%}")

if "reco_finale" in st.session_state:
    st.subheader("🤖 Recommandations finales Claude")
    st.markdown(st.session_state["reco_finale"])
