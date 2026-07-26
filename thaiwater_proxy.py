# -*- coding: utf-8 -*-
"""
thaiwater_proxy.py — Proxy ดึงระดับน้ำ ThaiWater (สสน.) จ.สงขลา
รัน: python thaiwater_proxy.py  →  http://localhost:5001
"""
import re, json, datetime, requests
from flask import Flask, jsonify

app = Flask(__name__)
PAGE = "https://songkhla.thaiwater.net/wl"
HDR  = {"User-Agent": "Mozilla/5.0 (HTY-FloodCommand/4.0)", "Accept": "text/html"}

# ── ข้อมูลจริงที่ดึงไว้ (27 ก.ค. 2569 01:20 น.) ใช้เป็น fallback ──
FALLBACK = [
  {"name":"สะพานข้ามคลองอู่ตะเภา","tambon":"คูเต่า","amphoe":"หาดใหญ่","river":"คลองอู่ตะเภา","level":-0.04,"bank":0.84,"status":"น้ำมาก","agency":"สสน.","time":"01:20 น.","key":True,"role":"คลองอู่ตะเภา · คูเต่า หาดใหญ่"},
  {"name":"บ้านคลองหวะ","tambon":"คอหงส์","amphoe":"หาดใหญ่","river":"คลองหวะ","level":4.74,"bank":8.88,"status":"น้ำปกติ","agency":"ชลประทาน","time":"01:20 น.","key":True,"role":"คลองหวะ · คอหงส์ หาดใหญ่"},
  {"name":"บ้านม่วงก็อง","tambon":"พังลา","amphoe":"สะเดา","river":"คลองอู่ตะเภา","level":9.61,"bank":16.13,"status":"น้ำปกติ","agency":"ชลประทาน","time":"01:20 น.","key":True,"role":"ต้นน้ำ · พังลา สะเดา"},
  {"name":"บ้านนาสีทอง","tambon":"เขาพระ","amphoe":"รัตภูมิ","river":"คลองรัตภูมิ","level":33.54,"bank":39.92,"status":"น้ำมาก","agency":"ชลประทาน","time":"01:20 น.","key":False},
  {"name":"นาทวี","tambon":"นาทวี","amphoe":"นาทวี","river":"คลองนาทวี","level":19.91,"bank":22.71,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"บางกล่ำ","tambon":"ท่าช้าง","amphoe":"บางกล่ำ","river":"คลองบางกล่ำ","level":-0.07,"bank":1.59,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"ปากรอ","tambon":"ปากรอ","amphoe":"สิงหนคร","river":"ทะเลสาบสงขลา","level":0.14,"bank":0.97,"status":"น้ำมาก","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานข้ามคลองระโนด","tambon":"ระโนด","amphoe":"ระโนด","river":"คลองระโนด","level":0.07,"bank":1.18,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานเทพาสันติสุข","tambon":"เทพา","amphoe":"เทพา","river":"คลองเทพา","level":0.07,"bank":2.43,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
  {"name":"สะพานสวนเฉลิมพระเกียรติฯ","tambon":"หัวเขา","amphoe":"สิงหนคร","river":"ทะเลสาบสงขลา","level":-0.01,"bank":0.90,"status":"น้ำปกติ","agency":"สสน.","time":"01:20 น.","key":False},
]

KEY_NAMES = {"สะพานข้ามคลองอู่ตะเภา","บ้านคลองหวะ","บ้านม่วงก็อง"}

# ── CORS ──
@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "*"
    r.headers["Access-Control-Allow-Methods"] = "GET,OPTIONS"
    return r

# ── scrape จากหน้าเว็บ ──
def scrape():
    r = requests.get(PAGE, headers=HDR, timeout=20)
    r.encoding = "utf-8"
    html = r.text
    stations = []

    # วิธี 1: หา JSON ที่ฝังใน <script>
    for pat in [r'var\s+stationData\s*=\s*(\[.*?\]);',
                r'"stations"\s*:\s*(\[.*?\])',
                r'data\s*:\s*(\[.*?\])\s*[,}]']:
        m = re.search(pat, html, re.S)
        if m:
            try:
                for s in json.loads(m.group(1)):
                    stations.append({
                        "name": s.get("name", s.get("station_name","")),
                        "tambon": s.get("tambon",""), "amphoe": s.get("amphoe",""),
                        "river": s.get("river", s.get("basin","")),
                        "level": float(s.get("level", s.get("water_level",0))),
                        "bank": float(s.get("bank", s.get("bank_level",0))),
                        "status": s.get("status",""), "agency": s.get("agency",""),
                        "time": s.get("time",""), "key": False,
                    })
                if stations:
                    return stations, "json-embed"
            except Exception:
                pass

    # วิธี 2: parse HTML table
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.S)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.S)
        if len(cells) >= 6:
            clean = lambda s: re.sub(r'<[^>]+>','',s).strip()
            name = clean(cells[0]).replace("คลิ๊กเพื่อแสดงตำแหน่งบนแผนที่","").strip()
            if not name or "สถานี" in name:
                continue
            try:
                loc = clean(cells[1])
                stations.append({
                    "name": name,
                    "tambon": (re.search(r'ต\.(\S+)',loc) or [None,""])[1] if re.search(r'ต\.(\S+)',loc) else "",
                    "amphoe": (re.search(r'อ\.(\S+)',loc) or [None,""])[1] if re.search(r'อ\.(\S+)',loc) else "",
                    "river": clean(cells[2]) if len(cells)>2 else "",
                    "level": float(re.sub(r'[^\d.\-]','',clean(cells[3])) or 0),
                    "bank": float(re.sub(r'[^\d.\-]','',clean(cells[4])) or 0),
                    "status": clean(cells[5]).split('\n')[0].strip(),
                    "agency": clean(cells[9]) if len(cells)>9 else "",
                    "time": clean(cells[7]) if len(cells)>7 else "",
                    "key": False,
                })
            except (ValueError, IndexError):
                continue
    return stations, "html-table"

# ── routes ──
@app.route("/tw/stations")
def stations():
    source = "fallback"
    try:
        data, source = scrape()
        if not data:
            raise ValueError("scrape ได้ 0 สถานี")
    except Exception as e:
        data = [dict(s) for s in FALLBACK]  # ใช้ข้อมูลสำรอง
        print(f"⚠️  scrape ล้มเหลว ({e}) → ใช้ fallback")

    for s in data:
        s["key"] = any(k in s["name"] for k in KEY_NAMES)
        s["province"] = "สงขลา"

    return jsonify({
        "source": f"ThaiWater (สสน.) · {source}",
        "province": "สงขลา",
        "updated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "count": len(data),
        "stations": data,
    })

@app.route("/tw/health")
def health():
    try:
        r = requests.get(PAGE, headers=HDR, timeout=10)
        return jsonify({"ok": r.status_code==200, "status": r.status_code})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/tw/debug")
def debug():
    """ดูว่า scrape ได้จริงไหม — เปิดในเบราว์เซอร์: localhost:5001/tw/debug"""
    try:
        r = requests.get(PAGE, headers=HDR, timeout=20)
        r.encoding = "utf-8"
        has_table = "<td" in r.text
        has_json  = "stationData" in r.text or '"stations"' in r.text
        return jsonify({
            "http_status": r.status_code,
            "page_length": len(r.text),
            "has_html_table": has_table,
            "has_embedded_json": has_json,
            "hint": "ถ้าทั้งสองเป็น false → หน้าเว็บ render ด้วย JavaScript ต้องใช้ Selenium หรือหา API endpoint จริง (กด F12 → Network → หา request ที่ส่งข้อมูลสถานี)"
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    print("=" * 50)
    print("  ThaiWater Proxy — HTY FLOOD COMMAND")
    print("  http://localhost:5001/tw/stations")
    print("  http://localhost:5001/tw/debug   (ตรวจ scrape)")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5001, debug=False)