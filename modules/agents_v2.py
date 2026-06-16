"""
IA TARIF — Agents V2 module
AgentRaisonnement, AgentCritique, AgentML, AgentMemoireMetier,
AgentChallenger, AgentOptimisationProgramme + affichage.
"""
import streamlit as st
import numpy as np 
import pandas as pd
import json
from datetime import datetime
from modules.ui import tableau_resultats, card
from modules.db import _get_conn, _ph, db_init

class AgentRaisonnement:
    def planifier(self, contexte):
        plan = []
        def add(code, titre, justification, priorite="normale"):
            plan.append({"code":code,"titre":titre,"justification":justification,"priorite":priorite})
        add("validation","Valider les paramètres","Contrôler alpha, lambda, GNPI, tranches.","haute")
        if contexte.get("has_triangle"):
            add("burning_cost","Calculer le Burning Cost","Triangle disponible — lecture historique.","haute")
        else:
            add("missing_triangle","Bloquer le BC","Aucune donnée projetée — BC non simulable.","critique")
        add("simulation","Lancer la simulation","Comparer expérience historique et vision stochastique.","haute")
        if contexte.get("has_market"):
            add("market_curve","Ajuster la Market Curve","Données marché disponibles — benchmark cat.","normale")
        else:
            add("market_curve_skip","Ignorer la Market Curve","Aucune donnée marché fiable.","normale")
        add("critique","Auditer les résultats","Détecter incohérences et taux extrêmes.","haute")
        if contexte.get("n_rows",0) >= 30:
            add("machine_learning","Tester des modèles ML","Volume minimal disponible.","normale")
        else:
            add("machine_learning_skip","Ne pas surinterpréter le ML","Volume trop faible pour ML robuste.","normale")
        add("selection","Sélectionner le taux retenu","Appliquer règle prudente par tranche.","haute")
        add("negociation","Proposer des variantes","Programmes selon intérêt cédante/réassureur.","normale")
        return plan


class AgentCritique:
    def __init__(self, seuil_ecart_warn=0.30, seuil_ecart_critique=0.50, seuil_taux_extreme=0.50):
        self.seuil_ecart_warn = seuil_ecart_warn
        self.seuil_ecart_critique = seuil_ecart_critique
        self.seuil_taux_extreme = seuil_taux_extreme

    @staticmethod
    def _map_by_name(rows):
        return {r.get("tranche",r.get("Tranche","")): r for r in (rows or [])}

    @staticmethod
    def _num(x, default=0.0):
        try:
            if x is None or x == "": return default
            if isinstance(x, str):
                return float(x.replace("%","").replace(",",".").strip())
            return float(x)
        except: return default

    def auditer(self, tranches, gnpi, resultats_bc, resultats_sim, resultats_mkt, rapport_rows):
        alertes = []; decisions = []; score = 100
        bc_map = self._map_by_name(resultats_bc)
        sim_map = self._map_by_name(resultats_sim)
        mkt_map = self._map_by_name(resultats_mkt)
        rpt_map = self._map_by_name(rapport_rows)

        def alerte(niveau, tranche, message, impact=-5):
            nonlocal score
            alertes.append({"niveau":niveau,"tranche":tranche,"message":message})
            score += impact

        for i, t in enumerate(tranches or []):
            nom = t.get("nom",f"Tranche {i+1}"); typ = t.get("type","")
            bc=bc_map.get(nom,{}); sim=sim_map.get(nom,{}); rpt=rpt_map.get(nom,{})
            bc_pur=self._num(bc.get("taux_pur")); bc_risque=self._num(bc.get("taux_risque"))
            bc_tech=self._num(bc.get("taux_technique")); sim_tech=self._num(sim.get("taux_technique"))
            retenu=self._num(rpt.get("taux_retenu"))
            n_nz = int(self._num(bc.get("n_ann_nonzero"),0))

            if bc_tech>0 and not (bc_pur<=bc_risque<=bc_tech+1e-12):
                alerte("CRITIQUE",nom,"Hiérarchie BC incohérente : τ_pur ≤ τ_risque ≤ τ_tech non respectée.",-15)

            if n_nz<3 and typ=="travaillante":
                alerte("WARN",nom,f"BC fragile : {n_nz} année(s) non nulle(s). Simulation prioritaire.",-6)
            elif n_nz<3 and typ=="cat":
                decisions.append({"tranche":nom,"decision":"BC nul acceptable pour tranche cat."})

            if bc_tech>0 and sim_tech>0:
                ecart=abs(bc_tech-sim_tech)/max(bc_tech,1e-12)
                if ecart>=self.seuil_ecart_critique:
                    alerte("CRITIQUE",nom,f"Écart BC/Sim très élevé : {ecart:.0%}. Vérifier seuil et stabilisation.",-15)
                elif ecart>=self.seuil_ecart_warn:
                    alerte("WARN",nom,f"Écart BC/Sim significatif : {ecart:.0%}. Justification obligatoire.",-8)

            for label,val in [("BC",bc_tech),("Sim",sim_tech),("Retenu",retenu)]:
                if val<0: alerte("CRITIQUE",nom,f"Taux {label} négatif.",-20)
                if 0<val>self.seuil_taux_extreme: alerte("CRITIQUE",nom,f"Taux {label} > {self.seuil_taux_extreme:.0%}.",-20)

            if t.get("portee",0)<=0 or t.get("priorite",0)<0:
                alerte("CRITIQUE",nom,"Priorité ou portée invalide.",-20)

        score=max(0,min(100,score))
        verdict="ROBUSTE" if score>=85 else "ACCEPTABLE AVEC RÉSERVES" if score>=65 else "À REVOIR"
        return {"synthese":{"score":score,"verdict":verdict,"nb_alertes":len(alertes),
                "nb_critiques":sum(1 for a in alertes if a["niveau"]=="CRITIQUE"),
                "nb_warn":sum(1 for a in alertes if a["niveau"]=="WARN")},
                "alertes":alertes,"decisions":decisions}


class AgentML:
    def __init__(self, random_state=42): self.random_state=random_state

    def entrainer_depuis_df_proj(self, df, target="Sprime_ultime"):
        try:
            from sklearn.model_selection import train_test_split
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            from sklearn.tree import DecisionTreeRegressor
            from sklearn.ensemble import RandomForestRegressor
        except Exception as e:
            return {"disponible":False,"message":f"scikit-learn indisponible : {e}","modeles":[],"meilleur_modele":None,"importance":[]}

        if df is None or df.empty or target not in df.columns:
            return {"disponible":False,"message":"Target indisponible.","modeles":[],"meilleur_modele":None,"importance":[]}

        data=df.copy().replace([np.inf,-np.inf],np.nan)
        y=pd.to_numeric(data[target],errors="coerce"); X=data.drop(columns=[target],errors="ignore")
        keep=[c for c in X.columns if X[c].notna().mean()>=0.60]; X=X[keep]
        for c in X.columns:
            if X[c].dtype=="object": X[c]=X[c].astype(str).fillna("NA")
            else: X[c]=pd.to_numeric(X[c],errors="coerce")
        mask=y.notna(); X=X.loc[mask].copy(); y=y.loc[mask].copy()
        if len(X)<30: return {"disponible":False,"message":"Moins de 30 observations exploitables.","modeles":[],"meilleur_modele":None,"importance":[]}
        X_enc=pd.get_dummies(X,dummy_na=True).fillna(0)

        X_tr,X_te,y_tr,y_te=train_test_split(X_enc,y,test_size=0.25,random_state=self.random_state)
        models={"Arbre":DecisionTreeRegressor(max_depth=4,min_samples_leaf=5,random_state=self.random_state),
                "Random Forest":RandomForestRegressor(n_estimators=250,max_depth=8,min_samples_leaf=3,random_state=self.random_state,n_jobs=-1)}
        try:
            from xgboost import XGBRegressor
            models["XGBoost"]=XGBRegressor(n_estimators=300,max_depth=4,learning_rate=0.05,subsample=0.85,colsample_bytree=0.85,objective="reg:squarederror",random_state=self.random_state)
        except: pass

        resultats=[]; best_name=None; best_mae=None; best_model=None
        for name,model in models.items():
            try:
                model.fit(X_tr,y_tr); pred=model.predict(X_te)
                mae=float(mean_absolute_error(y_te,pred)); rmse=float(np.sqrt(mean_squared_error(y_te,pred))); r2=float(r2_score(y_te,pred))
                resultats.append({"modele":name,"MAE":mae,"RMSE":rmse,"R2":r2,"n_train":int(len(X_tr)),"n_test":int(len(X_te))})
                if best_mae is None or mae<best_mae: best_mae=mae; best_name=name; best_model=model
            except Exception as e:
                resultats.append({"modele":name,"MAE":None,"RMSE":None,"R2":None,"erreur":str(e)})

        importance=[]
        if best_model is not None and hasattr(best_model,"feature_importances_"):
            imp=pd.Series(best_model.feature_importances_,index=X_enc.columns).sort_values(ascending=False).head(10)
            importance=[{"variable":k,"importance":float(v)} for k,v in imp.items()]

        return {"disponible":True,"message":"Benchmark statistique exécuté. Interprétation prudente recommandée.",
                "modeles":resultats,"meilleur_modele":best_name,"importance":importance}


class AgentMemoireMetier:
    @staticmethod
    def _to_float(x, default=0.0):
        try:
            if x is None or x=="": return default
            if isinstance(x,str):
                s=x.replace("%","").replace(" ","").replace(",",".")
                val=float(s); return val/100 if "%"in x or val>1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _row_get(row,*keys,default=None):
        for k in keys:
            if isinstance(row,dict) and k in row: return row.get(k)
        return default

    def charger_rapports_historiques(self, user_email, current_session_id=None, limite=100):
        try:
            con,db=_get_conn(); cur=con.cursor(); p=_ph()
            if current_session_id:
                cur.execute(f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                    JOIN resultats r ON r.session_id=s.id
                    WHERE s.user_email={p} AND r.etape='rapport' AND s.id!={p}
                    ORDER BY s.updated_at DESC LIMIT {int(limite)}""",(user_email,current_session_id))
            else:
                cur.execute(f"""SELECT s.id,s.nom_session,s.gnpi,r.data_json FROM sessions s
                    JOIN resultats r ON r.session_id=s.id
                    WHERE s.user_email={p} AND r.etape='rapport'
                    ORDER BY s.updated_at DESC LIMIT {int(limite)}""",(user_email,))
            rows=cur.fetchall(); con.close()
        except: return []
        historiques=[]
        for sid,nom,gnpi_h,data_json in rows:
            try:
                d=json.loads(data_json); rr=d.get("rows",[]); pt=d.get("prime_totale",0)
                if rr: historiques.append({"session_id":sid,"nom_session":nom,"gnpi":gnpi_h,"prime_totale":pt,"rows":rr})
            except: continue
        return historiques

    def benchmark(self, user_email, tranches, rapport_rows, gnpi, current_session_id=None):
        historiques=self.charger_rapports_historiques(user_email,current_session_id=current_session_id)
        if not historiques:
            return {"disponible":False,"message":"Aucun ancien rapport exploitable dans la mémoire métier.","comparaisons":[],"synthese":{}}
        current_by_type={}
        for r in rapport_rows or []:
            typ=str(self._row_get(r,"type","Type",default="")).lower()
            taux=self._to_float(self._row_get(r,"taux_retenu","Taux retenu",default=0))
            if typ and taux>0: current_by_type.setdefault(typ,[]).append(taux)
        hist_by_type={}; hist_global=[]
        for h in historiques:
            rows=h.get("rows",[]); pt=self._to_float(h.get("prime_totale",0)); gh=self._to_float(h.get("gnpi",0))
            if gh>0 and pt>0: hist_global.append(pt/gh)
            for r in rows:
                typ=str(self._row_get(r,"type","Type",default="")).lower()
                taux=self._to_float(self._row_get(r,"taux_retenu","Taux retenu",default=0))
                if typ and taux>0: hist_by_type.setdefault(typ,[]).append(taux)
        comparaisons=[]
        for typ,vals in current_by_type.items():
            if typ not in hist_by_type or len(hist_by_type[typ])<2: continue
            cur_med=float(np.median(vals)); hist_med=float(np.median(hist_by_type[typ]))
            hist_q25=float(np.quantile(hist_by_type[typ],0.25)); hist_q75=float(np.quantile(hist_by_type[typ],0.75))
            ecart=(cur_med-hist_med)/max(hist_med,1e-12)
            comparaisons.append({"type":typ,"taux_dossier":cur_med,"mediane_historique":hist_med,
                "q25_historique":hist_q25,"q75_historique":hist_q75,"ecart_vs_mediane":ecart,
                "diagnostic":"au-dessus" if ecart>0.20 else "sous la référence" if ecart<-0.20 else "proche de l'historique",
                "n_reference":len(hist_by_type[typ])})
        pt_curr=sum(self._to_float(self._row_get(r,"prime_AED","Prime (AED)",default=0)) for r in rapport_rows or [])
        tg=pt_curr/gnpi if gnpi else 0
        return {"disponible":True,"message":"Mémoire métier activée.","comparaisons":comparaisons,
                "synthese":{"nb_dossiers_reference":len(historiques),"taux_global_dossier":tg,
                "mediane_taux_global_historique":float(np.median(hist_global)) if hist_global else 0,"memoire_active":True}}


class AgentChallenger:
    @staticmethod
    def _num(x,default=0.0):
        try:
            if x is None or x=="": return default
            if isinstance(x,str):
                s=x.replace("%","").replace(" ","").replace(",",".")
                val=float(s); return val/100 if "%"in x or val>1.5 else val
            return float(x)
        except: return default

    @staticmethod
    def _map(rows): return {r.get("tranche",r.get("Tranche","")): r for r in (rows or [])}

    def challenger(self, tranches, resultats_bc, resultats_sim, resultats_mkt, rapport_rows):
        bc=self._map(resultats_bc); sim=self._map(resultats_sim)
        mkt=self._map(resultats_mkt); rpt=self._map(rapport_rows)
        avis=[]
        for i,t in enumerate(tranches or []):
            nom=t.get("nom",f"Tranche {i+1}"); typ=t.get("type","")
            bt=self._num(bc.get(nom,{}).get("taux_technique"))
            stt=self._num(sim.get(nom,{}).get("taux_technique"))
            mt=self._num(mkt.get(nom,{}).get("taux",mkt.get(nom,{}).get("taux_tech")))
            rt=self._num(rpt.get(nom,{}).get("taux_retenu"))
            n_nz=int(self._num(bc.get(nom,{}).get("n_ann_nonzero"),0))
            prudent=max(bt,stt,mt)
            marche=mt if (typ!="travaillante" and mt>0) else stt if stt>0 else bt
            equilibre=np.mean([x for x in [bt,stt,mt] if x>0]) if any(x>0 for x in [bt,stt,mt]) else 0
            dispersion=(max(p for p in [prudent,marche,equilibre])-min(p for p in [prudent,marche,equilibre]))/max(equilibre,1e-12) if equilibre else 0
            conflit="fort" if dispersion>0.35 else "modéré" if dispersion>0.15 else "faible"
            arbitrage="Conserver le taux retenu" if (rt>=min(prudent,equilibre) or rt==0) else "Relever le taux ou documenter l'écart"
            if typ=="travaillante" and n_nz<3: arbitrage="Ne pas se reposer sur le BC — jugement expert documenté"
            avis.append({"tranche":nom,"type":typ,"taux_retenu":rt,"avis_prudentiel":prudent,
                "avis_marche":marche,"avis_equilibre":equilibre,"conflit":conflit,"arbitrage":arbitrage})
        return {"avis":avis,"nb_conflits_forts":sum(1 for a in avis if a["conflit"]=="fort")}


class AgentOptimisationProgramme:
    def __init__(self, gnpi): self.gnpi=gnpi

    @staticmethod
    def _base_rate(t, idx, rbc, rsim, rmkt):
        nom=t.get("nom","")
        def lk(rows,key):
            for r in rows or []:
                if r.get("tranche")==nom: return float(r.get(key,0) or 0)
            if idx<len(rows or []): return float((rows or [])[idx].get(key,0) or 0)
            return 0.0
        bc=lk(rbc,"taux_technique"); sim=lk(rsim,"taux_technique"); mkt=lk(rmkt,"taux")
        return max(bc,sim) if t.get("type")=="travaillante" else max(sim,mkt)

    def _estimate_rate(self, t_ref, t_new, base_rate):
        p0=max(float(t_ref.get("priorite",1)),1); l0=max(float(t_ref.get("portee",1)),1)
        p1=max(float(t_new.get("priorite",p0)),1); l1=max(float(t_new.get("portee",l0)),1)
        rec0=max(float(t_ref.get("nb_reconstitutions",1)),1); rec1=max(float(t_new.get("nb_reconstitutions",rec0)),1)
        adj=(l1/l0)**0.55*(p0/p1)**0.35*(rec1/rec0)**0.08
        return max(base_rate*adj,0)

    def explorer(self, tranches, rbc, rsim, rmkt, objectif="equilibre", prime_cible=None, top_n=8):
        if not tranches: return {"alternatives":[],"message":"Programme vide."}
        alternatives=[]
        for mp in [0.85,1.00,1.15]:
            for md in [0.90,1.00,1.10]:
                for dr in [-1,0,1]:
                    new_t=[]; prime=0.0; protection=0.0
                    for i,t in enumerate(tranches):
                        tn=dict(t)
                        tn["portee"]=round(float(t.get("portee",0))*mp/500_000)*500_000
                        tn["priorite"]=round(float(t.get("priorite",0))*md/500_000)*500_000
                        tn["portee"]=max(tn["portee"],500_000); tn["priorite"]=max(tn["priorite"],0)
                        tn["nb_reconstitutions"]=int(max(1,min(4,int(t.get("nb_reconstitutions",1))+dr)))
                        base=self._base_rate(t,i,rbc,rsim,rmkt)
                        taux=self._estimate_rate(t,tn,base)
                        prime_t = self.gnpi * taux
                        tn["_taux"] = taux
                        tn["_prime"] = prime_t
                        tn["_base_rate"] = base
                        prime += prime_t
                        protection += tn["portee"] * (1 + tn["nb_reconstitutions"] * tn.get("taux_reconstitution", 100) / 100)
                        new_t.append(tn)
                    taux_g=prime/self.gnpi if self.gnpi else 0
                    pen=abs(prime-prime_cible)/max(prime_cible,1) if prime_cible else 0
                    if objectif=="cedante": score=protection/1e6-60*taux_g-10*pen
                    elif objectif=="reassureur": score=100*taux_g-0.03*protection/1e6-5*pen
                    else: score=protection/1e6-35*taux_g-8*pen
                    comparabilite = max(0.0, 100.0 - 100.0 * abs(mp - 1.0) - 100.0 * abs(md - 1.0) - 12.0 * abs(dr))
                    alternatives.append({"label":f"Portée {mp:.0%}|Priorité {md:.0%}|Rec {dr:+d}",
                        "prime":prime,"taux_global":taux_g,"protection_theorique":protection,
                        "score":score,"indice_comparabilite":comparabilite,"tranches":new_t})
        alternatives=sorted(alternatives,key=lambda x:x["score"],reverse=True)[:top_n]
        return {"alternatives":alternatives,"message":f"{len(alternatives)} alternatives selon objectif {objectif}."}


def afficher_plan_actuariel(plan):
    if not plan: return
    tableau_resultats([{"Ordre":i,"Étape":p["titre"],"Priorité":p["priorite"],"Justification":p["justification"]}
        for i,p in enumerate(plan,1)],"Séquence de traitement actuariel")

def afficher_critique_actuariel(critique):
    if not critique: return
    syn=critique.get("synthese",{})
    c1,c2,c3=st.columns(3)
    with c1: card("Score audit",f"{syn.get('score',0)}/100",icone="")
    with c2: card("Verdict",syn.get("verdict","—"),couleur="#1a1a1a",icone="")
    with c3: card("Alertes",f"{syn.get('nb_alertes',0)}",couleur="#f59e0b",icone="")
    alertes=critique.get("alertes",[])
    if alertes: tableau_resultats([{"Niveau":a["niveau"],"Tranche":a["tranche"],"Message":a["message"]} for a in alertes],"Alertes critiques")

def afficher_memoire_metier(memoire):
    if not memoire:
        return

    st.markdown("#### Mémoire métier inter-dossiers")

    if not memoire.get("disponible"):
        st.info(memoire.get("message", "Mémoire indisponible."))
        return

    syn = memoire.get("synthese", {}) or {}

    c1, c2, c3 = st.columns(3)
    with c1:
        card("Dossiers référence", syn.get("nb_dossiers_reference", 0), icone="")
    with c2:
        card("Taux dossier", f"{float(syn.get('taux_global_dossier', 0) or 0):.4%}", couleur="#1a1a1a", icone="")
    with c3:
        card("Médiane historique", f"{float(syn.get('mediane_taux_global_historique', 0) or 0):.4%}", couleur="#3b82f6", icone="")

    st.caption(
        "Nb réf. hist. = nombre d'observations historiques disponibles pour le type de tranche considéré. "
        "Ces observations servent au calcul de la médiane historique et des quartiles Q25-Q75."
    )

    rows = []
    for c in memoire.get("comparaisons", []) or []:
        rows.append({
            "Type": c.get("type", ""),
            "Dossier": f"{float(c.get('taux_dossier', 0) or 0):.4%}",
            "Médiane hist.": f"{float(c.get('mediane_historique', 0) or 0):.4%}",
            "Q25-Q75": (
                f"{float(c.get('q25_historique', 0) or 0):.4%}/"
                f"{float(c.get('q75_historique', 0) or 0):.4%}"
            ),
            "Écart": f"{float(c.get('ecart_vs_mediane', 0) or 0):+.1%}",
            "Diagnostic": c.get("diagnostic", ""),
            "Nb réf. hist.": int(c.get("n_reference", 0) or 0),
        })

    if rows:
        tableau_resultats(rows)
    else:
        st.info("Aucune comparaison exploitable par type de tranche.")

def afficher_challenger(challenge):
    if not challenge: return
    st.markdown("#### Analyse contradictoire actuarielle")
    rows=[{"Tranche":a["tranche"],"Type":a["type"],"Retenu":f"{a['taux_retenu']:.4%}",
        "Prudentiel":f"{a['avis_prudentiel']:.4%}","Marché":f"{a['avis_marche']:.4%}",
        "Équilibre":f"{a['avis_equilibre']:.4%}","Conflit":a["conflit"],"Arbitrage":a["arbitrage"]}
        for a in challenge.get("avis",[])]
    if rows: tableau_resultats(rows)

def afficher_optimisation_avancee(opt):
    if not opt:
        return

    st.markdown("#### Recherche de programmes alternatifs comparables")
    st.caption(opt.get("message", ""))

    alternatives = opt.get("alternatives", []) or []

    def _fmt_aed(x):
        return f"{float(x or 0):,.0f} AED"

    def _structure_resume(tranches_alt, max_items=3):
        if not tranches_alt:
            return "—"
        morceaux = []
        for j, t in enumerate(tranches_alt[:max_items], 1):
            nom = t.get("nom", f"T{j}")
            priorite = float(t.get("priorite", 0.0) or 0.0) / 1_000_000
            portee = float(t.get("portee", 0.0) or 0.0) / 1_000_000
            rec = int(t.get("nb_reconstitutions", 0) or 0)
            morceaux.append(f"{nom}: {portee:.1f}M xs {priorite:.1f}M, Rec {rec}")
        if len(tranches_alt) > max_items:
            morceaux.append(f"+{len(tranches_alt) - max_items} tranche(s)")
        return " | ".join(morceaux)

    rows = [{
        "Rang": i,
        "Scénario": a.get("label", f"Alternative {i}"),
        "Structure": _structure_resume(a.get("tranches", []) or [], max_items=2),
        "Prime": _fmt_aed(a.get("prime", 0.0)),
        "Taux global": f"{float(a.get('taux_global', 0.0) or 0.0):.4%}",
        "Protection": f"{float(a.get('protection_theorique', 0.0) or 0.0):,.0f}",
        "Comparabilité": f"{float(a.get('indice_comparabilite', 0.0) or 0.0):.0f}/100",
        "Score": f"{float(a.get('score', 0.0) or 0.0):.2f}",
    } for i, a in enumerate(alternatives, 1)]

    if rows:
        tableau_resultats(rows)

    if alternatives:
        st.markdown("##### Structure détaillée des alternatives")
        st.caption(
            "Sélectionnez une alternative pour afficher la composition complète du programme : priorité, portée, "
            "reconstitutions, taux estimé et prime estimée par tranche."
        )

        choix = st.selectbox(
            "Afficher la structure détaillée",
            options=list(range(len(alternatives))),
            format_func=lambda idx: (
                f"Rang {idx + 1} — {alternatives[idx].get('label', f'Alternative {idx + 1}')}"
            ),
            key="select_structure_alternative_agentique"
        )

        alt = alternatives[choix]
        tranches_alt = alt.get("tranches", []) or []

        if tranches_alt:
            rows_struct = []
            for j, t in enumerate(tranches_alt, 1):
                rows_struct.append({
                    "Rang": j,
                    "Tranche": t.get("nom", f"Tranche {j}"),
                    "Type": t.get("type", ""),
                    "Priorité": f"{float(t.get('priorite', 0.0) or 0.0):,.0f}",
                    "Portée": f"{float(t.get('portee', 0.0) or 0.0):,.0f}",
                    "AAD": f"{float(t.get('AAD', 0.0) or 0.0):,.0f}" if t.get("AAD") else "—",
                    "AAL": f"{float(t.get('AAL', 0.0) or 0.0):,.0f}" if t.get("AAL") else "—",
                    "Reconstitutions": int(t.get("nb_reconstitutions", 0) or 0),
                    "Taux rec.": f"{float(t.get('taux_reconstitution', 0.0) or 0.0):.0f}%",
                    "Taux estimé": f"{float(t.get('_taux', 0.0) or 0.0):.4%}",
                    "Prime estimée": _fmt_aed(t.get("_prime", 0.0)),
                })

            tableau_resultats(rows_struct, f"Structure détaillée — {alt.get('label', 'Alternative')}")
        else:
            st.info("Aucune structure détaillée disponible pour cette alternative.")

def afficher_ml_actuariel(ml):
    if not ml: return
    st.markdown("#### Approximation statistique — benchmark")
    if not ml.get("disponible"): st.info(ml.get("message","ML non disponible.")); return
    rows=[{"Modèle":r.get("modele"),"MAE":f"{r.get('MAE',0):,.0f}" if r.get("MAE") else "Erreur",
        "RMSE":f"{r.get('RMSE',0):,.0f}" if r.get("RMSE") else "Erreur",
        "R²":f"{r.get('R2',0):.4f}" if r.get("R2") else "Erreur",
        "Statut":"" if r.get("MAE") else r.get("erreur","Erreur")} for r in ml.get("modeles",[])]
    tableau_resultats(rows,"Comparaison des modèles ML")
    if ml.get("importance"):
        tableau_resultats([{"Variable":x["variable"],"Importance":f"{x['importance']:.4f}"} for x in ml["importance"]],
            f"Variables importantes — {ml.get('meilleur_modele')}")
# -----------------------------------------------------------------------------
# Alias de compatibilité avec app.py
# -----------------------------------------------------------------------------
# Les noms historiques sont conservés pour ne pas casser les imports existants.
# Les libellés affichés restent professionnels grâce aux fonctions ci-dessus.

def afficher_plan_agentique(plan):
    return afficher_plan_actuariel(plan)


def afficher_critique_agentique(critique):
    return afficher_critique_actuariel(critique)


def afficher_ml_agentique(ml):
    return afficher_ml_actuariel(ml)
