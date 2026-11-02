import hashlib
import json
import os
import re
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import requests

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_PASS")
DESTINATAIRE = "malohartmann@gmail.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
        " like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

DB_FILE = "annonces_vues.json"


def charger_base():
  if os.path.exists(DB_FILE):
    try:
      with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception:
      return []
  return []


def sauvegarder_base(annonces):
  with open(DB_FILE, "w", encoding="utf-8") as f:
    json.dump(annonces, f, ensure_ascii=False, indent=2)


BASE_ANNONCES = charger_base()
SEEN_URLS = {a["url"] for a in BASE_ANNONCES}


def calculer_score(titre, description):
  texte = f"{titre} {description}".lower()
  score = 0
  indices = []

  # Type d'objet
  if "cave" in texte and "liqueur" in texte:
    score += 40
    indices.append("Cave à liqueur")
  elif "coffret" in texte and "liqueur" in texte:
    score += 30
    indices.append("Coffret liqueur")

  # Style d'époque
  if "napoléon" in texte or "napoleon" in texte:
    score += 30
    indices.append("Napoléon III")

  # Carafes
  if (
      "4 carafe" in texte
      or "4 flacon" in texte
      or "quatre carafe" in texte
      or "quatre flacon" in texte
  ):
    score += 35
    indices.append("4 carafes d'origine")

  # Verres : cas 2 manquants (14 verres) ou référence aux 16 verres
  manque_deux = any(
      k in texte
      for k in [
          "14 verre",
          "14 flacon",
          "manque 2 verre",
          "manque deux verres",
          "incomplet de 2",
          "14/16",
          "14 sur 16",
      ]
  )
  modele_seize = any(
      k in texte for k in ["16 verre", "16 flacon", "manque", "incomplet"]
  )

  if manque_deux:
    score += 90
    indices.append("Critère exact : 14 verres / 2 verres manquants")
  elif "15 verre" in texte or "manque 1 verre" in texte:
    score += 60
    indices.append("Comptage proche : 15 verres / manque 1 verre")
  elif modele_seize:
    score += 25
    indices.append("Modèle pour 16 verres")

  # Serrure et clé
  if "clé" in texte or "clef" in texte:
    score += 35
    indices.append("Avec clé d'origine")

  # Matériaux
  if "noirci" in texte or "laiton" in texte or "marqueterie" in texte:
    score += 25
    indices.append("Bois noirci / Filets de laiton")

  # Indice coupure de presse
  if (
      "journal" in texte
      or "coupure" in texte
      or "presse" in texte
      or "papier" in texte
  ):
    score += 50
    indices.append("Présence papier / coupure de presse")

  # Localisation
  if any(
      loc in texte
      for loc in [
          "isere",
          "isère",
          "38",
          "bourgoin",
          "rhone",
          "rhône",
          "lyon",
          "grenoble",
          "dolomieu",
          "chambéry",
          "chambery",
      ]
  ):
    score += 45
    indices.append("Zone Isère / AURA")

  return score, indices


def envoyer_alerte(plateforme, titre, url, score, indices):
  if not GMAIL_USER or not GMAIL_PASS:
    return
  msg = MIMEMultipart()
  msg["From"] = GMAIL_USER
  msg["To"] = DESTINATAIRE
  msg["Subject"] = f"🚨 [{plateforme}] Alerte Cave à Liqueur (Score: {score})"

  corps = f"""
Nouvelle annonce repérée avec un score d'intérêt de {score}/100 :

• Plateforme : {plateforme}
• Titre : {titre}
• Lien direct : {url}
• Indices relevés : {", ".join(indices)}

Tableau de bord : https://malohartmann-arch.github.io/surveillance-cave/
    """
  msg.attach(MIMEText(corps, "plain", "utf-8"))

  try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
      server.login(GMAIL_USER, GMAIL_PASS)
      server.send_message(msg)
      print(f"Email envoyé pour l'annonce : {titre}")
  except Exception as e:
    print(f"Erreur envoi mail : {e}")


def enregistrer_annonce(plateforme, titre, url, score, indices):
  if url in SEEN_URLS:
    return
  BASE_ANNONCES.insert(
      0,
      {
          "plateforme": plateforme,
          "titre": titre,
          "url": url,
          "score": score,
          "indices": indices,
      },
  )
  SEEN_URLS.add(url)
  sauvegarder_base(BASE_ANNONCES)
  if score >= 60:
    envoyer_alerte(plateforme, titre, url, score, indices)


# --- SCRAPERS ---


def scan_interencheres():
  try:
    url = "https://www.interencheres.com/recherche/lots?search=cave%20a%20liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      if "/lots/" in a["href"]:
        full_url = (
            a["href"]
            if a["href"].startswith("http")
            else f"https://www.interencheres.com{a['href']}"
        )
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Interencheres", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Interencheres : {e}")


def scan_ebay():
  try:
    url = "https://www.ebay.fr/sch/i.html?_nkw=cave+a+liqueur+napoleon+iii&_sop=10"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for item in soup.select(".s-item__link"):
      href = item.get("href")
      titre = item.get_text(strip=True)
      if (
          href
          and "ebay.fr/itm/" in href
          and len(titre) > 10
          and href not in SEEN_URLS
      ):
        score, ind = calculer_score(titre, "")
        enregistrer_annonce("eBay", titre, href, score, ind)
  except Exception as e:
    print(f"Erreur eBay : {e}")


def scan_proantic():
  try:
    url = "https://www.proantic.com/resultats.php?clef=cave+a+liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      if "item.php?id=" in a["href"]:
        full_url = (
            a["href"]
            if a["href"].startswith("http")
            else f"https://www.proantic.com/{a['href']}"
        )
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Proantic", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Proantic : {e}")


def scan_anticstore():
  try:
    url = "https://www.anticstore.com/recherche?q=cave+a+liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      href = a["href"]
      if (
          href.startswith("/")
          and len(href.split("/")) > 2
          and ("cave" in href or "liqueur" in href)
      ):
        full_url = f"https://www.anticstore.com{href}"
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Anticstore", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Anticstore : {e}")


def scan_selency():
  try:
    url = "https://www.selency.fr/recherche?q=cave+a+liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      href = a["href"]
      if "/produit/" in href:
        full_url = (
            href if href.startswith("http") else f"https://www.selency.fr{href}"
        )
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Selency", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Selency : {e}")


def scan_catawiki():
  try:
    url = "https://www.catawiki.com/fr/s?q=cave+a+liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      href = a["href"]
      if "/l/" in href:
        full_url = (
            href
            if href.startswith("http")
            else f"https://www.catawiki.com{href}"
        )
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Catawiki", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Catawiki : {e}")


def scan_drouot():
  try:
    url = "https://drouot.com/fr/l?query=cave+a+liqueur"
    r = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
      href = a["href"]
      if "/l/" in href:
        full_url = (
            href if href.startswith("http") else f"https://drouot.com{href}"
        )
        titre = a.get_text(strip=True)
        if len(titre) > 10 and full_url not in SEEN_URLS:
          score, ind = calculer_score(titre, "")
          enregistrer_annonce("Drouot", titre, full_url, score, ind)
  except Exception as e:
    print(f"Erreur Drouot : {e}")


def generer_page_html():
  heure_paris = datetime.now(timezone(timedelta(hours=1))).strftime(
      "%d/%m/%Y à %Hh%M"
  )

  cartes = ""
  for itm in BASE_ANNONCES[:40]:
    couleur = "#3182ce"
    if itm["score"] >= 80:
      couleur = "#e53e3e"
    elif itm["score"] >= 50:
      couleur = "#dd6b20"

    indices_badges = "".join([
        (
            f"<span style='background:#edf2f7;color:#4a5568;padding:3px"
            f" 8px;border-radius:4px;font-size:12px;margin-right:5px;'>{ind}</span>"
        )
        for ind in itm["indices"]
    ])
    cartes += f"""
        <div style="background:white; border-radius:10px; padding:16px; margin-bottom:14px; box-shadow:0 2px 4px rgba(0,0,0,0.06); border-left:6px solid {couleur}; text-align:left;">
            <div style="font-size:12px; font-weight:bold; color:#718096; margin-bottom:4px;">{itm['plateforme']} • Score: {itm['score']}/100</div>
            <div style="font-size:16px; font-weight:600; margin-bottom:8px; color:#2d3748;">{itm['titre']}</div>
            <div style="margin-bottom:12px;">{indices_badges}</div>
            <a href="{itm['url']}" target="_blank" style="display:inline-block; background:#2b6cb0; color:white; text-decoration:none; padding:8px 14px; border-radius:6px; font-size:13px; font-weight:500;">Consulter l'annonce ↗</a>
        </div>
        """

  section_vide = f"""
    <div style="background:white; border-radius:12px; padding:24px; box-shadow:0 2px 6px rgba(0,0,0,0.05); border-left:6px solid #38a169; text-align:left; margin-bottom:20px;">
        <h3 style="margin-top:0; color:#2f855a; font-size:18px; margin-bottom:12px;">🟢 Surveillance active (aucun signalement suspect à cette heure)</h3>
        <p style="color:#4a5568; font-size:14px; line-height:1.6; margin-bottom:16px;">
            Le robot scanne en continu les nouvelles annonces et catalogues de vente. Dès qu'une correspondance est identifiée, elle sera listée ici et transmise immédiatement par email.
        </p>
        <div style="background:#f7fafc; border-radius:8px; padding:16px; border:1px solid #e2e8f0; font-size:13px; line-height:1.7; color:#4a5568;">
            <strong style="color:#2d3748; display:block; margin-bottom:6px;">📋 Critères et particularités surveillés par le robot :</strong>
            • <strong>Objet :</strong> Cave à liqueur d'époque Napoléon III (bois noirci et filets de laiton)<br>
            • <strong>Verrerie d'origine :</strong> Ensemble 4 carafes + 14 verres présents (modèle complet pour 16 verres, 2 verres manquants)<br>
            • <strong>Éléments discriminants :</strong> Présence de la clé d'origine, coupure de presse ou papier ancien inséré<br>
            • <strong>Périmètre géographique :</strong> Dolomieu, Nord-Isère (38), région Auvergne-Rhône-Alpes (Lyon, Grenoble, Chambéry)<br>
            • <strong>Plateformes passées au crible :</strong> Interencheres, eBay, Proantic, Anticstore, Selency, Catawiki, Drouot Digital<br>
            • <strong>Fréquence :</strong> Analyse automatique exécutée toutes les heures
        </div>
    </div>
    """

  contenu_principal = cartes if cartes else section_vide

  html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Surveillance Cave à Liqueur</title>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f0f4f8; margin:0; padding:20px; color:#2d3748;">
    <div style="max-width:720px; margin:0 auto; text-align:center;">
        <div style="background:#ebf8ff; border:1px solid #bee3f8; border-radius:8px; padding:10px 14px; margin-bottom:18px; font-size:13px; color:#2b6cb0; font-weight:500;">
            🔔 <strong>Alerte :</strong> Consultation en direct ici ou par notification email immédiate transmise à Malo.
        </div>
        <h1 style="font-size:22px; margin-bottom:4px; color:#1a202c;">🔎 Veille Cave à Liqueur Napoléon III</h1>
        <p style="color:#718096; font-size:13px; margin-bottom:6px;">Dispositif de recherche automatique 24h/24</p>
        <p style="color:#a0aec0; font-size:12px; margin-top:0; margin-bottom:24px;">Dernière vérification automatique : <span style="color:#4a5568; font-weight:600;">{heure_paris}</span></p>
        {contenu_principal}
    </div>
</body>
</html>"""

  with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)


def main():
  scan_interencheres()
  scan_ebay()
  scan_proantic()
  scan_anticstore()
  scan_selency()
  scan_catawiki()
  scan_drouot()
  generer_page_html()


if __name__ == "__main__":
  main()
