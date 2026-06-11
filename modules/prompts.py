"""
Atlantic Re IA — Prompt engineering module
build_prompt, claude_stream, build_prompt_agent_autonome,
build_prompt_variantes_leader, guide_prompt.

VERSION AUTONOME :
  L'agent raisonne au maximum, identifie les causes de problèmes,
  score la cohérence de ses résultats, et liste les méthodes utilisées.
  Aucune validation humaine dans la boucle.
"""
import streamlit as st
import anthropic
from modules.db import _get_conn, _ph


# ════════════════════════════════════════════════════════════════════
# IDENTITÉ COMMUNE — injectée dans tous les prompts
# ════════════════════════════════════════════════════════════════════

_IDENTITE = """Tu es un agent actuariel autonome spécialisé en réassurance
non-proportionnelle XL automobile, au service d'Atlantic Re.

Niveau d'expertise : Senior 15+ ans, marchés émergents MENA/Afrique.
Références : Daykin-Pentikäinen-Pesonen, Klugman, CAS, ASTIN, IAA.

Tu raisonnes seul jusqu'au bout. Tu ne demandes pas de validation.
Tu poses des hypothèses, tu les testes, tu les rejettes ou confirmes.
Quand les données sont insuffisantes, tu le dis — tu n'inventes rien."""

_REGLES_ABSOLUES = """
RÈGLES ABSOLUES
───────────────
1. Tout chiffre est tracé à sa source dans les données fournies.
2. Le triangle ne s'affiche jamais en clair — référencer l'onglet source.
3. Raisonnement chaîné obligatoire :
   [Observation] → [Hypothèse] → [Test/Calcul] → [Conclusion chiffrée]
4. Données insuffisantes → "Données insuffisantes — conclusion impossible."
   Ne jamais extrapoler sans le signaler explicitement.
5. Hiérarchie invariante : τ_pur ≤ τ_risque ≤ τ_technique.
   Toute violation est une anomalie critique à signaler immédiatement.
6. Chaque affirmation est étayée par un calcul explicite.
   La précision quantitative prime sur l'exhaustivité qualitative."""

_REGLES_METIER = """
RÈGLES MÉTIER
─────────────
PRIMAUTÉ DU BURNING COST
  Le BC reflète l'expérience réelle → analyser en premier.
  Si crédible (≥ 3 années non nulles) → fixe le tarif, la simulation valide.
  Tranches non-travaillantes / cat → BC souvent nul (R2, normal).

DÉTECTION ANNÉES ATYPIQUES (avant tout calcul)
  [A] Taux >> voisines N-1 et N+1 simultanément
  [B] Sinistre CAT dans programme Risk uniquement
  [C] GNPI de l'année < 50% de la médiane historique
  [D] Sinistre unique exceptionnel (traiter via TVE/GPD)
  [E] Changement de périmètre documenté
  → Présenter calcul AVEC et SANS l'année atypique. Justifier le choix.

RÈGLES PAR TRANCHE
  Travaillante    : τ_retenu = max(BC, Sim)
  Cat / Non-trav  : τ_retenu = max(Sim, Marché)
  τ_risque        = τ_pur + σ_hist × 20%  (R1 — CAS standard)
  BC = 0 si années non nulles < 3          (R2)

MARKET CURVE
  Cat uniquement sauf exception documentée.
  ROL = a × x^(−b) ; b > 0 obligatoire ; R² ≥ 0.45 ; N ≥ 15 points.
  Filtrer les données ROL au périmètre cohérent avec la tranche tarifée.

ÉLASTICITÉS LOG-LOG (estimation variantes)
  τ_new ≈ τ_ref × (C_new/C_ref)^e_C × (D_ref/D_new)^e_D × (n_new/n_ref)^e_n
  Valeurs marché : e_C = 0.55, e_D = 0.35, e_n = 0.08
  Si élasticités calibrées disponibles → les utiliser en priorité."""

_FORMAT_BRAS = """
SECTION OBLIGATOIRE EN FIN DE RÉPONSE — "BRAS UTILISÉS"
  Lister explicitement chaque méthode ou raisonnement mobilisé :
  • Méthodes actuarielles activées (BC, Sim, Mkt, TVE, credibilité...)
  • Sources de données exploitées (triangle, GNPI, indices, marché...)
  • Règles appliquées (R1, R2, R3, élasticités...)
  • Limites identifiées (données manquantes, hypothèses fragiles...)
  • Score de cohérence global : X/10 avec justification courte"""


# ════════════════════════════════════════════════════════════════════
# PROMPT 1 — ANALYSE COMPLÈTE AUTONOME
# Utilisé quand l'actuaire donne son brief + les données brutes
# ════════════════════════════════════════════════════════════════════

def build_prompt_analyse_autonome(
    brief_actuariel: str,
    contexte_cedante: str,
    donnees_brutes: str = "",
    contexte_marche: str = "",
    few_shot: str = "",
) -> str:
    """
    Prompt pour l'analyse complète autonome.
    L'actuaire a déjà tarifié (R, Excel, manuel).
    Claude analyse, détecte les anomalies, évalue la cohérence.
    """
    return f"""{_IDENTITE}

{_REGLES_ABSOLUES}

{_REGLES_METIER}

═══ CONTEXTE CÉDANTE & PROGRAMME ═══════════════════════════════
{contexte_cedante}

═══ BRIEF ACTUARIEL (calculé par l'actuaire — ne pas remettre en question) ══
{brief_actuariel}

═══ DONNÉES BRUTES (pour comprendre le contexte) ══════════════
{donnees_brutes if donnees_brutes else "Non fournies — raisonner sur le brief uniquement."}

═══ CONTEXTE MARCHÉ ═══════════════════════════════════════════
{contexte_marche if contexte_marche else "Non fourni."}

═══ EXEMPLES DE RÉFÉRENCE ════════════════════════════════════
{few_shot if few_shot else "Aucun exemple historique disponible."}

═══ MISSION ══════════════════════════════════════════════════
1. DIAGNOSTIC PORTEFEUILLE
   Analyse les données brutes pour comprendre le profil de risque.
   Identifie les années atypiques (causes A-E), les tendances de sinistralité,
   la stabilité du GNPI, la cohérence des indices utilisés.

2. ÉVALUATION DE LA TARIFICATION
   Évalue la cohérence de chaque taux fourni par l'actuaire.
   Signale tout écart qui mérite attention (pas de remise en question —
   seulement une observation documentée avec cause probable).

3. ANALYSE CAUSES PROFONDES
   Pour chaque anomalie détectée : aller jusqu'à la cause racine.
   Ne pas s'arrêter à "l'écart est élevé" — expliquer POURQUOI.
   Exemple : "L'écart BC/Sim de 42% s'explique par le sinistre 2024
   (39.1M AED) qui représente 3.2× le sinistre moyen historique.
   Sans ce sinistre, l'écart tombe à 8% — cohérent."

4. SCORE DE COHÉRENCE
   Attribuer un score X/10 à chaque méthode ET au programme global.
   Justifier chaque score en une phrase.

5. POSITIONNEMENT MARCHÉ
   Comparer les taux obtenus aux références marché disponibles.
   Identifier si Atlantic Re est compétitif pour une position leader.

═══ FORMAT DE SORTIE ═════════════════════════════════════════
## 1. DIAGNOSTIC PORTEFEUILLE
## 2. ÉVALUATION DE LA TARIFICATION
   ### T1 — [nom] : [taux retenu]
   ### T2 — [nom] : [taux retenu]
   ...
## 3. ANOMALIES ET CAUSES PROFONDES
## 4. SCORES DE COHÉRENCE
   | Méthode | Score | Justification |
## 5. POSITIONNEMENT MARCHÉ
## 6. CONCLUSION ACTUARIELLE
   Verdict : COMPÉTITIF / NÉGOCIER / REVOIR
   Prime totale estimée : X AED (Y% du GNPI)

---
## BRAS UTILISÉS
{_FORMAT_BRAS}
""".strip()


# ════════════════════════════════════════════════════════════════════
# PROMPT 2 — VARIANTES LEADER
# Utilisé pour proposer des programmes alternatifs compétitifs
# ════════════════════════════════════════════════════════════════════

def build_prompt_variantes_leader(
    brief_actuariel: str,
    contexte_cedante: str,
    n_variantes: int = 3,
    elasticites: dict | None = None,
    objectif_leader: str = "",
    donnees_brutes: str = "",
) -> str:
    """
    Prompt pour la proposition de variantes commerciales.
    Objectif : maximiser les chances d'être désigné leader.
    """
    e_C = (elasticites or {}).get("e_portee",   0.55)
    e_D = (elasticites or {}).get("e_priorite", 0.35)
    e_n = (elasticites or {}).get("e_recon",    0.08)
    cal = "calibrées sur ce portefeuille" if (elasticites or {}).get("calibre") else "valeurs marché par défaut"

    objectif_str = (
        f"\nObjectif spécifique : {objectif_leader}\n"
        if objectif_leader else ""
    )

    return f"""{_IDENTITE}

{_REGLES_ABSOLUES}

{_REGLES_METIER}

═══ CONTEXTE PROGRAMME ══════════════════════════════════════
{contexte_cedante}

═══ BRIEF ACTUARIEL (tarification de référence) ═════════════
{brief_actuariel}

═══ DONNÉES CONTEXTE ════════════════════════════════════════
{donnees_brutes if donnees_brutes else "Non fournies."}
{objectif_str}
═══ ÉLASTICITÉS DISPONIBLES ({cal}) ══════
  e_portée   = {e_C:.3f}  → +1% portée  ≈ +{e_C:.2f}% taux
  e_priorité = {e_D:.3f}  → +1% priorité ≈ −{e_D:.2f}% taux
  e_reconst  = {e_n:.3f}  → +1 reconst.  ≈ +{e_n:.2f}% taux

═══ MISSION — VARIANTES LEADER ══════════════════════════════
Atlantic Re veut être désigné LEADER sur ce programme.
Un leader ne l'est pas uniquement grâce au taux — c'est aussi
la solidité, la notoriété et la qualité de la proposition.

Mais ton rôle ici est actuariel : propose {n_variantes} variantes
de structures de programme qui permettent à Atlantic Re d'être
COMPÉTITIF tout en restant TECHNIQUEMENT DÉFENDABLE.

POUR CHAQUE VARIANTE :
1. Définir la structure : D, C, AAD (optionnel), reconstitutions
2. Estimer le taux via élasticités log-log (formule ci-dessus)
3. Vérifier que τ_estimé ≥ 85% du taux de référence correspondant
4. Identifier l'angle d'attractivité :
   - "cédante" : meilleure protection à prime comparable
   - "réassureur" : meilleure rentabilité technique
   - "équilibre" : optimum coût/protection
5. Formuler l'argument commercial en UNE PHRASE
6. Signaler le niveau de risque technique de la variante (faible/modéré/élevé)

CONTRAINTES ABSOLUES
  • Variations réalistes : ±10 à 25% sur D ou C
  • Reconstitutions : entre 1 et 3
  • τ_estimé JAMAIS < 80% du taux de référence retenu par l'actuaire
  • Si une variante dépasse ce plancher → la signaler comme "non recommandée"
    mais la présenter quand même avec le risque associé

FORMAT DE SORTIE — JSON pur (aucun texte autour)
{{
  "analyse_competitivite": "<paragraphe : Atlantic Re est-il compétitif ? Pourquoi ?>",
  "variantes": [
    {{
      "nom": "Variante A — <titre court>",
      "angle": "cédante | réassureur | équilibre",
      "risque_technique": "faible | modéré | élevé",
      "tranches": [
        {{
          "nom": "<nom>",
          "priorite": <AED>,
          "portee": <AED>,
          "nb_reconstitutions": <int>,
          "AAD": <AED ou null>,
          "tau_estime": <décimal ex 0.0234>,
          "prime_estimee": <AED>,
          "vs_reference": "<ex: −4.2% vs τ_ref>",
          "methode_estimation": "élasticité log-log | jugement expert"
        }}
      ],
      "prime_totale": <AED>,
      "taux_global": <décimal>,
      "argument_commercial": "<une phrase pour la cédante>",
      "justification_technique": "<pourquoi défendable>",
      "alerte": "<null ou message si risque identifié>"
    }}
  ],
  "recommandation": "<quelle variante privilégier et pourquoi>",
  "score_competitivite": <1-10>,
  "bras_utilises": {{
    "methodes": ["élasticités log-log", "règle R1", ...],
    "donnees": ["taux de référence actuaire", "élasticités {cal}", ...],
    "limites": ["...", "..."],
    "score_coherence_global": <1-10>,
    "note_coherence": "<justification>"
  }}
}}
""".strip()


# ════════════════════════════════════════════════════════════════════
# PROMPT 3 — GÉNÉRAL (existant, conservé pour compatibilité)
# ════════════════════════════════════════════════════════════════════

def build_prompt(role, task, data, contexte="", instructions="",
                 input_data="", output_instructions="",
                 contexte_global="", exemples="", contraintes=""):
    """
    Prompt engineering général — conservé pour compatibilité avec app.py.
    Inclut les règles actuarielles et le format de sortie standard.
    """
    prompt = f"""
╔══════════════════════════════════════════════════════════════╗
║  ATLANTIC RE IA — AGENT ACTUARIEL EXPERT                     ║
║  Réassurance Non-Proportionnelle XL · Automobile             ║
╚══════════════════════════════════════════════════════════════╝

{_IDENTITE}

{_REGLES_ABSOLUES}

═══ CONTRAINTES MÉTIER ══════════════════════════════════════
{contraintes if contraintes else _REGLES_METIER}

═══ CONTEXTE GLOBAL ═════════════════════════════════════════
{contexte_global if contexte_global else "Portefeuille automobile, réassurance non-proportionnelle."}

═══ CONTEXTE SPÉCIFIQUE ═════════════════════════════════════
{contexte if contexte else "Non fourni."}

═══ TÂCHE ════════════════════════════════════════════════════
{task}

═══ DONNÉES D'ANALYSE ═══════════════════════════════════════
{data}
{("DONNÉES SUPPLÉMENTAIRES :\n" + input_data) if input_data else ""}

═══ INSTRUCTIONS ════════════════════════════════════════════
{instructions if instructions else "Appliquer les règles actuarielles — analyse structurée."}

═══ EXEMPLES FEW-SHOT ══════════════════════════════════════
{exemples if exemples else """
CAS 1 — Travaillante BC crédible :
  T1 (13M xs 2M) — BC : 8 ans non-nuls | τ_pur=2.18% σ=1.45% τ_tech=3.26% ✅
  Sim : τ_pur=3.12% τ_tech=4.59% | Écart 29% → analyser atypiques
  RETENU : max(3.26%, 4.59%) = 4.59%

CAS 2 — Année atypique cause B :
  2019 : τ=8.2% vs 2018=1.1%, 2020=1.4% → CAT dans programme Risk
  BC sans 2019 : τ_tech=2.85% (vs 4.12% avec) → ÉCARTÉ, justifié

CAS 3 — Cat sans données :
  T2 Cat : BC=0% (R2, normal) | Sim=1.24% | Mkt=1.34% (R²=0.52 N=22)
  RETENU : max(1.24%, 1.34%) = 1.34%"""}

═══ FORMAT DE SORTIE ════════════════════════════════════════
{output_instructions if output_instructions else """
1. ANALYSE PRÉALABLE (années atypiques, crédibilité BC)
2. SYNTHÈSE BC / SIM / MKT
3. TARIF RETENU PAR TRANCHE
4. CONCLUSION (ACCEPTER / NÉGOCIER / RÉVISER + prime totale)

---
BRAS UTILISÉS :
• Méthodes activées : [liste]
• Données exploitées : [liste]
• Limites : [liste]
• Score cohérence : X/10"""}

La précision quantitative prime sur l'exhaustivité qualitative.
Chaque affirmation est étayée par un calcul explicite.
╔══════════════════════════════════════════════════════════════╗
"""
    return prompt.strip()


# ════════════════════════════════════════════════════════════════════
# FEW-SHOT DYNAMIQUE — inchangé
# ════════════════════════════════════════════════════════════════════

def _charger_few_shot_dynamiques(user_email, n_max=3):
    """Charge les N meilleurs exemples de sessions validées comme few-shot."""
    try:
        con, db = _get_conn(); cur = con.cursor(); p = _ph()
        cur.execute(
            f"""SELECT s.nom_session, s.gnpi, r.data_json FROM sessions s
                JOIN resultats r ON r.session_id=s.id
                WHERE s.user_email={p} AND r.etape='rapport'
                ORDER BY s.updated_at DESC LIMIT {n_max}""",
            (user_email,))
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
            rapport_rows = d.get("rows", []); pt = d.get("prime_totale", 0)
            if not rapport_rows: continue
            lines_ex = [
                f"SESSION : {nom or 'Sans nom'} | "
                f"GNPI {(gnpi_h or 0):,.0f} | Prime {pt:,.0f}"
            ]
            for r in rapport_rows[:4]:
                nom_t = r.get("tranche", "") or r.get("Tranche", "")
                typ_t = r.get("type",    "") or r.get("Type",    "")
                tau   = r.get("taux_retenu", "") or r.get("Taux retenu", "")
                meth  = r.get("methode", "") or r.get("Méthode", "")
                lines_ex.append(f"  {nom_t} ({typ_t}) → {tau} via {meth}")
            exemples.append("\n".join(lines_ex))
        except Exception:
            continue
    if not exemples:
        return ""
    return "\n\n".join([f"CAS {i+1} :\n{ex}" for i, ex in enumerate(exemples)])


# ════════════════════════════════════════════════════════════════════
# CLAUDE STREAM — inchangé + mode autonome
# ════════════════════════════════════════════════════════════════════

def claude_stream(api_key, prompt, max_tokens=4000,
                  session_key="", use_opus=True):
    """
    Streaming Claude avec affichage Streamlit.
    use_opus=True  → claude-opus-4-5  (agent autonome — défaut)
    use_opus=False → claude-haiku-4-5 (analyses rapides)
    """
    model  = "claude-opus-4-5" if use_opus else "claude-haiku-4-5-20251001"
    client = anthropic.Anthropic(api_key=api_key)
    placeholder = st.empty()
    full_text   = ""
    label       = "Opus (autonome)" if use_opus else "Haiku ⚡"
    with st.status(f"🤖 Agent Claude {label} en cours...",
                   expanded=True) as status:
        st.write("🔗 Connexion...")
        st.write("📊 Chargement données actuarielles...")
        try:
            with client.messages.stream(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                st.write("✍️ Raisonnement en cours...")
                for text in stream.text_stream:
                    full_text += text
                    placeholder.markdown(full_text + "▌")
            status.update(label="✅ Analyse terminée",
                          state="complete", expanded=False)
        except Exception as e:
            status.update(label="❌ Erreur", state="error")
            st.error(f"Erreur API : {e}")
            return ""
    placeholder.markdown(full_text)
    if session_key:
        st.session_state[session_key] = full_text
    return full_text


# ════════════════════════════════════════════════════════════════════
# PROMPT INPUTS — inchangé (UI helper)
# ════════════════════════════════════════════════════════════════════

def prompt_inputs(key_prefix, placeholder_contexte="",
                  placeholder_instructions="",
                  placeholder_input="", placeholder_output=""):
    with st.expander("✏️ Personnaliser le prompt", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            contexte = st.text_area("📌 Contexte",
                placeholder=placeholder_contexte or "Ex: Portefeuille automobile UAE...",
                height=80, key=f"{key_prefix}_contexte")
            instructions = st.text_area("📋 Instructions",
                placeholder=placeholder_instructions or "Ex: Attention à la tranche Cat L1...",
                height=80, key=f"{key_prefix}_instructions")
        with c2:
            input_data = st.text_area("📥 Données supplémentaires",
                placeholder=placeholder_input or "Ex: Taux marché référence : 3.2%...",
                height=80, key=f"{key_prefix}_input")
            output_instructions = st.text_area("📤 Format de sortie",
                placeholder=placeholder_output or "Ex: Tableau + recommandation chiffrée...",
                height=80, key=f"{key_prefix}_output")
    return contexte, instructions, input_data, output_instructions


def guide_prompt(etape, exemples_contexte, exemples_instructions,
                 exemples_input, exemples_output=None):
    with st.expander(f"💡 Conseils pour prompter sur : {etape}",
                     expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📌 Contexte**")
            for ex in exemples_contexte: st.markdown(f"- {ex}")
            st.markdown("**📋 Instructions**")
            for ex in exemples_instructions: st.markdown(f"- {ex}")
        with c2:
            st.markdown("**📥 Données**")
            for ex in exemples_input: st.markdown(f"- {ex}")
            if exemples_output:
                st.markdown("**📤 Format**")
                for ex in exemples_output: st.markdown(f"- {ex}")
