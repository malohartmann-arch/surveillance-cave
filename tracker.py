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

  # Type d'objet
  if "cave" in texte and "lique
