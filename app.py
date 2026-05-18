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
st.header("🎲 Simulation Pareto / Poisson")

col1, col2 = st.columns(2)
with col1:
    st.subheader("Paramètres")
    alpha = st.number_input("Alpha (Pareto - sévérité)", value=1.5, min_value=0.1, step=0.1)
    lambda_ = st.number_input("Lambda (Poisson - fréquence)", value=5.0, min_value=0.1, step=0.1)
    n_sim = st.number_input("Nombre de simulations", value=10000, step=1000)
    seuil_min = st.number_input("Seuil minimum sinistre (MAD)", value=100_000, step=50_000)

with col2:
    st.subheader("Paramètres de chargement")
    tx_risque = st.number_input("Chargement risque (%)", value=20, min_value=0, max_value=100) / 100
    tx_secu = st.number_input("Chargement sécurité (%)", value=18, min_value=0, max_value=100) / 100

if st.button("▶ Lancer la simulation"):
    with st.spinner("Simulation en cours..."):

        np.random.seed(42)
        resultats_sim = []

        for t in tranches_input:
            priorite = t["priorite"]
            portee = t["portee"]
            aal = t["AAL"]
            aad = t["AAD"]
            nb_recon = t["nb_reconstitutions"]

            charges_annuelles = []

            for _ in range(int(n_sim)):
                # Nombre de sinistres (Poisson)
                n_sin = np.random.poisson(lambda_)

                # Sévérité (Pareto)
                severites = pareto.rvs(alpha, scale=seuil_min, size=n_sin) if n_sin > 0 else []

                # Charge dans la tranche par sinistre
                charge_tranche = 0
                for s in severites:
                    part = min(max(s - priorite, 0), portee)
                    charge_tranche += part

                # Application AAD
                if aad:
                    charge_tranche = max(charge_tranche - aad, 0)

                # Application AAL
                if aal:
                    charge_tranche = min(charge_tranche, aal)

                # Application reconstitutions
                plafond = portee * (1 + nb_recon)
                charge_tranche = min(charge_tranche, plafond)

                charges_annuelles.append(charge_tranche)

            charges = np.array(charges_annuelles)
            charge_moyenne = np.mean(charges)

            # Taux pur
            taux_pur = charge_moyenne / gnpi

            # Plusieurs taux
            taux_risque_sim = taux_pur * (1 + tx_risque)
            taux_technique_sim = taux_risque_sim * (1 + tx_secu)
            taux_final_sim = taux_technique_sim * (
                1 + t["brokage"] + t["frais"] + t["marge"] + t["retrocession"]
            )

            # Variantes conditions
            # Sans AAL
            charges_sans_aal = []
            for _ in range(int(n_sim)):
                n_sin = np.random.poisson(lambda_)
                severites = pareto.rvs(alpha, scale=seuil_min, size=n_sin) if n_sin > 0 else []
                charge = sum(min(max(s - priorite, 0), portee) for s in severites)
                if aad: charge = max(charge - aad, 0)
                charges_sans_aal.append(min(charge, portee * (1 + nb_recon)))
            taux_sans_aal = np.mean(charges_sans_aal) / gnpi

            # Sans AAD
            charges_sans_aad = []
            for _ in range(int(n_sim)):
                n_sin = np.random.poisson(lambda_)
                severites = pareto.rvs(alpha, scale=seuil_min, size=n_sin) if n_sin > 0 else []
                charge = sum(min(max(s - priorite, 0), portee) for s in severites)
                if aal: charge = min(charge, aal)
                charges_sans_aad.append(min(charge, portee * (1 + nb_recon)))
            taux_sans_aad = np.mean(charges_sans_aad) / gnpi

            resultats_sim.append({
                "tranche": t["nom"],
                "type": t["type"],
                "taux_pur": taux_pur,
                "taux_risque": taux_risque_sim,
                "taux_technique": taux_technique_sim,
                "taux_final": taux_final_sim,
                "taux_sans_aal": taux_sans_aal,
                "taux_sans_aad": taux_sans_aad,
                "charge_moyenne": charge_moyenne
            })

        # Affichage résultats
        st.subheader("📊 Résultats simulation")
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
