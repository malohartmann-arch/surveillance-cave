import hashlib
import json
import os
import re
import smtplib
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

  if "cave" in texte and "liqueur" in texte:
    score += 40
    indices.append("Cave à liqueur")
  elif "coffret" in texte and "liqueur" in texte:
    score += 30
    indices.append("Coffret liqueur")

  if "napoléon" in texte or "napoleon" in texte:
    score += 30
    indices.append("Napoléon III")

  if "15 verre" in texte or "15 flacon" in texte or "manque un verre" in texte:
    score += 80
    indices.append("Critère discriminant : 15 verres / manque 1 verre")
  elif "verre" in texte:
    score += 10

  if "clé" in texte or "clef" in texte:
    score += 35
    indices.append("Avec clé d'origine")

  if "noirci" in texte or "laiton" in texte or "marqueterie" in texte:
    score += 25
    indices.append("Bois noirci / Laiton")

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
      ]
  ):
    score += 45
    indices.append("Zone Isère / AURA")

  if "journal" in texte or "coupure" in texte or "presse" in texte:
    score += 50
    indices.append("Présence papier / coupure de presse")

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
      if "/l/" in href:  # Format des lots Catawiki
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
      if "/l/" in href:  # Lots Drouot Digital
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
  cartes = ""
  for itm in BASE_ANNONCES[:40]:  # Affiche les 40 annonces les plus récentes
    couleur = "#3182ce"
    if itm["score"] >= 80:
      couleur = "#e53e3e"  # Rouge (très suspect)
    elif itm["score"] >= 50:
      couleur = "#dd6b20"  # Orange

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

  if not cartes:
    cartes = """
        <div style="background:white; border-radius:10px; padding:30px; box-shadow:0 2px 4px rgba(0,0,0,0.06); border-left:6px solid #38a169; text-align:center;">
            <h3 style="margin-top:0; color:#2f855a;">Surveillance active</h3>
            <p style="color:#4a5568;">Aucune annonce suspecte pour l'instant. Le système effectue des vérifications régulières sur l'ensemble des plateformes.</p>
        </div>
        """

  html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Surveillance Cave à Liqueur</title>
</head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f7fafc; margin:0; padding:20px; color:#2d3748;">
    <div style="max-width:700px; margin:0 auto; text-align:center;">
        <h1 style="font-size:22px; margin-bottom:6px;">🔎 Veille Cave à Liqueur Napoléon III</h1>
        <p style="color:#718096; font-size:13px; margin-bottom:24px;">Canaux surveillés : Interencheres, eBay, Proantic, Selency, Catawiki, Drouot</p>
        {cartes}
    </div>
</body>
</html>"""

  with open("index.html", "w", encoding="utf-8") as f:
    f.write(html)


def main():
  scan_interencheres()
  scan_ebay()
  scan_proantic()
  scan_selency()
  scan_catawiki()
  scan_drouot()
  generer_page_html()


if __name__ == "__main__":
  main()
