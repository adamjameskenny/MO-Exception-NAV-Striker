import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# --- PAGE SETUP ---
st.set_page_config(page_title="MO Recon Engine", page_icon="📊", layout="wide")
st.title("📊 Middle Office Recon & NAV Engine")
st.markdown("""
*Simulating a daily T+1 reconciliation workflow. This tool merges internal ledgers with Prime Broker statements, flags exceptions, and calculates performance fees over a High Water Mark.*
""")

# --- 1. GENERATE DUMMY DATA (With intentional breaks) ---
@st.cache_data
def load_data():
    internal_data = pd.DataFrame({
        "ISIN": ["US0378331005", "US4592001014", "NL0010273215", "GB0001820812", "US88160R1014"],
        "Asset": ["Apple", "IBM", "ASML", "Vodafone", "Tesla"],
        "Currency": ["USD", "USD", "EUR", "GBP", "USD"],
        "Int_Qty": [1000, 500, 200, 5000, 300],
        "Int_Price": [150.0, 130.0, 800.0, 1.2, 200.0] # Tesla price pre-split
    })
    
    pb_data = pd.DataFrame({
        "ISIN": ["US0378331005", "US4592001014", "NL0010273215", "GB0001820812", "US88160R1014"],
        "PB_Qty": [1000, 500, 200, 4000, 300], # Break: Vodafone quantity mismatch (T+1 settlement fail?)
        "PB_Price": [150.0, 130.0, 800.0, 1.2, 66.66] # Break: Tesla 3-for-1 split price drop
    })
    return internal_data, pb_data

internal_df, pb_df = load_data()

# --- SIDEBAR: PARAMETERS ---
st.sidebar.header("⚙️ Pricing & Fee Controls")
price_drop_threshold = st.sidebar.slider("Alert: Price Drop Threshold (%)", 5, 50, 20)
hwm = st.sidebar.number_input("High Water Mark (HWM) $", value=1_000_000, step=50000)
hurdle_rate = st.sidebar.number_input("Hurdle Rate (%)", value=5.0, step=0.5)

# --- 2. THE RECONCILIATION ENGINE (ISIN MERGE) ---
st.header("1. Position & Pricing Reconciliation")
st.write("Merging Internal Ledger with Prime Broker Feed via ISIN...")

# Merge on ISIN (The Primary Key)
recon_df = pd.merge(internal_df, pb_df, on="ISIN", how="outer")

# Calculate differences
recon_df["Qty_Break"] = recon_df["Int_Qty"] - recon_df["PB_Qty"]
recon_df["Price_Diff_%"] = ((recon_df["PB_Price"] - recon_df["Int_Price"]) / recon_df["Int_Price"]) * 100

# Function to highlight breaks in red
def highlight_breaks(row):
    color = 'background-color: #ffcccc' if row['Qty_Break'] != 0 or abs(row['Price_Diff_%']) >= price_drop_threshold else ''
    return [color] * len(row)

st.dataframe(recon_df.style.apply(highlight_breaks, axis=1), use_container_width=True)

# --- 3. EXCEPTION REPORTING ---
st.header("2. Exception Dashboard")
col1, col2 = st.columns(2)

with col1:
    st.error("🚨 Quantity Breaks (Settlement Fails?)")
    qty_breaks = recon_df[recon_df["Qty_Break"] != 0]
    if not qty_breaks.empty:
        st.write(qty_breaks[["ISIN", "Asset", "Int_Qty", "PB_Qty", "Qty_Break"]])
    else:
        st.success("No quantity breaks. All trades settled.")

with col2:
    st.warning(f"⚠️ Price Drops > {price_drop_threshold}% (Check Corp Actions)")
    price_breaks = recon_df[recon_df["Price_Diff_%"] <= -price_drop_threshold]
    if not price_breaks.empty:
        st.write(price_breaks[["ISIN", "Asset", "Int_Price", "PB_Price", "Price_Diff_%"]])
    else:
        st.success("No suspicious price drops.")

# --- 4. NAV & PERFORMANCE FEE CALCULATION ---
st.header("3. Gross Asset Value & Fee Accrual")

# Assume breaks are investigated and we use PB prices & PB quantities for verified NAV
recon_df["Market_Value"] = recon_df["PB_Qty"] * recon_df["PB_Price"]
gav = recon_df["Market_Value"].sum()

# Fee Math
hurdle_target = hwm * (1 + (hurdle_rate / 100))
perf_fee = 0
if gav > hurdle_target:
    perf_fee = (gav - hwm) * 0.20 # 20% performance fee on profit above HWM

nav = gav - perf_fee

m1, m2, m3, m4 = st.columns(4)
m1.metric("Gross Asset Value (GAV)", f"${gav:,.2f}")
m2.metric("HWM + Hurdle Target", f"${hurdle_target:,.2f}")
m3.metric("Accrued Performance Fee", f"${perf_fee:,.2f}")
m4.metric("Final NAV", f"${nav:,.2f}", delta=f"${nav - hwm:,.2f} vs HWM")

# --- 5. FX HEDGING EXPOSURE ---
st.header("4. Currency Exposure (FX Hedging)")
currency_exposure = recon_df.groupby("Currency")["Market_Value"].sum().reset_index()

fig = px.pie(currency_exposure, values="Market_Value", names="Currency", hole=0.4, 
             title="Fund Currency Breakdown", color_discrete_sequence=px.colors.qualitative.Pastel)
st.plotly_chart(fig, use_container_width=True)

st.info("💡 Middle Office Action: If EUR or GBP exposure exceeds risk limits against the USD base fund, instruct FX Forwards to hedge currency risk.")
