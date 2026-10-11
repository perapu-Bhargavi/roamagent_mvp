import json
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="TravelGenie AI", page_icon="🧭", layout="wide")
DATA_FILE = Path(__file__).parent / "data" / "routes.json"

@st.cache_data
def load_routes():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("routes", [])

def mins(t):
    h, m = map(int, t.split(":"))
    return h * 60 + m

def duration(n):
    return f"{n // 60}h {n % 60}m"

def find_journeys(routes, origin, destination, minimum_transfer=30):
    journeys = []
    origin, destination = origin.strip().lower(), destination.strip().lower()
    if not origin or not destination or origin == destination:
        return []
    for r in routes:
        if r["from"].strip().lower() == origin and r["to"].strip().lower() == destination:
            dep, arr = mins(r["departure"]), mins(r["arrival"])
            if arr <= dep: arr += 1440
            journeys.append({"legs":[r], "fare":int(r["fare"]), "departure":r["departure"],
                "arrival":r["arrival"], "duration":arr-dep, "wait":0, "transfers":0})
    for a in routes:
        if a["from"].strip().lower() != origin: continue
        for b in routes:
            if a["to"].strip().lower() != b["from"].strip().lower(): continue
            if b["to"].strip().lower() != destination: continue
            ad, aa, bd, ba = mins(a["departure"]), mins(a["arrival"]), mins(b["departure"]), mins(b["arrival"])
            if aa <= ad: aa += 1440
            if bd <= ad: bd += 1440; ba += 1440
            if ba <= bd: ba += 1440
            while bd < aa: bd += 1440; ba += 1440
            wait = bd-aa
            if wait < minimum_transfer: continue
            journeys.append({"legs":[a,b], "fare":int(a["fare"])+int(b["fare"]),
                "departure":a["departure"], "arrival":b["arrival"], "duration":ba-ad,
                "wait":wait, "transfers":1})
    unique = {tuple(x.get("id","") for x in j["legs"]):j for j in journeys}
    return sorted(unique.values(), key=lambda j:(j["fare"],j["duration"]))

def simulate_disruption(routes, route_id, delay, budget):
    affected = next((r for r in routes if r["id"] == route_id), None)
    if not affected: return None, []
    arrival = mins(affected["arrival"]) + delay
    alt_time = f"{(arrival // 60) % 24:02d}:{arrival % 60:02d}"
    alternatives = [j for j in find_journeys(routes, affected["from"], affected["to"])
                    if j["fare"] <= budget and any(x["id"] != route_id for x in j["legs"])]
    return {"route":affected, "delay":delay, "arrival":alt_time}, alternatives

routes = load_routes()
st.markdown("""<div style="padding:24px;border-radius:16px;background:linear-gradient(120deg,#102a43,#176b87);color:white">
<div style="letter-spacing:2px;font-size:13px">AGENTIC AI TRAVEL TECHNOLOGY · ROAMAGENT MVP</div>
<h1 style="color:white;margin-bottom:6px">🧭 TravelGenie AI</h1>
<p style="margin:0;color:#e5f4ff">Explore journeys, compare fares, and discover possible alternatives from available route data.</p>
</div>""", unsafe_allow_html=True)
st.write("")
if not routes:
    st.error("No routes found. Check that data/routes.json exists."); st.stop()

cities = sorted({c.strip() for r in routes for c in (r.get("from",""), r.get("to","")) if c.strip()})
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Plan a journey", "⚠️ Simulate disruption", "🚌 Route dataset", "ℹ️ About"])

with tab1:
    st.subheader("Find a journey")
    c1,c2 = st.columns(2)
    origin = c1.selectbox("Starting city", cities)
    dests = [c for c in cities if c != origin]
    destination = c2.selectbox("Destination", dests)
    budget = st.number_input("Maximum fare (₹)", min_value=0, max_value=100000, value=10000, step=100)
    if st.button("Find journeys", type="primary", use_container_width=True):
        results = [j for j in find_journeys(routes, origin, destination) if j["fare"] <= budget]
        if not results: st.warning("No journeys found for this route and budget in the current dataset.")
        else:
            st.success(f"Found {len(results)} option(s), ranked by lowest fare first.")
            for i,j in enumerate(results,1):
                with st.container(border=True):
                    a,b,c = st.columns(3)
                    a.metric(f"Option {i} · Fare", f"₹{j['fare']}")
                    b.metric("Duration", duration(j["duration"]))
                    c.metric("Transfers", str(j["transfers"]))
                    st.write(f"**Departure:** {j['departure']} · **Arrival:** {j['arrival']}")
                    for n,leg in enumerate(j["legs"],1):
                        st.write(f"{n}. **{leg['from']} → {leg['to']}** · {leg.get('mode','transport').title()} · {leg['departure']}–{leg['arrival']} · ₹{leg['fare']}")
                    if j["transfers"]: st.caption(f"Transfer wait: {j['wait']} minutes")
    st.caption("Prototype uses sample route data. It does not connect to live traffic, live availability, or booking.")

with tab2:
    st.subheader("What if a route is delayed?")
    st.write("Demonstration simulation only; no live disruption feed is connected.")
    opts = {f"{r['id']} · {r['from']} → {r['to']} ({r['departure']})":r["id"] for r in routes}
    label = st.selectbox("Select route", list(opts))
    delay = st.slider("Simulated delay (minutes)", 15, 360, 120, 15)
    budget2 = st.number_input("Alternative fare budget (₹)", 0, 100000, 10000, 100, key="budget2")
    if st.button("Simulate disruption", type="primary", use_container_width=True):
        affected, alternatives = simulate_disruption(routes, opts[label], delay, budget2)
        st.warning(f"Simulated arrival for {affected['route']['id']}: {affected['arrival']} after a {delay}-minute delay.")
        if alternatives:
            st.success(f"{len(alternatives)} alternative(s) found.")
            for i,j in enumerate(alternatives,1):
                path = " → ".join([j["legs"][0]["from"]] + [x["to"] for x in j["legs"]])
                st.write(f"**Option {i}:** {path} · ₹{j['fare']} · {duration(j['duration'])}")
        else: st.info("No alternative journey found within this budget in the sample data.")

with tab3:
    st.subheader("Available route dataset")
    st.write(f"Dataset contains **{len(routes)} routes**.")
    st.dataframe(routes, use_container_width=True, hide_index=True)
    st.download_button("Download routes.json", json.dumps({"routes":routes},indent=2),
                       file_name="routes.json", mime="application/json")

with tab4:
    st.subheader("About this prototype")
    st.markdown("""
**TravelGenie AI (RoamAgent MVP)** demonstrates transport journey planning from a JSON dataset.

**Current features**
- Direct and one-transfer journey search
- Origin, destination, and budget inputs
- Fare-first ranking and journey-duration estimates
- Simulated delay with possible alternative routes
- Route data viewer and JSON download

**Technology:** Python, Streamlit, JSON.

**Limitations:** Sample/static data only. No live traffic, live alerts, real-time seat availability, or ticket booking is connected.
""")

st.divider()
st.caption("TravelGenie AI · College prototype · Results depend on the included dataset.")
