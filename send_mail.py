# -*- coding: utf-8 -*-
"""new_games.py'nin ürettiği en son CSV + HTML dosyalarını tasarımlı bir mail ile gönderir.
Ortam değişkenleri: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, MAIL_TO
SMTP_HOST yoksa mail atmaz, mail_preview.html dosyasına önizleme yazar."""
import csv, glob, html, os, smtplib, ssl, sys
from email.message import EmailMessage
from email.utils import make_msgid

# ============================== AYARLAR ==============================
BRAND        = "New Games"         # logonun yanında / logo yoksa başlıkta görünen isim
LINKEDIN_URL = ""                  # ör. "https://www.linkedin.com/in/kullanici-adin"  (boşsa gösterilmez)
LOGO_FILE    = "logo.png"          # depoya bu isimle yüklenen logo (yoksa sadece isim yazılır)
TOP_N        = 10                  # mailin içinde listelenecek oyun sayısı (0 = liste yok)
# =====================================================================

csvs = sorted(glob.glob("new_games_*.csv"))
if not csvs:
    sys.exit("CSV bulunamadı, mail atılmadı")
csv_path = csvs[-1]
html_path = csv_path[:-4] + ".html"

with open(csv_path, encoding="utf-8-sig") as f:
    rows = list(csv.DictReader(f))
ios = sum(r["platform"] == "iOS" for r in rows)
android = len(rows) - ios
day = csv_path[len("new_games_"):-4]
e = html.escape

has_logo = os.path.exists(LOGO_FILE)
logo_cid = make_msgid(domain="newgames.local")
if has_logo:
    head = (f'<img src="cid:{logo_cid[1:-1]}" alt="{e(BRAND)}" height="44" '
            f'style="height:44px;vertical-align:middle;border:0">'
            f'<span style="font-size:20px;font-weight:700;color:#ffffff;vertical-align:middle;'
            f'padding-left:10px">{e(BRAND)}</span>')
else:
    head = f'<span style="font-size:22px;font-weight:700;color:#ffffff">{e(BRAND)}</span>'

# en çok oy alan canlı oyunlar üstte
live = [r for r in rows if r.get("status") == "live"]
live.sort(key=lambda r: int(r.get("ratings") or 0), reverse=True)
items = ""
for r in live[:TOP_N]:
    items += (
        '<tr><td style="padding:9px 0;border-bottom:1px solid #1a201c;text-align:left">'
        f'<a href="{e(r["store_url"])}" style="color:#ffffff;text-decoration:none;font-weight:600">{e(r["title"])}</a>'
        f'<br><span style="color:#7f8f86;font-size:12px">{e(r["developer"])} · {e(r["released"])}</span></td>'
        '<td style="padding:9px 0;border-bottom:1px solid #1a201c;text-align:right;white-space:nowrap">'
        f'<span style="border:1px solid #1df08b;color:#1df08b;font-size:11px;padding:2px 8px;border-radius:10px">{r["platform"]}</span>'
        '</td></tr>')
top_block = (
    '<tr><td style="padding:8px 32px 0">'
    f'<div style="color:#7f8f86;font-size:12px;text-transform:uppercase;letter-spacing:1px;text-align:left;padding-bottom:4px">Highlights</div>'
    f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px">{items}</table>'
    '</td></tr>') if items else ""

linkedin = (
    f'<a href="{e(LINKEDIN_URL)}" style="display:inline-block;background:#1df08b;color:#050505;'
    'text-decoration:none;font-size:13px;font-weight:600;padding:7px 16px;border-radius:5px">LinkedIn</a>'
) if LINKEDIN_URL else ""

body = f"""<!doctype html><html lang="en"><body style="margin:0;padding:0;background:#050505">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" bgcolor="#050505"
 style="background:#050505;font-family:Arial,Helvetica,sans-serif;color:#ffffff"><tr><td align="center" style="padding:28px 12px">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;text-align:center">
<tr><td style="padding:0 32px 22px">{head}</td></tr>
<tr><td style="padding:0 32px"><div style="font-size:30px;font-weight:800;line-height:1.2;letter-spacing:2px;text-transform:uppercase;color:#1df08b">What's new today?</div></td></tr>
<tr><td style="padding:18px 32px 6px;font-size:15px;color:#c5d1ca">Scan of {e(day)}</td></tr>
<tr><td style="padding:0 32px"><div style="font-size:46px;font-weight:800;color:#1df08b;line-height:1.1">{len(rows):,}</div>
<div style="font-size:15px;color:#c5d1ca;padding-top:4px">new mobile games found</div></td></tr>
<tr><td style="padding:18px 32px 20px">
<span style="display:inline-block;background:#101311;border-radius:8px;padding:10px 18px;margin:0 4px;font-size:14px"><b>{ios:,}</b> <span style="color:#7f8f86">iOS</span></span>
<span style="display:inline-block;background:#101311;border-radius:8px;padding:10px 18px;margin:0 4px;font-size:14px"><b>{android:,}</b> <span style="color:#7f8f86">Android</span></span>
</td></tr>
{top_block}
<tr><td style="padding:24px 32px 6px;font-size:14px;color:#c5d1ca">Full list attached: searchable HTML table and CSV.</td></tr>
<tr><td style="padding:22px 32px 0">{linkedin}</td></tr>
<tr><td style="padding:18px 32px 0;font-size:12px;color:#56635b">See you tomorrow · {e(BRAND)}</td></tr>
</table></td></tr></table></body></html>"""

if not os.environ.get("SMTP_HOST"):
    with open("mail_preview.html", "w", encoding="utf-8") as f:
        f.write(body)
    sys.exit("SMTP_HOST yok: mail atılmadı, önizleme mail_preview.html dosyasına yazıldı")

msg = EmailMessage()
msg["Subject"] = f"{len(rows)} new mobile games · {day}"
msg["From"] = f"{BRAND} <{os.environ['SMTP_USER']}>"
msg["To"] = os.environ["MAIL_TO"]
msg.set_content(f"Scan of {day}: {len(rows)} new games ({ios} iOS, {android} Android).\n"
                "CSV and HTML attached." + (f"\n\nLinkedIn: {LINKEDIN_URL}" if LINKEDIN_URL else ""))
msg.add_alternative(body, subtype="html")
if has_logo:
    ext = os.path.splitext(LOGO_FILE)[1].lstrip(".").lower().replace("jpg", "jpeg") or "png"
    with open(LOGO_FILE, "rb") as f:
        msg.get_payload()[1].add_related(f.read(), maintype="image", subtype=ext, cid=logo_cid)
for path, sub in ((csv_path, "csv"), (html_path, "html")):
    with open(path, "rb") as f:
        msg.add_attachment(f.read(), maintype="text", subtype=sub, filename=os.path.basename(path))

host, port = os.environ["SMTP_HOST"], int(os.environ.get("SMTP_PORT") or "465")
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
