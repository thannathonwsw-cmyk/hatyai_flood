# -*- coding: utf-8 -*-
"""
thaiwater_proxy.py v2 — ThaiWater + TMD proxy พร้อม in-memory cache
สำหรับ HTY FLOOD COMMAND v5
─────────────────────────────────────────────────────────────
รัน:  python thaiwater_proxy.py  →  http://localhost:5001
TMD:  ตั้ง env TMD_UID / TMD_UKEY (ขอที่ data.tmd.go.th) แล้ว deploy บน Render
"""
import os, re, json, time, threading, datetime, requests
from flask import Flask, jsonify, request

app = Flask(__name__)
PAGE = "https://songkhla.thaiwater.net/wl"
HDR  = {"User-Agent": "Mozilla/5.0 (HTY-FloodCommand/5.0)", "Accept": "text/html"}

# ── TMD config (อ่านจาก environment variables) ──
TMD_UID  = os.environ.get("TMD_UID", "")
TMD_UKEY = os.environ.get("TMD_UKEY", "")
TMD_BASES = ["https://data.tmd.go.th/nwpapi/v1", "https://data.tmd.go.th/api/v1"]

# ═══════════════ IN-MEMORY TTL CACHE ═══════════════
_cache, _lock, _hits, _miss = {}, threading.Lock(), 0, 0
def cget(k):
    global _hits, _miss
    with _lock:
        e = _cache.get(k)
        if e and e["exp"] > time.time():
            _hits += 1; return e["val"], True
        _miss += 1
    return None, False
def cset(k, v, ttl):
    with _lock:
        _cache[k] = {"val": v, "exp": time.time() + ttl, "born": time.time()}

# ── CORS + cache headers ──
@app.after_request
def after(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return r

# ═══════════════ ThaiWater (สสน.) ═══════════════
FALLBACK = [
  {"name":"สะพานข้ามคลองอู่ตะเภา","tambon":"คูเต่า","amphoe":"หาดใหญ่","river":"คลองอู่ตะเภา","level":-0.04,"bank":0.84,"status":"น้ำมาก","agency":"สสน.","time":"01:20 น.","key":True},
  {"name":"บ้านคลองหวะ","tambon":"คอหงส์","amphoe":"หาดใหญ่","river":"คลองหวะ","level":4.74,"bank":8.88,"status":"น้ำปกติ","agency":"ชลประทาน","time":"01:20 น.","key":True},
  {"name":"บ้านม่วงก็อง","tambon":"พังลา","amphoe":"สะเดา","river":"คลองอู่ตะเภา","level":9.61,"bank":16.13,"status":"น้ำปกติ","agency":"ชลประทาน","time":"01:20 น.","key":True},
  {"name":"บ้านนาสีทอง","tambon":"เขาพระ","amphoe":"รัตภูมิ","river":"คลองรัตภูมิ","level":33.54,"bank":39.92,"status":"น้ำมาก","agency":"ชลประทาน","time":"01:20 น.","key":False},
  {"name":"นาทวี","tambon":"นาทวี","amphoe":"นาทวี","river":"คลองนาทวี","level":19.91,"bank":22.71,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"บางกล่ำ","tambon":"ท่าช้าง","amphoe":"บางกล่ำ","river":"คลองบางกล่ำ","level":-0.07,"bank":1.59,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"ปากรอ","tambon":"ปากรอ","amphoe":"สิงหนคร","river":"ทะเลสาบสงขลา","level":0.14,"bank":0.97,"status":"น้ำมาก","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานข้ามคลองระโนด","tambon":"ระโนด","amphoe":"ระโนด","river":"คลองระโนด","level":0.07,"bank":1.18,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานเทพาสันติสุข","tambon":"เทพา","amphoe":"เทพา","river":"คลองเทพา","level":0.07,"bank":2.43,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานสวนเฉลิมพระเกียรติฯ","tambon":"หัวเขา","amphoe":"สิงหนคร","river":"ทะเลสาบสงขลา","level":-0.01,"bank":0.90,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
]
KEY_NAMES = {"สะพานข้ามคลองอู่ตะเภา","บ้านคลองหวะ","บ้านม่วงก็อง"}

def scrape():
    r = requests.get(PAGE, headers=HDR, timeout=20); r.encoding = "utf-8"; html = r.text; out = []
    m = re.search(r'var\s+stationData\s*=\s*(\[.*?\]);', html, re.S)
    if m:
        try:
            for s in json.loads(m.group(1)):
                out.append({"name":s.get("name",""),"tambon":s.get("tambon",""),"amphoe":s.get("amphoe",""),
                    "river":s.get("river",""),"level":float(s.get("level",0)),"bank":float(s.get("bank",0)),
                    "status":s.get("status",""),"agency":s.get("agency",""),"time":s.get("time",""),"key":False})
            if out: return out, "json-embed"
        except Exception: pass
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S):
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) >= 6:
            cl = lambda s: re.sub(r'<[^>]+>','',s).strip()
            name = cl(cells[0]).replace("คลิ๊กเพื่อแสดงตำแหน่งบนแผนที่","").strip()
            if not name or "สถานี" in name: continue
            try:
                loc = cl(cells[1]); tb = re.search(r'ต\.(\S+)',loc); am = re.search(r'อ\.(\S+)',loc)
                out.append({"name":name,"tambon":tb.group(1) if tb else "","amphoe":am.group(1) if am else "",
                    "river":cl(cells[2]) if len(cells)>2 else "","level":float(re.sub(r'[^\d.\-]','',cl(cells[3])) or 0),
                    "bank":float(re.sub(r'[^\d.\-]','',cl(cells[4])) or 0),"status":cl(cells[5]).split('\n')[0].strip(),
                    "agency":cl(cells[9]) if len(cells)>9 else "","time":cl(cells[7]) if len(cells)>7 else "","key":False})
            except (ValueError, IndexError): continue
    return out, "html-table"

@app.route("/tw/stations")
def stations():
    ck = "tw:stations"; cached, hit = cget(ck)
    if hit:
        resp = jsonify(cached); resp.headers["X-Cache"]="HIT"; resp.headers["Cache-Control"]="max-age=60"; return resp
    src = "fallback"
    try:
        data, src = scrape()
        if not data: raise ValueError("scrape ได้ 0 สถานี")
    except Exception as e:
        data = [dict(s) for s in FALLBACK]; print(f"⚠️ scrape ล้มเหลว ({e}) → fallback")
    for s in data: s["key"] = any(k in s["name"] for k in KEY_NAMES); s["province"] = "สงขลา"
    payload = {"source":f"ThaiWater (สสน.) · {src}","province":"สงขลา",
        "updated":datetime.datetime.now().astimezone().isoformat(timespec="seconds"),"count":len(data),"stations":data}
    cset(ck, payload, 300)  # cache 5 นาที
    resp = jsonify(payload); resp.headers["X-Cache"]="MISS"; resp.headers["Cache-Control"]="max-age=300"; return resp

# ═══════════════ TMD forwarder (ต้องเรียกผ่าน proxy เพราะ TMD ไม่เปิด CORS) ═══════════════
@app.route("/tmd/health")
def tmd_health():
    return jsonify({"has_key":bool(TMD_UID and TMD_UKEY),"uid_set":bool(TMD_UID),"ukey_set":bool(TMD_UKEY)})

@app.route("/tmd/proxy")
def tmd_proxy():
    """เรียก: /tmd/proxy?path=/forecasts/daily&q={"station":"..."}  (q = JSON ของ query params)"""
    if not (TMD_UID and TMD_UKEY):
        return jsonify({"error":"ยังไม่ได้ตั้ง TMD_UID/TMD_UKEY บนเซิร์ฟเวอร์","has_key":False}), 503
    path = request.args.get("path", "/forecasts/daily")
    q = request.args.get("q", "{}")
    ck = f"tmd:{path}:{q}"; cached, hit = cget(ck)
    if hit:
        resp = jsonify(cached); resp.headers["X-Cache"]="HIT"; resp.headers["Cache-Control"]="max-age=600"; return resp
    try: params = json.loads(q)
    except Exception: params = {}
    headers = {"uid":TMD_UID,"ukey":TMD_UKEY,"Accept":"application/json","User-Agent":"HTY-FloodCommand/5.0"}
    last = None
    for base in TMD_BASES:  # ลอง NWP API ก่อน แล้ว fallback legacy
        try:
            r = requests.get(base+path, headers=headers, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                ttl = 1800 if "forecast" in path else (600 if "warning" in path else 900)
                cset(ck, data, ttl)
                resp = jsonify(data); resp.headers["X-Cache"]="MISS"; resp.headers["Cache-Control"]=f"max-age={ttl}"
                return resp
            last = f"HTTP {r.status_code} @ {base}"
        except Exception as e:
            last = f"{e} @ {base}"
    return jsonify({"error":str(last),"hint":"ตรวจ uid/ukey หรือ path ให้ตรง doc ของ TMD"}), 502

# ═══════════════ debug / stats ═══════════════
@app.route("/cache/stats")
def cache_stats():
    with _lock:
        now = time.time()
        items = {k:{"ttl_left_s":max(0,round(v["exp"]-now)),"age_s":round(now-v["born"])} for k,v in _cache.items()}
    return jsonify({"hits":_hits,"miss":_miss,"entries":len(items),"items":items})

@app.route("/tw/debug")
def tw_debug():
    try:
        r = requests.get(PAGE, headers=HDR, timeout=20); r.encoding="utf-8"
        return jsonify({"http_status":r.status_code,"page_length":len(r.text),
            "has_html_table":"<td" in r.text,"has_embedded_json":"stationData" in r.text or '"stations"' in r.text})
    except Exception as e:
        return jsonify({"error":str(e)})

if __name__ == "__main__":
    print("="*54)
    print("  ThaiWater + TMD Proxy v2 — HTY FLOOD COMMAND")
    print("  /tw/stations  /tmd/proxy  /tmd/health  /cache/stats")
    print(f"  TMD key: {'✅ ตั้งแล้ว' if (TMD_UID and TMD_UKEY) else '❌ ยังไม่มี (ตั้ง TMD_UID/TMD_UKEY)'}")
    print("="*54)
    app.run(host="0.0.0.0", port=5001, debug=False)