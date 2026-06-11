"""
Atlantic Re IA — Agents V2 module
VERSION AUTONOME

Agents déterministes (Python pur) :
  AgentRaisonnement, AgentCritique, AgentML,
  AgentMemoireMetier, AgentChallenger, AgentOptimisationProgramme

Agents LLM (Claude API) :
  AgentAnalyseComplete  — analyse profonde autonome sur brief libre
  AgentVariantesLeader  — propose des variantes compétitives

L'agent LLM :
  - Raisonne au maximum, remonte aux causes racines
  - Score la cohérence de chaque méthode et du programme global
  - Liste les "bras utilisés" à la fin de chaque réponse
  - Ne demande aucune validation humaine
  - Accepte un brief libre (R, Excel, manuel — peu importe)
"""
import streamlit as st
import numpy as np
import pandas as pd
import json
import anthropic
from datetime import datetime
from modules.ui import tableau_resultats, card
from modules.db import _get_conn, _ph
from modules.prompts import (
    build_prompt_analyse_autonome,
    build_prompt_variantes_leader,
    build_prompt,
    _charger_few_shot_dynamiques,
    claude_stream,
)


# ════════════════════════════════════════════════════════════════════
# AGENTS DÉTERMINISTES — inchangés
# ════════════════════════════════════════════════════════════════════

class AgentRaisonnement:
    def planifier(self, contexte):
        plan = []
        def add(code, titre, justification, priorite="normale"):
            plan.append({"code": code, "titre": titre,
                         "justification": justification, "priorite": priorite})
        add("validation",   "Valider les paramètres",
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
        add("critique",   "Auditer les résultats",
            "Détecter incohérences et taux extrêmes.", "haute")
        if contexte.get("n_rows", 0) >= 30:
            add("machine_learning", "Tester des modèles ML",
                "Volume minimal disponible.", "normale")
        else:
            add("machine_learning_skip", "Ne pas surinterpréter le ML",
                "Volume trop faible pour ML robuste.", "normale")
        add("selection",   "Sélectionner le taux retenu",
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
        rpt_map = self._map_by_name(rapport_rows)

        def alerte(niveau, tranche, message, impact=-5):
            nonlocal score
            alertes.append({"niveau": niveau, "tranche": tranche, "message": message})
            score += impact

        for i, t in enumerate(tranches or []):
            nom = t.get("nom", f"Tranche {i+1}"); typ = t.get("type", "")
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
                           f"Écart BC/Sim très élevé : {ecart:.0%}. Cause racine à investiguer.", -15)
                elif ecart >= self.seuil_ecart_warn:
                    alerte("WARN", nom,
                           f"Écart BC/Sim significatif : {ecart:.0%}. Justification requise.", -8)
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
            return {"disponible": False, "message": "< 30 observations.",
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
                                   "n_test":  int(len(X_te))})
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
                "message": "Benchmark ML exécuté.",
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
                    f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                        JOIN resultats r ON r.session_id=s.id
                        WHERE s.user_email={p} AND r.etape='rapport' AND s.id!={p}
                        ORDER BY s.updated_at DESC LIMIT {int(limite)}""",
                    (user_email, current_session_id))
            else:
                cur.execute(
                    f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                        JOIN resultats r ON r.session_id=s.id
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
                                        "gnpi": gnpi_h, "prime_totale": pt, "rows": rr})
            except: continue
        return historiques

    def benchmark(self, user_email, tranches, rapport_rows, gnpi,
                  current_session_id=None):
        historiques = self.charger_rapports_historiques(
            user_email, current_session_id=current_session_id)
        if not historiques:
            return {"disponible": False,
                    "message": "Aucun rapport historique exploitable.",
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
            nom = t.get("nom", f"Tranche {i+1}"); typ = t.get("type", "")
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
            arbitrage = ("Conserver" if (rt >= min(prudent, equilibre) or rt == 0)
                         else "Relever ou documenter l'écart")
            if typ == "travaillante" and n_nz < 3:
                arbitrage = "BC non crédible — jugement expert documenté"
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
        bc  = lk(rbc,  "taux_technique")
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
                "message": f"{len(alternatives)} alternatives — objectif {objectif}."}


# ════════════════════════════════════════════════════════════════════
# AGENT LLM 1 — ANALYSE COMPLÈTE AUTONOME
# ════════════════════════════════════════════════════════════════════

class AgentAnalyseComplete:
    """
    Analyse profonde et autonome d'un dossier de tarification.

    Reçoit :
      - brief_actuariel : texte libre avec les résultats calculés par
        l'actuaire (R, Excel, manuel — peu importe)
      - contexte_cedante : programme, tranches, clauses
      - donnees_brutes : triangle, GNPI, indices, cotations marché
        (optionnel mais améliore l'analyse)

    Produit :
      - Diagnostic portefeuille
      - Évaluation de la tarification tranche par tranche
      - Causes racines des anomalies
      - Scores de cohérence
      - Positionnement marché
      - Conclusion avec verdict
      - Section "bras utilisés"
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client  = anthropic.Anthropic(api_key=api_key)

    def analyser(
        self,
        brief_actuariel:  str,
        contexte_cedante: str,
        donnees_brutes:   str = "",
        contexte_marche:  str = "",
        user_email:       str = "",
        stream_container=None,
    ) -> str:
        """
        Lance l'analyse autonome. Retourne le texte complet de l'analyse.
        Si stream_container est fourni (st.empty()), streame en live.
        """
        few_shot = _charger_few_shot_dynamiques(user_email, n_max=2) if user_email else ""
        prompt   = build_prompt_analyse_autonome(
            brief_actuariel  = brief_actuariel,
            contexte_cedante = contexte_cedante,
            donnees_brutes   = donnees_brutes,
            contexte_marche  = contexte_marche,
            few_shot         = few_shot,
        )

        full_text = ""
        try:
            with self.client.messages.stream(
                model      = "claude-opus-4-5",
                max_tokens = 6000,
                messages   = [{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    full_text += text
                    if stream_container:
                        stream_container.markdown(full_text + "▌")
        except Exception as e:
            return f"❌ Erreur API : {e}"

        if stream_container:
            stream_container.markdown(full_text)
        return full_text


# ════════════════════════════════════════════════════════════════════
# AGENT LLM 2 — VARIANTES LEADER
# ════════════════════════════════════════════════════════════════════

class AgentVariantesLeader:
    """
    Propose des variantes de programme compétitives pour une position leader.

    Reçoit :
      - brief_actuariel : taux calculés par l'actuaire (texte libre)
      - contexte_cedante : structure du programme de référence
      - elasticites : dict calibré depuis labo (optionnel)
      - donnees_brutes : contexte portefeuille (optionnel)

    Produit :
      - N variantes structurées avec taux estimés
      - Argument commercial par variante
      - Analyse compétitivité
      - Score cohérence
      - Bras utilisés
    """

    def __init__(self, api_key: str, gnpi: float,
                 elasticites: dict | None = None):
        self.api_key     = api_key
        self.gnpi        = gnpi
        self.elasticites = elasticites
        self.client      = anthropic.Anthropic(api_key=api_key)

    def proposer(
        self,
        brief_actuariel:  str,
        contexte_cedante: str,
        n_variantes:      int  = 3,
        objectif_leader:  str  = "",
        donnees_brutes:   str  = "",
    ) -> dict:
        """
        Retourne un dict avec :
          "variantes"            : liste des variantes
          "analyse_competitivite": texte d'analyse
          "recommandation"       : variante recommandée
          "score_competitivite"  : 1-10
          "bras_utilises"        : méthodes, données, limites, cohérence
          "erreur"               : message si échec (absent si succès)
        """
        prompt = build_prompt_variantes_leader(
            brief_actuariel  = brief_actuariel,
            contexte_cedante = contexte_cedante,
            n_variantes      = n_variantes,
            elasticites      = self.elasticites,
            objectif_leader  = objectif_leader,
            donnees_brutes   = donnees_brutes,
        )
        try:
            message = self.client.messages.create(
                model      = "claude-opus-4-5",
                max_tokens = 4096,
                messages   = [{"role": "user", "content": prompt}]
            )
            texte = message.content[0].text.strip()
            # Nettoyer blocs markdown éventuels
            if texte.startswith("```"):
                texte = "\n".join(
                    l for l in texte.split("\n")
                    if not l.startswith("```")
                ).strip()
            reponse = json.loads(texte)
            return {
                "variantes":             reponse.get("variantes",             []),
                "analyse_competitivite": reponse.get("analyse_competitivite", ""),
                "recommandation":        reponse.get("recommandation",        ""),
                "score_competitivite":   reponse.get("score_competitivite",   0),
                "bras_utilises":         reponse.get("bras_utilises",         {}),
            }
        except json.JSONDecodeError as e:
            return {"variantes": [], "erreur": f"Réponse non parseable : {e}"}
        except Exception as e:
            return {"variantes": [], "erreur": str(e)}


# ════════════════════════════════════════════════════════════════════
# FONCTIONS D'AFFICHAGE — agents déterministes
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
    with c1: card("Score audit",  f"{syn.get('score', 0)}/100",  icone="🧠")
    with c2: card("Verdict",       syn.get("verdict", "—"),
                  couleur="#1a1a1a", icone="⚖️")
    with c3: card("Alertes",       f"{syn.get('nb_alertes', 0)}",
                  couleur="#f59e0b", icone="⚠️")
    alertes = critique.get("alertes", [])
    if alertes:
        tableau_resultats([{
            "Niveau": a["niveau"], "Tranche": a["tranche"], "Message": a["message"]
        } for a in alertes], "Alertes")


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
        "Médiane": f"{c['mediane_historique']:.4%}",
        "Q25/Q75": f"{c['q25_historique']:.4%}/{c['q75_historique']:.4%}",
        "Écart": f"{c['ecart_vs_mediane']:+.1%}",
        "Diagnostic": c["diagnostic"], "N": c["n_reference"]
    } for c in memoire.get("comparaisons", [])]
    if rows: tableau_resultats(rows)


def afficher_challenger(challenge):
    if not challenge: return
    st.markdown("#### Analyse contradictoire")
    rows = [{
        "Tranche": a["tranche"], "Type": a["type"],
        "Retenu":     f"{a['taux_retenu']:.4%}",
        "Prudentiel": f"{a['avis_prudentiel']:.4%}",
        "Marché":     f"{a['avis_marche']:.4%}",
        "Équilibre":  f"{a['avis_equilibre']:.4%}",
        "Conflit":    a["conflit"],
        "Arbitrage":  a["arbitrage"]
    } for a in challenge.get("avis", [])]
    if rows: tableau_resultats(rows)


def afficher_optimisation_avancee(opt):
    if not opt: return
    st.markdown("#### Programmes alternatifs (exploration mécanique)")
    st.caption(opt.get("message", ""))
    rows = [{
        "Rang": i, "Scénario": a["label"],
        "Prime": f"{a['prime']:,.0f}",
        "Taux global": f"{a['taux_global']:.4%}",
        "Score": f"{a['score']:.2f}"
    } for i, a in enumerate(opt.get("alternatives", []), 1)]
    if rows: tableau_resultats(rows)


def afficher_ml_actuariel(ml):
    if not ml: return
    st.markdown("#### Benchmark ML")
    if not ml.get("disponible"):
        st.info(ml.get("message", "ML non disponible.")); return
    rows = [{
        "Modèle": r.get("modele"),
        "MAE":  f"{r.get('MAE',  0):,.0f}" if r.get("MAE")  else "Erreur",
        "RMSE": f"{r.get('RMSE', 0):,.0f}" if r.get("RMSE") else "Erreur",
        "R²":   f"{r.get('R2',   0):.4f}"  if r.get("R2")   else "Erreur",
        "Statut": "✅" if r.get("MAE") else r.get("erreur", "Erreur")
    } for r in ml.get("modeles", [])]
    tableau_resultats(rows, "Modèles ML")
    if ml.get("importance"):
        tableau_resultats([{
            "Variable": x["variable"], "Importance": f"{x['importance']:.4f}"
        } for x in ml["importance"]], f"Variables — {ml.get('meilleur_modele')}")


# ════════════════════════════════════════════════════════════════════
# AFFICHAGE AGENT LLM — Analyse complète
# ════════════════════════════════════════════════════════════════════

def afficher_analyse_complete(texte: str):
    """Affiche la sortie de AgentAnalyseComplete."""
    if not texte:
        st.info("Aucune analyse disponible."); return
    # Chercher la section bras utilisés pour la mettre en évidence
    if "BRAS UTILISÉS" in texte.upper():
        parties = texte.split("## BRAS UTILISÉS", 1)
        st.markdown(parties[0])
        with st.expander("🔧 Bras utilisés par l'agent", expanded=True):
            st.markdown("## BRAS UTILISÉS" + parties[1])
    else:
        st.markdown(texte)


# ════════════════════════════════════════════════════════════════════
# AFFICHAGE AGENT LLM — Variantes leader
# ════════════════════════════════════════════════════════════════════

def afficher_variantes_leader(resultat: dict, gnpi: float):
    """Affiche les variantes proposées par AgentVariantesLeader."""
    if not resultat:
        st.info("Aucun résultat disponible."); return

    if resultat.get("erreur"):
        st.error(f"Erreur agent : {resultat['erreur']}"); return

    variantes = resultat.get("variantes", [])
    if not variantes:
        st.warning("Aucune variante générée."); return

    # ── Compétitivité ─────────────────────────────────────────────────
    analyse = resultat.get("analyse_competitivite", "")
    score   = resultat.get("score_competitivite", 0)
    if analyse:
        col1, col2 = st.columns([4, 1])
        with col1: st.info(analyse)
        with col2:
            couleur = "#2d8a4e" if score >= 7 else "#f59e0b" if score >= 5 else "#dc2626"
            card("Compétitivité", f"{score}/10", couleur=couleur, icone="🎯")

    # ── Recommandation ────────────────────────────────────────────────
    rec = resultat.get("recommandation", "")
    if rec:
        st.success(f"**Recommandation :** {rec}")

    # ── Tableau de synthèse ───────────────────────────────────────────
    st.markdown("#### Synthèse comparative")
    rows_synth = []
    for v in variantes:
        rows_synth.append({
            "Programme":        v.get("nom", "—"),
            "Angle":            v.get("angle", "—"),
            "Risque technique": v.get("risque_technique", "—"),
            "Prime totale (AED)": f"{float(v.get('prime_totale', 0)):,.0f}",
            "Taux global":      f"{float(v.get('taux_global', 0)):.4%}",
            "Argument":         v.get("argument_commercial", "—"),
        })
    tableau_resultats(rows_synth)

    # ── Détail variantes ──────────────────────────────────────────────
    st.markdown("#### Détail par variante")
    couleurs_angle = {
        "cédante":    "#2d8a4e",
        "réassureur": "#1e40af",
        "équilibre":  "#92400e",
    }
    couleurs_risque = {
        "faible": "#2d8a4e",
        "modéré": "#f59e0b",
        "élevé":  "#dc2626",
    }
    for v in variantes:
        angle  = v.get("angle", "").lower()
        risque = v.get("risque_technique", "").lower()
        alerte = v.get("alerte")
        with st.expander(
            f"**{v.get('nom', '—')}** · "
            f"{float(v.get('prime_totale', 0)):,.0f} AED · "
            f"τ {float(v.get('taux_global', 0)):.4%}",
            expanded=False
        ):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(
                    f"<span style='background:{couleurs_angle.get(angle,'#374151')};"
                    f"color:white;padding:4px 10px;border-radius:4px;font-size:12px'>"
                    f"Angle : {angle}</span>",
                    unsafe_allow_html=True)
            with c2:
                st.markdown(
                    f"<span style='background:{couleurs_risque.get(risque,'#374151')};"
                    f"color:white;padding:4px 10px;border-radius:4px;font-size:12px'>"
                    f"Risque : {risque}</span>",
                    unsafe_allow_html=True)
            with c3:
                if alerte:
                    st.warning(f"⚠️ {alerte}")

            st.markdown(f"**Argument :** {v.get('argument_commercial', '—')}")
            st.caption(f"Justification technique : {v.get('justification_technique', '—')}")

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
                        "vs réf.":   t.get("vs_reference", "—"),
                        "Méthode":   t.get("methode_estimation", "—"),
                        "Prime (AED)":f"{float(t.get('prime_estimee', 0)):,.0f}",
                    })
                tableau_resultats(rows_t)

    # ── Bras utilisés ────────────────────────────────────────────────
    bras = resultat.get("bras_utilises", {})
    if bras:
        with st.expander("🔧 Bras utilisés par l'agent", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                methodes = bras.get("methodes", [])
                if methodes:
                    st.markdown("**Méthodes activées**")
                    for m in methodes: st.markdown(f"- {m}")
                donnees = bras.get("donnees", [])
                if donnees:
                    st.markdown("**Données exploitées**")
                    for d in donnees: st.markdown(f"- {d}")
            with c2:
                limites = bras.get("limites", [])
                if limites:
                    st.markdown("**Limites identifiées**")
                    for l in limites: st.markdown(f"- {l}")
                score_c = bras.get("score_coherence_global", 0)
                note_c  = bras.get("note_coherence", "")
                if score_c:
                    couleur_c = ("#2d8a4e" if score_c >= 7
                                 else "#f59e0b" if score_c >= 5 else "#dc2626")
                    card("Cohérence globale", f"{score_c}/10",
                         couleur=couleur_c, icone="📊")
                    if note_c: st.caption(note_c)


# ════════════════════════════════════════════════════════════════════
# Alias compatibilité app.py
# ════════════════════════════════════════════════════════════════════

def afficher_plan_agentique(plan):      return afficher_plan_actuariel(plan)
def afficher_critique_agentique(c):     return afficher_critique_actuariel(c)
def afficher_ml_agentique(ml):          return afficher_ml_actuariel(ml)
