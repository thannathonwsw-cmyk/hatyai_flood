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
from flask import Flask, jsonify, request, Response

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
# ── TMD config (อ่าน token ตัวเดียวจาก env) ──
TMD_TOKEN = os.environ.get("TMD_TOKEN", "")
TMD_BASE  = "https://data.tmd.go.th/nwpapi/v1"
HY_LAT, HY_LON = "7.0082", "100.4767"
TMD_FIELDS = "pc,pr,tc,rh,ws,wd,cond,slp"   # ลองทุกตัวที่เกี่ยวข้อง (ฝน = pc หรือ pr)

# ═══════════════ TMD NWP API (OAuth2 Bearer) ═══════════════
@app.route("/tmd/health")
def tmd_health():
    return jsonify({"has_token":bool(TMD_TOKEN),"token_len":len(TMD_TOKEN)})

def _tmd_get(path, params):
    h = {"accept":"application/json",
         "authorization":f"Bearer {TMD_TOKEN}",
         "User-Agent":"HTY-FloodCommand/5.0 (proxy)"}
    return requests.get(TMD_BASE+path, params=params, headers=h, timeout=20)

@app.route("/tmd/proxy")
def tmd_proxy():
    if not TMD_TOKEN:
        return jsonify({"error":"ยังไม่ได้ตั้ง TMD_TOKEN","has_token":False}),503
    path = request.args.get("path","/forecast/location/daily")
    q    = request.args.get("q","{}")
    ck = f"tmd:{path}:{q}"; cached,hit = cget(ck)
    if hit:
        r=jsonify(cached); r.headers["X-Cache"]="HIT"; r.headers["Cache-Control"]="max-age=600"; return r
    try: params = json.loads(q)
    except Exception: params = {}
    try:
        rr = _tmd_get(path, params)
        if rr.status_code != 200:
            return jsonify({"error":f"HTTP {rr.status_code}","body":rr.text[:300]}),502
        data = rr.json(); cset(ck, data, 1800)   # cache 30 นาที (ประหยัด datapoint)
        resp = jsonify(data); resp.headers["X-Cache"]="MISS"; resp.headers["Cache-Control"]="max-age=1800"
        for hk in ["X-RateLimit-Remaining","X-Datapoint-Remaining"]:   # ส่ง quota กลับไปให้เว็บดู
            if hk in rr.headers: resp.headers[hk] = rr.headers[hk]
        return resp
    except Exception as e:
        return jsonify({"error":str(e)}),502

@app.route("/tmd/test")
def tmd_test():
    """รอบสุดท้าย: ลอง POST + อ่าน spec จาก server + province code (ตัดทุกความเป็นไปได้ที่เหลือ)"""
    if not TMD_TOKEN:
        return jsonify({"has_token":False}),503
    H=lambda extra=None:{"accept":"application/json","authorization":f"Bearer {TMD_TOKEN}",
                         "User-Agent":"HTY-FloodCommand/5.0",**(extra or {})}
    today=datetime.date.today().isoformat(); mid="2026-07-30"
    def shape(body):
        if not isinstance(body,dict): return {"type":type(body).__name__,"raw":str(body)[:200]}
        found=None
        def walk(o,p,d):
            nonlocal found
            if found or d>6: return
            if isinstance(o,dict):
                for k,v in o.items(): walk(v,p+"/"+str(k),d+1)
            elif isinstance(o,list) and o and isinstance(o[0],dict):
                ks=set(o[0].keys())
                if (ks & {"time","date","data","forecasts","forecast","tc","pc","pr","rh"}) or ("data" in o[0]):
                    found={"path":p,"len":len(o),"first_keys":list(o[0].keys()),"first":o[0]}
        walk(body,"",0)
        if found: return {"type":"LIST ✅",**found}
        for k,v in body.items():
            if isinstance(v,dict) and set(v.keys())<={"min","max"}:
                return {"type":"range_only","key":k,"min":v.get("min"),"max":v.get("max")}
        return {"type":"dict","keys":list(body.keys()),"raw":json.dumps(body,ensure_ascii=False)[:300]}
    def get(path,params):
        try:
            r=requests.get(TMD_BASE+path,params=params,headers=H(),timeout=12)
            try:b=r.json()
            except:b=r.text[:300]
            return {"m":"GET","path":path,"status":r.status_code,**shape(b)}
        except Exception as e: return {"m":"GET","path":path,"status":"ERR","error":str(e)[:60]}
    def post(path,body):
        try:
            r=requests.post(TMD_BASE+path,json=body,headers=H({"content-type":"application/json"}),timeout=12)
            try:b=r.json()
            except:b=r.text[:300]
            return {"m":"POST","path":path,"status":r.status_code,**shape(b)}
        except Exception as e: return {"m":"POST","path":path,"status":"ERR","error":str(e)[:60]}
    results=[]
    for path in ["/forecast/location/daily","/forecast/location/hourly","/forecast/daily","/forecast/hourly"]:
        results.append(post(path,{"lat":float(HY_LAT),"lon":float(HY_LON),"fields":TMD_FIELDS,"date":today,"hour":0,"duration":7}))
        results.append(post(path,{"province":"สงขลา","amphoe":"หาดใหญ่","fields":TMD_FIELDS,"date":today,"duration":7}))
    results.append(get("/forecast/location/daily",{"province":"90","amphoe":"หาดใหญ่","fields":TMD_FIELDS,"duration":7}))
    results.append(get("/forecast/location/daily",{"lat":HY_LAT,"lon":HY_LON,"fields":TMD_FIELDS,"date":mid,"duration":7}))
    spec={}
    for p in ["/","/forecast","/forecast/location","/openapi.json","/swagger.json","/forecast/daily/datarange"]:
        try:
            r=requests.get(TMD_BASE+p,headers=H(),timeout=8); ct=r.headers.get('content-type','')
            try:b=r.json()
            except:b=r.text[:200]
            spec[p]={"status":r.status_code,"ct":ct[:30],"body":b}
        except Exception as e: spec[p]={"status":"ERR","error":str(e)[:50]}
    winners=[r for r in results if r.get("type","").startswith("LIST")]
    return jsonify({"winners":winners,"results":results,"spec_discovery":spec,
      "read_me":"winners ไม่ว่าง = เจอ forecast จริง (ดู .first) | results[].m=POST = ลอง method POST | spec_discovery = endpoint/doc ที่ server มีจริง"})

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
# ═══════════════ HIMAWARI-9 via NASA GIBS (discover layer จาก capabilities — ไม่เดา) ═══════════════
GIBS_CAPS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
def _parse_gibs(xml):
    out=[]
    for m in re.finditer(r'<Layer>(.*?)</Layer>', xml, re.S):
        blk=m.group(1)
        idm=re.search(r'<ows:Identifier>(.*?)</ows:Identifier>', blk, re.S)
        if not idm: continue
        lid=idm.group(1).strip()
        if not re.search(r'himawari|ahi', lid, re.I): continue
        ttm=re.search(r'<ows:Title>(.*?)</ows:Title>', blk, re.S); title=ttm.group(1).strip() if ttm else lid
        tmsm=re.search(r'<TileMatrixSet>(.*?)</TileMatrixSet>', blk, re.S); tms=tmsm.group(1).strip() if tmsm else 'GoogleMapsCompatible_Level9'
        fmt='png'; fm=re.search(r'<Format>(.*?)</Format>', blk, re.S)
        if fm: fmt='jpg' if 'jpeg' in fm.group(1) else 'png'
        raw=[]; dim=re.search(r'<Dimension>.*?<ows:Identifier>\s*Time\s*</ows:Identifier>(.*?)</Dimension>', blk, re.S)
        if dim: raw=[t.strip() for t in re.findall(r'<Value>(.*?)</Value>', dim.group(1), re.S)]
        singles=[t for t in raw if t and '/' not in t and re.match(r'\d{4}-\d{2}-\d{2}', t)]   # timestamp เดี่ยวเท่านั้น
        periods=[t for t in raw if '/' in t]                                                   # period expression (ห้ามเอาไปใส่ URL)
        isIR=bool(re.search(r'brightness|infrared|\bIR\b|band.?1[345]|band.?0?[789]', lid+title, re.I))
        isVis=bool(re.search(r'correctedreflectance|truecolor|visible|band.?0?[123]', lid+title, re.I))
        out.append({"id":lid,"title":title,"tms":tms,"fmt":fmt,"isIR":isIR,"isVis":isVis,
                    "latest":singles[-1] if singles else None,
                    "period":periods[-1] if periods else None,"n_singles":len(singles),
                    "subdaily":len(singles)>2,"values_tail":raw[-3:]})
    return out
@app.route("/himawari/layers")
def himawari_layers():
    ck="himawari:layers"; cached,hit=cget(ck)
    if hit:
        r=jsonify(cached); r.headers["X-Cache"]="HIT"; r.headers["Cache-Control"]="max-age=3600"; return r
    try:
        rr=requests.get(GIBS_CAPS, headers={"User-Agent":"HTY-FloodCommand/5.0"}, timeout=30); rr.raise_for_status()
        layers=_parse_gibs(rr.text)
        payload={"source":"NASA GIBS WMTS epsg3857 (Himawari-9)","count":len(layers),"layers":layers,
                 "today_utc":datetime.datetime.utcnow().strftime('%Y-%m-%d'),
                 "yesterday_utc":(datetime.datetime.utcnow()-datetime.timedelta(days=1)).strftime('%Y-%m-%d'),
                 "note":"layer id/time/tms ดึงจาก capabilities จริง · count=0 → GIBS ไม่มี Himawari ใน projection นี้ (เว็บจะ fallback RainViewer IR)"}
        cset(ck,payload,3600); r=jsonify(payload); r.headers["X-Cache"]="MISS"; r.headers["Cache-Control"]="max-age=3600"; return r
    except Exception as e:
        return jsonify({"error":str(e),"count":0,"layers":[]}),502
@app.route("/himawari/caps")
def himawari_caps():
    """debug: GIBS มีคำว่า himawari/ahi ไหม + snippet รอบๆ"""
    try:
        rr=requests.get(GIBS_CAPS, headers={"User-Agent":"HTY-FloodCommand/5.0"}, timeout=30); t=rr.text; i=t.lower().find('himawari')
        return jsonify({"len":len(t),"has_himawari":i>=0 or 'ahi' in t.lower(),
                        "snippet":(t[max(0,i-200):i+600] if i>=0 else t[:600])})
    except Exception as e:
        return jsonify({"error":str(e)})
# ═══════════════ GIBS tile proxy (แก้ CORS — server ดึงภาพส่งต่อ) ═══════════════
@app.route("/gibs/tile")
def gibs_tile():
    layer=request.args.get("layer",""); tms=request.args.get("tms","GoogleMapsCompatible_Level9")
    time=request.args.get("time",""); fmt=request.args.get("fmt","png")
    z=request.args.get("z"); y=request.args.get("y"); x=request.args.get("x")
    if not (layer and time and z and y and x): return jsonify({"error":"missing params"}),400
    url=f"https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}/default/{time}/{tms}/{z}/{y}/{x}.{fmt}"
    ck=f"gibstile:{layer}:{time}:{z}:{x}:{y}"; cached,hit=cget(ck)
    try:
        if hit: data,ct=cached
        else:
            r=requests.get(url,headers={"User-Agent":"HTY-FloodCommand/5.0"},timeout=15)
            if r.status_code!=200: return Response(status=r.status_code)
            data=r.content; ct=r.headers.get('Content-Type','image/png'); cset(ck,(data,ct),600)
        resp=Response(data,mimetype=ct)
        resp.headers['Access-Control-Allow-Origin']='*'      # ← ตัวแก้ CORS
        resp.headers['Cache-Control']='public, max-age=600'
        return resp
    except Exception as e:
        return jsonify({"error":str(e)}),502
if __name__ == "__main__":
    print("="*54)
    print("  ThaiWater + TMD Proxy v2 — HTY FLOOD COMMAND")
    print("  /tw/stations  /tmd/proxy  /tmd/health  /cache/stats")
    print(f"  TMD key: {'✅ ตั้งแล้ว' if (TMD_UID and TMD_UKEY) else '❌ ยังไม่มี (ตั้ง TMD_UID/TMD_UKEY)'}")
    print("="*54)
    app.run(host="0.0.0.0", port=5001, debug=False)