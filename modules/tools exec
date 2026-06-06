"""
Atlantic Re IA — LLM Tools executor module
Fonctions _executer_* utilisées par l'Agent LLM (tab_full).
"""
import streamlit as st
import numpy as np
import pandas as pd
import json
from datetime import datetime
from modules.db import db_save_session, db_save_etape


def _get_runtime(key, default=None):
    """Helper pour lire les variables runtime depuis st.session_state."""
    return st.session_state.get(key, default)

def _executer_burning_cost():
    """Calcul BC — utilisé par l'Agent LLM (tab_full)"""
    if "df_proj" not in st.session_state: return {"erreur": "df_proj manquant"}
    df_proj = st.session_state["df_proj"].copy()
    resultats = []
    for t_info in _get_runtime('tranches_input', []):
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
            tp    = charge_moy / _get_runtime('gnpi', 183_000_000)
            sigma = float(np.std(charges_nz)) / _get_runtime('gnpi', 183_000_000)
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


@st.cache_data(show_spinner=False, ttl=3600)
def _executer_simulation(alpha, lambda_, seuil, n_sim):
    """Simulation Pareto/Poisson — utilisée par l'Agent LLM (tab_full)"""
    if "coeffs" not in st.session_state: return {"erreur": "coeffs manquants"}
    coeffs = st.session_state["coeffs"]
    np.random.seed(42)
    resultats = []
    for t_info in _get_runtime('tranches_input', []):
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
            tp = P0 / _get_runtime('gnpi', 183_000_000); tr = (P0 + 0.2 * sig) / _get_runtime('gnpi', 183_000_000)
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
        x = (t['priorite'] + t['portee']/2) / _get_runtime('gnpi', 183_000_000)
        rol = a * (x**(-b)); tp = rol * t['portee'] / _get_runtime('gnpi', 183_000_000)
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
            tts = [calc_tt(t, a, b) for t in _get_runtime('tranches_input', [])]
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
