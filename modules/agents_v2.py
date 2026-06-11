"""
Atlantic Re IA — Agents V2 module
AgentRaisonnement, AgentCritique, AgentML, AgentMemoireMetier,
AgentChallenger, AgentOptimisationProgramme, AgentVariantesLeader.

AJOUT : AgentVariantesLeader
  Reçoit les taux calculés (BC + Sim + Mkt) et utilise Claude pour proposer
  des variantes de programme commercialement pertinentes en vue d'une
  position leader. Ne recalcule pas — raisonne sur des chiffres vrais.
"""
import streamlit as st
import numpy as np
import pandas as pd
import json
from datetime import datetime
from modules.ui import tableau_resultats, card
from modules.db import _get_conn, _ph, db_init


# ════════════════════════════════════════════════════════════════════
# AGENTS EXISTANTS — inchangés
# ════════════════════════════════════════════════════════════════════

class AgentRaisonnement:
    def planifier(self, contexte):
        plan = []
        def add(code, titre, justification, priorite="normale"):
            plan.append({"code": code, "titre": titre,
                         "justification": justification, "priorite": priorite})
        add("validation", "Valider les paramètres",
            "Contrôler alpha, lambda, GNPI, tranches.", "haute")
        if contexte.get("has_triangle"):
            add("burning_cost", "Calculer le Burning Cost",
                "Triangle disponible — lecture historique.", "haute")
        else:
            add("missing_triangle", "Bloquer le BC",
                "Aucune donnée projetée — BC non simulable.", "critique")
        add("simulation", "Lancer la simulation",
            "Comparer expérience historique et vision stochastique.", "haute")
        if contexte.get("has_market"):
            add("market_curve", "Ajuster la Market Curve",
                "Données marché disponibles — benchmark cat.", "normale")
        else:
            add("market_curve_skip", "Ignorer la Market Curve",
                "Aucune donnée marché fiable.", "normale")
        add("critique", "Auditer les résultats",
            "Détecter incohérences et taux extrêmes.", "haute")
        if contexte.get("n_rows", 0) >= 30:
            add("machine_learning", "Tester des modèles ML",
                "Volume minimal disponible.", "normale")
        else:
            add("machine_learning_skip", "Ne pas surinterpréter le ML",
                "Volume trop faible pour ML robuste.", "normale")
        add("selection", "Sélectionner le taux retenu",
            "Appliquer règle prudente par tranche.", "haute")
        add("negociation", "Proposer des variantes",
            "Programmes selon intérêt cédante/réassureur.", "normale")
        return plan


class AgentCritique:
    def __init__(self, seuil_ecart_warn=0.30,
                 seuil_ecart_critique=0.50, seuil_taux_extreme=0.50):
        self.seuil_ecart_warn     = seuil_ecart_warn
        self.seuil_ecart_critique = seuil_ecart_critique
        self.seuil_taux_extreme   = seuil_taux_extreme

    @staticmethod
    def _map_by_name(rows):
        return {r.get("tranche", r.get("Tranche", "")): r for r in (rows or [])}

    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "": return default
            if isinstance(x, str):
                return float(x.replace("%", "").replace(",", ".").strip())
            return float(x)
        except: return default

    def auditer(self, tranches, gnpi, resultats_bc, resultats_sim,
                resultats_mkt, rapport_rows):
        alertes = []; decisions = []; score = 100
        bc_map  = self._map_by_name(resultats_bc)
        sim_map = self._map_by_name(resultats_sim)
        mkt_map = self._map_by_name(resultats_mkt)
        rpt_map = self._map_by_name(rapport_rows)

        def alerte(niveau, tranche, message, impact=-5):
            nonlocal score
            alertes.append({"niveau": niveau, "tranche": tranche,
                             "message": message})
            score += impact

        for i, t in enumerate(tranches or []):
            nom = t.get("nom", f"Tranche {i+1}")
            typ = t.get("type", "")
            bc  = bc_map.get(nom, {});  sim = sim_map.get(nom, {})
            rpt = rpt_map.get(nom, {})
            bc_pur    = self._num(bc.get("taux_pur"))
            bc_risque = self._num(bc.get("taux_risque"))
            bc_tech   = self._num(bc.get("taux_technique"))
            sim_tech  = self._num(sim.get("taux_technique"))
            retenu    = self._num(rpt.get("taux_retenu"))
            n_nz      = int(self._num(bc.get("n_ann_nonzero"), 0))

            if bc_tech > 0 and not (bc_pur <= bc_risque <= bc_tech + 1e-12):
                alerte("CRITIQUE", nom,
                       "Hiérarchie BC incohérente : τ_pur ≤ τ_risque ≤ τ_tech non respectée.", -15)
            if n_nz < 3 and typ == "travaillante":
                alerte("WARN", nom,
                       f"BC fragile : {n_nz} année(s) non nulle(s). Simulation prioritaire.", -6)
            elif n_nz < 3 and typ == "cat":
                decisions.append({"tranche": nom,
                                   "decision": "BC nul acceptable pour tranche cat."})
            if bc_tech > 0 and sim_tech > 0:
                ecart = abs(bc_tech - sim_tech) / max(bc_tech, 1e-12)
                if ecart >= self.seuil_ecart_critique:
                    alerte("CRITIQUE", nom,
                           f"Écart BC/Sim très élevé : {ecart:.0%}. Vérifier seuil et stabilisation.", -15)
                elif ecart >= self.seuil_ecart_warn:
                    alerte("WARN", nom,
                           f"Écart BC/Sim significatif : {ecart:.0%}. Justification obligatoire.", -8)
            for label, val in [("BC", bc_tech), ("Sim", sim_tech), ("Retenu", retenu)]:
                if val < 0:
                    alerte("CRITIQUE", nom, f"Taux {label} négatif.", -20)
                if 0 < val > self.seuil_taux_extreme:
                    alerte("CRITIQUE", nom,
                           f"Taux {label} > {self.seuil_taux_extreme:.0%}.", -20)
            if t.get("portee", 0) <= 0 or t.get("priorite", 0) < 0:
                alerte("CRITIQUE", nom, "Priorité ou portée invalide.", -20)

        score   = max(0, min(100, score))
        verdict = ("ROBUSTE" if score >= 85
                   else "ACCEPTABLE AVEC RÉSERVES" if score >= 65
                   else "À REVOIR")
        return {
            "synthese": {"score": score, "verdict": verdict,
                         "nb_alertes": len(alertes),
                         "nb_critiques": sum(1 for a in alertes if a["niveau"] == "CRITIQUE"),
                         "nb_warn":     sum(1 for a in alertes if a["niveau"] == "WARN")},
            "alertes": alertes, "decisions": decisions
        }


class AgentML:
    def __init__(self, random_state=42): self.random_state = random_state

    def entrainer_depuis_df_proj(self, df, target="Sprime_ultime"):
        try:
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            from sklearn.tree import DecisionTreeRegressor
            from sklearn.ensemble import RandomForestRegressor
        except Exception as e:
            return {"disponible": False,
                    "message": f"scikit-learn indisponible : {e}",
                    "modeles": [], "meilleur_modele": None, "importance": []}

        if df is None or df.empty or target not in df.columns:
            return {"disponible": False, "message": "Target indisponible.",
                    "modeles": [], "meilleur_modele": None, "importance": []}

        data = df.copy().replace([np.inf, -np.inf], np.nan)
        y    = pd.to_numeric(data[target], errors="coerce")
        X    = data.drop(columns=[target], errors="ignore")
        keep = [c for c in X.columns if X[c].notna().mean() >= 0.60]
        X    = X[keep]
        for c in X.columns:
            if X[c].dtype == "object": X[c] = X[c].astype(str).fillna("NA")
            else: X[c] = pd.to_numeric(X[c], errors="coerce")
        mask = y.notna(); X = X.loc[mask].copy(); y = y.loc[mask].copy()
        if len(X) < 30:
            return {"disponible": False,
                    "message": "Moins de 30 observations exploitables.",
                    "modeles": [], "meilleur_modele": None, "importance": []}
        X_enc = pd.get_dummies(X, dummy_na=True).fillna(0)
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_enc, y, test_size=0.25, random_state=self.random_state)
        models = {
            "Arbre": DecisionTreeRegressor(
                max_depth=4, min_samples_leaf=5, random_state=self.random_state),
            "Random Forest": RandomForestRegressor(
                n_estimators=250, max_depth=8, min_samples_leaf=3,
                random_state=self.random_state, n_jobs=-1),
        }
        try:
            from xgboost import XGBRegressor
            models["XGBoost"] = XGBRegressor(
                n_estimators=300, max_depth=4, learning_rate=0.05,
                subsample=0.85, colsample_bytree=0.85,
                objective="reg:squarederror", random_state=self.random_state)
        except: pass

        resultats = []; best_name = None; best_mae = None; best_model = None
        for name, model in models.items():
            try:
                model.fit(X_tr, y_tr)
                pred = model.predict(X_te)
                mae  = float(mean_absolute_error(y_te, pred))
                rmse = float(np.sqrt(mean_squared_error(y_te, pred)))
                r2   = float(r2_score(y_te, pred))
                resultats.append({"modele": name, "MAE": mae, "RMSE": rmse,
                                   "R2": r2, "n_train": int(len(X_tr)),
                                   "n_test": int(len(X_te))})
                if best_mae is None or mae < best_mae:
                    best_mae = mae; best_name = name; best_model = model
            except Exception as e:
                resultats.append({"modele": name, "MAE": None, "RMSE": None,
                                   "R2": None, "erreur": str(e)})

        importance = []
        if best_model is not None and hasattr(best_model, "feature_importances_"):
            imp = (pd.Series(best_model.feature_importances_,
                             index=X_enc.columns)
                   .sort_values(ascending=False).head(10))
            importance = [{"variable": k, "importance": float(v)}
                          for k, v in imp.items()]
        return {"disponible": True,
                "message": "Benchmark statistique exécuté. Interprétation prudente recommandée.",
                "modeles": resultats, "meilleur_modele": best_name,
                "importance": importance}


class AgentMemoireMetier:
    @staticmethod
    def _to_float(x, default=0.0):
        try:
            if x is None or x == "": return default
            if isinstance(x, str):
                s = x.replace("%", "").replace(" ", "").replace(",", ".")
                val = float(s)
                return val / 100 if "%" in x or val > 1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _row_get(row, *keys, default=None):
        for k in keys:
            if isinstance(row, dict) and k in row: return row.get(k)
        return default

    def charger_rapports_historiques(self, user_email,
                                      current_session_id=None, limite=100):
        try:
            con, db = _get_conn(); cur = con.cursor(); p = _ph()
            if current_session_id:
                cur.execute(
                    f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json
                        FROM sessions s JOIN resultats r ON r.session_id=s.id
                        WHERE s.user_email={p} AND r.etape='rapport' AND s.id!={p}
                        ORDER BY s.updated_at DESC LIMIT {int(limite)}""",
                    (user_email, current_session_id))
            else:
                cur.execute(
                    f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json
                        FROM sessions s JOIN resultats r ON r.session_id=s.id
                        WHERE s.user_email={p} AND r.etape='rapport'
                        ORDER BY s.updated_at DESC LIMIT {int(limite)}""",
                    (user_email,))
            rows = cur.fetchall(); con.close()
        except: return []
        historiques = []
        for sid, nom, gnpi_h, data_json in rows:
            try:
                d  = json.loads(data_json)
                rr = d.get("rows", []); pt = d.get("prime_totale", 0)
                if rr:
                    historiques.append({"session_id": sid, "nom_session": nom,
                                        "gnpi": gnpi_h, "prime_totale": pt,
                                        "rows": rr})
            except: continue
        return historiques

    def benchmark(self, user_email, tranches, rapport_rows, gnpi,
                  current_session_id=None):
        historiques = self.charger_rapports_historiques(
            user_email, current_session_id=current_session_id)
        if not historiques:
            return {"disponible": False,
                    "message": "Aucun ancien rapport exploitable dans la mémoire métier.",
                    "comparaisons": [], "synthese": {}}
        current_by_type = {}
        for r in rapport_rows or []:
            typ  = str(self._row_get(r, "type", "Type", default="")).lower()
            taux = self._to_float(self._row_get(r, "taux_retenu", "Taux retenu", default=0))
            if typ and taux > 0:
                current_by_type.setdefault(typ, []).append(taux)
        hist_by_type = {}; hist_global = []
        for h in historiques:
            rows = h.get("rows", [])
            pt   = self._to_float(h.get("prime_totale", 0))
            gh   = self._to_float(h.get("gnpi", 0))
            if gh > 0 and pt > 0: hist_global.append(pt / gh)
            for r in rows:
                typ  = str(self._row_get(r, "type", "Type", default="")).lower()
                taux = self._to_float(self._row_get(r, "taux_retenu", "Taux retenu", default=0))
                if typ and taux > 0:
                    hist_by_type.setdefault(typ, []).append(taux)
        comparaisons = []
        for typ, vals in current_by_type.items():
            if typ not in hist_by_type or len(hist_by_type[typ]) < 2: continue
            cur_med  = float(np.median(vals))
            hist_med = float(np.median(hist_by_type[typ]))
            hist_q25 = float(np.quantile(hist_by_type[typ], 0.25))
            hist_q75 = float(np.quantile(hist_by_type[typ], 0.75))
            ecart    = (cur_med - hist_med) / max(hist_med, 1e-12)
            comparaisons.append({
                "type": typ, "taux_dossier": cur_med,
                "mediane_historique": hist_med,
                "q25_historique": hist_q25, "q75_historique": hist_q75,
                "ecart_vs_mediane": ecart,
                "diagnostic": ("au-dessus" if ecart > 0.20
                               else "sous la référence" if ecart < -0.20
                               else "proche de l'historique"),
                "n_reference": len(hist_by_type[typ])
            })
        pt_curr = sum(
            self._to_float(self._row_get(r, "prime_MAD", "Prime (MAD)", default=0))
            for r in rapport_rows or [])
        tg = pt_curr / gnpi if gnpi else 0
        return {
            "disponible": True, "message": "Mémoire métier activée.",
            "comparaisons": comparaisons,
            "synthese": {
                "nb_dossiers_reference": len(historiques),
                "taux_global_dossier": tg,
                "mediane_taux_global_historique": float(np.median(hist_global))
                    if hist_global else 0,
                "memoire_active": True
            }
        }


class AgentChallenger:
    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "": return default
            if isinstance(x, str):
                s = x.replace("%", "").replace(" ", "").replace(",", ".")
                val = float(s)
                return val / 100 if "%" in x or val > 1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _map(rows):
        return {r.get("tranche", r.get("Tranche", "")): r for r in (rows or [])}

    def challenger(self, tranches, resultats_bc, resultats_sim,
                   resultats_mkt, rapport_rows):
        bc  = self._map(resultats_bc);  sim = self._map(resultats_sim)
        mkt = self._map(resultats_mkt); rpt = self._map(rapport_rows)
        avis = []
        for i, t in enumerate(tranches or []):
            nom = t.get("nom", f"Tranche {i+1}")
            typ = t.get("type", "")
            bt  = self._num(bc.get(nom, {}).get("taux_technique"))
            stt = self._num(sim.get(nom, {}).get("taux_technique"))
            mt  = self._num(mkt.get(nom, {}).get("taux",
                            mkt.get(nom, {}).get("taux_tech")))
            rt  = self._num(rpt.get(nom, {}).get("taux_retenu"))
            n_nz = int(self._num(bc.get(nom, {}).get("n_ann_nonzero"), 0))
            prudent   = max(bt, stt, mt)
            marche    = (mt if (typ != "travaillante" and mt > 0)
                         else stt if stt > 0 else bt)
            equilibre = (np.mean([x for x in [bt, stt, mt] if x > 0])
                         if any(x > 0 for x in [bt, stt, mt]) else 0)
            dispersion = ((max(p for p in [prudent, marche, equilibre])
                           - min(p for p in [prudent, marche, equilibre]))
                          / max(equilibre, 1e-12)) if equilibre else 0
            conflit   = ("fort" if dispersion > 0.35
                         else "modéré" if dispersion > 0.15 else "faible")
            arbitrage = ("Conserver le taux retenu"
                         if (rt >= min(prudent, equilibre) or rt == 0)
                         else "Relever le taux ou documenter l'écart")
            if typ == "travaillante" and n_nz < 3:
                arbitrage = "Ne pas se reposer sur le BC — jugement expert documenté"
            avis.append({
                "tranche": nom, "type": typ, "taux_retenu": rt,
                "avis_prudentiel": prudent, "avis_marche": marche,
                "avis_equilibre": equilibre, "conflit": conflit,
                "arbitrage": arbitrage
            })
        return {"avis": avis,
                "nb_conflits_forts": sum(1 for a in avis if a["conflit"] == "fort")}


class AgentOptimisationProgramme:
    def __init__(self, gnpi): self.gnpi = gnpi

    @staticmethod
    def _base_rate(t, idx, rbc, rsim, rmkt):
        nom = t.get("nom", "")
        def lk(rows, key):
            for r in rows or []:
                if r.get("tranche") == nom: return float(r.get(key, 0) or 0)
            if idx < len(rows or []):
                return float((rows or [])[idx].get(key, 0) or 0)
            return 0.0
        bc  = lk(rbc, "taux_technique")
        sim = lk(rsim, "taux_technique")
        mkt = lk(rmkt, "taux")
        return max(bc, sim) if t.get("type") == "travaillante" else max(sim, mkt)

    def _estimate_rate(self, t_ref, t_new, base_rate):
        p0   = max(float(t_ref.get("priorite", 1)), 1)
        l0   = max(float(t_ref.get("portee",   1)), 1)
        p1   = max(float(t_new.get("priorite", p0)), 1)
        l1   = max(float(t_new.get("portee",   l0)), 1)
        rec0 = max(float(t_ref.get("nb_reconstitutions", 1)), 1)
        rec1 = max(float(t_new.get("nb_reconstitutions", rec0)), 1)
        adj  = (l1/l0)**0.55 * (p0/p1)**0.35 * (rec1/rec0)**0.08
        return max(base_rate * adj, 0)

    def explorer(self, tranches, rbc, rsim, rmkt,
                 objectif="equilibre", prime_cible=None, top_n=8):
        if not tranches:
            return {"alternatives": [], "message": "Programme vide."}
        alternatives = []
        for mp in [0.85, 1.00, 1.15]:
            for md in [0.90, 1.00, 1.10]:
                for dr in [-1, 0, 1]:
                    new_t = []; prime = 0.0; protection = 0.0
                    for i, t in enumerate(tranches):
                        tn = dict(t)
                        tn["portee"]   = max(round(float(t.get("portee",  0)) * mp / 500_000) * 500_000, 500_000)
                        tn["priorite"] = max(round(float(t.get("priorite",0)) * md / 500_000) * 500_000, 0)
                        tn["nb_reconstitutions"] = int(max(1, min(4, int(t.get("nb_reconstitutions", 1)) + dr)))
                        base = self._base_rate(t, i, rbc, rsim, rmkt)
                        taux = self._estimate_rate(t, tn, base)
                        prime      += self.gnpi * taux
                        protection += tn["portee"] * (1 + tn["nb_reconstitutions"]
                                       * tn.get("taux_reconstitution", 100) / 100)
                        new_t.append(tn)
                    taux_g = prime / self.gnpi if self.gnpi else 0
                    pen    = abs(prime - prime_cible) / max(prime_cible, 1) if prime_cible else 0
                    if   objectif == "cedante":    score = protection/1e6 - 60*taux_g - 10*pen
                    elif objectif == "reassureur": score = 100*taux_g - 0.03*protection/1e6 - 5*pen
                    else:                          score = protection/1e6 - 35*taux_g - 8*pen
                    alternatives.append({
                        "label":    f"Portée {mp:.0%}|Priorité {md:.0%}|Rec {dr:+d}",
                        "prime":    prime, "taux_global": taux_g,
                        "protection_theorique": protection,
                        "score":    score, "tranches": new_t
                    })
        alternatives = sorted(alternatives, key=lambda x: x["score"], reverse=True)[:top_n]
        return {"alternatives": alternatives,
                "message": f"{len(alternatives)} alternatives selon objectif {objectif}."}


# ════════════════════════════════════════════════════════════════════
# NOUVEAU — AgentVariantesLeader
# ════════════════════════════════════════════════════════════════════

class AgentVariantesLeader:
    """
    Agent LLM de proposition commerciale.

    Reçoit les taux calculés par les méthodes actuarielles (BC + Sim + Mkt)
    et utilise Claude pour proposer des variantes de programme pertinentes
    en vue d'une position leader.

    Ce que fait cet agent :
    - Raisonne sur l'attractivité commerciale de chaque variante
    - Argumente du point de vue de la cédante ET du réassureur
    - Estime les taux des variantes via élasticités log-log (approximation)
    - Produit un tableau comparatif structuré

    Ce qu'il ne fait pas :
    - Il ne recalcule pas BC / Sim / Mkt — il travaille sur vos chiffres
    - Il ne remplace pas le jugement actuariel — il explore des pistes
    """

    # Élasticités log-log par défaut (marché XL automobile)
    # Remplacées par les valeurs calibrées du labo si disponibles
    E_PORTEE   = 0.55
    E_PRIORITE = 0.35
    E_RECON    = 0.08

    def __init__(self, gnpi: float, api_key: str,
                 e_portee:   float | None = None,
                 e_priorite: float | None = None,
                 e_recon:    float | None = None):
        self.gnpi       = gnpi
        self.api_key    = api_key
        self.e_portee   = e_portee   or self.E_PORTEE
        self.e_priorite = e_priorite or self.E_PRIORITE
        self.e_recon    = e_recon    or self.E_RECON

    # ── Estimation du taux d'une variante ────────────────────────────
    def _estimer_taux(self, tau_ref: float, t_ref: dict, t_new: dict) -> float:
        """
        Approximation log-log du taux pour une structure modifiée.
        tau_new ≈ tau_ref × (C_new/C_ref)^e_portée × (D_ref/D_new)^e_priorité
                          × (n_rec_new/n_rec_ref)^e_recon
        """
        D0   = max(float(t_ref.get("priorite",             1)), 1)
        C0   = max(float(t_ref.get("portee",               1)), 1)
        n0   = max(float(t_ref.get("nb_reconstitutions",   1)), 1)
        D1   = max(float(t_new.get("priorite",            D0)), 1)
        C1   = max(float(t_new.get("portee",              C0)), 1)
        n1   = max(float(t_new.get("nb_reconstitutions",  n0)), 1)
        adj  = ((C1/C0) ** self.e_portee
                * (D0/D1) ** self.e_priorite
                * (n1/n0) ** self.e_recon)
        return max(tau_ref * adj, 0.0)

    # ── Construction du résumé tarifaire pour le prompt ──────────────
    def _resume_tarification(self, tranches, resultats_bc,
                              resultats_sim, resultats_mkt,
                              taux_retenus: list) -> str:
        """Formate les résultats calculés en texte structuré pour Claude."""
        bc_map  = {r.get("tranche", ""): r for r in (resultats_bc  or [])}
        sim_map = {r.get("tranche", ""): r for r in (resultats_sim or [])}
        mkt_map = {r.get("tranche", ""): r for r in (resultats_mkt or [])}

        lignes = [
            f"GNPI : {self.gnpi:,.0f} AED\n",
            "TARIFICATION DE RÉFÉRENCE (calculée)\n",
            "-" * 52,
        ]
        prime_totale = 0.0
        for i, t in enumerate(tranches):
            nom  = t.get("nom", f"T{i+1}")
            typ  = t.get("type", "")
            D    = float(t.get("priorite", 0))
            C    = float(t.get("portee",   0))
            n_rec = int(t.get("nb_reconstitutions", 1))
            bc   = bc_map.get(nom, {})
            sim  = sim_map.get(nom, {})
            mkt  = mkt_map.get(nom, {})
            tau  = float(taux_retenus[i]) if i < len(taux_retenus) else 0.0
            prime = self.gnpi * tau
            prime_totale += prime
            lignes.append(
                f"\n{nom} ({typ}) — {C/1e6:.0f}M xs {D/1e6:.0f}M | {n_rec} reconst."
            )
            lignes.append(
                f"  BC     : τ_tech = {float(bc.get('taux_technique',0)):.4%}"
                f"  (n_nz = {int(float(bc.get('n_ann_nonzero',0)))} ans)"
            )
            lignes.append(
                f"  Sim    : τ_tech = {float(sim.get('taux_technique',0)):.4%}"
                f"  (σ = {float(sim.get('sigma',0)):.4%})"
            )
            if mkt.get("taux_tech") or mkt.get("taux"):
                tau_mkt = float(mkt.get("taux_tech", mkt.get("taux", 0)))
                lignes.append(f"  Mkt    : τ_tech = {tau_mkt:.4%}")
            lignes.append(f"  RETENU : τ = {tau:.4%}  | prime = {prime:,.0f} AED")

        lignes.append(f"\nPrime totale programme : {prime_totale:,.0f} AED")
        lignes.append(f"Taux global            : {prime_totale/self.gnpi:.4%}")
        return "\n".join(lignes)

    # ── Prompt principal ──────────────────────────────────────────────
    def _construire_prompt(self, resume_tarif: str,
                            tranches: list,
                            n_variantes: int,
                            contexte_marche: str = "") -> str:
        tranches_str = "\n".join(
            f"  {t.get('nom','T?')} : {t.get('portee',0)/1e6:.0f}M xs "
            f"{t.get('priorite',0)/1e6:.0f}M | {t.get('type','')} | "
            f"{t.get('nb_reconstitutions',1)} reconst."
            for t in tranches
        )
        contexte_mkt = (f"\nContexte marché disponible :\n{contexte_marche}\n"
                        if contexte_marche else "")

        return f"""Tu es actuaire senior spécialisé en réassurance non-proportionnelle.
Atlantic Re vise une position LEADER sur ce programme.

{resume_tarif}
{contexte_mkt}
Structure du programme de référence :
{tranches_str}

---
MISSION : Propose exactement {n_variantes} variantes de programme.

Chaque variante doit :
1. Être techniquement défendable (ne pas tomber sous le taux pur)
2. Offrir quelque chose de concret à la cédante :
   - Meilleure protection (portée plus large ou priorité plus basse)
   - Prime moins élevée (structure optimisée)
   - Clauses plus souples (AAD réduit, reconstitutions supplémentaires)
   - Ou une combinaison des trois
3. Avoir un argument commercial en une phrase — ce qui la rend attractive
4. Avoir une estimation de taux cohérente avec les élasticités log-log :
   e_portée = {self.e_portee:.2f}, e_priorité = {self.e_priorite:.2f}

Contraintes :
- Variations réalistes : ±10 à 25% sur D ou C
- AAD optionnel sur T1 (travaillante uniquement)
- Reconstitutions : entre 1 et 3
- Le taux estimé ne peut pas être inférieur à 80% du taux retenu de référence

FORMAT DE RÉPONSE OBLIGATOIRE (JSON uniquement, aucun texte autour) :
{{
  "variantes": [
    {{
      "nom": "Variante A — <nom court>",
      "angle": "cédante | réassureur | équilibre",
      "tranches": [
        {{
          "nom": "<nom tranche>",
          "priorite": <valeur en AED>,
          "portee": <valeur en AED>,
          "nb_reconstitutions": <entier>,
          "AAD": <valeur en AED ou null>,
          "tau_estime": <taux décimal, ex: 0.0234>,
          "prime_estimee": <prime en AED>
        }}
      ],
      "prime_totale": <prime totale en AED>,
      "taux_global": <taux global décimal>,
      "argument_commercial": "<phrase d'accroche pour la cédante>",
      "justification_technique": "<pourquoi ce taux est défendable>"
    }}
  ],
  "recommandation": "<laquelle des {n_variantes} variantes privilégier et pourquoi>"
}}"""

    # ── Appel API Claude ──────────────────────────────────────────────
    def _appeler_claude(self, prompt: str) -> dict:
        """Appel direct à l'API Claude. Retourne le JSON parsé."""
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
        texte = message.content[0].text.strip()
        # Nettoyer les éventuels blocs markdown
        if texte.startswith("```"):
            lignes = texte.split("\n")
            texte  = "\n".join(
                l for l in lignes
                if not l.startswith("```")
            ).strip()
        return json.loads(texte)

    # ── Méthode principale ────────────────────────────────────────────
    def proposer(self, tranches: list, resultats_bc: list,
                 resultats_sim: list, resultats_mkt: list,
                 taux_retenus: list, n_variantes: int = 3,
                 contexte_marche: str = "") -> dict:
        """
        Point d'entrée principal.

        Paramètres
        ----------
        tranches        : liste des tranches du programme
        resultats_bc    : résultats Burning Cost par tranche
        resultats_sim   : résultats Simulation par tranche
        resultats_mkt   : résultats Market Curve par tranche
        taux_retenus    : liste des taux finaux retenus (un par tranche)
        n_variantes     : nombre de variantes à produire (défaut 3)
        contexte_marche : texte libre sur le marché (optionnel)

        Retourne
        --------
        dict avec clés :
          "variantes"      : liste des variantes structurées
          "recommandation" : recommandation Claude
          "resume_ref"     : résumé du programme de référence
          "erreur"         : message d'erreur si échec (sinon absent)
        """
        resume = self._resume_tarification(
            tranches, resultats_bc, resultats_sim, resultats_mkt, taux_retenus)
        prompt = self._construire_prompt(
            resume, tranches, n_variantes, contexte_marche)
        try:
            reponse = self._appeler_claude(prompt)
            return {
                "variantes":      reponse.get("variantes", []),
                "recommandation": reponse.get("recommandation", ""),
                "resume_ref":     resume,
            }
        except json.JSONDecodeError as e:
            return {"variantes": [], "recommandation": "",
                    "resume_ref": resume,
                    "erreur": f"Réponse Claude non parseable : {e}"}
        except Exception as e:
            return {"variantes": [], "recommandation": "",
                    "resume_ref": resume,
                    "erreur": str(e)}


# ════════════════════════════════════════════════════════════════════
# FONCTIONS D'AFFICHAGE — agents existants
# ════════════════════════════════════════════════════════════════════

def afficher_plan_actuariel(plan):
    if not plan: return
    tableau_resultats([{
        "Ordre": i, "Étape": p["titre"],
        "Priorité": p["priorite"], "Justification": p["justification"]
    } for i, p in enumerate(plan, 1)], "Séquence de traitement actuariel")


def afficher_critique_actuariel(critique):
    if not critique: return
    syn = critique.get("synthese", {})
    c1, c2, c3 = st.columns(3)
    with c1: card("Score audit",    f"{syn.get('score', 0)}/100",  icone="🧠")
    with c2: card("Verdict",         syn.get("verdict", "—"),
                  couleur="#1a1a1a", icone="⚖️")
    with c3: card("Alertes",         f"{syn.get('nb_alertes', 0)}",
                  couleur="#f59e0b", icone="⚠️")
    alertes = critique.get("alertes", [])
    if alertes:
        tableau_resultats([{
            "Niveau": a["niveau"], "Tranche": a["tranche"],
            "Message": a["message"]
        } for a in alertes], "Alertes critiques")


def afficher_memoire_metier(memoire):
    if not memoire: return
    st.markdown("#### Mémoire métier inter-dossiers")
    if not memoire.get("disponible"):
        st.info(memoire.get("message", "Mémoire indisponible.")); return
    syn = memoire.get("synthese", {})
    c1, c2, c3 = st.columns(3)
    with c1: card("Dossiers référence", syn.get("nb_dossiers_reference", 0), icone="🧠")
    with c2: card("Taux dossier",  f"{syn.get('taux_global_dossier', 0):.4%}",
                  couleur="#1a1a1a", icone="📌")
    with c3: card("Médiane historique",
                  f"{syn.get('mediane_taux_global_historique', 0):.4%}",
                  couleur="#3b82f6", icone="📚")
    rows = [{
        "Type": c["type"], "Dossier": f"{c['taux_dossier']:.4%}",
        "Médiane hist.": f"{c['mediane_historique']:.4%}",
        "Q25-Q75": f"{c['q25_historique']:.4%}/{c['q75_historique']:.4%}",
        "Écart": f"{c['ecart_vs_mediane']:+.1%}",
        "Diagnostic": c["diagnostic"], "N": c["n_reference"]
    } for c in memoire.get("comparaisons", [])]
    if rows: tableau_resultats(rows)


def afficher_challenger(challenge):
    if not challenge: return
    st.markdown("#### Analyse contradictoire actuarielle")
    rows = [{
        "Tranche": a["tranche"], "Type": a["type"],
        "Retenu":      f"{a['taux_retenu']:.4%}",
        "Prudentiel":  f"{a['avis_prudentiel']:.4%}",
        "Marché":      f"{a['avis_marche']:.4%}",
        "Équilibre":   f"{a['avis_equilibre']:.4%}",
        "Conflit":     a["conflit"],
        "Arbitrage":   a["arbitrage"]
    } for a in challenge.get("avis", [])]
    if rows: tableau_resultats(rows)


def afficher_optimisation_avancee(opt):
    if not opt: return
    st.markdown("#### Recherche de programmes alternatifs comparables")
    st.caption(opt.get("message", ""))
    rows = [{
        "Rang": i, "Scénario": a["label"],
        "Prime": f"{a['prime']:,.0f} MAD",
        "Taux global": f"{a['taux_global']:.4%}",
        "Score": f"{a['score']:.2f}"
    } for i, a in enumerate(opt.get("alternatives", []), 1)]
    if rows: tableau_resultats(rows)


def afficher_ml_actuariel(ml):
    if not ml: return
    st.markdown("#### Approximation statistique — benchmark")
    if not ml.get("disponible"):
        st.info(ml.get("message", "ML non disponible.")); return
    rows = [{
        "Modèle": r.get("modele"),
        "MAE":  f"{r.get('MAE',  0):,.0f}" if r.get("MAE")  else "Erreur",
        "RMSE": f"{r.get('RMSE', 0):,.0f}" if r.get("RMSE") else "Erreur",
        "R²":   f"{r.get('R2',   0):.4f}"  if r.get("R2")   else "Erreur",
        "Statut": "✅" if r.get("MAE") else r.get("erreur", "Erreur")
    } for r in ml.get("modeles", [])]
    tableau_resultats(rows, "Comparaison des modèles ML")
    if ml.get("importance"):
        tableau_resultats([{
            "Variable": x["variable"],
            "Importance": f"{x['importance']:.4f}"
        } for x in ml["importance"]],
        f"Variables importantes — {ml.get('meilleur_modele')}")


# ════════════════════════════════════════════════════════════════════
# NOUVEAU — Affichage des variantes leader
# ════════════════════════════════════════════════════════════════════

def afficher_variantes_leader(resultat: dict, gnpi: float):
    """
    Affiche les variantes de programme proposées par AgentVariantesLeader.

    Paramètres
    ----------
    resultat : dict retourné par AgentVariantesLeader.proposer()
    gnpi     : GNPI pour calcul des primes absolues
    """
    if not resultat:
        st.info("Aucun résultat de variantes disponible.")
        return

    if resultat.get("erreur"):
        st.error(f"Erreur agent variantes : {resultat['erreur']}")
        with st.expander("Prompt envoyé"):
            st.text(resultat.get("resume_ref", ""))
        return

    variantes = resultat.get("variantes", [])
    if not variantes:
        st.warning("Aucune variante générée.")
        return

    # ── Programme de référence ────────────────────────────────────────
    with st.expander("Programme de référence (taux calculés)", expanded=False):
        st.text(resultat.get("resume_ref", ""))

    # ── Recommandation globale ────────────────────────────────────────
    rec = resultat.get("recommandation", "")
    if rec:
        st.info(f"**Recommandation Claude :** {rec}")

    # ── Tableau de synthèse comparatif ────────────────────────────────
    st.markdown("#### Tableau comparatif — programmes alternatifs")
    rows_synth = []
    for v in variantes:
        rows_synth.append({
            "Programme":         v.get("nom", "—"),
            "Angle":             v.get("angle", "—"),
            "Prime totale (AED)":f"{float(v.get('prime_totale', 0)):,.0f}",
            "Taux global":       f"{float(v.get('taux_global', 0)):.4%}",
            "Argument":          v.get("argument_commercial", "—"),
        })
    tableau_resultats(rows_synth)

    # ── Détail par variante ───────────────────────────────────────────
    st.markdown("#### Détail par variante")
    for v in variantes:
        angle_couleur = {
            "cédante":    "#2d8a4e",
            "réassureur": "#1e40af",
            "équilibre":  "#92400e",
        }.get(v.get("angle", "").lower(), "#374151")

        with st.expander(
            f"**{v.get('nom', '—')}**  ·  "
            f"Prime {float(v.get('prime_totale', 0)):,.0f} AED  ·  "
            f"τ global {float(v.get('taux_global', 0)):.4%}",
            expanded=False
        ):
            # Angle et arguments
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown(
                    f"<div style='background:{angle_couleur};color:white;"
                    f"padding:6px 12px;border-radius:6px;font-size:13px;"
                    f"font-weight:600'>Angle : {v.get('angle','—')}</div>",
                    unsafe_allow_html=True)
            with col2:
                st.markdown(
                    f"**Argument :** {v.get('argument_commercial', '—')}")

            st.caption(
                f"Justification technique : {v.get('justification_technique', '—')}")

            # Tableau des tranches
            tranches_v = v.get("tranches", [])
            if tranches_v:
                rows_t = []
                for t in tranches_v:
                    aad = t.get("AAD")
                    rows_t.append({
                        "Tranche":   t.get("nom", "—"),
                        "Priorité":  f"{float(t.get('priorite', 0))/1e6:.2f}M",
                        "Portée":    f"{float(t.get('portee',   0))/1e6:.2f}M",
                        "Reconst.":  t.get("nb_reconstitutions", 1),
                        "AAD":       f"{float(aad)/1e6:.2f}M" if aad else "—",
                        "τ estimé":  f"{float(t.get('tau_estime', 0)):.4%}",
                        "Prime (AED)": f"{float(t.get('prime_estimee', 0)):,.0f}",
                    })
                tableau_resultats(rows_t)


# ════════════════════════════════════════════════════════════════════
# Alias de compatibilité avec app.py
# ════════════════════════════════════════════════════════════════════

def afficher_plan_agentique(plan):
    return afficher_plan_actuariel(plan)

def afficher_critique_agentique(critique):
    return afficher_critique_actuariel(critique)

def afficher_ml_agentique(ml):
    return afficher_ml_actuariel(ml)
