# -*- coding: utf-8 -*-
"""new_games.py'nin ürettiği en son CSV + HTML dosyalarını mail atar.
Ayarlar ortam değişkenlerinden okunur: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO"""
import csv, glob, os, smtplib, ssl, sys
from email.message import EmailMessage

csvs = sorted(glob.glob("new_games_*.csv"))
if not csvs:
    sys.exit("CSV bulunamadı, mail atılmadı")
csv_path = csvs[-1]
html_path = csv_path[:-4] + ".html"

with open(csv_path, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
ios = sum(r["platform"] == "iOS" for r in rows)
day = csv_path[len("new_games_"):-4]

msg = EmailMessage()
msg["Subject"] = f"Yeni oyunlar {day}: {ios} iOS, {len(rows) - ios} Android"
msg["From"] = os.environ["SMTP_USER"]
msg["To"] = os.environ["MAIL_TO"]
msg.set_content(f"{day} taraması: {len(rows)} yeni oyun ({ios} iOS, {len(rows) - ios} Android).\n"
                "CSV ve HTML ekte.")
for path, sub in ((csv_path, "csv"), (html_path, "html")):
    with open(path, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype=sub, filename=os.path.basename(path))

host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT", "465"))
ctx = ssl.create_default_context()
if port == 465:
    s = smtplib.SMTP_SSL(host, port, context=ctx)
else:
    s = smtplib.SMTP(host, port)
    s.starttls(context=ctx)
with s:
    s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    s.send_message(msg)
print("Mail gönderildi:", msg["Subject"])
