import streamlit as st
import pandas as pd
import math
import os

st.set_page_config(page_title="Speedcubing Grandmaster Elo", page_icon="🧊", layout="wide")

RANKS_TSV   = "WCA_333_RanksAverage.tsv"
PERSONS_TSV = "WCA_Persons.tsv"
PEAKS_CSV   = "peaks.csv"

# ── Elo formula ────────────────────────────────────────────────────────────────
# Sub 60s:  Elo = 2850 - 1062 * log10(t / wr)  → WR=2850, 6.60s=2600
# 60s+:     Elo = 500  - 400  * log10(t / 60)  → 60s=500, last place~100

def calc_elo(avg_s, wr_s):
    if avg_s <= 0 or wr_s <= 0:
        return 0.0
    if avg_s < 60:
        return 2850 - 1062.0 * math.log10(avg_s / wr_s)
    else:
        return 500.0 - 400.0 * math.log10(avg_s / 60.0)

def fmt_time(cs):
    s = cs / 100
    if s >= 60:
        m = int(s // 60)
        return f"{m}:{s % 60:05.2f}"
    return f"{s:.2f}s"

TITLE_THRESHOLDS = [
    (2600, "Grandmaster",          "GM"),
    (2539, "International Master", "IM"),
    (2492, "FIDE Master",          "FM"),
    (2431, "Candidate Master",     "CM"),
    (2200, "Class A Competitor",   "A"),
    (1500, "Class B",              "B"),
    (500,  "Class C",              "C"),
    (0,    "Class D",              "D"),
]

def get_title(elo):
    for threshold, name, short in TITLE_THRESHOLDS:
        if elo >= threshold:
            return name, short
    return "Class D", "D"

def title_rank(short):
    order = ["GM","IM","FM","CM","A","B","C","D"]
    return order.index(short) if short in order else 99


# ── Load TSV files ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading WCA data...")
def load_data():
    # Read ranks — strip any quotes from column names PowerShell may have added
    ranks_df = pd.read_csv(RANKS_TSV, sep="\t", dtype=str)
    ranks_df.columns = [c.strip().strip('"').strip("'") for c in ranks_df.columns]

    # Normalise to expected column names regardless of case
    ranks_df.columns = [c.lower() for c in ranks_df.columns]
    ranks_df = ranks_df.rename(columns={
        "personid":      "person_id",
        "eventid":       "event_id",
        "worldrank":     "world_rank",
        "continentrank": "continent_rank",
        "countryrank":   "country_rank",
    })

    ranks_df = ranks_df[ranks_df["event_id"] == "333"].copy()
    ranks_df["best"]       = pd.to_numeric(ranks_df["best"],       errors="coerce")
    ranks_df["world_rank"] = pd.to_numeric(ranks_df["world_rank"], errors="coerce")
    ranks_df = ranks_df.dropna(subset=["best","world_rank"])

    # Read persons
    persons_df = pd.read_csv(PERSONS_TSV, sep="\t", dtype=str)
    persons_df.columns = [c.strip().strip('"').strip("'") for c in persons_df.columns]
    persons_df.columns = [c.lower() for c in persons_df.columns]
    persons_df = persons_df.rename(columns={
        "wcaid":     "wca_id",
        "subid":     "sub_id",
        "countryid": "country_id",
    })

    persons_df = persons_df[persons_df["sub_id"].astype(str).str.strip() == "1"]
    persons_df = persons_df[["wca_id","name","country_id"]]

    df = ranks_df.merge(persons_df, left_on="person_id", right_on="wca_id", how="left")
    df = df.sort_values("world_rank").reset_index(drop=True)
    return df


# ── Peak title protection ──────────────────────────────────────────────────────
def load_peaks():
    if os.path.exists(PEAKS_CSV):
        return pd.read_csv(PEAKS_CSV, dtype={"person_id": str, "peak_elo": float, "peak_title": str})
    return pd.DataFrame(columns=["person_id","peak_elo","peak_title"])

def save_peaks(df):
    df[["person_id","peak_elo","peak_title"]].to_csv(PEAKS_CSV, index=False)

def apply_peak_protection(df, peaks_df):
    if peaks_df.empty:
        df["peak_elo"]   = df["elo"]
        df["peak_title"] = df["title_short"]
        return df
    df = df.merge(peaks_df, on="person_id", how="left")
    df["peak_elo"]   = df["peak_elo"].fillna(df["elo"])
    df["peak_title"] = df["peak_title"].fillna(df["title_short"])
    upgrade_elo   = df["elo"] > df["peak_elo"]
    upgrade_title = df.apply(lambda r: title_rank(r["title_short"]) < title_rank(r["peak_title"]), axis=1)
    df.loc[upgrade_elo,   "peak_elo"]   = df.loc[upgrade_elo,   "elo"]
    df.loc[upgrade_title, "peak_title"] = df.loc[upgrade_title, "title_short"]
    return df


# ── Main ───────────────────────────────────────────────────────────────────────
for f in [RANKS_TSV, PERSONS_TSV]:
    if not os.path.exists(f):
        st.error(f"Cannot find `{f}` — make sure it is in the same folder as elo_dashboard.py")
        st.stop()

df = load_data()

wr_cs     = int(df["best"].min())
wr_s      = wr_cs / 100
wr_holder = df[df["best"] == wr_cs].iloc[0]

df["avg_s"]    = df["best"] / 100
df["elo"]      = df["avg_s"].apply(lambda x: calc_elo(x, wr_s))
df["title"], df["title_short"] = zip(*df["elo"].apply(get_title))
df["time_fmt"] = df["best"].apply(fmt_time)

peaks_df = load_peaks()
df = apply_peak_protection(df, peaks_df)
save_peaks(df)

df["display_title"] = df["peak_title"]
df["display_elo"]   = df[["elo","peak_elo"]].max(axis=1)

# ── Header ─────────────────────────────────────────────────────────────────────
st.title("🧊 Dynamic Grandmaster Elo · Speedcubing")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("World Record",  fmt_time(wr_cs))
c2.metric("WR Holder",     wr_holder.get("name", wr_holder["person_id"]))
c3.metric("Total Ranked",  f"{len(df):,}")
c4.metric("Grandmasters",  len(df[df["display_title"] == "GM"]))
c5.metric("Intl. Masters", len(df[df["display_title"] == "IM"]))

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["🏆 Leaderboard", "🔍 WCA ID Lookup", "🎚️ What-If Simulator", "📊 Title Distribution"])

with tab1:
    search = st.text_input("Search by name or WCA ID", placeholder="e.g. Feliks or 2009ZEMD01")
    view = df[["world_rank","name","person_id","country_id","time_fmt","display_elo","display_title"]].copy()
    view.columns = ["World Rank","Name","WCA ID","Country","Average","Elo","Title"]
    view["Elo"] = view["Elo"].round(0).astype(int)
    if search:
        mask = (
            view["Name"].str.contains(search, case=False, na=False) |
            view["WCA ID"].str.contains(search, case=False, na=False)
        )
        view = view[mask]
    st.dataframe(view.head(10000), use_container_width=True, hide_index=True)

with tab2:
    wca_id = st.text_input("Enter WCA ID", placeholder="e.g. 2009ZEMD01").strip().upper()
    if wca_id:
        row = df[df["person_id"].str.upper() == wca_id]
        if row.empty:
            st.warning("No competitor found with that WCA ID.")
        else:
            r = row.iloc[0]
            title_full, _ = get_title(r["display_elo"])
            st.subheader(r.get("name", wca_id))
            st.caption(str(wca_id) + " · " + str(r.get("country_id","—")))
            a, b, c, d = st.columns(4)
            a.metric("Elo Rating",  f"{r['display_elo']:.0f}")
            b.metric("World Rank",  f"#{int(r['world_rank']):,}")
            c.metric("3x3 Average", fmt_time(int(r["best"])))
            d.metric("Title",       r["display_title"] + " — " + title_full)
            if r["peak_title"] != r["title_short"]:
                st.info("🛡️ Title protected — this player earned a higher title in a previous dataset.")

with tab3:
    st.caption("Drag to simulate a hypothetical new world record.")
    hyp_s = st.slider("Hypothetical World Record (seconds)", min_value=2.50, max_value=6.00,
                      value=float(wr_s), step=0.01, format="%.2fs")
    sample = df.head(25).copy()
    sample["new_elo"]   = sample["avg_s"].apply(lambda x: calc_elo(x, hyp_s))
    sample["elo_delta"] = (sample["new_elo"] - sample["elo"]).round(0).astype(int)
    sample["new_title"] = sample["new_elo"].apply(lambda e: get_title(e)[1])
    out = sample[["world_rank","name","person_id","time_fmt","new_elo","elo_delta","new_title"]].copy()
    out.columns = ["Rank","Name","WCA ID","Average","New Elo","Δ Elo","Title"]
    out["New Elo"] = out["New Elo"].round(0).astype(int)
    st.dataframe(out, use_container_width=True, hide_index=True)

with tab4:
    st.caption("Title counts based on peak (protected) titles.")
    title_order = ["GM","IM","FM","CM","A","B","C","D"]
    title_names = {
        "GM":"Grandmaster","IM":"International Master","FM":"FIDE Master",
        "CM":"Candidate Master","A":"Class A Competitor","B":"Class B","C":"Class C","D":"Class D"
    }
    counts = df["display_title"].value_counts()
    total  = len(df)
    for t in title_order:
        c = counts.get(t, 0)
        pct = c / total * 100
        col1, col2, col3, col4 = st.columns([2,5,1,1])
        col1.write(f"**{t}** — {title_names[t]}")
        col2.progress(min(pct / 30, 1.0))
        col3.write(f"{c:,}")
        col4.write(f"{pct:.1f}%")
