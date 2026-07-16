"""
IA TARIF — Jugement actuariel et analyse de sensibilite
Module a placer dans : modules/rapport_sensibilite.py

Objectif
--------
Ajouter dans la partie Rapport un bloc court et professionnel qui produit :
1. un jugement actuariel global ;
2. une table de sensibilite par tranche et par methode ;
3. un graphique sobre de sensibilite pour chaque tranche ;
4. un texte exploitable dans le rapport final ou dans le prompt LLM.

Le module ne remplace pas la tarification. Il interprete les resultats deja produits
par les methodes BC, Simulation et Courbe de reference marche.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    import streamlit as st
except Exception:  # permet les tests hors Streamlit
    st = None


# =============================================================================
# Helpers robustes
# =============================================================================


def _to_float(x: Any, default: float = 0.0) -> float:
    """Convertit proprement un nombre, un pourcentage texte ou une valeur vide."""
    if x is None:
        return default
    if isinstance(x, (int, float, np.integer, np.floating)):
        if np.isnan(x) or np.isinf(x):
            return default
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace("%", "").replace(" ", "").replace("\u00a0", "")
        s = s.replace(",", ".")
        if s in {"", "-", "—", "nan", "None"}:
            return default
        try:
            val = float(s)
            # Si le texte contenait %, on le ramene en taux decimal.
            if "%" in x:
                val /= 100.0
            return val
        except Exception:
            return default
    return default


def _fmt_pct(x: Any, digits: int = 3) -> str:
    val = _to_float(x, 0.0)
    return f"{val * 100:.{digits}f} %"


def _fmt_num(x: Any, digits: int = 2) -> str:
    val = _to_float(x, 0.0)
    return f"{val:,.{digits}f}".replace(",", " ")


def _get(d: Any, keys: Iterable[str], default: Any = None) -> Any:
    """Recherche la premiere cle disponible dans un dict ou une Series."""
    if d is None:
        return default
    for k in keys:
        try:
            if isinstance(d, dict) and k in d:
                return d[k]
            if hasattr(d, "index") and k in d.index:
                return d[k]
        except Exception:
            continue
    return default


def _normaliser_nom_tranche(x: Any) -> str:
    return str(x or "").strip()


def _type_tranche(t: Dict[str, Any], row_rapport: Optional[Any] = None) -> str:
    typ = _get(t, ["type", "Type"], "") or _get(row_rapport, ["type", "Type"], "")
    return str(typ or "").strip().lower()


def _rate_from_report(row: Any, keys: Iterable[str]) -> float:
    return _to_float(_get(row, keys, 0.0), 0.0)


def _find_by_tranche(items: Optional[List[Dict[str, Any]]], nom: str) -> Optional[Dict[str, Any]]:
    if not items:
        return None
    nom_l = _normaliser_nom_tranche(nom).lower()
    for r in items:
        rn = _normaliser_nom_tranche(_get(r, ["tranche", "Tranche", "nom", "Nom"], "")).lower()
        if rn == nom_l:
            return r
    return None


def _rapport_row(df_rapport: Optional[pd.DataFrame], nom: str) -> Optional[pd.Series]:
    if df_rapport is None or not isinstance(df_rapport, pd.DataFrame) or df_rapport.empty:
        return None
    nom_l = _normaliser_nom_tranche(nom).lower()
    for _, row in df_rapport.iterrows():
        rn = _normaliser_nom_tranche(_get(row, ["Tranche", "tranche", "Nom", "nom"], "")).lower()
        if rn == nom_l:
            return row
    return None


def _is_cat_type(typ: Any) -> bool:
    """Identifie les tranches Cat / non travaillantes sans dépendre d'un libellé unique."""
    t = str(typ or "").strip().lower().replace("-", "_").replace(" ", "_")
    return ("cat" in t) or ("non_travaillante" in t) or ("non" in t and "trava" in t)


def _has_any_key(d: Any, keys: Iterable[str]) -> bool:
    if not isinstance(d, dict):
        return False
    return any(k in d and d.get(k) not in (None, "", "—") for k in keys)


def _cat_event_counts(st_state: Optional[Dict[str, Any]] = None) -> Dict[int, int]:
    """
    Base Cat indicative utilisée uniquement si aucun calibrage Cat spécifique
    n'est disponible par tranche. Elle correspond à l'instruction métier :
    2024 = 6, 2022 = 4, 2023 = 2, 2020 = 1.
    """
    st_state = st_state or {}
    raw = (
        st_state.get("cat_event_counts")
        or st_state.get("donnees_cat_counts")
        or st_state.get("donnees_cat_indicatives")
    )

    if isinstance(raw, dict):
        out = {}
        for k, v in raw.items():
            try:
                out[int(k)] = int(float(v))
            except Exception:
                continue
        if out:
            return out

    # Valeurs indicatives demandées pour le rapport Cat.
    return {2024: 6, 2022: 4, 2023: 2, 2020: 1}


def _find_market_context(resultats_mkt: Optional[List[Dict[str, Any]]], nom: str) -> Optional[Dict[str, Any]]:
    """
    Récupère le contexte de marché de la combinaison retenue.

    Dans l'application, resultats_mkt est souvent une liste de modèles de courbe
    contenant chacun : r2, n_points, a, b, score, taux_tranches.
    Les taux par tranche sont dans taux_tranches, donc une recherche directe par
    nom de tranche renvoie None et faisait afficher R2=0.
    """
    if not resultats_mkt:
        return None

    nom_l = _normaliser_nom_tranche(nom).lower()

    # Cas 1 : structure déjà par tranche.
    direct = _find_by_tranche(resultats_mkt, nom)
    if direct:
        return direct

    # Cas 2 : liste de courbes, chacune avec taux_tranches. On retient la première
    # car elle correspond généralement à la courbe sélectionnée / meilleure.
    for modele in resultats_mkt:
        if not isinstance(modele, dict):
            continue
        for tt in modele.get("taux_tranches", []) or []:
            rn = _normaliser_nom_tranche(_get(tt, ["tranche", "Tranche", "nom", "Nom"], "")).lower()
            if rn == nom_l:
                out = dict(tt)
                out.update({
                    "r2": modele.get("r2", modele.get("R2", modele.get("R²", None))),
                    "n_points": modele.get("n_points", modele.get("n", modele.get("N", None))),
                    "quantile": modele.get("quantile", None),
                    "a": modele.get("a", None),
                    "b": modele.get("b", None),
                    "score": modele.get("score", None),
                    "r2_ok": modele.get("r2_ok", None),
                })
                return out

    return None


# =============================================================================
# Construction des taux centraux
# =============================================================================


def extraire_taux_mkt(taux_mkt_final: Any, nom: str) -> float:
    """Extrait un taux marche quelle que soit la structure stockee."""
    if taux_mkt_final is None:
        return 0.0

    # Liste de dicts : [{tranche, taux_technique/taux_mkt/...}]
    if isinstance(taux_mkt_final, list):
        r = _find_by_tranche(taux_mkt_final, nom)
        if r:
            return _to_float(_get(r, ["taux_technique", "taux_mkt", "taux", "ROL", "rol"], 0.0), 0.0)
        return 0.0

    # DataFrame
    if isinstance(taux_mkt_final, pd.DataFrame):
        rr = _rapport_row(taux_mkt_final, nom)
        if rr is not None:
            return _rate_from_report(rr, ["taux_technique", "taux_mkt", "Taux Marché", "Taux Mkt", "taux"])
        return 0.0

    # Dict direct
    if isinstance(taux_mkt_final, dict):
        if nom in taux_mkt_final:
            return _to_float(taux_mkt_final[nom], 0.0)
        r = _find_by_tranche(list(taux_mkt_final.values()), nom) if all(isinstance(v, dict) for v in taux_mkt_final.values()) else None
        if r:
            return _to_float(_get(r, ["taux_technique", "taux_mkt", "taux"], 0.0), 0.0)

    return 0.0


@dataclass
class SensibiliteLigne:
    tranche: str
    type_tranche: str
    methode: str
    taux_central: float
    taux_favorable: float
    taux_adverse: float
    parametre_dominant: str
    scenario_favorable: str
    scenario_adverse: str
    credibilite: str
    jugement: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "Tranche": self.tranche,
            "Type": self.type_tranche,
            "Methode": self.methode,
            "Taux central": self.taux_central,
            "Favorable": self.taux_favorable,
            "Adverse": self.taux_adverse,
            "Amplitude": max(self.taux_adverse - self.taux_favorable, 0.0),
            "Parametre dominant": self.parametre_dominant,
            "Scenario favorable": self.scenario_favorable,
            "Scenario adverse": self.scenario_adverse,
            "Credibilite": self.credibilite,
            "Jugement": self.jugement,
        }


# =============================================================================
# Sensibilites par methode
# =============================================================================


def _sensibilite_bc(nom: str, typ: str, r_bc: Optional[Dict[str, Any]], taux_central: float) -> Optional[SensibiliteLigne]:
    if not r_bc and taux_central <= 0:
        return None

    taux = taux_central or _to_float(_get(r_bc, ["taux_technique", "taux_bc", "taux"], 0.0), 0.0)
    if taux <= 0:
        return None

    n_nonzero = int(_to_float(_get(r_bc, ["n_ann_nonzero", "n_annees_nonzero", "nb_annees_nonzero"], 0), 0))
    sigma = _to_float(_get(r_bc, ["sigma_hist", "sigma", "volatilite"], 0.0), 0.0)
    ic_lo = _to_float(_get(r_bc, ["ic_lo", "IC_lo", "borne_inf"], 0.0), 0.0)
    ic_hi = _to_float(_get(r_bc, ["ic_hi", "IC_hi", "borne_sup"], 0.0), 0.0)

    if ic_lo > 0 and ic_hi > 0 and ic_hi >= ic_lo:
        fav, adv = ic_lo, ic_hi
        sfav = f"borne basse bootstrap ou intervalle fourni : {_fmt_pct(fav)}"
        sadv = f"borne haute bootstrap ou intervalle fourni : {_fmt_pct(adv)}"
        param = "experience historique / bootstrap"
    else:
        # Approximation prudente lorsque l'IC n'est pas disponible.
        amp = min(max(sigma * 0.60, taux * 0.15), taux * 0.75) if sigma > 0 else taux * 0.20
        fav = max(taux - amp, 0.0)
        adv = taux + amp
        sfav = "experience favorable : charge historique reduite ou annee lourde neutralisee"
        sadv = "experience adverse : sinistralite historique plus volatile ou annee lourde conservee"
        param = "volatilite historique"

    if n_nonzero == 0:
        cred = "non exploitable"
        jugement = "BC non exploitable : aucune annee non nulle utilisable."
    elif n_nonzero < 3:
        cred = "faible"
        jugement = "BC peu credible : moins de 3 annees non nulles. A utiliser seulement comme indication secondaire."
    elif sigma > taux * 1.5 and taux > 0:
        cred = "moderee"
        jugement = "BC sensible a la volatilite historique. Une revue des annees atypiques est necessaire."
    else:
        cred = "correcte"
        jugement = "BC utilisable comme reference historique sous reserve de qualite du triangle."

    return SensibiliteLigne(nom, typ, "Burning Cost", taux, fav, adv, param, sfav, sadv, cred, jugement)


def _loi_simulation(
    st_state: Optional[Dict[str, Any]] = None,
    r_sim: Optional[Dict[str, Any]] = None,
    typ: str = "",
) -> Tuple[str, Dict[str, float]]:
    """
    Récupère la loi de sévérité retenue et ses paramètres.

    Point important pour les tranches Cat : si l'application n'a pas encore
    calibré une simulation Cat séparée, on n'affiche pas les paramètres globaux
    de la tranche travaillante comme s'ils étaient spécifiques aux Cat. On utilise
    seulement une fréquence Cat indicative fondée sur les comptes fournis, et on
    signale que la sévérité Cat par tranche n'est pas calibrée.
    """
    st_state = st_state or {}
    r_sim = r_sim or {}

    is_cat = _is_cat_type(typ)
    has_specific_cat_calibration = _has_any_key(
        r_sim,
        [
            "source_cat", "n_cat_events", "donnees_cat_specifiques",
            "calibrage_cat", "cat_alpha", "cat_lambda", "alpha_cat",
            "lambda_cat", "xi_cat", "beta_cat", "mu_cat", "sigma_cat",
        ],
    )

    if is_cat and not has_specific_cat_calibration:
        counts = _cat_event_counts(st_state)
        total = int(sum(counts.values()))
        n_years = int(len(counts))
        lambda_cat = float(total / max(n_years, 1))
        return "Cat indicative", {
            "lambda": lambda_cat,
            "n_cat": float(total),
            "n_years_cat": float(n_years),
            "specific_params": 0.0,
        }

    loi = (
        _get(r_sim, ["loi_severite", "distribution", "severity_law", "loi"], "")
        or st_state.get("loi_severite_retenue", "")
        or st_state.get("loi_retendue", "")
        or st_state.get("severity_law", "")
        or "Pareto"
    )
    loi = str(loi).strip() or "Pareto"

    params = {
        "alpha": _to_float(_get(r_sim, ["cat_alpha", "alpha_cat", "alpha", "alpha_est"], st_state.get("alpha_est", 0.0)), 0.0),
        "lambda": _to_float(_get(r_sim, ["cat_lambda", "lambda_cat", "lambda", "lambda_", "lambda_est"], st_state.get("lambda_est", 0.0)), 0.0),
        "seuil": _to_float(_get(r_sim, ["seuil_cat", "cat_seuil", "seuil", "seuil_est", "threshold"], st_state.get("seuil_est", 0.0)), 0.0),
        "xi": _to_float(_get(r_sim, ["xi_cat", "cat_xi", "xi", "xi_gpd", "shape"], st_state.get("xi_est", 0.0)), 0.0),
        "beta": _to_float(_get(r_sim, ["beta_cat", "cat_beta", "beta", "beta_gpd", "sigma_gpd", "scale"], st_state.get("beta_est", 0.0)), 0.0),
        "mu": _to_float(_get(r_sim, ["mu_cat", "cat_mu", "mu", "mu_log", "mu_ln"], st_state.get("mu_ln", 0.0)), 0.0),
        "sigma": _to_float(_get(r_sim, ["sigma_cat", "cat_sigma", "sigma", "sigma_log", "sigma_ln"], st_state.get("sigma_ln", 0.0)), 0.0),
    }
    return loi, params


def _sensibilite_simulation(
    nom: str,
    typ: str,
    r_sim: Optional[Dict[str, Any]],
    taux_central: float,
    st_state: Optional[Dict[str, Any]] = None,
) -> Optional[SensibiliteLigne]:
    if not r_sim and taux_central <= 0:
        return None

    taux = taux_central or _to_float(_get(r_sim, ["taux_technique", "taux_sim", "taux"], 0.0), 0.0)
    if taux <= 0:
        return None

    loi, params = _loi_simulation(st_state, r_sim, typ)
    lam = params.get("lambda", 0.0)

    loi_l = loi.lower()
    if "cat indicative" in loi_l:
        counts = _cat_event_counts(st_state)
        lam_cat = params.get("lambda", 0.0)
        total_cat = int(params.get("n_cat", sum(counts.values())))
        detail_counts = ", ".join(f"{annee}={nb}" for annee, nb in sorted(counts.items()))
        amp_fav = 0.18
        amp_adv = 0.32
        param = (
            f"Frequence Cat indicative : {total_cat} evenements ({detail_counts}), "
            f"lambda={lam_cat:.3f}. Severite Cat par tranche non calibree."
        )
        sfav = "frequence Cat plus faible ou absence d'evenement majeur cedant"
        sadv = "frequence Cat plus elevee ou evenement majeur atteignant la tranche"
    elif "gpd" in loi_l or "pareto general" in loi_l:
        xi = params.get("xi", 0.0)
        beta = params.get("beta", 0.0)
        # GPD : sensibilite forte si xi augmente et/ou beta augmente.
        amp_fav = 0.18 + min(max(abs(xi), 0.0), 1.0) * 0.15
        amp_adv = 0.25 + min(max(abs(xi), 0.0), 1.0) * 0.25
        param = f"GPD : xi={xi:.4f}, beta={beta:,.0f}, lambda={lam:.3f}"
        sfav = "xi ou beta plus faibles, queue moins lourde"
        sadv = "xi ou beta plus eleves, queue plus lourde"
    elif "log" in loi_l:
        mu = params.get("mu", 0.0)
        sig = params.get("sigma", 0.0)
        amp_fav = 0.15 + min(max(sig, 0.0), 2.0) * 0.08
        amp_adv = 0.20 + min(max(sig, 0.0), 2.0) * 0.12
        param = f"Lognormale : mu={mu:.4f}, sigma={sig:.4f}, lambda={lam:.3f}"
        sfav = "sigma lognormal plus faible, dispersion reduite"
        sadv = "sigma lognormal plus eleve, queue plus epaisse"
    else:
        alpha = params.get("alpha", 0.0)
        amp_fav = 0.15 if alpha <= 0 else min(max(0.45 / max(alpha, 0.20), 0.12), 0.45)
        amp_adv = 0.20 if alpha <= 0 else min(max(0.75 / max(alpha, 0.20), 0.18), 0.85)
        param = f"Pareto : alpha={alpha:.4f}, seuil={params.get('seuil', 0.0):,.0f}, lambda={lam:.3f}"
        sfav = "alpha plus eleve ou frequence plus faible"
        sadv = "alpha plus faible ou frequence plus elevee"

    # La frequence agit quasi lineairement sur la charge attendue.
    if lam > 0:
        sfav += " ; lambda bas"
        sadv += " ; lambda haut"

    fav = max(taux * (1.0 - amp_fav), 0.0)
    adv = taux * (1.0 + amp_adv)

    if _is_cat_type(typ):
        if "cat indicative" in loi_l:
            cred = "indicative"
            jugement = (
                "Simulation Cat indicative : frequence Cat separee utilisee, mais severite specifique "
                "non calibree par tranche. Ne pas assimiler aux parametres de la tranche travaillante."
            )
        else:
            cred = "controle Cat"
            jugement = (
                "Simulation de queue utile pour controler la tranche Cat. "
                "Elle ne remplace pas le Burning Cost lorsque celui-ci dispose d'au moins 3 annees non nulles."
            )
    else:
        cred = "controle"
        jugement = "Simulation utile comme controle stochastique du Burning Cost."

    return SensibiliteLigne(nom, typ, "Simulation", taux, fav, adv, param, sfav, sadv, cred, jugement)


def _sensibilite_market(
    nom: str,
    typ: str,
    r_mkt: Optional[Dict[str, Any]],
    taux_central: float,
) -> Optional[SensibiliteLigne]:
    taux = taux_central or _to_float(_get(r_mkt, ["taux_technique", "taux_mkt", "taux", "ROL", "rol"], 0.0), 0.0)
    if taux <= 0:
        return None

    n_ref = int(_to_float(_get(r_mkt, ["n_points", "n", "N", "n_refs", "nb_references"], 0), 0))
    r2 = _to_float(_get(r_mkt, ["r2", "R2", "R²", "r_squared", "coef_determination"], 0.0), 0.0)
    p10 = _to_float(_get(r_mkt, ["p10", "q10", "taux_p10"], 0.0), 0.0)
    p90 = _to_float(_get(r_mkt, ["p90", "q90", "taux_p90"], 0.0), 0.0)

    if p10 > 0 and p90 > 0 and p90 >= p10:
        fav, adv = p10, p90
        sfav = f"borne basse marche : {_fmt_pct(fav)}"
        sadv = f"borne haute marche : {_fmt_pct(adv)}"
        param = f"references marche : N={n_ref if n_ref else 'non fourni'}, R2={r2:.3f}"
    else:
        if n_ref >= 100 and r2 >= 0.60:
            spread = 0.15
        elif n_ref >= 50:
            spread = 0.25
        else:
            spread = 0.40
        fav = max(taux * (1.0 - spread), 0.0)
        adv = taux * (1.0 + spread)
        sfav = "positionnement bas de la courbe de reference"
        sadv = "positionnement haut de la courbe de reference"
        param = f"qualite marche : N={n_ref if n_ref else 'non fourni'}, R2={r2:.3f}"

    if n_ref >= 100 and r2 >= 0.50:
        cred = "credible"
        jugement = "Courbe marche credible pour benchmark externe et positionnement de la tranche."
    elif n_ref >= 50:
        cred = "assez credible"
        jugement = "Courbe marche exploitable avec reserves, surtout en comparaison avec la simulation."
    else:
        cred = "faible"
        jugement = "Courbe marche peu robuste : nombre de references insuffisant ou qualite d'ajustement faible."

    return SensibiliteLigne(nom, typ, "Courbe de reference marche", taux, fav, adv, param, sfav, sadv, cred, jugement)


# =============================================================================
# Table de sensibilite complete
# =============================================================================


def construire_table_sensibilite(
    tranches_input: List[Dict[str, Any]],
    resultats_bc: Optional[List[Dict[str, Any]]] = None,
    resultats_sim: Optional[List[Dict[str, Any]]] = None,
    resultats_mkt: Optional[List[Dict[str, Any]]] = None,
    taux_mkt_final: Any = None,
    df_rapport: Optional[pd.DataFrame] = None,
    session_state: Optional[Dict[str, Any]] = None,
) -> pd.DataFrame:
    """Construit une table longue : une ligne par tranche et methode."""
    lignes: List[SensibiliteLigne] = []
    st_state = session_state or {}

    for t in tranches_input or []:
        nom = _normaliser_nom_tranche(_get(t, ["nom", "tranche", "Tranche", "Nom"], ""))
        if not nom:
            continue
        row = _rapport_row(df_rapport, nom)
        typ = _type_tranche(t, row) or "non renseigne"

        r_bc = _find_by_tranche(resultats_bc, nom)
        r_sim = _find_by_tranche(resultats_sim, nom)
        r_mkt = _find_market_context(resultats_mkt, nom)

        # Taux centraux priorises : rapport final si disponible, sinon resultats methode.
        taux_bc = _rate_from_report(row, ["Taux BC", "taux_bc", "BC"]) if row is not None else 0.0
        taux_sim = _rate_from_report(row, ["Taux Sim.", "Taux Simulation", "taux_sim", "Simulation"]) if row is not None else 0.0
        taux_mkt = _rate_from_report(row, ["Taux Marché", "Taux Mkt", "taux_mkt", "Marche"]) if row is not None else 0.0

        taux_bc = taux_bc or _to_float(_get(r_bc, ["taux_technique", "taux_bc", "taux"], 0.0), 0.0)
        taux_sim = taux_sim or _to_float(_get(r_sim, ["taux_technique", "taux_sim", "taux"], 0.0), 0.0)
        taux_mkt = taux_mkt or extraire_taux_mkt(taux_mkt_final, nom)
        taux_mkt = taux_mkt or _to_float(_get(r_mkt, ["taux_technique", "taux_mkt", "taux", "ROL", "rol"], 0.0), 0.0)

        for obj in (
            _sensibilite_bc(nom, typ, r_bc, taux_bc),
            _sensibilite_simulation(nom, typ, r_sim, taux_sim, st_state),
            _sensibilite_market(nom, typ, r_mkt, taux_mkt),
        ):
            if obj is not None:
                lignes.append(obj)

    if not lignes:
        return pd.DataFrame(columns=[
            "Tranche", "Type", "Methode", "Taux central", "Favorable", "Adverse",
            "Amplitude", "Parametre dominant", "Scenario favorable", "Scenario adverse",
            "Credibilite", "Jugement",
        ])

    return pd.DataFrame([x.as_dict() for x in lignes])


# =============================================================================
# Jugement actuariel global
# =============================================================================


def _niveau_convergence(vals: List[float]) -> Tuple[str, float]:
    vals = [float(v) for v in vals if v and v > 0]
    if len(vals) < 2:
        return "non mesurable", 0.0
    med = float(np.median(vals))
    if med <= 0:
        return "non mesurable", 0.0
    ecart = (max(vals) - min(vals)) / med
    if ecart <= 0.10:
        return "forte", ecart
    if ecart <= 0.25:
        return "acceptable", ecart
    if ecart <= 0.50:
        return "faible", ecart
    return "tres faible", ecart


def generer_jugement_actuariel(
    df_sensibilite: pd.DataFrame,
    df_rapport: Optional[pd.DataFrame] = None,
) -> str:
    """Produit un jugement court et directement exploitable dans le rapport."""
    if df_sensibilite is None or df_sensibilite.empty:
        return "Jugement actuariel non disponible : aucune sensibilite exploitable n'a ete calculee."

    lignes = []
    lignes.append("Jugement actuariel synthetique")

    for tranche, g in df_sensibilite.groupby("Tranche"):
        taux_centraux = g["Taux central"].dropna().astype(float).tolist()
        conv, ecart = _niveau_convergence(taux_centraux)
        type_t = str(g["Type"].iloc[0]) if "Type" in g.columns and len(g) else "non renseigne"
        amp = float(g["Amplitude"].max()) if "Amplitude" in g.columns and len(g) else 0.0

        if conv in {"forte", "acceptable"}:
            statut = "programme stable"
        elif conv == "faible":
            statut = "programme exploitable avec reserves"
        else:
            statut = "programme a revoir"

        methode_plus_sensible = "non determinee"
        try:
            idx = g["Amplitude"].astype(float).idxmax()
            methode_plus_sensible = str(g.loc[idx, "Methode"])
        except Exception:
            pass

        if _is_cat_type(type_t):
            bc_rows = g[g["Methode"].astype(str).str.lower().str.contains("burning", na=False)]
            bc_cred = str(bc_rows["Credibilite"].iloc[0]).lower() if not bc_rows.empty else ""
            if bc_cred in {"correcte", "credible", "crédible"}:
                orientation = "Pour une tranche Cat, le Burning Cost historique reste prioritaire lorsque au moins 3 annees non nulles sont disponibles."
            else:
                orientation = "Pour une tranche Cat sans BC historique credible, la simulation de queue et le benchmark marche servent de relais prudents."
        else:
            orientation = "Pour une tranche travaillante, le Burning Cost reste la reference si l'experience est credible."

        lignes.append(
            f"- {tranche} : convergence {conv} entre methodes "
            f"(ecart relatif environ {ecart:.1%}) ; {statut}. "
            f"Sensibilite dominante : {methode_plus_sensible} "
            f"(amplitude environ {amp:.3%}). {orientation}"
        )

    lignes.append(
        "Conclusion : les taux retenus doivent etre presentes comme des resultats techniques a valider, "
        "et non comme des optimums absolus. Les scenarios de sensibilite servent a encadrer la negociation "
        "et a identifier les parametres qui exposent le plus le programme."
    )
    return "\n".join(lignes)


# =============================================================================
# Affichage Streamlit
# =============================================================================


def _df_affichage(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    for c in ["Taux central", "Favorable", "Adverse", "Amplitude"]:
        if c in out.columns:
            out[c] = out[c].apply(lambda x: _fmt_pct(x, 3))
    return out


def afficher_graphique_sensibilite(df_tranche: pd.DataFrame, titre: str = "Analyse de sensibilite") -> None:
    """Graphique type tornado horizontal, sobre et compact."""
    if st is None:
        return
    if df_tranche is None or df_tranche.empty:
        st.info("Aucune sensibilite disponible pour cette tranche.")
        return

    import matplotlib.pyplot as plt

    d = df_tranche.copy().reset_index(drop=True)
    d["central"] = d["Taux central"].astype(float) * 100
    d["fav"] = d["Favorable"].astype(float) * 100
    d["adv"] = d["Adverse"].astype(float) * 100

    n = len(d)
    fig_h = max(2.2, 0.65 * n + 1.3)
    fig, ax = plt.subplots(figsize=(9.5, fig_h))

    y = np.arange(n)
    central_global = float(np.nanmedian(d["central"]))

    for i, row in d.iterrows():
        c = row["central"]
        fav = min(row["fav"], c)
        adv = max(row["adv"], c)
        ax.barh(i, c - fav, left=fav, height=0.42, color="#74b995", alpha=0.95)
        ax.barh(i, adv - c, left=c, height=0.42, color="#d97f86", alpha=0.95)
        ax.text(fav, i + 0.23, f"{fav:.2f}%", ha="right", va="center", fontsize=9)
        ax.text(adv, i + 0.23, f"{adv:.2f}%", ha="left", va="center", fontsize=9)
        ax.text(c, i - 0.28, f"central {c:.2f}%", ha="center", va="center", fontsize=8, color="#444444")

    ax.axvline(central_global, color="#444444", linestyle="--", linewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(d["Methode"].tolist(), fontsize=10)
    ax.set_xlabel("Taux technique (%)")
    ax.set_title(titre, fontsize=13, fontweight="bold")
    ax.grid(axis="x", alpha=0.22)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.invert_yaxis()

    st.pyplot(fig)
    plt.close(fig)


def afficher_bloc_jugement_sensibilite(
    tranches_input: List[Dict[str, Any]],
    resultats_bc: Optional[List[Dict[str, Any]]] = None,
    resultats_sim: Optional[List[Dict[str, Any]]] = None,
    resultats_mkt: Optional[List[Dict[str, Any]]] = None,
    taux_mkt_final: Any = None,
    df_rapport: Optional[pd.DataFrame] = None,
    session_state: Optional[Dict[str, Any]] = None,
    expanded: bool = True,
) -> pd.DataFrame:
    """
    Affiche dans Streamlit le bloc complet de jugement et sensibilite.
    Retourne le DataFrame long de sensibilite pour export ou prompt LLM.
    """
    if st is None:
        return pd.DataFrame()

    df_sens = construire_table_sensibilite(
        tranches_input=tranches_input,
        resultats_bc=resultats_bc,
        resultats_sim=resultats_sim,
        resultats_mkt=resultats_mkt,
        taux_mkt_final=taux_mkt_final,
        df_rapport=df_rapport,
        session_state=session_state or dict(st.session_state),
    )

    with st.expander("Jugement actuariel et analyse de sensibilite", expanded=expanded):
        if df_sens.empty:
            st.info("Aucune analyse de sensibilite disponible. Executez d'abord les methodes de tarification.")
            return df_sens

        jugement = generer_jugement_actuariel(df_sens, df_rapport=df_rapport)
        st.markdown("#### Jugement actuariel")
        st.markdown(jugement.replace("\n", "  \n"))

        st.markdown("#### Synthese des sensibilites")
        colonnes = [
            "Tranche", "Type", "Methode", "Taux central", "Favorable", "Adverse",
            "Amplitude", "Parametre dominant", "Credibilite", "Jugement",
        ]
        st.dataframe(_df_affichage(df_sens[colonnes]), use_container_width=True, height=320)

        noms = df_sens["Tranche"].dropna().unique().tolist()
        if noms:
            choix = st.selectbox("Tranche a visualiser", noms, key="rapport_sensibilite_tranche")
            d_tr = df_sens[df_sens["Tranche"] == choix]
            afficher_graphique_sensibilite(d_tr, titre=f"Analyse de sensibilite — {choix}")

        st.caption(
            "Lecture : la partie gauche represente un scenario favorable, la partie droite un scenario adverse. "
            "Ces amplitudes encadrent la sensibilite technique ; elles ne remplacent pas une recalibration actuarielle complete."
        )

    return df_sens


def construire_bloc_prompt_llm_sensibilite(df_sensibilite: pd.DataFrame) -> str:
    """Construit un bloc texte a injecter dans input_data du prompt LLM."""
    if df_sensibilite is None or df_sensibilite.empty:
        return "ANALYSE DE SENSIBILITE : non disponible."

    lignes = ["ANALYSE DE SENSIBILITE CALCULEE PAR L'APPLICATION"]
    for _, r in df_sensibilite.iterrows():
        lignes.append(
            f"- {r['Tranche']} | {r['Methode']} : central={_fmt_pct(r['Taux central'])}, "
            f"favorable={_fmt_pct(r['Favorable'])}, adverse={_fmt_pct(r['Adverse'])}, "
            f"parametre dominant={r['Parametre dominant']}, credibilite={r['Credibilite']}."
        )
    lignes.append(
        "Instruction au LLM : utiliser ces sensibilites uniquement comme lecture de stabilite et de negociation ; "
        "ne pas recalculer les taux et ne pas inventer de scenario supplementaire non fourni."
    )
    return "\n".join(lignes)
