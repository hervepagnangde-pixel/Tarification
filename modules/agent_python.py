"""
IA TARIF — Agent Python pur
AgentActuarielPython : pipeline complet BC -> Simulation -> Market Curve -> Rapport -> Variantes.

Module sans LLM, utilisable hors ligne.
Correction intégrée : initialisation robuste de df_ml et optimisation directe des variantes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from modules.optimization import _lookup_taux, _lookup_result, _json_safe


class AgentActuarielPython:
    """
    Agent de tarification 100 % Python.

    Le moteur applique des règles actuarielles explicites :
      1. validation des paramètres ;
      2. Burning Cost ;
      3. simulation fréquence-sévérité ;
      4. contrôles de cohérence ;
      5. courbe de marché ;
      6. rapport de tarification ;
      7. variantes comparables de programme.
    """

    def __init__(
        self,
        tranches,
        gnpi,
        df_proj,
        coeffs,
        alpha_est,
        lambda_est,
        seuil_est,
        Pm_proxy,
        chargement_majeurs,
        df_mkt_clean=None,
        df_ml=None,
        loi_sim="pareto",
        mu_ln=None,
        sigma_ln=None,
        gpd_xi=None,
        gpd_beta=None,
    ):
        self.tranches = tranches or []
        self.gnpi = float(gnpi or 0.0)
        self.df_proj = df_proj if df_proj is not None else pd.DataFrame()
        self.coeffs = np.asarray(coeffs if coeffs is not None else [1.0], dtype=float)
        self.alpha = float(alpha_est or 1.5)
        self.lambda_ = float(lambda_est or 0.0)
        self.seuil = float(seuil_est or 0.0)
        self.Pm_proxy = float(Pm_proxy or 0.0)
        self.chargement_majeurs = float(chargement_majeurs or 0.0)
        self.df_mkt = df_mkt_clean

        # IMPORTANT : certains workflows lancent l'agent avant le module labo/ML.
        # L'attribut doit donc toujours exister, même si aucun dataset ML n'est disponible.
        self.df_ml = df_ml
        self.loi_sim = str(loi_sim or "pareto").lower()
        self.mu_ln = None if mu_ln is None else float(mu_ln)
        self.sigma_ln = None if sigma_ln is None else float(sigma_ln)
        self.gpd_xi = None if gpd_xi is None else float(gpd_xi)
        self.gpd_beta = None if gpd_beta is None else float(gpd_beta)

        self.log = []
        self.anomalies = []
        self.resultats_bc = []
        self.resultats_sim = []
        self.resultats_mkt = []
        self.rapport_rows = []
        self.variantes = {}
        self.prime_totale = 0.0

    # ------------------------------------------------------------------
    # UTILITAIRES
    # ------------------------------------------------------------------
    def _log(self, etape, decision, detail=""):
        self.log.append({"etape": etape, "decision": decision, "detail": detail})

    def _alerte(self, niveau, message):
        """niveau : INFO / WARN / CRITIQUE."""
        self.anomalies.append({"niveau": niveau, "message": message})

    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "":
                return default
            if isinstance(x, str):
                s = x.replace("%", "").replace(" ", "").replace(",", ".")
                val = float(s)
                return val / 100.0 if "%" in x or val > 1.5 else val
            return float(x)
        except Exception:
            return default

    @staticmethod
    def _arrondir_aed(x, pas=500_000, minimum=0.0):
        try:
            return max(round(float(x) / pas) * pas, minimum)
        except Exception:
            return minimum

    def _get_taux_rec_list(self, t_info):
        n_rec = int(t_info.get("nb_reconstitutions", 0) or 0)
        if "taux_reconstitutions" in t_info and t_info.get("taux_reconstitutions"):
            vals = list(t_info.get("taux_reconstitutions") or [])
        else:
            vals = [float(t_info.get("taux_reconstitution", 100.0) or 100.0)] * n_rec
        return [float(v or 0.0) for v in vals[:n_rec]]

    # ------------------------------------------------------------------
    # OPTIMISATION ACTUARIELLE — SANS ÉLASTICITÉS PAR DÉFAUT
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # OPTIMISATION ACTUARIELLE — SANS ÉLASTICITÉS
    # ------------------------------------------------------------------
    def _tirer_severites(self, n, rng):
        """
        Tire des sévérités selon la loi sélectionnée.
        Utilise les paramètres actuariels déjà estimés : Pareto, Lognormale ou GPD.
        """
        n = int(max(n, 0))
        if n == 0:
            return np.array([], dtype=float)

        loi = str(self.loi_sim or "pareto").lower()

        if loi in ("lognormale", "lognormal"):
            if self.mu_ln is None or self.sigma_ln is None or self.sigma_ln <= 0:
                self._alerte("WARN", "Paramètres lognormaux absents : retour à Pareto.")
            else:
                return rng.lognormal(mean=float(self.mu_ln), sigma=float(self.sigma_ln), size=n)

        if loi == "gpd":
            if self.gpd_beta is None or self.gpd_beta <= 0:
                self._alerte("WARN", "Paramètres GPD absents : retour à Pareto.")
            else:
                u = np.clip(rng.random(n), 1e-12, 1 - 1e-12)
                xi = float(self.gpd_xi or 0.0)
                beta = float(self.gpd_beta)

                if abs(xi) < 1e-8:
                    return self.seuil - beta * np.log(1 - u)

                return self.seuil + (beta / xi) * ((1 - u) ** (-xi) - 1)

        # Pareto avec alpha/seuil estimés. Ce n'est pas une élasticité arbitraire.
        alpha = max(float(self.alpha or 1.5), 1e-6)
        seuil = max(float(self.seuil or 1.0), 1.0)
        u = np.clip(rng.random(n), 1e-12, 1 - 1e-12)
        return seuil * (1 - u) ** (-1 / alpha)

    def _charges_techniques(self, t_info):
        """
        Récupère les chargements techniques disponibles sur la tranche.
        Les clés absentes valent 0.
        """
        brokage = self._num(t_info.get("brokage", 0.0))
        frais = self._num(t_info.get("frais", 0.0))
        marge = self._num(t_info.get("marge", 0.0))
        retro = self._num(t_info.get("retrocession", 0.0))

        chargement_total = brokage + frais + marge
        chargement_total = min(max(chargement_total, 0.0), 0.80)
        retro = min(max(retro, 0.0), 0.80)

        return chargement_total, retro

    def _taux_simule_candidat(self, t_info, n_sim=20000, seed=12345):
        """
        Calcule le taux technique d'une tranche candidate par simulation directe.

        Le taux est recalculé à partir :
          - de la fréquence lambda ;
          - de la loi de sévérité ;
          - de la priorité ;
          - de la portée ;
          - des clauses AAD/AAL ;
          - du nombre de reconstitutions ;
          - des chargements techniques.
        """
        if self.gnpi <= 0:
            return {
                "taux_pur": 0.0,
                "taux_technique": 0.0,
                "prime": 0.0,
                "var_retenu": np.nan,
                "moyenne_retenu": np.nan,
                "message": "GNPI nul ou négatif.",
            }

        D = float(t_info.get("priorite", 0.0) or 0.0)
        C = float(t_info.get("portee", 0.0) or 0.0)
        aad = t_info.get("AAD")
        aal = t_info.get("AAL")
        n_rec = int(t_info.get("nb_reconstitutions", 0) or 0)

        if D < 0 or C <= 0:
            return {
                "taux_pur": 0.0,
                "taux_technique": 0.0,
                "prime": 0.0,
                "var_retenu": np.nan,
                "moyenne_retenu": np.nan,
                "message": "Priorité ou portée invalide.",
            }

        rng = np.random.default_rng(seed)
        lambda_ = max(float(self.lambda_ or 0.0), 0.0)
        n_sim = int(max(n_sim, 1))

        pertes_cedees = np.zeros(n_sim, dtype=float)
        pertes_retenues = np.zeros(n_sim, dtype=float)
        limite_annuelle = C * (1 + max(n_rec, 0))

        for i in range(n_sim):
            n_sin = rng.poisson(lambda_)
            sev = self._tirer_severites(n_sin, rng)

            if len(sev) == 0:
                continue

            brut = float(sev.sum())
            cede = float(np.minimum(np.maximum(sev - D, 0.0), C).sum())

            if aad:
                cede = max(cede - float(aad), 0.0)
            if aal:
                cede = min(cede, float(aal))

            cede = min(cede, limite_annuelle)
            retenu = max(brut - cede, 0.0)

            pertes_cedees[i] = cede
            pertes_retenues[i] = retenu

        charge_pure = float(np.mean(pertes_cedees))
        taux_pur = charge_pure / self.gnpi

        chargement_total, retro = self._charges_techniques(t_info)
        denom = max(1.0 - chargement_total, 1e-6)
        taux_technique = taux_pur * (1.0 - retro) / denom

        return {
            "taux_pur": float(taux_pur),
            "taux_technique": float(taux_technique),
            "prime": float(taux_technique * self.gnpi),
            "var_retenu": float(np.var(pertes_retenues)),
            "moyenne_retenu": float(np.mean(pertes_retenues)),
            "priorite": D,
            "portee": C,
            "nb_reconstitutions": n_rec,
        }

    def _extraire_bornes_optimisation(self, t_info, variable):
        """
        Retourne les bornes explicites fournies dans la tranche.

        Aucune borne n'est inventée. Si les bornes ne sont pas dans t_info,
        l'optimisation dichotomique est déclarée indisponible.
        """
        if variable == "priorite":
            couples = [
                ("priorite_min", "priorite_max"),
                ("borne_priorite_min", "borne_priorite_max"),
                ("D_min", "D_max"),
                ("d_min", "d_max"),
            ]
        elif variable == "portee":
            couples = [
                ("portee_min", "portee_max"),
                ("borne_portee_min", "borne_portee_max"),
                ("C_min", "C_max"),
                ("c_min", "c_max"),
            ]
        else:
            return None, None

        for k_min, k_max in couples:
            if k_min in t_info and k_max in t_info:
                b_min = self._num(t_info.get(k_min), default=np.nan)
                b_max = self._num(t_info.get(k_max), default=np.nan)
                if np.isfinite(b_min) and np.isfinite(b_max) and b_max > b_min:
                    return float(b_min), float(b_max)

        return None, None

    def _extraire_grilles_finetti(self, t_info):
        """
        Retourne une grille de candidats D/C issue de données explicites.

        Sources acceptées, dans l'ordre :
          1. listes fournies dans t_info : grille_priorites/grille_portees ;
          2. couples candidats fournis dans t_info : candidats_programme ;
          3. dataset ML/labo df_ml, s'il existe et contient priorite/portee.

        Si aucune source explicite n'existe, aucune grille n'est créée.
        """
        candidats_pairs = []

        # 1) Couples explicites directement fournis
        for key in ["candidats_programme", "candidats", "programmes_candidats"]:
            vals = t_info.get(key)
            if isinstance(vals, list):
                for item in vals:
                    if isinstance(item, dict):
                        D = self._num(item.get("priorite", item.get("D")), default=np.nan)
                        C = self._num(item.get("portee", item.get("C")), default=np.nan)
                        if np.isfinite(D) and np.isfinite(C) and D >= 0 and C > 0:
                            candidats_pairs.append((float(D), float(C)))

        if candidats_pairs:
            return sorted(set(candidats_pairs))

        # 2) Grilles explicites séparées
        priorites = None
        portees = None
        for k in ["grille_priorites", "priorites_candidates", "priorites_candidates_aed"]:
            if isinstance(t_info.get(k), list) and t_info.get(k):
                priorites = [self._num(x, default=np.nan) for x in t_info.get(k)]
                break
        for k in ["grille_portees", "portees_candidates", "portees_candidates_aed"]:
            if isinstance(t_info.get(k), list) and t_info.get(k):
                portees = [self._num(x, default=np.nan) for x in t_info.get(k)]
                break

        if priorites and portees:
            pairs = []
            for D in priorites:
                for C in portees:
                    if np.isfinite(D) and np.isfinite(C) and D >= 0 and C > 0:
                        pairs.append((float(D), float(C)))
            if pairs:
                return sorted(set(pairs))

        # 3) Dataset labo/ML : on utilise uniquement des scénarios réellement générés
        df_ml = getattr(self, "df_ml", None)
        if isinstance(df_ml, pd.DataFrame) and {"priorite", "portee"}.issubset(df_ml.columns):
            df = df_ml.copy().replace([np.inf, -np.inf], np.nan)
            df["priorite"] = pd.to_numeric(df["priorite"], errors="coerce")
            df["portee"] = pd.to_numeric(df["portee"], errors="coerce")

            # Si le dataset porte le type ou le nom de tranche, on filtre sans inventer.
            nom = t_info.get("nom", "")
            typ = t_info.get("type", "")
            if "tranche_base" in df.columns and nom:
                df_nom = df[df["tranche_base"].astype(str) == str(nom)]
                if len(df_nom) >= 2:
                    df = df_nom
            elif "type" in df.columns and typ:
                df_typ = df[df["type"].astype(str) == str(typ)]
                if len(df_typ) >= 2:
                    df = df_typ

            df = df[(df["priorite"] >= 0) & (df["portee"] > 0)].dropna(subset=["priorite", "portee"])
            pairs = [(float(r["priorite"]), float(r["portee"])) for _, r in df[["priorite", "portee"]].drop_duplicates().iterrows()]
            if pairs:
                return sorted(set(pairs))

        return []

    def optimiser_dichotomie_tranche(
        self,
        t_info,
        taux_cible,
        variable="priorite",
        borne_min=None,
        borne_max=None,
        tol=1e-5,
        max_iter=40,
        n_sim=20000,
    ):
        """
        Optimisation dichotomique sans bornes inventées.

        Si borne_min/borne_max ne sont pas fournies par l'appel ou par t_info,
        la méthode refuse de s'exécuter. Cela évite les bornes arbitraires
        du type 25 %, 50 %, 200 % ou 300 % du programme initial.
        """
        t_base = dict(t_info)
        taux_cible = float(taux_cible or 0.0)

        if taux_cible <= 0:
            return {
                "converge": False,
                "message": "Taux cible nul ou négatif.",
                "tranche": t_base.get("nom", ""),
            }

        if variable not in {"priorite", "portee"}:
            return {
                "converge": False,
                "message": "Variable d'optimisation non reconnue. Utiliser 'priorite' ou 'portee'.",
                "tranche": t_base.get("nom", ""),
            }

        if borne_min is None or borne_max is None:
            b_min, b_max = self._extraire_bornes_optimisation(t_base, variable)
            borne_min = b_min if borne_min is None else borne_min
            borne_max = b_max if borne_max is None else borne_max

        if borne_min is None or borne_max is None:
            return {
                "converge": False,
                "message": (
                    "Bornes d'optimisation absentes. Fournir explicitement "
                    f"{variable}_min/{variable}_max ou borne_{variable}_min/borne_{variable}_max."
                ),
                "tranche": t_base.get("nom", ""),
                "variable": variable,
            }

        borne_min = float(borne_min)
        borne_max = float(borne_max)
        if not np.isfinite(borne_min) or not np.isfinite(borne_max) or borne_max <= borne_min:
            return {
                "converge": False,
                "message": "Bornes d'optimisation invalides.",
                "tranche": t_base.get("nom", ""),
                "variable": variable,
                "borne_min": borne_min,
                "borne_max": borne_max,
            }

        def evaluer(x, seed_offset=0):
            tc = dict(t_base)
            tc[variable] = float(x)
            return self._taux_simule_candidat(tc, n_sim=n_sim, seed=12345 + seed_offset)

        res_min = evaluer(borne_min, 1)
        res_max = evaluer(borne_max, 2)
        tau_min = float(res_min.get("taux_technique", 0.0) or 0.0)
        tau_max = float(res_max.get("taux_technique", 0.0) or 0.0)

        if not (min(tau_min, tau_max) <= taux_cible <= max(tau_min, tau_max)):
            meilleur = res_min if abs(tau_min - taux_cible) <= abs(tau_max - taux_cible) else res_max
            return {
                "converge": False,
                "message": "Taux cible hors de la plage fournie par l'utilisateur.",
                "tranche": t_base.get("nom", ""),
                "variable": variable,
                "borne_min": borne_min,
                "borne_max": borne_max,
                "tau_min": tau_min,
                "tau_max": tau_max,
                "meilleur_point": meilleur,
            }

        low, high = borne_min, borne_max
        best = None

        for k in range(int(max_iter)):
            mid = 0.5 * (low + high)
            res_mid = evaluer(mid, 10 + k)
            tau_mid = float(res_mid.get("taux_technique", 0.0) or 0.0)
            best = res_mid

            if abs(tau_mid - taux_cible) <= tol:
                break

            if variable == "priorite":
                # priorité ↑ => taux ↓
                if tau_mid > taux_cible:
                    low = mid
                else:
                    high = mid
            else:
                # portée ↑ => taux ↑
                if tau_mid < taux_cible:
                    low = mid
                else:
                    high = mid

        if best is None:
            best = res_min
            k = 0

        return {
            "converge": True,
            "tranche": t_base.get("nom", ""),
            "variable": variable,
            "valeur_optimale": float(best.get(variable, 0.0) or 0.0),
            "tau_star": float(best.get("taux_technique", 0.0) or 0.0),
            "prime_star": float(best.get("prime", 0.0) or 0.0),
            "iterations": int(k + 1),
            "detail": best,
            "bornes_utilisees": {"min": borne_min, "max": borne_max, "source": "explicite"},
        }

    def frontiere_de_finetti_tranche(
        self,
        t_info,
        budget_prime_pct,
        n_points_priorite=None,
        n_points_portee=None,
        n_sim=15000,
    ):
        """
        Frontière De Finetti sans grille inventée.

        La frontière est calculée uniquement sur des couples D/C fournis
        explicitement ou présents dans le dataset labo/ML. Si aucune grille
        n'existe, la méthode refuse de produire une fausse optimisation.
        """
        t_base = dict(t_info)
        budget_prime_pct = float(budget_prime_pct or 0.0)

        if budget_prime_pct <= 0:
            return {
                "converge": False,
                "message": "Budget de prime nul ou négatif.",
                "tranche": t_base.get("nom", ""),
            }

        candidats_dc = self._extraire_grilles_finetti(t_base)
        if not candidats_dc:
            return {
                "converge": False,
                "message": (
                    "Aucune grille De Finetti explicite disponible. Fournir grille_priorites/grille_portees, "
                    "candidats_programme ou un df_ml contenant priorite et portee."
                ),
                "tranche": t_base.get("nom", ""),
                "budget": budget_prime_pct,
                "frontiere": [],
            }

        candidats = []
        seed = 5000
        for idx, (D, C) in enumerate(candidats_dc):
            tc = dict(t_base)
            tc["priorite"] = float(D)
            tc["portee"] = float(C)

            res = self._taux_simule_candidat(tc, n_sim=n_sim, seed=seed + idx)
            candidats.append(
                {
                    "D": float(D),
                    "C": float(C),
                    "tau": float(res.get("taux_technique", 0.0) or 0.0),
                    "prime": float(res.get("prime", 0.0) or 0.0),
                    "var_retenu": float(res.get("var_retenu", np.nan)),
                    "moyenne_retenu": float(res.get("moyenne_retenu", np.nan)),
                    "detail": res,
                }
            )

        admissibles = [c for c in candidats if c["tau"] <= budget_prime_pct]
        if not admissibles:
            meilleur = min(candidats, key=lambda c: abs(c["tau"] - budget_prime_pct))
            return {
                "converge": False,
                "message": "Aucun candidat sous le budget explicite. Le point le plus proche est retourné.",
                "tranche": t_base.get("nom", ""),
                "budget": budget_prime_pct,
                "optimal": meilleur,
                "frontiere": candidats,
                "source_grille": "explicite_ou_df_ml",
            }

        optimal = min(admissibles, key=lambda c: c["var_retenu"])
        return {
            "converge": True,
            "tranche": t_base.get("nom", ""),
            "budget": budget_prime_pct,
            "optimal": optimal,
            "frontiere": admissibles,
            "n_candidats": len(candidats),
            "n_admissibles": len(admissibles),
            "source_grille": "explicite_ou_df_ml",
        }

    def etape_0_validation(self):
        self._log("Validation", "Vérification des paramètres actuariels")

        if self.df_proj is None or self.df_proj.empty:
            self._alerte("CRITIQUE", "Aucune donnée projetée disponible pour le calcul.")

        if self.gnpi <= 0:
            self._alerte("CRITIQUE", "GNPI nul ou négatif.")

        if self.alpha < 0.8:
            self._alerte("CRITIQUE", f"Alpha = {self.alpha:.4f} < 0.8 : queue très lourde, résultats sensibles.")
        elif self.alpha > 4.0:
            self._alerte("WARN", f"Alpha = {self.alpha:.4f} > 4.0 : vérifier la pertinence de la loi de sévérité.")
        else:
            self._log("Alpha", f"Paramètre alpha cohérent : {self.alpha:.4f}")

        if self.lambda_ < 0.0:
            self._alerte("CRITIQUE", f"Lambda = {self.lambda_:.4f} négatif.")
        elif self.lambda_ < 0.5:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} faible : fréquence quasi nulle au-dessus du seuil.")
        elif self.lambda_ > 50:
            self._alerte("WARN", f"Lambda = {self.lambda_:.4f} élevé : vérifier le seuil de modélisation.")
        else:
            self._log("Lambda", f"Fréquence moyenne cohérente : {self.lambda_:.4f}")

        trav = [t for t in self.tranches if t.get("type") == "travaillante"]
        cat = [t for t in self.tranches if t.get("type") == "cat"]
        if not trav:
            self._alerte("WARN", "Aucune tranche travaillante dans le programme.")
        if not cat:
            self._alerte("INFO", "Aucune tranche cat : courbe de marché potentiellement non applicable.")
        self._log("Programme", f"{len(trav)} tranche(s) travaillante(s), {len(cat)} tranche(s) cat.")

    # ------------------------------------------------------------------
    # ÉTAPE 1 — BURNING COST
    # ------------------------------------------------------------------
    def etape_1_burning_cost(self):
        self._log("Burning Cost", "Calcul BC individuel par sinistre et agrégation annuelle.")
        resultats = []

        if self.df_proj is None or self.df_proj.empty:
            self.resultats_bc = []
            self._alerte("CRITIQUE", "Burning Cost impossible : df_proj vide.")
            return []

        for t_info in self.tranches:
            nom = t_info.get("nom", "Tranche")
            D = float(t_info.get("priorite", 0.0) or 0.0)
            L = float(t_info.get("portee", 0.0) or 0.0)
            aal = t_info.get("AAL")
            aad = t_info.get("AAD")
            n_rec = int(t_info.get("nb_reconstitutions", 0) or 0)
            taux_rec_list = self._get_taux_rec_list(t_info)
            cap = (n_rec + 1) * L

            df_p = self.df_proj.copy()
            if "Sprime_ultime" not in df_p.columns or "annee_surv" not in df_p.columns:
                self._alerte("CRITIQUE", f"{nom} : colonnes df_proj insuffisantes pour le BC.")
                continue
            if "coeff_stab" not in df_p.columns:
                df_p["coeff_stab"] = 1.0

            df_p["Ck"] = df_p.apply(
                lambda row: min(max(float(row.get("Sprime_ultime", 0.0)) - D, 0.0), L)
                * float(row.get("coeff_stab", 1.0) or 1.0),
                axis=1,
            )

            charges_ann = df_p.groupby("annee_surv")["Ck"].sum()
            charges_finales = []
            for ann, ch in charges_ann.items():
                ch = float(ch)
                if aad:
                    ch = max(ch - float(aad), 0.0)
                if aal:
                    ch = min(ch, float(aal))
                charges_finales.append({"annee": int(ann), "charge": float(min(ch, cap))})

            df_ch = pd.DataFrame(charges_finales)
            N = len(df_ch)
            charges_nonzero = [c["charge"] for c in charges_finales if c["charge"] > 0]
            n_nz = len(charges_nonzero)

            Pr_Rec = 0.0
            if N > 0 and L > 0:
                for C_n in df_ch["charge"].values:
                    for r_idx, t_r_i in enumerate(taux_rec_list):
                        Pr_Rec += (float(t_r_i) / 100.0) * min(L, max(float(C_n) - r_idx * L, 0.0))
                Pr_Rec /= L
            Rec = Pr_Rec / (Pr_Rec + N) if (Pr_Rec + N) > 0 else 0.0

            if n_nz < 3:
                tp = tr = tt = sigma = 0.0
                charge_moy = 0.0
                Pr_Rec = 0.0
                Rec = 0.0
                chargement_majeurs_bc = 0.0
                self._alerte("WARN", f"{nom} : BC non crédible, seulement {n_nz} année(s) non nulle(s).")
            else:
                charge_moy = float(df_ch["charge"].mean())
                chargement_majeurs_bc = self.chargement_majeurs
                tp = charge_moy / max(self.gnpi, 1.0)
                sigma = float(np.std(charges_nonzero)) / max(self.gnpi, 1.0)
                tr = tp + sigma * 0.20
                denom = max(
                    1
                    - float(t_info.get("brokage", 0.0) or 0.0)
                    - float(t_info.get("frais", 0.0) or 0.0)
                    - float(t_info.get("marge", 0.0) or 0.0)
                    - float(t_info.get("retrocession", 0.0) or 0.0),
                    0.01,
                )
                tt = (tr * (1 - Rec)) / denom

            resultats.append(
                {
                    "tranche": nom,
                    "type": t_info.get("type", ""),
                    "charge_moy": round(charge_moy, 2),
                    "n_ann_nonzero": int(n_nz),
                    "sigma_hist": round(sigma if n_nz >= 3 else 0.0, 6),
                    "Pr_Rec": round(Pr_Rec, 6),
                    "Rec": round(Rec, 6),
                    "taux_pur": round(tp, 6),
                    "taux_risque": round(tr, 6),
                    "taux_technique": round(tt, 6),
                    "chargement_majeurs": round(chargement_majeurs_bc, 6),
                    "detail_annuel": charges_finales,
                }
            )
            self._log("BC", f"{nom}: taux pur={tp:.4%}, taux technique={tt:.4%}, années non nulles={n_nz}.")

        self.resultats_bc = resultats
        return resultats

    # ------------------------------------------------------------------
    # ÉTAPE 2 — SIMULATION
    # ------------------------------------------------------------------
    def etape_2_simulation(self, n_sim=10000, seed=42):
        """
        Simulation fréquence-sévérité.
        La loi de sévérité utilisée est celle retenue dans l'interface :
        Pareto, Lognormale ou GPD. Le LLM ne choisit pas la loi à la place
        de l'utilisateur ; il exploite les paramètres déjà validés.
        """
        loi = str(getattr(self, "loi_sim", "pareto") or "pareto").lower()
        self._log(
            "Simulation",
            f"Simulation fréquence-sévérité : loi={loi}, lambda={self.lambda_:.4f}, seuil={self.seuil:,.0f}, n={n_sim:,}.",
        )
        rng = np.random.default_rng(seed)
        resultats = []

        if self.lambda_ <= 0 or self.seuil <= 0:
            self._alerte("CRITIQUE", "Simulation impossible : lambda ou seuil invalide.")
            self.resultats_sim = []
            return []
        if loi == "pareto" and self.alpha <= 0:
            self._alerte("CRITIQUE", "Simulation Pareto impossible : alpha invalide.")
            self.resultats_sim = []
            return []
        if loi == "lognormale":
            if self.mu_ln is None:
                self.mu_ln = float(np.log(max(self.seuil, 1.0)))
            if self.sigma_ln is None or self.sigma_ln <= 0:
                self._alerte("CRITIQUE", "Simulation lognormale impossible : sigma invalide.")
                self.resultats_sim = []
                return []
        if loi == "gpd":
            if self.gpd_xi is None:
                self.gpd_xi = 0.0
            if self.gpd_beta is None or self.gpd_beta <= 0:
                self._alerte("CRITIQUE", "Simulation GPD impossible : beta invalide.")
                self.resultats_sim = []
                return []

        coeffs = self.coeffs[np.isfinite(self.coeffs)]
        if len(coeffs) == 0:
            coeffs = np.array([1.0])

        def generer_sinistres(n_sin):
            if n_sin <= 0:
                return np.array([], dtype=float)
            if loi == "pareto":
                u = rng.uniform(size=n_sin)
                return self.seuil * (u ** (-1.0 / self.alpha))
            if loi == "lognormale":
                sp = rng.lognormal(float(self.mu_ln), float(self.sigma_ln), size=n_sin)
                return np.maximum(sp, self.seuil)
            if loi == "gpd":
                u = rng.uniform(size=n_sin)
                xi = float(self.gpd_xi)
                beta = float(self.gpd_beta)
                if abs(xi) < 1e-10:
                    return self.seuil - beta * np.log(np.clip(u, 1e-12, 1.0))
                return self.seuil + beta / xi * ((1.0 - np.clip(u, 1e-12, 1-1e-12)) ** (-xi) - 1.0)
            # Garde-fou : loi inconnue, on bloque plutôt que de revenir silencieusement à Pareto.
            raise ValueError(f"Loi de sévérité inconnue : {loi}")

        for t_info in self.tranches:
            nom = t_info.get("nom", "Tranche")
            D = float(t_info.get("priorite", 0.0) or 0.0)
            P = float(t_info.get("portee", 0.0) or 0.0)
            r = int(t_info.get("nb_reconstitutions", 0) or 0)
            aal = t_info.get("AAL")
            aad = t_info.get("AAD")
            cap = (r + 1) * P

            def simuler(avec_aal=True, avec_aad=True, avec_rec=True):
                charges = []
                for _ in range(int(n_sim)):
                    n_sin = rng.poisson(self.lambda_)
                    s_tot = 0.0
                    if n_sin > 0:
                        sp = generer_sinistres(int(n_sin))
                        ic = rng.choice(len(coeffs), size=int(n_sin), replace=True)
                        for k in range(int(n_sin)):
                            s = float(sp[k])
                            c = float(coeffs[ic[k]])
                            if s <= D:
                                s_i = 0.0
                            elif s <= D + P:
                                s_i = c * (s - D)
                            else:
                                s_i = c * P
                            s_tot += s_i
                    ch = s_tot
                    if avec_aad and aad:
                        ch = max(ch - float(aad), 0.0)
                    if avec_aal and aal:
                        ch = min(ch, float(aal))
                    charges.append(min(ch, cap) if avec_rec else ch)
                return np.array(charges, dtype=float)

            def calc(ch):
                p0 = float(np.mean(ch))
                sig = float(np.std(ch))
                tp = p0 / max(self.gnpi, 1.0)
                tr = (p0 + 0.2 * sig) / max(self.gnpi, 1.0)
                denom = max(
                    1
                    - float(t_info.get("brokage", 0.0) or 0.0)
                    - float(t_info.get("frais", 0.0) or 0.0)
                    - float(t_info.get("marge", 0.0) or 0.0)
                    - float(t_info.get("retrocession", 0.0) or 0.0),
                    0.01,
                )
                tt = tr / denom
                return round(tp, 6), round(tr, 6), round(tt, 6), round(sig / max(self.gnpi, 1.0), 6)

            c_base = simuler(True, True, True)
            c_saal = simuler(False, True, True)
            c_saad = simuler(True, False, True)
            c_srec = simuler(True, True, False)

            tp, tr, tt, sigma_sim = calc(c_base)
            _, _, tt_aal, _ = calc(c_saal)
            _, _, tt_aad, _ = calc(c_saad)
            _, _, tt_rec, _ = calc(c_srec)

            parametres = {
                "loi": loi,
                "lambda": round(self.lambda_, 6),
                "seuil": round(self.seuil, 2),
                "n_sim": int(n_sim),
                "seed": int(seed),
            }
            if loi == "pareto":
                parametres["alpha"] = round(self.alpha, 6)
            elif loi == "lognormale":
                parametres["mu"] = round(float(self.mu_ln), 6)
                parametres["sigma"] = round(float(self.sigma_ln), 6)
            elif loi == "gpd":
                parametres["xi"] = round(float(self.gpd_xi), 6)
                parametres["beta"] = round(float(self.gpd_beta), 2)

            resultats.append(
                {
                    "tranche": nom,
                    "type": t_info.get("type", ""),
                    "taux_pur": tp,
                    "taux_risque": tr,
                    "taux_technique": tt,
                    "sigma_sim": sigma_sim,
                    "chargement_majeurs": round(self.chargement_majeurs, 6),
                    "sans_aal": tt_aal,
                    "sans_aad": tt_aad,
                    "sans_rec": tt_rec,
                    "impact_aal": round(tt_aal - tt, 6),
                    "impact_aad": round(tt_aad - tt, 6),
                    "impact_rec": round(tt_rec - tt, 6),
                    "parametres_simulation": parametres,
                    "loi_severite": loi,
                    "param_lambda": round(self.lambda_, 6),
                    "param_seuil": round(self.seuil, 2),
                    "n_sim": int(n_sim),
                    "seed": int(seed),
                }
            )
            self._log("Simulation", f"{nom}: loi={loi}, taux pur={tp:.4%}, taux technique={tt:.4%}.")

        self.resultats_sim = resultats
        return resultats

    # ------------------------------------------------------------------
    # ÉTAPE 3 — CONTRÔLES BC / SIMULATION
    # ------------------------------------------------------------------
    def etape_3_controles(self):
        self._log("Contrôles", "Vérification de la cohérence BC / Simulation.")
        bc_map = {r.get("tranche"): r for r in self.resultats_bc}
        sim_map = {r.get("tranche"): r for r in self.resultats_sim}

        for t in self.tranches:
            nom = t.get("nom", "")
            bc_tt = float(bc_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            si_tt = float(sim_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)

            if t.get("type") == "travaillante" and bc_tt > 0 and si_tt > 0:
                ecart = abs(bc_tt - si_tt) / max(bc_tt, 1e-12)
                if ecart > 0.50:
                    self._alerte("CRITIQUE", f"{nom}: écart BC/Simulation = {ecart:.0%}, analyse complémentaire requise.")
                elif ecart > 0.30:
                    self._alerte("WARN", f"{nom}: écart BC/Simulation = {ecart:.0%}, justification nécessaire.")
                else:
                    self._log("Contrôle BC/Simulation", f"{nom}: écart={ecart:.0%}, convergence acceptable.")

            if t.get("type") == "cat" and bc_tt == 0:
                self._log("Contrôle Cat", f"{nom}: BC nul cohérent pour une tranche cat non touchée historiquement.")

    # ------------------------------------------------------------------
    # ÉTAPE 4 — MARKET CURVE
    # ------------------------------------------------------------------
    def etape_4_market_curve(self, r2_min=0.40):
        cat_tranches = [t for t in self.tranches if t.get("type") != "travaillante"]
        if not cat_tranches:
            self._log("Courbe de marché", "Aucune tranche non travaillante/cat : courbe de marché non appliquée.")
            self.resultats_mkt = []
            return []
        if self.df_mkt is None or len(self.df_mkt) == 0:
            self._alerte("INFO", "Données marché non fournies : courbe de marché ignorée.")
            self.resultats_mkt = []
            return []

        df_mkt = self.df_mkt.copy().replace([np.inf, -np.inf], np.nan)
        if not {"midpoints", "ROLs"}.issubset(df_mkt.columns):
            self._alerte("CRITIQUE", "Données marché insuffisantes : colonnes midpoints et ROLs requises.")
            self.resultats_mkt = []
            return []

        df_mkt["midpoints"] = pd.to_numeric(df_mkt["midpoints"], errors="coerce")
        df_mkt["ROLs"] = pd.to_numeric(df_mkt["ROLs"], errors="coerce")
        df_mkt = df_mkt[(df_mkt["midpoints"] > 0) & (df_mkt["ROLs"] > 0)].dropna()

        if len(df_mkt) < 8:
            self._alerte("WARN", f"Courbe de marché peu exploitable : seulement {len(df_mkt)} point(s).")
            self.resultats_mkt = []
            return []

        self._log("Courbe de marché", f"Ajustement ROL = a x^(-b) sur {len(df_mkt)} point(s).")

        def fit_power(x, y):
            lx = np.log(x)
            ly = np.log(y)
            c = np.polyfit(lx, ly, 1)
            a = float(np.exp(c[1]))
            b = float(-c[0])
            ly_pred = np.polyval(c, lx)
            r2 = 1 - np.sum((ly - ly_pred) ** 2) / (np.sum((ly - ly.mean()) ** 2) + 1e-10)
            return a, b, float(r2)

        def calc_taux_cat(t, a, b):
            x = (float(t.get("priorite", 0.0)) + float(t.get("portee", 0.0)) / 2.0) / max(self.gnpi, 1.0)
            rol = a * (x ** (-b))
            tp = rol * float(t.get("portee", 0.0)) / max(self.gnpi, 1.0)
            tr = tp * 1.002
            denom = max(
                1
                - float(t.get("brokage", 0.0) or 0.0)
                - float(t.get("frais", 0.0) or 0.0)
                - float(t.get("marge", 0.0) or 0.0)
                - float(t.get("retrocession", 0.0) or 0.0),
                0.01,
            )
            tt = tr / denom
            return {
                "tranche": t.get("nom", ""),
                "type": t.get("type", ""),
                "x_norm": round(x, 6),
                "rol": round(rol, 6),
                "taux_pur": round(tp, 6),
                "taux_tech": round(tt, 6),
                "taux": round(tt, 6),
                "chargement_majeurs": round(self.chargement_majeurs, 6),
            }

        best = None
        for q in [0.40, 0.60, 0.80, 1.00, 0.20]:
            try:
                mq = np.quantile(df_mkt["midpoints"], q)
                df_q = df_mkt[df_mkt["midpoints"] <= mq]
                if len(df_q) < 8:
                    continue
                a, b, r2 = fit_power(df_q["midpoints"].values, df_q["ROLs"].values)
                if b <= 0:
                    continue
                taux_tranches = [calc_taux_cat(t, a, b) for t in cat_tranches]
                if any(tt.get("taux", 0) <= 0 for tt in taux_tranches):
                    continue
                score = r2 + (0.3 if r2 >= r2_min else 0.0) + 0.01 * len(df_q)
                if best is None or score > best["score"]:
                    best = {
                        "a": a,
                        "b": b,
                        "r2": r2,
                        "n": len(df_q),
                        "quantile": q,
                        "taux_tranches": taux_tranches,
                        "score": score,
                    }
            except Exception:
                continue

        if best is None:
            self._alerte("CRITIQUE", "Aucun ajustement valide de courbe de marché.")
            self.resultats_mkt = []
            return []

        if best["r2"] < r2_min:
            self._alerte("WARN", f"Courbe de marché de faible qualité : R2={best['r2']:.3f}.")
        else:
            self._log("Courbe de marché", f"R2={best['r2']:.3f}, N={best['n']}, a={best['a']:.5f}, b={best['b']:.4f}.")

        all_tts = []
        cat_map = {tt["tranche"]: tt for tt in best["taux_tranches"]}
        for t in self.tranches:
            nom = t.get("nom", "")
            if nom in cat_map:
                all_tts.append(cat_map[nom])
            else:
                all_tts.append(
                    {
                        "tranche": nom,
                        "type": t.get("type", ""),
                        "x_norm": 0,
                        "rol": 0,
                        "taux_pur": 0,
                        "taux_tech": 0,
                        "taux": 0,
                        "chargement_majeurs": 0,
                    }
                )
        self.resultats_mkt = all_tts
        return all_tts

    # ------------------------------------------------------------------
    # ÉTAPE 5 — RAPPORT
    # ------------------------------------------------------------------
    def etape_5_rapport(self):
        self._log("Rapport", "Sélection : max(BC, Simulation) pour travaillante ; max(Simulation, Marché) sinon.")
        mkt_map = {r.get("tranche"): r.get("taux", 0.0) for r in self.resultats_mkt}
        rows = []
        pt = 0.0

        for idx_t, t in enumerate(self.tranches):
            nom = t.get("nom", f"Tranche {idx_t + 1}")
            bc_tt = _lookup_taux(self.resultats_bc, nom, idx_t, "taux_technique")
            si_tt = _lookup_taux(self.resultats_sim, nom, idx_t, "taux_technique")
            mkt = float(mkt_map.get(nom, 0.0) or 0.0) if t.get("type") != "travaillante" else 0.0

            if t.get("type") == "travaillante":
                taux = max(bc_tt, si_tt)
                meth = f"max(BC={bc_tt:.4%}, Simulation={si_tt:.4%})"
            else:
                taux = max(si_tt, mkt)
                meth = f"max(Simulation={si_tt:.4%}, Marché={mkt:.4%})"

            prime = self.gnpi * taux
            pt += prime
            ecart = abs(bc_tt - si_tt) / max(bc_tt, 1e-12) * 100 if bc_tt > 0 else 0.0
            rows.append(
                {
                    "tranche": nom,
                    "type": t.get("type", ""),
                    "taux_bc": round(bc_tt, 6),
                    "taux_sim": round(si_tt, 6),
                    "taux_mkt": round(mkt, 6),
                    "taux_retenu": round(taux, 6),
                    "methode": meth,
                    "prime_AED": round(prime, 2),
                    "ecart_bc_sim_pct": round(ecart, 1),
                }
            )
            self._log("Sélection", f"{nom}: {meth}, prime={prime:,.0f} AED.")

        self.rapport_rows = rows
        self.prime_totale = pt
        return rows, pt

    # ------------------------------------------------------------------
    # ÉTAPE 6 — OPTIMISATION SANS BORNES PAR DÉFAUT
    # ------------------------------------------------------------------
    def etape_6_optimisation(self):
        """
        Génère des variantes comparables sans pourcentages prédéfinis.

        Règle stricte :
        - aucun multiplicateur 95 %, 105 %, 110 %, etc. ;
        - aucune borne 25 %, 50 %, 200 %, 300 % ;
        - les variantes ne sont produites que si des bornes/grilles explicites
          existent dans les données ou dans le dataset labo/ML.
        """
        self._log(
            "Optimisation",
            "Recherche de programmes alternatifs sans bornes par défaut.",
            "Dichotomie et De Finetti utilisent uniquement des bornes ou grilles explicites.",
        )

        sim_map = {r.get("tranche"): r for r in self.resultats_sim}
        bc_map = {r.get("tranche"): r for r in self.resultats_bc}
        mkt_map = {r.get("tranche"): r for r in self.resultats_mkt}

        def taux_base(t):
            nom = t.get("nom", "")
            bc = float(bc_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            sim = float(sim_map.get(nom, {}).get("taux_technique", 0.0) or 0.0)
            mkt = float(mkt_map.get(nom, {}).get("taux", 0.0) or 0.0)
            if t.get("type") == "travaillante":
                return max(bc, sim)
            return max(sim, mkt)

        def convergence_ref(t):
            nom = t.get("nom", "")
            vals = []
            for v in [
                bc_map.get(nom, {}).get("taux_technique", 0.0),
                sim_map.get(nom, {}).get("taux_technique", 0.0),
                mkt_map.get(nom, {}).get("taux", 0.0),
            ]:
                v = float(v or 0.0)
                if v > 0:
                    vals.append(v)
            if len(vals) <= 1:
                return 0.0
            return float(np.std(vals) / max(np.mean(vals), 1e-12))

        def construire_programme_depuis_tranches(label, tranches_alt, methode):
            prime = 0.0
            protection = 0.0
            variance_retenue = 0.0
            convergence = 0.0
            ecart_structure = 0.0
            tranches_calc = []

            for idx, (t0, t_alt_in) in enumerate(zip(self.tranches, tranches_alt)):
                t_alt = dict(t_alt_in)
                res = self._taux_simule_candidat(t_alt, n_sim=3000, seed=7000 + idx)
                taux = float(res.get("taux_technique", 0.0) or 0.0)
                prime_t = float(res.get("prime", 0.0) or 0.0)

                if taux <= 0:
                    taux = taux_base(t0)
                    prime_t = self.gnpi * taux

                D0 = float(t0.get("priorite", 0.0) or 0.0)
                C0 = float(t0.get("portee", 0.0) or 0.0)
                D1 = float(t_alt.get("priorite", 0.0) or 0.0)
                C1 = float(t_alt.get("portee", 0.0) or 0.0)
                rec0 = int(t0.get("nb_reconstitutions", 0) or 0)
                rec1 = int(t_alt.get("nb_reconstitutions", 0) or 0)

                prime += prime_t
                protection += C1 * (rec1 + 1)
                variance_retenue += float(res.get("var_retenu", 0.0) or 0.0)
                convergence += convergence_ref(t0)

                if D0 > 0:
                    ecart_structure += abs(D1 / D0 - 1.0)
                if C0 > 0:
                    ecart_structure += abs(C1 / C0 - 1.0)
                ecart_structure += abs(rec1 - rec0) / max(rec0 + 1, 1)

                t_alt["_taux"] = taux
                t_alt["_prime"] = prime_t
                t_alt["_methode_optimisation"] = methode
                t_alt["_var_retenu"] = float(res.get("var_retenu", 0.0) or 0.0)
                tranches_calc.append(t_alt)

            n = max(len(self.tranches), 1)
            taux_global = prime / max(self.gnpi, 1.0)
            variance_moyenne = variance_retenue / n
            convergence_moyenne = convergence / n
            ecart_structure_moyen = ecart_structure / n
            score = -np.log1p(max(variance_moyenne, 0.0)) - 2.0 * convergence_moyenne - 1.5 * ecart_structure_moyen

            return {
                "label": label,
                "description": "Programme évalué sans borne ni multiplicateur par défaut.",
                "methode_optimisation": methode,
                "tranches": tranches_calc,
                "prime": round(prime, 2),
                "taux_global": round(taux_global, 6),
                "protection_theorique": round(protection, 2),
                "variance_proxy": round(float(variance_moyenne), 2),
                "indice_convergence_methodes": round(float(max(0.0, 1.0 - convergence_moyenne)) * 100, 2),
                "indice_comparabilite": round(float(max(0.0, 1.0 - ecart_structure_moyen)) * 100, 2),
                "score_de_finetti": round(float(score), 6),
            }

        variantes = {
            "programme_initial": construire_programme_depuis_tranches(
                "Programme initial",
                [dict(t) for t in self.tranches],
                "programme_initial",
            )
        }

        # Variante par dichotomie : uniquement si des bornes explicites existent.
        tranches_dicho = []
        ok_dicho = False
        for t in self.tranches:
            t_alt = dict(t)
            cible = taux_base(t)
            res_dicho = self.optimiser_dichotomie_tranche(
                t,
                taux_cible=cible,
                variable="priorite",
                n_sim=2500,
                tol=1e-5,
                max_iter=25,
            ) if cible > 0 else {"converge": False, "message": "Taux de référence nul."}

            detail = res_dicho.get("detail") or res_dicho.get("meilleur_point") or {}
            if res_dicho.get("converge") and detail:
                t_alt["priorite"] = self._arrondir_aed(detail.get("priorite", t.get("priorite", 0.0)), minimum=0.0)
                t_alt["_resultat_dichotomie"] = res_dicho
                ok_dicho = True
            else:
                t_alt["_resultat_dichotomie"] = res_dicho
                self._alerte("INFO", f"{t.get('nom', 'Tranche')} : dichotomie non exécutée — {res_dicho.get('message', 'bornes absentes')} ")
            tranches_dicho.append(t_alt)

        if ok_dicho:
            variantes["structure_dichotomie"] = construire_programme_depuis_tranches(
                "Structure par dichotomie",
                tranches_dicho,
                "dichotomie_priorite_bornes_explicites",
            )
        else:
            variantes["structure_dichotomie"] = {
                "label": "Structure par dichotomie",
                "description": "Non générée : aucune borne explicite exploitable.",
                "methode_optimisation": "dichotomie_non_executee_bornes_absentes",
                "tranches": tranches_dicho,
                "prime": variantes["programme_initial"]["prime"],
                "taux_global": variantes["programme_initial"]["taux_global"],
                "protection_theorique": variantes["programme_initial"]["protection_theorique"],
                "variance_proxy": variantes["programme_initial"]["variance_proxy"],
                "indice_convergence_methodes": variantes["programme_initial"]["indice_convergence_methodes"],
                "indice_comparabilite": 100.0,
                "score_de_finetti": variantes["programme_initial"]["score_de_finetti"],
                "diagnostic": "Dichotomie non exécutée : bornes explicites absentes.",
            }

        # Variante De Finetti : uniquement si une grille explicite ou df_ml existe.
        tranches_finetti = []
        ok_finetti = False
        for t in self.tranches:
            t_alt = dict(t)
            budget = max(taux_base(t), 0.000001)
            res_fin = self.frontiere_de_finetti_tranche(
                t,
                budget_prime_pct=budget,
                n_sim=1500,
            )
            opt = res_fin.get("optimal") or {}
            if opt and res_fin.get("frontiere"):
                t_alt["priorite"] = self._arrondir_aed(opt.get("D", t.get("priorite", 0.0)), minimum=0.0)
                t_alt["portee"] = self._arrondir_aed(opt.get("C", t.get("portee", 0.0)), minimum=0.0)
                t_alt["_resultat_finetti"] = res_fin
                ok_finetti = True
            else:
                t_alt["_resultat_finetti"] = res_fin
                self._alerte("INFO", f"{t.get('nom', 'Tranche')} : De Finetti non exécuté — {res_fin.get('message', 'grille absente')} ")
            tranches_finetti.append(t_alt)

        if ok_finetti:
            variantes["structure_de_finetti"] = construire_programme_depuis_tranches(
                "Structure De Finetti",
                tranches_finetti,
                "frontiere_de_finetti_grille_explicite",
            )
        else:
            variantes["structure_de_finetti"] = {
                "label": "Structure De Finetti",
                "description": "Non générée : aucune grille explicite ou df_ml exploitable.",
                "methode_optimisation": "finetti_non_execute_grille_absente",
                "tranches": tranches_finetti,
                "prime": variantes["programme_initial"]["prime"],
                "taux_global": variantes["programme_initial"]["taux_global"],
                "protection_theorique": variantes["programme_initial"]["protection_theorique"],
                "variance_proxy": variantes["programme_initial"]["variance_proxy"],
                "indice_convergence_methodes": variantes["programme_initial"]["indice_convergence_methodes"],
                "indice_comparabilite": 100.0,
                "score_de_finetti": variantes["programme_initial"]["score_de_finetti"],
                "diagnostic": "De Finetti non exécuté : grille explicite ou df_ml absent.",
            }

        initial_prime = variantes["programme_initial"]["prime"]
        for key, v in variantes.items():
            v["ecart_prime_vs_initial"] = round((v["prime"] - initial_prime) / max(initial_prime, 1.0), 6)
            if "diagnostic" in v:
                continue
            if key == "programme_initial":
                v["diagnostic"] = "Programme proposé par la cédante, utilisé comme base de comparaison."
            elif abs(v["ecart_prime_vs_initial"]) <= 0.15 and v["indice_comparabilite"] >= 70:
                v["diagnostic"] = "Programme alternatif comparable, calculé sans paramètres par défaut."
            else:
                v["diagnostic"] = "Programme indicatif : écart au programme initial à documenter."

        candidats = {
            k: v for k, v in variantes.items()
            if k != "programme_initial" and not str(v.get("methode_optimisation", "")).endswith("absente")
        }
        programme_recommande_key = max(candidats, key=lambda k: candidats[k]["score_de_finetti"]) if candidats else "programme_initial"
        variantes["programme_recommande"] = dict(variantes[programme_recommande_key])
        variantes["programme_recommande"]["cle_source"] = programme_recommande_key

        self._log(
            "Optimisation",
            "Variantes générées sans multiplicateurs fixes. Si aucune borne/grille explicite n'est fournie, l'optimisation est déclarée non exécutée.",
        )
        return variantes


    # ------------------------------------------------------------------
    # RAPPORT TEXTE
    # ------------------------------------------------------------------
    def generer_rapport_texte(self):
        taux_global = self.prime_totale / max(self.gnpi, 1.0)
        lignes = [
            "=" * 60,
            "RAPPORT DE TARIFICATION — AGENT PYTHON AUTONOME",
            "=" * 60,
            f"GNPI         : {self.gnpi:,.0f} AED",
            f"Prime totale : {self.prime_totale:,.0f} AED",
            f"Taux global  : {taux_global:.4%}",
            f"Tranches     : {len(self.tranches)}",
            "=" * 60,
            "",
            "PARAMÈTRES",
            f"Alpha        : {self.alpha:.4f}",
            f"Lambda       : {self.lambda_:.4f}",
            f"Seuil        : {self.seuil:,.0f} AED",
            f"Pm proxy     : {self.Pm_proxy:,.0f} AED",
            f"Charg. majeurs : {self.chargement_majeurs:.4%}",
            "",
            "RÉSULTATS PAR TRANCHE",
        ]

        for r in self.rapport_rows:
            statut = "DIVERGENCE" if r.get("ecart_bc_sim_pct", 0) > 30 else "COHÉRENT"
            lignes += [
                "",
                f"[{str(r.get('type','')).upper()}] {r.get('tranche','')}",
                f"BC={r.get('taux_bc',0):.4%} | Simulation={r.get('taux_sim',0):.4%} | Marché={r.get('taux_mkt',0):.4%}",
                f"Retenu : {r.get('taux_retenu',0):.4%} ({r.get('methode','')})",
                f"Prime  : {r.get('prime_AED',0):,.0f} AED | Statut : {statut} | Ecart BC/Sim : {r.get('ecart_bc_sim_pct',0):.0f}%",
            ]

        if self.anomalies:
            lignes += ["", "ALERTES"]
            for a in self.anomalies:
                lignes.append(f"[{a.get('niveau','')}] {a.get('message','')}")

        lignes += ["", "JOURNAL DES DÉCISIONS"]
        for entry in self.log:
            lignes.append(
                f"[{entry.get('etape','')}] {entry.get('decision','')}"
                + (f" — {entry.get('detail','')}" if entry.get("detail") else "")
            )
        lignes += ["", "=" * 60]
        return "\n".join(lignes)

    # ------------------------------------------------------------------
    # PIPELINE COMPLET
    # ------------------------------------------------------------------
    def run(self, n_sim=10000):
        self.etape_0_validation()
        self.etape_1_burning_cost()
        self.etape_2_simulation(n_sim)
        self.etape_3_controles()
        self.etape_4_market_curve()
        self.etape_5_rapport()
        self.variantes = self.etape_6_optimisation()
        return self.generer_rapport_texte()
