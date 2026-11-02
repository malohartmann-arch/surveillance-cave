import os
import smtplib
import sqlite3
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import feedparser
import requests

DEST_EMAIL = os.environ.get("GMAIL_USER")
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_PASS = os.environ.get("GMAIL_PASS")

DB_FILE = "annonces_vues.db"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

KEYWORDS_SCORE = {
    "15 verres": 45,
    "manque 1 verre": 45,
    "manque un verre": 45,
    "incomplet": 20,
    "clef": 20,
    "clé": 20,
    "journal": 35,
    "coupure": 35,
    "article": 15,
    "38": 20,
    "isere": 25,
    "isère": 25,
    "bourgoin": 35,
    "dolomieu": 50,
    "la-tour-du-pin": 40,
    "rhone": 15,
    "rhône": 15,
    "lyon": 15,
    "filets laiton": 20,
    "bois noirci": 20,
}


def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS annonces (
            id TEXT PRIMARY KEY,
            titre TEXT,
            url TEXT,
            score INTEGER
        )
    """)
  conn.commit()
  conn.close()


def annonce_deja_vue(annonce_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT id FROM annonces WHERE id = ?", (annonce_id,))
  row = cursor.fetchone()
  conn.close()
  return row is not None


def enregistrer_annonce(annonce_id, titre, url, score):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO annonces VALUES (?, ?, ?, ?)",
      (annonce_id, titre, url, score),
  )
  conn.commit()
  conn.close()


def calculer_score(titre, description):
  texte = f"{titre} {description}".lower()
  score = 0
  indices_trouves = []
  for kw, points in KEYWORDS_SCORE.items():
    if kw in texte:
      score += points
      indices_trouves.append(kw)
  return score, indices_trouves


def envoyer_alerte(source, titre, url, description, score, indices):
  print(f"[ALERTE] Envoi email pour '{titre}' (Score: {score})")
  if not GMAIL_USER or not GMAIL_PASS:
    print("Identifiants Gmail absents, envoi ignoré.")
    return

  msg = MIMEMultipart()
  msg["From"] = GMAIL_USER
  msg["To"] = DEST_EMAIL
  msg["Subject"] = (
      f"🚨 [{source.upper()}] Cave à liqueur détectée (Score: {score})"
  )

  corps = f"""Source : {source}
Titre : {titre}
Lien : {url}
Score de suspicion : {score}
Indices repérés : {', '.join(indices) if indices else 'Aucun'}

Extrait :
{description[:800]}
"""
  msg.attach(MIMEText(corps, "plain"))

  try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
      server.login(GMAIL_USER, GMAIL_PASS)
      server.sendmail(GMAIL_USER, DEST_EMAIL, msg.as_string())
    print("-> Email envoyé avec succès !")
  except Exception as e:
    print(f"Erreur d'envoi Gmail : {e}")


def scanner_interencheres_et_ebay():
  flux_urls = [
      (
          "Interencheres",
          "https://www.interencheres.com/rss/recherche?query=cave+a+liqueur",
      ),
      (
          "eBay",
          (
              "https://www.ebay.fr/sch/i.html?_nkw=cave+a+liqueur+napoleon+iii&_rss=1"
          ),
      ),
      (
          "eBay",
          (
              "https://www.ebay.fr/sch/i.html?_nkw=cave+a+liqueur+bois+noirci&_rss=1"
          ),
      ),
  ]
  for source, url in flux_urls:
    print(f"Scrutage {source}...")
    feed = feedparser.parse(url)
    print(f"  {len(feed.entries)} éléments trouvés sur {source}.")
    for entry in feed.entries:
      aid = entry.get("id", entry.link)
      if annonce_deja_vue(aid):
        continue
      score, indices = calculer_score(entry.title, entry.get("description", ""))
      enregistrer_annonce(aid, entry.title, entry.link, score)
      envoyer_alerte(
          source,
          entry.title,
          entry.link,
          entry.get("description", ""),
          score,
          indices,
      )


def scanner_proantic():
  print("Scrutage Proantic...")
  try:
    url = "https://www.proantic.com/recherche.php?search=cave+a+liqueur"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("a.item-link, div.fiche-item")
    print(f"  {len(items)} éléments trouvés sur Proantic.")
    for card in items:
      link_tag = card if card.name == "a" else card.find("a")
      if not link_tag or not link_tag.get("href"):
        continue
      href = link_tag.get("href")
      full_url = (
          href if href.startswith("http") else f"https://www.proantic.com/{href}"
      )
      title = card.get_text(strip=True)
      if annonce_deja_vue(full_url):
        continue
      score, indices = calculer_score(title, "")
      enregistrer_annonce(full_url, title, full_url, score)
      envoyer_alerte("Proantic", title, full_url, title, score, indices)
  except Exception as e:
    print(f"Erreur Proantic : {e}")


def scanner_selency():
  print("Scrutage Selency...")
  try:
    url = "https://www.selency.fr/recherche?q=cave+a+liqueur"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select("article a, a[data-testid='product-card']")
    print(f"  {len(items)} éléments trouvés sur Selency.")
    for card in items:
      href = card.get("href")
      if not href:
        continue
      full_url = (
          href if href.startswith("http") else f"https://www.selency.fr{href}"
      )
      title = card.get_text(strip=True)
      if annonce_deja_vue(full_url):
        continue
      score, indices = calculer_score(title, "")
      enregistrer_annonce(full_url, title, full_url, score)
      envoyer_alerte("Selency", title, full_url, title, score, indices)
  except Exception as e:
    print(f"Erreur Selency : {e}")


if __name__ == "__main__":
  init_db()
  scanner_interencheres_et_ebay()
  scanner_proantic()
  scanner_selency()
  print("Cycle de surveillance terminé avec succès.")
