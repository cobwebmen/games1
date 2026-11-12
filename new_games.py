# -*- coding: utf-8 -*-
"""
Yeni çıkan mobil oyunlar (App Store + Google Play) -> CSV + HTML
Google Colab'de tek hücreye yapıştırıp çalıştır.

iOS    : Apple'ın herkese açık "new-app" sitemap'i  -> uygulama ID'leri
         -> resmi iTunes Lookup API (çıkış tarihi, geliştirici, tür)
Android: Play'de "yeni çıkanlar" listesi yok. Kategori / top / arama sayfalarından
         (+ yeni iOS oyunlarının adlarını Play'de arayarak) aday paketler toplanır,
         her birinin detay sayfasındaki "released" tarihine bakılır.
"""
import subprocess, sys, re, gzip, json, time, html, csv, random, urllib.parse
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from google_play_scraper import app as gp_app
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests", "google-play-scraper"], check=True)
    import requests
    from google_play_scraper import app as gp_app

# ============================== AYARLAR ==============================
DAYS_BACK        = 1        # son kaç günde çıkan oyunlar
RUN_IOS          = True
RUN_ANDROID      = True

IOS_COUNTRY      = "us"     # lookup yapılacak mağaza (us en geniş katalog)
IOS_MAX_IDS      = 30000    # sitemap'teki en yeni kaç ID'ye bakılsın (200'lük paketlerle sorulur)
IOS_STOP_AFTER   = 15       # art arda bu kadar paket (x200 ID) boş gelirse dur

GP_TIER1 = ["us", "gb", "ca", "au", "nz", "de", "fr", "it", "es", "nl", "be", "at", "ch", "ie",
            "se", "no", "dk", "fi", "jp", "kr", "sg", "hk", "tw", "il", "ae", "sa"]
GP_TIER2 = ["tr", "br", "mx", "ar", "cl", "co", "pe", "pl", "cz", "hu", "ro", "gr", "pt", "ru",
            "ua", "za", "th", "my", "id", "ph", "vn", "in", "eg", "qa", "kw"]
GP_COUNTRIES     = GP_TIER1 + GP_TIER2
GP_KEYWORDS      = ["new games", "new game 2026", "puzzle", "merge", "match 3", "idle", "tycoon",
                    "simulator", "hyper casual", "arcade", "runner", "shooter", "rpg", "strategy",
                    "tower defense", "card game", "word game", "sort puzzle", "block puzzle",
                    "racing", "sports", "horror", "survival", "roguelike", "sandbox", "asmr",
                    "hidden object", "trivia", "casino", "board game", "kids game", "offline games"]
GP_SEARCH_COUNTRIES = ["us", "gb", "tr"]   # arama kelimeleri bu ülkelerde denenir
GP_CROSS_FROM_IOS   = 300    # en yeni kaç iOS oyununun adı Play'de aransın (0 = kapalı)
GP_MAX_CANDIDATES   = 15000  # en fazla kaç Play detay sayfası çekilsin
GP_THREADS          = 6

OUT_PREFIX       = "new_games"
# =====================================================================

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
S = requests.Session()
S.headers.update(UA)
NOW = datetime.now(timezone.utc)
CUTOFF = NOW - timedelta(days=DAYS_BACK)


def fetch(url, tries=4, timeout=60):
    for i in range(tries):
        try:
            r = S.get(url, timeout=timeout)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(2 * (i + 1) + random.random())
    return None


# ------------------------------- iOS ---------------------------------
def ios_ids_from_sitemap():
    idx = fetch("https://apps.apple.com/sitemaps_apps_index_new-app_1.xml")
    if not idx:
        print("  ! sitemap indeksi alınamadı"); return []
    files = re.findall(r"<loc>(.*?)</loc>", idx.decode())
    print(f"  sitemap: {len(files)} dosya indiriliyor...")
    ids = set()

    def one(u):
        b = fetch(u)
        if not b:
            return set()
        try:
            b = gzip.decompress(b)
        except OSError:
            pass
        return {int(x) for x in re.findall(rb"/id(\d+)", b)}

    with ThreadPoolExecutor(8) as ex:
        for n, s in enumerate(ex.map(one, files), 1):
            ids |= s
            if n % 100 == 0:
                print(f"    {n}/{len(files)} dosya, {len(ids)} ID")
    return sorted(ids, reverse=True)      # büyük ID = daha yeni uygulama


def ios_lookup(ids):
    url = f"https://itunes.apple.com/lookup?id={','.join(map(str, ids))}&country={IOS_COUNTRY}&entity=software"
    for i in range(6):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200:
                return r.json().get("results", [])
            time.sleep(15 * (i + 1) if r.status_code in (403, 429) else 3)   # rate limit
        except (requests.RequestException, ValueError):
            time.sleep(3)
    return []


def run_ios():
    print("iOS taranıyor...")
    ids = ios_ids_from_sitemap()[:IOS_MAX_IDS]
    rows, empty = [], 0
    for k in range(0, len(ids), 200):
        hit = 0
        for a in ios_lookup(ids[k:k + 200]):
            try:
                rel = datetime.fromisoformat(a["releaseDate"].replace("Z", "+00:00"))
            except (KeyError, ValueError):
                continue
            if rel < CUTOFF:
                continue
            hit += 1
            if "Games" not in a.get("genres", []) and a.get("primaryGenreName") != "Games":
                continue
            rows.append({
                "platform": "iOS",
                "title": a.get("trackName", ""),
                "developer": a.get("artistName", ""),
                "seller": a.get("sellerName", ""),
                "released": rel.strftime("%Y-%m-%d"),
                "status": "pre-order" if rel > NOW else "live",
                "genres": ", ".join(g for g in a.get("genres", []) if g != "Games"),
                "price": a.get("formattedPrice", ""),
                "ratings": a.get("userRatingCount", 0),
                "installs": "",
                "app_id": a.get("bundleId", ""),
                "store_url": (a.get("trackViewUrl") or "").split("?")[0],
                "developer_url": (a.get("artistViewUrl") or "").split("?")[0],
                "website": a.get("sellerUrl") or "",
                "email": "",
                "icon": a.get("artworkUrl100", ""),
            })
        empty = 0 if hit else empty + 1
        if (k // 200) % 10 == 0:
            print(f"    {k + 200}/{len(ids)} ID soruldu, {len(rows)} yeni oyun")
        if empty >= IOS_STOP_AFTER:
            break
        time.sleep(1.0)
    print(f"  iOS: {len(rows)} yeni oyun")
    return rows


# ----------------------------- Android -------------------------------
GP_CATS = ["GAME", "GAME_ACTION", "GAME_ADVENTURE", "GAME_ARCADE", "GAME_BOARD", "GAME_CARD",
           "GAME_CASINO", "GAME_CASUAL", "GAME_EDUCATIONAL", "GAME_MUSIC", "GAME_PUZZLE",
           "GAME_RACING", "GAME_ROLE_PLAYING", "GAME_SIMULATION", "GAME_SPORTS",
           "GAME_STRATEGY", "GAME_TRIVIA", "GAME_WORD"]
GP_ID = re.compile(r"/store/apps/details\?id=([A-Za-z0-9_.]+)")


def gp_ids(url):
    b = fetch(url, tries=2, timeout=30)
    return set(GP_ID.findall(b.decode("utf8", "replace"))) if b else set()


def gp_detail(pkg):
    for i in range(3):
        try:
            d = gp_app(pkg, lang="en", country="us")
            break
        except Exception as e:
            if "NotFound" in type(e).__name__:
                return None
            time.sleep(3 * (i + 1))
    else:
        return None
    if not str(d.get("genreId", "")).startswith("GAME"):
        return None
    try:
        rel = datetime.strptime(d.get("released") or "", "%b %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if rel < CUTOFF - timedelta(days=1):
        return None
    dev_id = str(d.get("developerId") or "")
    dev_path = "dev?id=" if dev_id.isdigit() else "developer?id="
    return {
        "platform": "Android",
        "title": d.get("title", ""),
        "developer": d.get("developer", ""),
        "seller": "",
        "released": rel.strftime("%Y-%m-%d"),
        "status": "live",
        "genres": d.get("genre", ""),
        "price": "Free" if d.get("free") else str(d.get("price", "")),
        "ratings": d.get("ratings") or 0,
        "installs": d.get("installs") or "",
        "app_id": pkg,
        "store_url": f"https://play.google.com/store/apps/details?id={pkg}",
        "developer_url": "https://play.google.com/store/apps/" + dev_path + dev_id,   # dev_id zaten URL-encoded gelir
        "website": d.get("developerWebsite") or "",
        "email": d.get("developerEmail") or "",
        "icon": d.get("icon", ""),
    }


def run_android(ios_rows):
    print("Google Play taranıyor...")
    urls = []
    for c in GP_COUNTRIES:
        urls.append(f"https://play.google.com/store/games?hl=en&gl={c}")
        for cat in GP_CATS:
            urls.append(f"https://play.google.com/store/apps/category/{cat}?hl=en&gl={c}")
            urls.append(f"https://play.google.com/store/apps/top/category/{cat}?hl=en&gl={c}")
    for c in GP_SEARCH_COUNTRIES:
        for kw in GP_KEYWORDS:
            urls.append(f"https://play.google.com/store/search?q={urllib.parse.quote(kw)}&c=apps&hl=en&gl={c}")
    # yeni iOS oyunlarının adlarını Play'de ara (çoğu oyun iki mağazada aynı hafta çıkar)
    for r in sorted(ios_rows, key=lambda x: x["released"], reverse=True)[:GP_CROSS_FROM_IOS]:
        urls.append(f"https://play.google.com/store/search?q={urllib.parse.quote(r['title'][:50])}&c=apps&hl=en&gl=us")

    cand = set()
    with ThreadPoolExecutor(GP_THREADS) as ex:
        for n, s in enumerate(ex.map(gp_ids, urls), 1):
            cand |= s
            if n % 200 == 0:
                print(f"    {n}/{len(urls)} sayfa, {len(cand)} aday paket")
    cand = list(cand)[:GP_MAX_CANDIDATES]
    print(f"  {len(cand)} aday paketin detayına bakılıyor...")

    rows = []
    with ThreadPoolExecutor(GP_THREADS) as ex:
        futs = [ex.submit(gp_detail, p) for p in cand]
        for n, f in enumerate(as_completed(futs), 1):
            r = f.result()
            if r:
                rows.append(r)
            if n % 500 == 0:
                print(f"    {n}/{len(cand)} detay, {len(rows)} yeni oyun")
    print(f"  Android: {len(rows)} yeni oyun")
    return rows


# ------------------------------ ÇIKTI --------------------------------
COLS = ["platform", "title", "developer", "seller", "released", "status", "genres", "price",
        "ratings", "installs", "app_id", "store_url", "developer_url", "website", "email", "icon"]


def write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)


def write_html(rows, path):
    e = html.escape
    trs = []
    for r in rows:
        links = f'<a href="{e(r["store_url"])}" target="_blank">store</a> · <a href="{e(r["developer_url"])}" target="_blank">dev</a>'
        if r["website"]:
            links += f' · <a href="{e(r["website"])}" target="_blank">web</a>'
        if r["email"]:
            links += f' · <a href="mailto:{e(r["email"])}">mail</a>'
        trs.append(
            f'<tr data-p="{r["platform"]}"><td><img loading="lazy" src="{e(r["icon"])}"></td>'
            f'<td><span class="b {r["platform"].lower()}">{r["platform"]}</span></td>'
            f'<td><b>{e(r["title"])}</b><br><small>{e(r["app_id"])}</small></td>'
            f'<td>{e(r["developer"])}' + (f'<br><small>{e(r["seller"])}</small>' if r["seller"] and r["seller"] != r["developer"] else "") + "</td>"
            f'<td>{r["released"]}' + (' <small>(pre-order)</small>' if r["status"] != "live" else "") + "</td>"
            f'<td>{e(r["genres"])}</td><td>{e(str(r["price"]))}</td>'
            f'<td data-v="{r["ratings"]}">{r["ratings"]}</td><td>{e(str(r["installs"]))}</td><td>{links}</td></tr>')
    page = f"""<!doctype html><html lang="tr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Yeni oyunlar {NOW:%Y-%m-%d}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:16px;background:#f6f7f9;color:#1c1e21}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:#667;margin-bottom:12px}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}}
input,select{{padding:7px 10px;border:1px solid #ccd;border-radius:6px;font:inherit}} input{{flex:1;min-width:200px}}
.wrap{{overflow-x:auto;background:#fff;border:1px solid #dde;border-radius:8px}}
table{{border-collapse:collapse;width:100%}} th,td{{padding:7px 10px;text-align:left;border-bottom:1px solid #eef;vertical-align:middle}}
th{{background:#f0f2f6;cursor:pointer;white-space:nowrap;position:sticky;top:0}} tr:hover td{{background:#fafbff}}
img{{width:40px;height:40px;border-radius:9px;display:block;background:#eee}} small{{color:#789}}
.b{{padding:2px 7px;border-radius:10px;font-size:12px;color:#fff}} .ios{{background:#2b6cf0}} .android{{background:#1c9a55}}
a{{color:#2457c5;text-decoration:none}} a:hover{{text-decoration:underline}}
</style>
<h1>Yeni çıkan oyunlar</h1>
<div class="sub">{NOW:%Y-%m-%d %H:%M} UTC · son {DAYS_BACK} gün · <span id="cnt">{len(rows)}</span> oyun</div>
<div class="bar"><input id="q" placeholder="Oyun, geliştirici, tür ara...">
<select id="pf"><option value="">Tüm platformlar</option><option>iOS</option><option>Android</option></select></div>
<div class="wrap"><table id="t"><thead><tr><th></th><th>Platform</th><th>Oyun</th><th>Geliştirici</th><th>Çıkış</th><th>Tür</th><th>Fiyat</th><th>Oy</th><th>İndirme</th><th>Link</th></tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>
<script>
const tb=document.querySelector('#t tbody'),q=document.getElementById('q'),pf=document.getElementById('pf');
function flt(){{let s=q.value.toLowerCase(),p=pf.value,n=0;for(const r of tb.rows){{const ok=(!p||r.dataset.p===p)&&(!s||r.textContent.toLowerCase().includes(s));r.style.display=ok?'':'none';n+=ok}}document.getElementById('cnt').textContent=n}}
q.oninput=flt;pf.onchange=flt;
document.querySelectorAll('#t th').forEach((th,i)=>{{let d=1;th.onclick=()=>{{const v=c=>c.cells[i].dataset.v??c.cells[i].textContent.trim();
[...tb.rows].sort((a,b)=>{{const x=v(a),y=v(b),nx=parseFloat(x),ny=parseFloat(y);return d*((!isNaN(nx)&&!isNaN(ny)&&i==7)?nx-ny:x.localeCompare(y))}}).forEach(r=>tb.appendChild(r));d=-d}}}});
</script></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


def main():
    t0 = time.time()
    rows = run_ios() if RUN_IOS else []
    if RUN_ANDROID:
        rows += run_android(rows)
    seen, uniq = set(), []
    for r in rows:
        key = (r["platform"], r["app_id"] or r["store_url"])
        if key not in seen:
            seen.add(key); uniq.append(r)
    uniq.sort(key=lambda r: (r["released"], r["platform"]), reverse=True)

    stamp = NOW.strftime("%Y-%m-%d")
    csv_path, html_path = f"{OUT_PREFIX}_{stamp}.csv", f"{OUT_PREFIX}_{stamp}.html"
    write_csv(uniq, csv_path)
    write_html(uniq, html_path)
    print(f"\nBitti: {len(uniq)} oyun, {time.time() - t0:.0f} sn -> {csv_path}, {html_path}")
    try:
        from google.colab import files       # Colab'deysek indir
        files.download(csv_path)
        files.download(html_path)
    except ImportError:
        pass


main()
