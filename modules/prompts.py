"""
Atlantic Re IA — Prompt engineering module
build_prompt, claude_stream, few-shot dynamique, guide_prompt.
"""
import streamlit as st
import anthropic
from modules.db import _get_conn, _ph

# ════════════════════════════════════════════
# PROMPT ENGINEERING
# ════════════════════════════════════════════

def prompt_inputs(key_prefix, placeholder_contexte="", placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    with st.expander("✏️ Personnaliser le prompt Claude", expanded=False):
        st.markdown("##### 🎯 Prompt Engineering")
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area("📌 Contexte",
                placeholder=placeholder_contexte or "Ex: Portefeuille automobile Maroc 2026...",
                height=80, key=f"{key_prefix}_contexte")
            instructions = st.text_area("📋 Instructions spécifiques",
                placeholder=placeholder_instructions or "Ex: Être attentif à la tranche Cat L1...",
                height=80, key=f"{key_prefix}_instructions")
        with c2:
            input_data = st.text_area("📥 Données supplémentaires",
                placeholder=placeholder_input or "Ex: Taux marché de référence : 3.2%...",
                height=80, key=f"{key_prefix}_input")
            output_instructions = st.text_area("📤 Format de sortie souhaité",
                placeholder=placeholder_output or "Ex: Tableau structuré + recommandation chiffrée...",
                height=80, key=f"{key_prefix}_output")
    return contexte, instructions, input_data, output_instructions


def _charger_few_shot_dynamiques(user_email, n_max=3):
    """Charge les N meilleurs exemples de sessions validées depuis la DB comme few-shot."""
    try:
        con, db = _get_conn(); cur = con.cursor(); p = _ph()
        cur.execute(f"""SELECT s.nom_session, s.gnpi, r.data_json FROM sessions s
            JOIN resultats r ON r.session_id=s.id
            WHERE s.user_email={p} AND r.etape='rapport'
            ORDER BY s.updated_at DESC LIMIT {n_max}""", (user_email,))
        rows = cur.fetchall(); con.close()
    except Exception:
        return ""
    if not rows:
        return ""
    exemples = []
    for nom, gnpi_h, data_json in rows:
        try:
            import json as _j
            d = _j.loads(data_json)
            rapport_rows = d.get("rows", [])
            pt = d.get("prime_totale", 0)
            if not rapport_rows: continue
            lines_ex = [f"SESSION : {nom or 'Sans nom'} | GNPI {(gnpi_h or 0):,.0f} MAD | Prime {pt:,.0f} MAD"]
            for r in rapport_rows[:4]:
                nom_t = r.get("tranche","") or r.get("Tranche","")
                typ_t = r.get("type","") or r.get("Type","")
                tau   = r.get("taux_retenu","") or r.get("Taux retenu","")
                meth  = r.get("methode","") or r.get("Méthode","")
                lines_ex.append(f"  {nom_t} ({typ_t}) → Retenu {tau} via {meth}")
            exemples.append("\n".join(lines_ex))
        except Exception:
            continue
    if not exemples:
        return ""
    return "\n\n".join([f"CAS HISTORIQUE {i+1} :\n{ex}" for i, ex in enumerate(exemples)])

def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    """
    Prompt engineering avancé pour tarification réassurance non-proportionnelle.
    Intègre : chain-of-thought, few-shot, contraintes actuarielles, cadre réglementaire.
    """
    prompt = f"""
╔══════════════════════════════════════════════════════════════╗
║  ATLANTIC RE IA — AGENT ACTUARIEL EXPERT                     ║
║  Réassurance Non-Proportionnelle XL · Automobile · Maroc    ║
╚══════════════════════════════════════════════════════════════╝

═══ IDENTITÉ & RÔLE ══════════════════════════════════════════
{role}

Niveau d'expertise requis : Senior (15+ ans réassurance non-prop, marchés émergents, automobile).

═══ CADRE RÉGLEMENTAIRE & NORMES ACTUARIELLES ═══════════════
• Standards IAA (International Actuarial Association)
• Normes IAIS pour la réassurance non-proportionnelle
• Réglementation DAPS Maroc (Circulaire n°AS/17)
• Principes ASTIN/CAS pour la tarification sinistre-à-sinistre
• Solvency II — Pilier 1 pour la modélisation du risque
• Standards IFoA (Institute & Faculty of Actuaries) — Actuarial Profession Standards

═══ RÈGLES ABSOLUES — ANTI-HALLUCINATION ════════════════════
1. VÉRIFICATION SYSTÉMATIQUE : Tout chiffre doit être tracé à sa source dans les données.
2. TRIANGLE INTERDIT : Ne JAMAIS reconstituer ou afficher un triangle dans le texte.
   → Référencer : "Consultez le triangle réel dans l'onglet BC."
3. RAISONNEMENT CHAÎNÉ (Chain-of-Thought) :
   [Observation factuelle] → [Hypothèse testée] → [Calcul explicite] → [Conclusion chiffrée]
4. INCERTITUDE OBLIGATOIRE : Si données insuffisantes → "Données insuffisantes pour conclure."
   Ne jamais extrapoler au-delà des données observées sans le signaler.
5. HIÉRARCHIE ACTUARIELLE INVARIABLE :
   τ_pur ≤ τ_risque ≤ τ_technique (toujours, sinon anomalie à signaler)
6. SOURCES PRIMAIRES : Préférer la littérature actuarielle (CAS, ASTIN, Daykin-Pentikäinen-Pesonen).

═══ CONTRAINTES MÉTIER SPÉCIFIQUES ═════════════════════════
{contraintes if contraintes else """
━━━ RÈGLE FONDAMENTALE : PRIMAUTÉ DU BURNING COST ━━━━━━━━━━
Le Burning Cost est LA méthode de référence en réassurance XL.
• Il reflète l'EXPÉRIENCE RÉELLE de la cédante → TOUJOURS analyser en premier.
• Si le BC est disponible et crédible → c'est lui qui fixe le tarif, la simulation est un outil de VALIDATION.
• EXCEPTION : branches non-travaillantes, partiellement travaillantes, cat → BC peu/pas crédible → simulation prioritaire.

━━━ DÉTECTION ET TRAITEMENT DES ANNÉES ATYPIQUES ━━━━━━━━━━
L'actuaire DOIT identifier les années atypiques AVANT de tarifer.
Causes d'écartement légitimes (doivent être documentées) :
  [A] ISOLEMENT : L'année présente un taux >> ses voisines immédiates (N-1 et N+1 ont des taux normaux)
  [B] NATURE CAT : L'année contient des sinistres CAT alors que la tranche tarifée est Risk uniquement (non R&C)
  [C] GNPI/EPI FAIBLE : Le GNPI de cette année est anormalement bas vs la moyenne historique (< 50% de la médiane)
  [D] SINISTRE UNIQUE : Un seul grand sinistre exceptionnel déforme l'année (doit être traité via TVE/GPD)
  [E] CHANGEMENT PORTEFEUILLE : Modification majeure du périmètre assuré cette année-là
Règle : Signaler l'anomalie, présenter les deux calculs (avec et sans), et justifier le choix retenu.

━━━ RÈGLES PAR TYPE DE TRANCHE ━━━━━━━━━━━━━━━━━━━━━━━━━━━
TRANCHE TRAVAILLANTE :
  → BC = méthode principale (expérience directement disponible)
  → Simulation = validation et détection de problèmes potentiels
  → Objectif simulation : ajuster α et λ pour que la distribution simulée colle
    au MAXIMUM à la distribution empirique, SURTOUT EN QUEUE
  → Si simulation ≠ BC malgré ajustement optimal : signal que l'affaire a un problème structurel
    (changement de portefeuille, sinistres atypiques non identifiés, etc.)
  → τ_retenu = max(BC, Sim) — côté prudence

TRANCHE NON-TRAVAILLANTE / PARTIELLEMENT TRAVAILLANTE :
  → BC généralement nul ou non crédible (manque de sinistres historiques au-dessus de la priorité)
  → SIMULATION = méthode principale — TRÈS grande attention aux paramètres
  → Market curve = référence secondaire (calibrage externe)
  → τ_retenu = max(Sim, Marché) — prudence absolue
  → Justifier pourquoi le BC n'est pas utilisé (règle R2)

TRANCHE CAT :
  → BC = souvent nul (R2) ou non représentatif → normal
  → SIMULATION = principale, TRÈS attention à α (queue lourde) et λ (fréquence événements)
  → Market curve = important pour benchmarking
  → τ_retenu = max(Sim, Marché) — ne jamais prendre le BC seul pour le cat

━━━ RÈGLES MARKET CURVE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Utiliser UNIQUEMENT des données de marché représentatives des tranches tarifées
• Si les tranches ont un ROL ~ 10% → filtrer les données entre ROL_min et ROL_max définis par tranche
  (ex: si ROL cible ~ 10%, utiliser données entre 0% et 15% seulement)
• Ne JAMAIS mélanger des données de ROL très élevé avec des tranches à faible ROL
• R² minimum acceptable : 0.40 avec N ≥ 15 points
• Si R² < 0.30 → mentionner la faible robustesse dans le rapport

━━━ RÈGLES NUMÉRIQUES (INVARIANTES) ━━━━━━━━━━━━━━━━━━━━━
• τ_pur ≤ τ_risque ≤ τ_technique (toujours, anomalie critique si non respecté)
• τ_risque = τ_pur + σ_hist × 20% (R1, CAS standard)
• BC = 0 si années non-nulles < 3 (R2)
• Market curve : cat uniquement sauf exception documentée (R4)
• Reconstitutions : cap = (n_rec + 1) × portée
• As-If sur incréments (méthode Finger 2006)
• Stabilisation : I_règl/I_surv ≥ 1 + seuil"""}

═══ CONTEXTE GLOBAL PORTEFEUILLE ════════════════════════════
{contexte_global if contexte_global else "Portefeuille automobile Maroc, réassurance non-proportionnelle, marché en développement."}

═══ CONTEXTE SPÉCIFIQUE ═════════════════════════════════════
{contexte if contexte else "Non fourni."}

═══ TÂCHE ═══════════════════════════════════════════════════
{task}

═══ DONNÉES D'ANALYSE ═══════════════════════════════════════
{data}
{("DONNÉES SUPPLÉMENTAIRES FOURNIES :\n" + input_data) if input_data else ""}

═══ INSTRUCTIONS DE PRÉCISION ═══════════════════════════════
{instructions if instructions else "Appliquer les règles actuarielles et produire une analyse structurée."}

═══ EXEMPLES FEW-SHOT (référence qualité) ═══════════════════
{exemples if exemples else """
CAS 1 — Tranche travaillante avec BC crédible :
  T1 (13M xs 2M) — Travaillante :
  → BC : 8 ans non-nuls / 10 | τ_pur=2.18% σ=1.45% τ_risque=2.47% τ_tech=3.26% ✅ CRÉDIBLE
  → Sim : τ_pur=3.12% τ_tech=4.59% | α=1.45 λ=3.2 → ajustement visuel OK
  → Écart BC/Sim = 29% > 25% → analyser les années atypiques
  → DÉCISION : BC=3.26% prioritaire (expérience directe) | retenu = max(3.26%, 4.59%) = 4.59% (prudence)

CAS 2 — Année atypique détectée (cause B) :
  Année 2019 : τ=8.2% vs voisines 2018=1.1%, 2020=1.4% → ATYPIQUE (ratio 6× voisines)
  Cause identifiée : sinistre CAT (inondation) dans un programme Risk uniquement
  → Décision : ÉCARTER 2019 de l'analyse BC
  → BC recalculé sans 2019 : τ_tech=2.85% (vs 4.12% avec 2019)

CAS 3 — Tranche cat sans données :
  T2 Cat (10M xs 15M) :
  → BC : 0 années non-nulles → τ_BC = 0% (R2 — NORMAL pour une tranche cat)
  → Sim : α=1.45 λ=0.8 → τ_sim=1.24% | ROL_sim=2.27%
  → Market : ROL_marché=1.85% (données filtrées ROL∈[0.5%, 3%], R²=0.52 N=22)
  → DÉCISION : τ_retenu = max(1.24%, 1.34%) = 1.34% (marché légèrement supérieur)

EXEMPLE MAUVAIS (à éviter) :
  "Le taux BC est faible donc on retient la simulation."
  → Non quantifié, cause de l'écart non identifiée, aucune analyse des années atypiques."""}

═══ FORMAT DE SORTIE REQUIS ════════════════════════════════
{output_instructions if output_instructions else """
1. ANALYSE PRÉALABLE (années atypiques, crédibilité BC par tranche)
2. SYNTHÈSE BURNING COST (avec/sans années atypiques si applicable)
3. SYNTHÈSE SIMULATION (adéquation distribution empirique, notamment en queue)
4. SYNTHÈSE MARKET CURVE (filtre ROL appliqué, R², représentativité)
5. TARIF RETENU PAR TRANCHE (règle de sélection justifiée)
6. CONCLUSION ACTUARIELLE (ACCEPTER / NÉGOCIER / RÉVISER + prime totale)"""}

La précision quantitative prime sur l'exhaustivité qualitative.
Chaque affirmation doit être étayée par un calcul explicite.
╔══════════════════════════════════════════════════════════════╗
"""
    return prompt.strip()


def claude_stream(api_key, prompt, max_tokens=2000, session_key="", use_opus=False):
    """
    use_opus=True  → claude-opus-4-5   (agent autonome, calculs complexes)
    use_opus=False → claude-haiku-4-5  (analyses copilote, 20x moins cher)
    """
    model = "claude-opus-4-5" if use_opus else "claude-haiku-4-5-20251001"
    client = anthropic.Anthropic(api_key=api_key)
    placeholder = st.empty()
    full_text = ""
    label_model = "Opus" if use_opus else "Haiku ⚡"
    with st.status(f"🤖 Agent Claude ({label_model}) en cours...", expanded=True) as status:
        st.write("🔗 Connexion au modèle...")
        st.write("📊 Chargement des données actuarielles...")
        try:
            with client.messages.stream(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                st.write("✍️ Génération de l'analyse...")
                for text in stream.text_stream:
                    full_text += text
                    placeholder.markdown(full_text + "▌")
            status.update(label="✅ Analyse terminée", state="complete", expanded=False)
        except Exception as e:
            status.update(label="❌ Erreur", state="error")
            st.error(f"Erreur API : {e}")
            return ""
    placeholder.markdown(full_text)
    if session_key:
        st.session_state[session_key] = full_text
    return full_text



def guide_prompt(etape, exemples_contexte, exemples_instructions, exemples_input, exemples_output=None):
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
            if exemples_output:
                st.markdown("**📤 Format de sortie**")
                for ex in exemples_output: st.markdown(f"- {ex}")
        st.markdown("""<div style="background:#fff8f0;border-left:4px solid #f59e0b;border-radius:0 8px 8px 0;
            padding:10px 14px;margin-top:8px;font-size:12px">
            ⚠️ <b>Règle d'or :</b> Plus vous donnez de contexte métier, plus l'analyse sera pertinente.
            </div>""", unsafe_allow_html=True)
