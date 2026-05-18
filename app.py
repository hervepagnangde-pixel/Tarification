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
st.subheader("Définir les tranches")

nb_tranches = st.number_input("Nombre de tranches", min_value=1, max_value=10, value=3)

tranches_input = []
for i in range(nb_tranches):
    st.markdown(f"**Tranche {i+1}**")
    col1, col2, col3 = st.columns(3)
    with col1:
        nom = st.text_input(f"Nom", value=f"Tranche {i+1}", key=f"nom_{i}")
        type_t = st.selectbox(f"Type", ["travaillante", "non_travaillante", "cat"], key=f"type_{i}")
        priorite = st.number_input(f"Priorité (MAD)", value=2_000_000, step=500_000, key=f"prio_{i}")
        portee = st.number_input(f"Portée/Limite (MAD)", value=13_000_000, step=500_000, key=f"port_{i}")
    with col2:
        st.markdown("**Conditions**")
        has_aal = st.checkbox(f"AAL", key=f"aal_{i}")
        aal_val = st.number_input(f"Montant AAL (MAD)", value=0, step=100_000, key=f"aal_v_{i}", disabled=not has_aal)
        has_aad = st.checkbox(f"AAD", key=f"aad_{i}")
        aad_val = st.number_input(f"Montant AAD (MAD)", value=0, step=100_000, key=f"aad_v_{i}", disabled=not has_aad)
    with col3:
        st.markdown("**Reconstitutions & Frais**")
        nb_recon = st.number_input(f"Nb reconstitutions", value=1, min_value=0, max_value=5, key=f"recon_{i}")
        tx_recon = st.number_input(f"Taux reconstitution (%)", value=100, min_value=0, max_value=200, key=f"txrecon_{i}")
        has_indices = st.checkbox(f"Indices", key=f"idx_{i}")
        brokage = st.number_input(f"Brokage (%)", value=10, min_value=0, max_value=30, key=f"brok_{i}")
        frais = st.number_input(f"Frais généraux (%)", value=5, min_value=0, max_value=20, key=f"frais_{i}")
        marge = st.number_input(f"Marge (%)", value=10, min_value=0, max_value=30, key=f"marge_{i}")
        retrocession = st.number_input(f"Rétrocession (%)", value=0, min_value=0, max_value=50, key=f"retro_{i}")

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

# ─── SIMULATION ───
st.header("🎲 Simulation")

# Upload fichiers
st.subheader("📂 Données de base")
col1, col2, col3 = st.columns(3)
with col1:
    f_sins = st.file_uploader("Base sinistres (Annee, Sinistres)", type=["xlsx","csv"])
with col2:
    f_gnpis = st.file_uploader("Base GNPIs (Annee, GNPI)", type=["xlsx","csv"])
with col3:
    f_indices = st.file_uploader("Table indices (Annee, Coefficients)", type=["xlsx","csv"])

# Choix indice
st.subheader("⚙️ Paramètres d'indexation")
col1, col2 = st.columns(2)
with col1:
    nom_indice = st.selectbox("Type d'indice", ["IPC", "Salaires", "Autre"])
with col2:
    appliquer_sur = st.multiselect(
        "Appliquer l'indice sur",
        ["Sinistres", "GNPIs"],
        default=["Sinistres", "GNPIs"]
    )

if f_sins and f_gnpis and f_indices:

    # Lecture fichiers
    df_sins   = pd.read_excel(f_sins)   if f_sins.name.endswith('xlsx')    else pd.read_csv(f_sins)
    df_gnpis  = pd.read_excel(f_gnpis)  if f_gnpis.name.endswith('xlsx')   else pd.read_csv(f_gnpis)
    df_idx    = pd.read_excel(f_indices) if f_indices.name.endswith('xlsx') else pd.read_csv(f_indices)

    # Standardiser noms colonnes
    df_sins.columns   = [c.strip() for c in df_sins.columns]
    df_gnpis.columns  = [c.strip() for c in df_gnpis.columns]
    df_idx.columns    = [c.strip() for c in df_idx.columns]

    # Jointure indices
    if "Sinistres" in appliquer_sur:
        df_sins = df_sins.merge(df_idx, on="Annee", how="left")
        df_sins["Sinistres_asif"] = df_sins["Sinistres"] * df_sins["Coefficients"]
    else:
        df_sins["Sinistres_asif"] = df_sins["Sinistres"]

    if "GNPIs" in appliquer_sur:
        df_gnpis = df_gnpis.merge(df_idx, on="Annee", how="left")
        df_gnpis["GNPI_asif"] = df_gnpis["GNPI"] * df_gnpis["Coefficients"]
    else:
        df_gnpis["GNPI_asif"] = df_gnpis["GNPI"]

    st.success("✅ As-If calculé")

    # Aperçu
    with st.expander("Voir données As-If"):
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Sinistres As-If**")
            st.dataframe(df_sins[["Annee","Sinistres","Sinistres_asif"]].head(20))
        with col2:
            st.write("**GNPIs As-If**")
            st.dataframe(df_gnpis[["Annee","GNPI","GNPI_asif"]])

    # ── Estimation paramètres ──
    st.subheader("📐 Estimation des paramètres")

    X = df_sins["Sinistres_asif"].dropna().values
    X = X[X > 0]

    # Seuil automatique (percentile 85)
    seuil = np.percentile(X, 85)

    # Alpha (estimateur MLE/Hill)
    X_above = X[X >= seuil]
    t = np.min(X_above)
    n = len(X_above)
    alpha_est = n / np.sum(np.log(X_above / t))

    # Lambda (Poisson As-If)
    N_obs = df_sins[df_sins["Sinistres_asif"] >= seuil].groupby("Annee").size()
    df_gnpis_idx = df_gnpis.set_index("Annee")
    N_asif = N_obs * (gnpi / df_gnpis_idx.loc[N_obs.index, "GNPI_asif"])
    lambda_est = float(N_asif.mean())

    # Affichage + correction manuelle
    st.info(f"Seuil automatique (P85) : {seuil:,.0f} MAD | N sinistres au-dessus : {n}")

    col1, col2, col3 = st.columns(3)
    with col1:
        alpha_final = st.number_input(
            "Alpha (Pareto)",
            value=round(float(alpha_est), 4),
            step=0.01, format="%.4f"
        )
    with col2:
        lambda_final = st.number_input(
            "Lambda (Poisson)",
            value=round(float(lambda_est), 4),
            step=0.1, format="%.4f"
        )
    with col3:
        seuil_final = st.number_input(
            "Seuil (MAD)",
            value=round(float(seuil), 0),
            step=50_000.0
        )

    # ── Simulation ──
    st.subheader("🚀 Lancer la simulation")
    n_sim = st.number_input("Nombre de simulations", value=10000, step=1000)

    # Coefficients stabilisation
    coeffs = (df_sins["Sinistres_asif"] / df_sins["Sinistres"]).dropna().values
    coeffs = coeffs[coeffs > 0]

    if st.button("▶ Lancer la simulation"):
        with st.spinner("Simulation en cours..."):

            np.random.seed(42)
            resultats_sim = []

            for t_info in tranches_input:
                D  = t_info["priorite"]
                P  = t_info["portee"]
                r  = t_info["nb_reconstitutions"]
                aal = t_info["AAL"]
                aad = t_info["AAD"]
                cap = (r + 1) * P

                charges = []
                charges_sans_aal = []
                charges_sans_aad = []
                charges_sans_rec = []

                for _ in range(int(n_sim)):
                    N = np.random.poisson(lambda_final)
                    S_total = 0
                    if N > 0:
                        pareto_sim = seuil_final * (np.random.uniform(size=N) ** (-1/alpha_final))
                        idx_coeffs = np.random.choice(len(coeffs), size=N, replace=True)
                        for i in range(N):
                            coeff_i = coeffs[idx_coeffs[i]]
                            S0 = pareto_sim[i]
                            if S0 <= D:
                                S_i = 0
                            elif S0 <= D + P:
                                S_i = coeff_i * (S0 - D)
                            else:
                                S_i = coeff_i * P
                            S_total += S_i

                    # Avec toutes conditions
                    c = S_total
                    if aad: c = max(c - aad, 0)
                    if aal: c = min(c, aal)
                    charges.append(min(c, cap))

                    # Sans AAL
                    c2 = S_total
                    if aad: c2 = max(c2 - aad, 0)
                    charges_sans_aal.append(min(c2, cap))

                    # Sans AAD
                    c3 = S_total
                    if aal: c3 = min(c3, aal)
                    charges_sans_aad.append(min(c3, cap))

                    # Sans reconstitution
                    c4 = S_total
                    if aad: c4 = max(c4 - aad, 0)
                    if aal: c4 = min(c4, aal)
                    charges_sans_rec.append(c4)

                # Calcul taux
                def calcul_taux(ch):
                    arr = np.array(ch)
                    P0  = np.mean(arr)
                    sig = np.std(arr)
                    taux_pur  = P0 / gnpi
                    taux_risq = (P0 + 0.2 * sig) / gnpi
                    taux_tech = taux_risq / (1 - t_info["brokage"] - t_info["frais"] - 0.0021)
                    taux_fin  = taux_tech * (1 + t_info["marge"] + t_info["retrocession"])
                    return taux_pur, taux_risq, taux_tech, taux_fin

                tp, tr, tt, tf           = calcul_taux(charges)
                tp2, tr2, tt2, tf2       = calcul_taux(charges_sans_aal)
                tp3, tr3, tt3, tf3       = calcul_taux(charges_sans_aad)
                tp4, tr4, tt4, tf4       = calcul_taux(charges_sans_rec)

                resultats_sim.append({
                    "tranche"         : t_info["nom"],
                    "type"            : t_info["type"],
                    "taux_pur"        : tp,
                    "taux_risque"     : tr,
                    "taux_technique"  : tt,
                    "taux_final"      : tf,
                    "sans_aal"        : tt2,
                    "sans_aad"        : tt3,
                    "sans_rec"        : tt4,
                })

            # Affichage
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

            # Analyse Claude conditions
            if api_key:
                with st.spinner("Claude analyse les conditions..."):
                    client = anthropic.Anthropic(api_key=api_key)
                    analyse = client.messages.create(
                        model="claude-opus-4-5", max_tokens=1500,
                        messages=[{"role":"user","content":f"""Tu es expert en réassurance non-proportionnelle.
Analyse ces résultats et dis pour chaque tranche si les conditions sont nécessaires, à ajuster ou inutiles.

Pour chaque tranche compare :
- Taux technique (toutes conditions) vs Sans AAL vs Sans AAD vs Sans reconstitution
- Si l'écart est faible → condition inutile
- Si l'écart est significatif → condition nécessaire
- Si l'écart est intermédiaire → à ajuster

Résultats :
{json.dumps(resultats_sim, indent=2)}

Tranches :
{json.dumps(tranches_input, indent=2)}

Donne une recommandation claire par tranche et par condition."""
                        }]
                    )
                    st.subheader("🤖 Analyse Claude des conditions")
                    st.markdown(analyse.content[0].text)

            st.session_state["resultats_sim"] = resultats_sim
            st.session_state["tranches"] = tranches_input
            st.success("✅ Simulation terminée !")
        df_res = pd.DataFrame([{
            "Tranche": r["tranche"],
            "Taux pur": f"{r['taux_pur']:.4%}",
            "Taux risque": f"{r['taux_risque']:.4%}",
            "Taux technique": f"{r['taux_technique']:.4%}",
            "Taux final": f"{r['taux_final']:.4%}",
            "Sans AAL": f"{r['taux_sans_aal']:.4%}",
            "Sans AAD": f"{r['taux_sans_aad']:.4%}",
        } for r in resultats_sim])
        st.dataframe(df_res, use_container_width=True)

        # Analyse Claude des conditions
        if api_key:
            with st.spinner("Claude analyse les conditions..."):
                client = anthropic.Anthropic(api_key=api_key)
                analyse = client.messages.create(
                    model="claude-opus-4-5", max_tokens=1500,
                    messages=[{"role": "user", "content": f"""Tu es expert en réassurance non-proportionnelle.
Analyse ces résultats de simulation et dis pour chaque tranche si les conditions (AAL, AAD, reconstitutions) sont nécessaires, à ajuster ou inutiles.

Résultats :
{json.dumps(resultats_sim, indent=2)}

Tranches :
{json.dumps(tranches_input, indent=2)}

Pour chaque tranche donne :
1. Analyse de l'impact AAL (si présent)
2. Analyse de l'impact AAD (si présent)
3. Recommandation reconstitutions
4. Verdict final : condition NÉCESSAIRE / À AJUSTER / INUTILE"""
                    }]
                )
                st.subheader("🤖 Analyse Claude des conditions")
                st.markdown(analyse.content[0].text)

        # Sauvegarder pour suite
        st.session_state["resultats_sim"] = resultats_sim
        st.session_state["tranches"] = tranches_input
        st.success("✅ Simulation terminée !")



# ─── MARKET CURVE ───
st.header("📈 Market Curve")

f_mkt = st.file_uploader("Données marché (Excel)", type=["xlsx","csv"])

if f_mkt:
    df_mkt = pd.read_excel(f_mkt)
    
    # Nettoyage
    df_curve = df_mkt[['Priorité en MAD','ROLs']].dropna()
    if df_curve['ROLs'].dtype == object:
        df_curve['ROLs'] = df_curve['ROLs'].str.replace('%','').astype(float)/100
    
    x = df_curve['Priorité en MAD'].values
    y = df_curve['ROLs'].values

    # Modèle puissance
    def power_model(x, a, b):
        return a * np.power(x, -b)

    params, _ = curve_fit(power_model, x, y, p0=[1, 0.5], maxfev=5000)
    a, b = params

    # Résidus pour percentiles
    y_pred = power_model(x, a, b)
    residus = y - y_pred

    p25 = np.percentile(residus, 25)
    p75 = np.percentile(residus, 75)

    st.write(f"Modèle ajusté : y = {a:.5f} × x^(-{b:.4f})")

    # Graphique
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.scatter(x, y, color='orange', s=60, zorder=5, label='Données marché')
    x_range = np.linspace(min(x), max(x), 300)
    ax.plot(x_range, power_model(x_range, a, b), 
            color='red', linewidth=2, label='Courbe centrale')
    ax.plot(x_range, power_model(x_range, a, b) + p25, 
            color='green', linewidth=1.5, linestyle='--', label='P25 (bas)')
    ax.plot(x_range, power_model(x_range, a, b) + p75, 
            color='blue', linewidth=1.5, linestyle='--', label='P75 (haut)')
    ax.set_xlabel('Priorité (MAD)')
    ax.set_ylabel('ROL')
    ax.set_title('Market Curve — P25 / Médiane / P75')
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig)

    # Taux par tranche
    st.subheader("📊 Taux marché par tranche")
    rows_mkt = []
    for t in tranches_input:
        rol_central = power_model(t['priorite'], a, b)
        rol_bas     = max(rol_central + p25, 0)
        rol_haut    = rol_central + p75

        taux_bas     = rol_bas     * (t['portee'] / gnpi)
        taux_central = rol_central * (t['portee'] / gnpi)
        taux_haut    = rol_haut    * (t['portee'] / gnpi)

        rows_mkt.append({
            "Tranche"       : t["nom"],
            "Type"          : t["type"],
            "Taux P25 (bas)": f"{taux_bas:.4%}",
            "Taux médian"   : f"{taux_central:.4%}",
            "Taux P75 (haut)": f"{taux_haut:.4%}",
            "ROL central"   : f"{rol_central:.4%}"
        })

    df_mkt_res = pd.DataFrame(rows_mkt)
    st.dataframe(df_mkt_res, use_container_width=True)

    # Analyse Claude
    if api_key:
        with st.spinner("Claude analyse la market curve..."):
            client = anthropic.Anthropic(api_key=api_key)
            analyse_mkt = client.messages.create(
                model="claude-opus-4-5", max_tokens=1000,
                messages=[{"role": "user", "content": f"""Tu es expert en réassurance non-proportionnelle.
Voici les taux de marché estimés par la market curve pour chaque tranche.
Pour chaque tranche dis quel taux choisir (P25, médian ou P75) et pourquoi.
Tiens compte du type de tranche (travaillante vs cat) et du contexte marché.

Taux marché :
{json.dumps(rows_mkt, indent=2)}

Tranches :
{json.dumps(tranches_input, indent=2)}"""
                }]
            )
            st.subheader("🤖 Recommandation Claude sur les taux marché")
            st.markdown(analyse_mkt.content[0].text)

    st.session_state["rows_mkt"] = rows_mkt
    st.success("✅ Market curve construite !")

# Résumé programme
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
