"""Verify MVP collections against NASA CMR (official catalog): concept id, title, temporal extent,
latest granule, and the variable records (name, units, long name) for the variables we need."""
import json, urllib.request, urllib.parse, warnings
import earthaccess
from harmony import Client, CapabilitiesRequest
warnings.filterwarnings("ignore")
CMR = "https://cmr.earthdata.nasa.gov/search"

def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)

WANT = [("M2TMNXSLV", "5.12.4", ["T2M"]),
        ("M2TMNXFLX", "5.12.4", ["PRECTOTCORR", "PRECTOT"]),
        ("M2TMNXLND", "5.12.4", ["GWETTOP", "PRECTOTLAND"]),
        ("M2TMNXAER", "5.12.4", ["TOTEXTTAU"]),
        ("GPM_3IMERGM", "07", ["precipitation"]),
        ("GPM_3IMERGDF", "07", ["precipitation"]),
        ("MOD08_M3", "6.1", ["AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean"]),
        ("MYD08_M3", "6.1", ["AOD_550_Dark_Target_Deep_Blue_Combined_Mean_Mean"])]
hc = Client()
for sn, ver, names in WANT:
    c = get(f"{CMR}/collections.umm_json?short_name={sn}&version={urllib.parse.quote(ver)}")
    if not c["hits"]:
        print(f"\n{sn} v{ver}: NOT FOUND in CMR"); continue
    it = c["items"][0]; m, u = it["meta"], it["umm"]
    rng = u.get("TemporalExtents", [{}])[0].get("RangeDateTimes", [{}])[0]
    g = get(f"{CMR}/granules.umm_json?collection_concept_id={m['concept-id']}&sort_key=-start_date&page_size=1")
    last = g["items"][0]["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10] if g["items"] else None
    g0 = get(f"{CMR}/granules.umm_json?collection_concept_id={m['concept-id']}&sort_key=start_date&page_size=1")
    first = g0["items"][0]["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10] if g0["items"] else None
    try:
        svc = [s["name"] for s in hc.submit(CapabilitiesRequest(collection_id=m["concept-id"]))["services"]]
    except Exception as e:
        svc = [f"capabilities error: {str(e)[:60]}"]
    print(f"\n{sn} v{u.get('Version')}  {m['concept-id']}  provider {m['provider-id']}")
    print(f"  title: {u.get('EntryTitle')}")
    print(f"  metadata extent: {rng.get('BeginningDateTime','')[:10]} .. {(rng.get('EndingDateTime') or 'ongoing')[:10]}  | first granule {first}  latest granule {last}")
    print(f"  harmony services: {svc}")
    vids = m.get("associations", {}).get("variables", [])
    found = {}
    for i in range(0, len(vids), 100):
        v = get(f"{CMR}/variables.umm_json?concept_id[]=" + "&concept_id[]=".join(vids[i:i+100]) + "&page_size=100")
        for x in v["items"]:
            nm = x["umm"]["Name"].split("/")[-1]
            if nm in names:
                found[nm] = (x["umm"]["Name"], x["umm"].get("Units"), x["umm"].get("LongName"))
    for nm in names:
        print(f"  var {nm}: " + (f"path={found[nm][0]} units={found[nm][1]} long_name={found[nm][2]}" if nm in found else "NOT in CMR variable records"))
