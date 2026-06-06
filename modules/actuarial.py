"""
Atlantic Re IA — Actuarial computations module
Tooltips, glossaire, Hill/MEF/GPD, Bühlmann-Straub, Bootstrap CI,
selectionner_seuil_pareto, identifier_sinistres_majeurs, 
section_analyse_distributions.
"""
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as _sp_stats
from modules.db import _get_conn, _ph, db_init
from modules.ui import tableau_resultats, card

def tooltip(terme, definition):
    """Retourne un terme avec tooltip HTML inline."""
    safe_def = definition.replace('"', '&quot;')
    return f'<span class="ar-tooltip" data-tip="{safe_def}">{terme}</span>'


GLOSSAIRE_ACTUARIEL = {
    "τ_pur":        "Taux pur = Charge moyenne / GNPI. Coût moyen annuel avant chargements.",
    "τ_risque":     "R1 : τ_risque = τ_pur + σ × 20%. Intègre un chargement de sécurité proportionnel à la volatilité.",
    "τ_technique":  "Taux technique = τ_risque × (1−Rec) / (1−Brokage−Frais−Marge−Rétro). Prix de revient du réassureur.",
    "σ":            "Écart-type des charges annuelles non nulles divisé par le GNPI. Mesure la volatilité historique.",
    "Rec":          "Facteur de reconstitution = Pr_Rec / (Pr_Rec + N). Réduction du taux liée aux primes de reconstitution.",
    "BC":           "Burning Cost = Σ charges XL nettes / Σ GNPI. Méthode de référence basée sur l'expérience réelle.",
    "ROL":          "Rate On Line = Prime XL / Portée. Indicateur standard de niveau de taux en réassurance cat.",
    "AAL":          "Annual Aggregate Limit. Plafond de la charge annuelle totale à la charge du réassureur.",
    "AAD":          "Annual Aggregate Deductible. Franchise annuelle agrégée : le réassuré conserve les premiers sinistres.",
    "Alpha (α)":    "Indice de queue Pareto. α faible = queue lourde (grands sinistres fréquents). Plage normale [0.8 ; 4.0].",
    "Lambda (λ)":   "Fréquence Poisson. Nombre moyen de sinistres/an au-dessus du seuil de modélisation.",
    "IBNR":         "Incurred But Not Reported. Sinistres survenus mais non encore déclarés. Estimés par Chain Ladder.",
    "IBNER":        "Incurred But Not Enough Reserved. Sinistres déclarés mais sous-réservés. Facteurs CL sur montants.",
    "GPD":          "Generalized Pareto Distribution. Utilisée pour modéliser les excédances au-dessus d'un seuil u (TVE).",
    "As-If":        "Revalorisation des sinistres historiques au niveau de coût de l'année de cotation. Sur incréments.",
    "Pm":           "Niveau de retour T ans. Calculé par GPD : Pm = u + (σ/ξ) × ((m×P(X>u))^ξ − 1).",
    "Credibility":  "Bühlmann-Straub : τ = Z × BC + (1−Z) × μ_priori. Z = n/(n+k), k = σ²_entre/σ²_intra.",
    "NSGA-II":      "Non-dominated Sorting Genetic Algorithm II (Deb 2002). Optimisation multi-objectif : τ min, Var min, Protection max.",
    "TOPSIS":       "Technique for Order Preference by Similarity to Ideal Solution. Compromise entre objectifs normalisés.",
    "Reconst.":     "Reconstitution : prime payée pour rétablir la capacité après sinistre. Taux variable par reconstitution.",
}


def html_glossaire_inline(texte):
    """Remplace automatiquement les termes du glossaire par des tooltips dans un texte HTML."""
    for terme, definition in GLOSSAIRE_ACTUARIEL.items():
        texte = texte.replace(terme, tooltip(terme, definition), 1)
    return texte


def buehlmann_straub_credibility(resultats_bc_list, a_priori_pct=None, gnpi_val=1.0):
    """
    Formule de Bühlmann-Straub (1967) — Crédibilité actuarielle.

    Z = n / (n + k)        où k = σ²_intra / σ²_inter
    τ_crédible = Z × τ_BC + (1 − Z) × μ_a_priori

    Avec σ²_intra = variance interne (fluctuation aléatoire) ≈ σ²_hist
         σ²_inter = variance entre portefeuilles (hétérogénéité structurelle)
         k         = ratio de crédibilité

    Retourne un dict par tranche avec Z, τ_crédible, interprétation.
    """
    resultats = {}
    for r in resultats_bc_list:
        nom       = r.get("tranche", "")
        tau_bc    = r.get("taux_technique", 0.0)
        sigma_h   = r.get("sigma_hist", 0.0)     # σ individuelle (intra)
        n_nz      = int(r.get("n_ann_nonzero", 0))

        # μ a priori : fourni manuellement ou calculé comme moyenne inter-portefeuilles
        mu = float(a_priori_pct or tau_bc or 0.03)

        if n_nz < 1 or sigma_h == 0:
            resultats[nom] = {
                "Z": 0.0, "tau_credible": mu,
                "interpretation": "Aucune donnée — a priori retenu",
                "formule": f"Z=0, τ={mu:.4%}"
            }
            continue

        # k estimé à partir du ratio de Bühlmann (hypothèse simplifiée)
        # σ²_inter estimée comme (variance entre la moyenne BC et l'a priori)
        sigma2_intra = sigma_h ** 2
        sigma2_inter = max((tau_bc - mu) ** 2, sigma2_intra * 0.1)  # garde-fou
        k = sigma2_intra / max(sigma2_inter, 1e-10)

        Z = n_nz / (n_nz + k)
        tau_credible = Z * tau_bc + (1 - Z) * mu

        if Z >= 0.80:
            interp = "Haute crédibilité — BC quasi-seul retenu"
        elif Z >= 0.50:
            interp = "Crédibilité moyenne — mélange BC et a priori"
        else:
            interp = "Faible crédibilité — a priori dominant"

        resultats[nom] = {
            "Z":              round(Z, 4),
            "tau_bc":         round(tau_bc, 6),
            "mu_a_priori":    round(mu, 6),
            "tau_credible":   round(tau_credible, 6),
            "k":              round(k, 4),
            "sigma_intra":    round(sigma_h, 6),
            "n_annees":       n_nz,
            "interpretation": interp,
            "formule":        f"Z={Z:.3f}, τ_BC={tau_bc:.4%}, μ={mu:.4%} → τ_cred={tau_credible:.4%}",
        }
    return resultats


def bootstrap_ci_bc(df_proj, tranche_info, gnpi_val, n_boot=2000, alpha_ci=0.05):
    """
    Intervalle de confiance Bootstrap sur le taux BC (Efron & Tibshirani, 1993).
    Rééchantillonne les années de sinistralité avec remise, recalcule le BC.
    Retourne IC [α/2, 1−α/2] sur le taux technique.
    """
    D   = tranche_info["priorite"];  L = tranche_info["portee"]
    aal = tranche_info.get("AAL");   aad = tranche_info.get("AAD")
    n_rec = tranche_info.get("nb_reconstitutions", 1)
    t_r   = tranche_info.get("taux_reconstitution", 100) / 100
    bk    = tranche_info["brokage"]; fg = tranche_info["frais"]
    mg    = tranche_info["marge"];   rt = tranche_info.get("retrocession", 0)
    cap   = (n_rec + 1) * L

    df_proj = df_proj.copy()
    df_proj["Ck"] = df_proj.apply(
        lambda row: min(max(row["Sprime_ultime"] - D, 0), L) * row["coeff_stab"], axis=1)
    charges_par_ann = df_proj.groupby("annee_surv")["Ck"].sum()
    charges_list    = []
    for ann, ch in charges_par_ann.items():
        if aad: ch = max(ch - aad, 0)
        if aal: ch = min(ch, aal)
        charges_list.append(float(min(ch, cap)))

    if len(charges_list) < 4:
        return None  # Pas assez de données pour bootstrap

    np.random.seed(42)
    boot_taux = []
    for _ in range(n_boot):
        sample    = np.random.choice(charges_list, size=len(charges_list), replace=True)
        nz        = [c for c in sample if c > 0]
        if len(nz) < 1: continue
        tp        = np.mean(sample) / gnpi_val
        sigma     = np.std(nz) / gnpi_val if len(nz) >= 2 else 0
        tr        = tp + sigma * 0.20
        tt        = (tr * (1 - 0.0)) / max(1 - bk - fg - mg - rt, 0.01)
        boot_taux.append(tt)

    if len(boot_taux) < 10:
        return None

    lo = float(np.percentile(boot_taux, 100 * alpha_ci / 2))
    hi = float(np.percentile(boot_taux, 100 * (1 - alpha_ci / 2)))
    med = float(np.median(boot_taux))
    return {"ic_lo": lo, "ic_hi": hi, "mediane_boot": med,
            "n_boot": n_boot, "alpha": alpha_ci,
            "label": f"IC {int((1-alpha_ci)*100)}% : [{lo:.4%}, {hi:.4%}]"}


def generer_pptx_rapport(gnpi_val, tranches, resultats_bc, resultats_sim,
                          taux_mkt_final, df_rapport, prime_totale, annee=2026):
    """
    Génère un rapport de tarification en format PPTX (6 slides).
    Palette : Ocean Executive — navy #0d2b3e + teal #00b5a5 + blanc
    """
    import io as _io_pptx
    import subprocess, os, tempfile, json as _json

    # Construire le script PptxGenJS
    taux_global = prime_totale / gnpi_val if gnpi_val else 0

    rows_rapport_js = "[]"
    if df_rapport is not None and not df_rapport.empty:
        rows_rapport_js = _json.dumps([
            {"t": str(r.get("Tranche","") or r.get("tranche","")),
             "bc": str(r.get("Taux BC","") or f"{r.get('taux_bc',0):.4%}"),
             "sim": str(r.get("Taux Sim.","") or f"{r.get('taux_sim',0):.4%}"),
             "mkt": str(r.get("Taux Marché","") or f"{r.get('taux_mkt',0):.4%}"),
             "ret": str(r.get("Taux retenu","") or f"{r.get('taux_retenu',0):.4%}"),
             "prime": str(r.get("Prime (MAD)","") or f"{r.get('prime_MAD',0):,.0f}")}
            for _, r in df_rapport.iterrows()
        ], ensure_ascii=False)

    tranches_js = _json.dumps([
        {"nom": t.get("nom",""), "type": t.get("type",""),
         "prio": f"{t.get('priorite',0)/1e6:.0f}M",
         "port": f"{t.get('portee',0)/1e6:.0f}M",
         "rec":  f"{t.get('nb_reconstitutions',1)}x{t.get('taux_reconstitution',100):.0f}%"}
        for t in tranches
    ], ensure_ascii=False)

    bc_js  = _json.dumps([{"t":r.get("tranche",""),"tt":f"{r.get('taux_technique',0):.4%}",
                            "tp":f"{r.get('taux_pur',0):.4%}","n":r.get("n_ann_nonzero",0)}
                           for r in (resultats_bc or [])], ensure_ascii=False)
    sim_js = _json.dumps([{"t":r.get("tranche",""),"tt":f"{r.get('taux_technique',0):.4%}",
                            "tp":f"{r.get('taux_pur',0):.4%}"}
                           for r in (resultats_sim or [])], ensure_ascii=False)

    script = f"""
const pptxgen = require("pptxgenjs");
const prs = new pptxgen();
prs.layout = 'LAYOUT_16x9';
prs.author = 'Atlantic Re IA';
prs.title = 'Rapport Tarification XL {annee}';

const NAV = "0d2b3e", TEAL = "00b5a5", WHITE = "FFFFFF", GRAY = "f2f8f7", MGRAY = "5a7a8a";
const tranches = {tranches_js};
const bcData   = {bc_js};
const simData  = {sim_js};
const rapport  = {rows_rapport_js};

// ── Slide 1 : Couverture ──────────────────────────────
let s1 = prs.addSlide();
s1.background = {{color: NAV}};
s1.addShape(prs.ShapeType.rect, {{x:0,y:4.5,w:10,h:1.125,fill:{{color:TEAL}}}});
s1.addText("ATLANTIC RE", {{x:0.5,y:0.8,w:9,h:1.2,fontSize:48,bold:true,color:WHITE,fontFace:"Georgia"}});
s1.addText("Rapport de Tarification {annee}", {{x:0.5,y:2.0,w:9,h:0.7,fontSize:24,color:TEAL,fontFace:"Calibri"}});
s1.addText("Réassurance Non-Proportionnelle · Automobile · Maroc", {{x:0.5,y:2.7,w:9,h:0.5,fontSize:14,color:WHITE,fontFace:"Calibri"}});
s1.addText("GNPI : {gnpi_val:,.0f} MAD  |  Prime totale : {prime_totale:,.0f} MAD  |  Taux global : {taux_global:.4%}", {{x:0.5,y:4.6,w:9,h:0.4,fontSize:12,color:NAV,fontFace:"Calibri"}});

// ── Slide 2 : Programme ───────────────────────────────
let s2 = prs.addSlide();
s2.background = {{color: GRAY}};
s2.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s2.addText("Programme de Réassurance", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
const tRows = [["Tranche","Type","Priorité","Portée","Reconstitutions"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(tranches.map(t=>[t.nom,t.type,t.prio,t.port,t.rec].map(v=>{{return{{text:v}}}})));
s2.addTable(tRows, {{x:0.4,y:1.1,w:9.2,colW:[2.5,1.5,1.8,1.8,1.6],border:{{type:'none'}},rowH:0.45,fontSize:13,fontFace:"Calibri",color:"1a1a1a",fill:{{color:WHITE}},border:{{pt:0.5,color:"d0e8e2"}}}});

// ── Slide 3 : Burning Cost ────────────────────────────
let s3 = prs.addSlide();
s3.background = {{color: GRAY}};
s3.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s3.addText("Burning Cost", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s3.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
s3.addText("Méthode de référence · As-If sur incréments · Règle R1 : τ_risque = τ_pur + σ × 20%", {{x:0.4,y:0.95,w:9.2,h:0.35,fontSize:11,color:MGRAY,italic:true}});
const bcRows = [[["Tranche","τ pur","τ technique","Années non nulles"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]].flat()
  .concat ? [["Tranche","τ pur","τ technique","Années non nulles"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(bcData.map(r=>[r.t,r.tp,r.tt,String(r.n)].map(v=>{{return{{text:v}}}}))) : [];
if(bcRows.length > 1) s3.addTable(bcRows, {{x:0.4,y:1.4,w:9.2,colW:[3,2,2.5,1.7],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.5,fontSize:13,fontFace:"Calibri",color:"1a1a1a"}});

// ── Slide 4 : Simulation ──────────────────────────────
let s4 = prs.addSlide();
s4.background = {{color: GRAY}};
s4.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s4.addText("Simulation Pareto / Poisson", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s4.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
const simRows = [["Tranche","τ pur","τ technique"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
  .concat(simData.map(r=>[r.t,r.tp,r.tt].map(v=>{{return{{text:v}}}})));
if(simRows.length > 1) s4.addTable(simRows, {{x:0.4,y:1.4,w:9.2,colW:[3.5,2.5,3.2],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.5,fontSize:13,fontFace:"Calibri",color:"1a1a1a"}});

// ── Slide 5 : Synthèse ────────────────────────────────
let s5 = prs.addSlide();
s5.background = {{color: GRAY}};
s5.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.9,fill:{{color:NAV}}}});
s5.addText("Synthèse de Tarification", {{x:0.4,y:0,w:9,h:0.9,fontSize:22,bold:true,color:WHITE,valign:"middle"}});
s5.addShape(prs.ShapeType.rect, {{x:0,y:0.85,w:10,h:0.06,fill:{{color:TEAL}}}});
if(rapport.length > 0) {{
  const rptRows = [["Tranche","BC","Simulation","Marché","Retenu","Prime (MAD)"].map(h=>{{text:h,options:{{bold:true,color:WHITE,fill:{{color:NAV}}}}}})]
    .concat(rapport.map(r=>[r.t,r.bc,r.sim,r.mkt,r.ret,r.prime].map(v=>{{return{{text:v}}}})));
  s5.addTable(rptRows, {{x:0.4,y:1.4,w:9.2,colW:[2.0,1.4,1.4,1.4,1.4,1.6],border:{{pt:0.5,color:"d0e8e2"}},rowH:0.45,fontSize:12,fontFace:"Calibri",color:"1a1a1a"}});
}}

// ── Slide 6 : Conclusion ──────────────────────────────
let s6 = prs.addSlide();
s6.background = {{color: NAV}};
s6.addShape(prs.ShapeType.rect, {{x:0,y:0,w:10,h:0.06,fill:{{color:TEAL}}}});
s6.addText("Conclusion & Recommandations", {{x:0.5,y:0.5,w:9,h:1,fontSize:30,bold:true,color:WHITE,fontFace:"Georgia"}});
s6.addText([
  {{text:"Prime totale\\n",   options:{{bold:true,fontSize:14,color:TEAL}}}},
  {{text:"{prime_totale:,.0f} MAD\\n\\n", options:{{fontSize:22,bold:true,color:WHITE}}}},
  {{text:"Taux global\\n",    options:{{bold:true,fontSize:14,color:TEAL}}}},
  {{text:"{taux_global:.4%}\\n\\n",       options:{{fontSize:22,bold:true,color:WHITE}}}},
  {{text:"Généré par Atlantic Re IA · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
     options:{{fontSize:10,color:"9ab5c5",italic:true}}}}
], {{x:0.8,y:1.8,w:4.5,h:3.5,valign:"top"}});
s6.addText("Sélection : max(BC, Sim) travaillante\\nmax(Sim, Marché) cat / non-travaillante\\n\\nBC = méthode de référence\\nSimulation = validation & prudence\\nMarket curve = benchmark externe cat", {{x:5.5,y:2.0,w:4.0,h:3.0,fontSize:13,color:"c8dce6",fontFace:"Calibri",valign:"top"}});

await prs.writeFile({{fileName:"/tmp/atlantic_re_rapport_{annee}.pptx"}});
console.log("OK");
"""

    # Écrire et exécuter le script Node.js
    tmp_dir = tempfile.mkdtemp()
    script_path = os.path.join(tmp_dir, "make_pptx.mjs")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script)

    try:
        result = subprocess.run(
            ["node", script_path],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "NODE_PATH": "/home/claude/.npm-global/lib/node_modules"}
        )
        pptx_path = f"/tmp/atlantic_re_rapport_{annee}.pptx"
        if os.path.exists(pptx_path):
            with open(pptx_path, "rb") as f:
                return f.read()
        return None
    except Exception:
        return None
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


def identifier_sinistres_majeurs_gpd(df_proj, gnpi, tranches_input,
                                      nb_annees_obs=10, retour_ans=20,
                                      u=None, pct_seuil=0.80):
    """
    Identification des sinistres majeurs par TVE — fit GPD (scipy).
    Traduction exacte du code R evir::gpd.
    Chargement calculé par tranche : chargement = sum((1/T) * min(max(X-D,0),C) / GNPI)

    Paramètres
    ----------
    u            : seuil TVE (si None → p80 × priorité travaillante)
    pct_seuil    : percentile pour calcul automatique du seuil
    retour_ans   : période de retour pour Pm
    nb_annees_obs: nombre d'années d'observation
    """
    from scipy import stats

    charges = df_proj['Sprime_ultime'].values
    charges = charges[charges > 0]
    n_total = len(charges)

    # ── Seuil TVE ──
    if u is None:
        D_trav = next((t['priorite'] for t in tranches_input if t['type'] == 'travaillante'),
                      charges[charges > 0].mean())
        u = pct_seuil * D_trav

    # ── Excédances au-dessus du seuil ──
    excesses = charges[charges >= u] - u
    n_excesses = len(excesses)

    if n_excesses < 5:
        # Fallback si trop peu de données : Pm = p99.5
        Pm = float(np.percentile(charges, 99.5))
        xi = 0.0; sigma_gpd = float(np.std(excesses)) if n_excesses > 0 else 1.0
        survie = n_excesses / max(n_total, 1)
        freq_annuelle = n_total / nb_annees_obs
        m = retour_ans * freq_annuelle
        fit_ok = False
    else:
        # ── Fit GPD (xi=forme, loc=0 fixé, sigma=échelle) ──
        xi, loc_gpd, sigma_gpd = stats.genpareto.fit(excesses, floc=0)
        survie       = n_excesses / n_total
        freq_annuelle = n_total / nb_annees_obs
        m             = retour_ans * freq_annuelle

        # ── Niveau de retour Pm (formule R evir) ──
        ms = m * survie
        if abs(xi) > 1e-10:
            Pm = u + (sigma_gpd / xi) * (ms**xi - 1)
        else:
            Pm = u + sigma_gpd * np.log(ms)
        fit_ok = True

    Pm = max(Pm, float(np.percentile(charges, 95)))  # garde-fou minimal

    # ── Séparation majeurs / courants ──
    mask_maj    = df_proj['Sprime_ultime'] >= Pm
    df_majeurs  = df_proj[mask_maj].copy()
    df_courants = df_proj[~mask_maj].copy()

    # ── Chargements par tranche (formule R) ──
    # chargement_tranche = sum((1/T) * min(max(X-D,0),C)) / GNPI
    chargements_par_tranche = {}
    for t in tranches_input:
        D = t['priorite']; C = t['portee']
        if len(df_majeurs) > 0:
            X_maj = df_majeurs['Sprime_ultime'].values
            charges_nettes = np.minimum(np.maximum(X_maj - D, 0), C)
            chargement_t   = float(np.sum((1.0 / retour_ans) * charges_nettes) / gnpi)
        else:
            charges_nettes = np.array([])
            chargement_t   = 0.0
        chargements_par_tranche[t['nom']] = {
            'chargement': round(chargement_t, 8),
            'type':        t['type'],
            'D':           D, 'C': C,
            'charges_nettes': charges_nettes.tolist(),
        }

    # ── Tableau détaillé sinistres majeurs ──
    rows_charg = []
    for _, row in df_majeurs.iterrows():
        x = row['Sprime_ultime']
        row_d = {"Annee": row.get('annee_surv', '—'), "Montant_stab": round(x),
                 "p_j": round(1.0/retour_ans, 4)}
        for t in tranches_input:
            D = t['priorite']; C = t['portee']
            cn  = float(min(max(x - D, 0), C))
            chg = (1.0/retour_ans) * cn / gnpi
            row_d[f"Ck {t['nom'][:8]}"]   = round(cn, 0)
            row_d[f"Charg {t['nom'][:8]}"] = round(chg, 6)
        rows_charg.append(row_d)
    df_chargements = pd.DataFrame(rows_charg)

    # Chargement de référence = tranche travaillante (compat. code existant)
    chargement_ref = next(
        (v['chargement'] for k,v in chargements_par_tranche.items() if v['type']=='travaillante'),
        sum(v['chargement'] for v in chargements_par_tranche.values()))

    # ── Diagnostics GPD ──
    gpd_diag = {
        "u": round(float(u), 0),
        "xi": round(float(xi), 4),
        "sigma_gpd": round(float(sigma_gpd), 2),
        "survie_P_X_gt_u": round(float(survie), 6),
        "n_excesses": int(n_excesses),
        "freq_annuelle": round(float(freq_annuelle), 4),
        "m": round(float(m), 2),
        "Pm": round(float(Pm), 0),
        "fit_ok": fit_ok,
        "excesses": excesses.tolist() if fit_ok else [],
    }

    return {
        "df_majeurs":              df_majeurs,
        "df_courants":             df_courants,
        "Pm":                      float(Pm),
        "chargement":              chargement_ref,
        "chargements_par_tranche": chargements_par_tranche,
        "df_chargements":          df_chargements,
        "alpha":                   float(-1/xi) if abs(xi) > 1e-4 else 1.5,
        "n_majeurs":               int(len(df_majeurs)),
        "n_courants":              int(len(df_courants)),
        "gpd_diag":                gpd_diag,
    }


# Alias pour compat. code existant
def identifier_sinistres_majeurs(df_proj, gnpi, D, C_tranche,
                                  nb_annees_obs=10, retour_ans=20, percentile_seuil=99.5):
    """Wrapper de compatibilité — appelle la version GPD complète."""
    tranches_compat = [{"nom": "Tranche", "type": "travaillante",
                         "priorite": D, "portee": C_tranche}]
    return identifier_sinistres_majeurs_gpd(
        df_proj, gnpi, tranches_compat,
        nb_annees_obs=nb_annees_obs, retour_ans=retour_ans,
        pct_seuil=0.995)
