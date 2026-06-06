"""
Atlantic Re IA — Notifications module
Email Gmail SMTP, webhook Slack/Teams, envoi rapport PDF.
"""
import streamlit as st
import json, urllib.request, urllib.error
from datetime import datetime
from modules.pdf_gen import generer_pdf_rapport, generer_pptx_rapport
from modules.pdf_gen import generer_pdf_rapport, generer_pptx_rapport

def envoyer_webhook_notification(sujet, corps_texte, niveau="info"):
    """
    Envoie une notification via webhook Slack ou Microsoft Teams.
    Configurer dans Secrets : SLACK_WEBHOOK_URL ou TEAMS_WEBHOOK_URL
    """
    import urllib.request, urllib.error
    slack_url  = ""
    teams_url  = ""
    try:
        slack_url  = st.secrets.get("SLACK_WEBHOOK_URL", "")
        teams_url  = st.secrets.get("TEAMS_WEBHOOK_URL", "")
    except Exception:
        pass

    icone = {"info":"ℹ️","alerte":"⚠️","rapport_final":"📋","succes":"✅"}.get(niveau,"📊")
    resultats = []

    # ── Slack ──────────────────────────────────────────────────────
    if slack_url:
        payload = json.dumps({
            "text": f"{icone} *[Atlantic Re IA]* {sujet}",
            "blocks": [
                {"type":"section","text":{"type":"mrkdwn",
                    "text":f"{icone} *{sujet}*\n{corps_texte[:500]}"}},
                {"type":"context","elements":[
                    {"type":"mrkdwn","text":f"Atlantic Re IA · {datetime.now().strftime('%d/%m/%Y %H:%M')}"}]}
            ]
        }).encode()
        try:
            req = urllib.request.Request(slack_url, data=payload,
                headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=5)
            resultats.append(("Slack", True, "OK"))
        except Exception as e:
            resultats.append(("Slack", False, str(e)[:80]))

    # ── Teams ──────────────────────────────────────────────────────
    if teams_url:
        color_map = {"info":"0076D7","alerte":"FF8C00","rapport_final":"107C10","succes":"107C10"}
        payload = json.dumps({
            "@type":"MessageCard","@context":"http://schema.org/extensions",
            "themeColor": color_map.get(niveau,"0076D7"),
            "summary": sujet,
            "sections":[{"activityTitle": f"{icone} {sujet}",
                          "activitySubtitle": "Atlantic Re IA",
                          "text": corps_texte[:500]}]
        }).encode()
        try:
            req = urllib.request.Request(teams_url, data=payload,
                headers={"Content-Type":"application/json"})
            urllib.request.urlopen(req, timeout=5)
            resultats.append(("Teams", True, "OK"))
        except Exception as e:
            resultats.append(("Teams", False, str(e)[:80]))

    return resultats
    if isinstance(obj, dict):  return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):  return [_json_safe(v) for v in obj]
    if isinstance(obj, np.bool_):   return bool(obj)
    if isinstance(obj, np.integer): return int(obj)
    if isinstance(obj, np.floating):return float(obj)
    if isinstance(obj, np.ndarray): return obj.tolist()
    return obj




# ════════════════════════════════════════════
# NOTIFICATION EMAIL — Alerte consultation agent
# ════════════════════════════════════════════

def envoyer_notification_email(sujet, corps, destinataire="hervepagnangde@gmail.com"):
    """
    Envoie via Gmail SMTP.
    IMPORTANT : Pour Gmail, il faut un App Password (16 caractères), PAS le mot de passe ordinaire.
    → Google Account → Sécurité → Validation en 2 étapes → Mots de passe des applications
    → Générer → Copier les 16 caractères → coller dans SMTP_PASS des Secrets
    """
    # Lire les secrets avec différentes méthodes (robustesse)
    smtp_user = ""
    smtp_pass = ""
    try:
        # Méthode 1 : accès direct par clé (niveau racine)
        smtp_user = st.secrets["SMTP_USER"]
        smtp_pass = st.secrets["SMTP_PASS"]
    except (KeyError, Exception):
        try:
            # Méthode 2 : via .get() (niveau racine)
            smtp_user = st.secrets.get("SMTP_USER", "")
            smtp_pass = st.secrets.get("SMTP_PASS", "")
        except Exception:
            pass
    # Méthode 3 : si les clés sont dans une section (ex: [roles] en TOML)
    # En TOML, tout ce qui suit [roles] est dans st.secrets["roles"]
    if not smtp_user or not smtp_pass:
        for section in ["roles", "smtp", "email", "config"]:
            try:
                sec = st.secrets.get(section, {})
                if hasattr(sec, "get"):
                    u = sec.get("SMTP_USER","") or sec.get("smtp_user","")
                    p = sec.get("SMTP_PASS","") or sec.get("smtp_pass","")
                    if u and p:
                        smtp_user = u; smtp_pass = p; break
            except Exception:
                pass

    if not smtp_user or not smtp_pass:
        return False, (
            "SMTP non configuré. "
            "Vérifiez que SMTP_USER et SMTP_PASS sont bien dans les Secrets Streamlit "
            "(sans section, au niveau racine du fichier secrets.toml)."
        )

    # Vérification : le mot de passe Gmail ordinaire ne fonctionne pas — App Password requis
    # Un App Password Google fait exactement 16 caractères sans espaces
    pass_clean = smtp_pass.replace(" ", "")
    is_app_password = len(pass_clean) == 16 and pass_clean.isalnum()
    if not is_app_password and "@" in smtp_user and "gmail" in smtp_user.lower():
        # Essayer quand même mais avertir si erreur
        pass

    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Atlantic Re IA] {sujet}"
    msg["From"]    = smtp_user
    msg["To"]      = destinataire

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;color:#0d2b3e">
    <div style="border-top:4px solid #00b5a5;padding:20px;max-width:600px">
      <h2 style="color:#0d2b3e">&#x1F916; Atlantic Re IA &#x2014; Notification</h2>
      <div style="background:#f2f8f7;padding:16px;border-left:4px solid #00b5a5">
        {corps}
      </div>
      <p style="color:#5a7a8a;font-size:12px;margin-top:20px">
        Atlantic Re IA &middot; Réassurance Non-Proportionnelle &middot; Maroc
      </p>
    </div></body></html>"""
    msg.attach(MIMEText(html_body, "html"))

    # Essai 1 : SSL port 465
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, destinataire, msg.as_string())
        return True, "Email envoyé (SSL 465)"
    except smtplib.SMTPAuthenticationError:
        hint = (
            "Authentification Gmail échouée. "
            "SOLUTION : créez un App Password Gmail (16 caractères) :\n"
            "myaccount.google.com → Sécurité → Validation 2 étapes → "
            "Mots de passe des applications → Créer → Copier les 16 caractères → "
            "Coller dans SMTP_PASS des Secrets Streamlit (sans espaces)."
        )
        return False, hint
    except Exception as e1:
        # Essai 2 : STARTTLS port 587
        try:
            with smtplib.SMTP("smtp.gmail.com", 587, timeout=10) as server:
                server.ehlo(); server.starttls(); server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, destinataire, msg.as_string())
            return True, "Email envoyé (STARTTLS 587)"
        except smtplib.SMTPAuthenticationError:
            hint = (
                "Authentification Gmail échouée (port 587). "
                "SOLUTION : App Password Gmail requis. "
                "Allez sur : myaccount.google.com → Sécurité → "
                "Validation 2 étapes → Mots de passe des applications"
            )
            return False, hint
        except Exception as e2:
            return False, f"Erreur SMTP (SSL: {e1} | TLS: {e2})"


def notifier_consultation(user_email, module, details=""):
    """Notifie automatiquement lors d'une consultation de l'agent."""
    sujet = f"Consultation par {user_email} — {module}"
    from datetime import datetime
    corps = f"""
    <p><b>Utilisateur :</b> {user_email}</p>
    <p><b>Module consulté :</b> {module}</p>
    <p><b>Date/Heure :</b> {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}</p>
    {f'<p><b>Détails :</b> {details}</p>' if details else ''}
    """
    ok, msg = envoyer_notification_email(sujet, corps)
    return ok




# ════════════════════════════════════════════
# RESSOURCES ACTUARIELLES — Sites web de référence
# ════════════════════════════════════════════

RESSOURCES_ACTUARIELLES = {
    "Réassurance & Marché": [
        {"nom": "Swiss Re Sigma",           "url": "https://www.swissre.com/institute/research/sigma-research/",        "desc": "Études et publications Swiss Re"},
        {"nom": "Munich Re Publications",   "url": "https://www.munichre.com/en/solutions/reinsurance.html",            "desc": "Publications Munich Re"},
        {"nom": "SCOR Technical Papers",    "url": "https://www.scor.com/en/expertise/insurance/reinsurance",           "desc": "SCOR réassurance"},
        {"nom": "ACMAR Maroc",              "url": "https://www.acmar.ma",                                               "desc": "Association Compagnies Maroc"},
        {"nom": "SCR Maroc",                "url": "https://www.atlantic-re.ma",                                         "desc": "Atlantic Re (ex SCR)"},
        {"nom": "DAPS Maroc",               "url": "https://www.mays.gov.ma",                                            "desc": "Direction Assurances & Prévoyance Sociale"},
    ],
    "Actuariat & Standards": [
        {"nom": "IAA (Intern. Actuarial)",  "url": "https://www.actuaries.org",                                          "desc": "Association Actuarielle Internationale"},
        {"nom": "CAS (Casualty Actuarial)", "url": "https://www.casact.org",                                             "desc": "Casualty Actuarial Society — Non-Vie"},
        {"nom": "SOA Publications",         "url": "https://www.soa.org/resources/research-reports/",                    "desc": "Society of Actuaries"},
        {"nom": "Institut des Actuaires FR","url": "https://www.institutdesactuaires.com",                               "desc": "Institut des Actuaires France"},
        {"nom": "ISFA Lyon",                "url": "https://isfa.univ-lyon1.fr",                                         "desc": "Institut de Science Financière et d'Assurances"},
        {"nom": "CNAM Paris",               "url": "https://www.cnam.fr",                                                "desc": "Conservatoire National des Arts et Métiers"},
    ],
    "Cours & Formations": [
        {"nom": "Cours Actuariat Paris",    "url": "https://www.actuariat-paris.fr",                                     "desc": "Master Actuariat Paris"},
        {"nom": "Coursera Actuarial",       "url": "https://www.coursera.org/search?query=actuarial+science",            "desc": "MOOCs actuariat en ligne"},
        {"nom": "EIOPA Publications",       "url": "https://www.eiopa.europa.eu/publications_en",                        "desc": "Publications réglementaires EU"},
        {"nom": "SCAHT Techniques NP",      "url": "https://cas.confex.com",                                             "desc": "CAS Forum Non-Proportionnel"},
        {"nom": "R-Actuarial",              "url": "https://actuarialsciencewithr.com",                                  "desc": "Actuariat avec R — cours pratiques"},
        {"nom": "Variance Journal",         "url": "https://www.variancemagazine.org",                                   "desc": "Journal CAS sur tarification non-vie"},
    ],
    "Finance & Économie": [
        {"nom": "NBER Working Papers",      "url": "https://www.nber.org/papers",                                        "desc": "National Bureau Economic Research"},
        {"nom": "BIS Publications",         "url": "https://www.bis.org/publications/",                                  "desc": "Banque des Règlements Internationaux"},
        {"nom": "IMF Insurance",            "url": "https://www.imf.org/en/Topics/climate-change/insurance",             "desc": "FMI & Assurance"},
        {"nom": "ASTIN Bulletin",           "url": "https://www.cambridge.org/core/journals/astin-bulletin",             "desc": "Journal ASTIN — tarification actuarielle"},
    ],
}
