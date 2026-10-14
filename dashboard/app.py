
from pathlib import Path
from io import BytesIO
import os

import boto3
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv


# ==================================================
# 1. PROJECT CONFIGURATION
# ==================================================

PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data" / "processed"

TRAFFIC_FILE = DATA_DIR / "cleaned_traffic.csv"
RECOMMENDATION_FILE = DATA_DIR / "signal_recommendations.csv"

load_dotenv(PROJECT_DIR / ".env")


# ==================================================
# 2. STREAMLIT PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="Smart Traffic Optimization",
    page_icon="🚦",
    layout="wide",
)

st.title("Smart Traffic Optimization System")
st.caption(
    "Historical traffic analytics and adaptive signal-time recommendations"
)


# ==================================================
# 3. DATA LOADING
# ==================================================

@st.cache_data(ttl=300)
def load_data(source):
    """Load traffic and recommendation data from R2 or local files."""

    if source == "Cloudflare R2":
        account_id = os.getenv("R2_ACCOUNT_ID")
        access_key = os.getenv("R2_ACCESS_KEY_ID")
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        bucket = os.getenv("R2_BUCKET_NAME")

        if not all([account_id, access_key, secret_key, bucket]):
            raise ValueError(
                "R2 credentials are missing. "
                "Check the .env file in your project root."
            )

        s3 = boto3.client(
            "s3",
            endpoint_url=(
                f"https://{account_id}.r2.cloudflarestorage.com"
            ),
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
        )

        # Download the processed traffic data into memory
        traffic_response = s3.get_object(
            Bucket=bucket,
            Key="processed/cleaned_traffic.csv",
        )

        # Download signal recommendations into memory
        recommendation_response = s3.get_object(
            Bucket=bucket,
            Key="processed/signal_recommendations.csv",
        )

        traffic = pd.read_csv(
            BytesIO(traffic_response["Body"].read()),
            parse_dates=["DateTime"],
        )

        recommendations = pd.read_csv(
            BytesIO(recommendation_response["Body"].read())
        )

    else:
        # Existing local-data workflow
        if not TRAFFIC_FILE.exists():
            raise FileNotFoundError(
                f"Cleaned dataset not found: {TRAFFIC_FILE}"
            )

        if not RECOMMENDATION_FILE.exists():
            raise FileNotFoundError(
                f"Signal recommendations not found: "
                f"{RECOMMENDATION_FILE}"
            )

        traffic = pd.read_csv(
            TRAFFIC_FILE,
            parse_dates=["DateTime"],
        )

        recommendations = pd.read_csv(RECOMMENDATION_FILE)

    # Validate the minimum columns needed by the dashboard
    required_traffic = {
        "DateTime", "Junction", "Vehicles", "Hour", "DayOfWeek"
    }

    required_recommendations = {
        "Junction",
        "Hour",
        "average_vehicles",
        "demand_ratio",
        "demand_category",
        "recommended_green_seconds",
    }

    missing_traffic = required_traffic - set(traffic.columns)
    missing_recommendations = (
        required_recommendations - set(recommendations.columns)
    )

    if missing_traffic:
        raise ValueError(
            f"Traffic data is missing columns: "
            f"{sorted(missing_traffic)}"
        )

    if missing_recommendations:
        raise ValueError(
            f"Recommendation data is missing columns: "
            f"{sorted(missing_recommendations)}"
        )

    return traffic, recommendations


# ==================================================
# 4. DATA SOURCE SELECTOR AND FALLBACK
# ==================================================

st.sidebar.header("Data Source")

data_source = st.sidebar.radio(
    "Load dashboard data from:",
    ["Cloudflare R2", "Local files"],
)

load_error = None

try:
    df, recommendations = load_data(data_source)

except Exception as error:
    if data_source == "Cloudflare R2":
        load_error = str(error)

        # Fall back to local files if R2 fails
        try:
            df, recommendations = load_data("Local files")

            st.sidebar.warning(
                "R2 is unavailable. Showing local data instead."
            )

        except Exception as local_error:
            st.error(
                "Unable to load data from Cloudflare R2 "
                "or local files."
            )
            st.exception(local_error)
            st.stop()

    else:
        st.error("Unable to load local data.")
        st.exception(error)
        st.stop()


if load_error:
    with st.expander("Cloud connection details"):
        st.code(load_error)

elif data_source == "Cloudflare R2":
    st.sidebar.success("Connected to Cloudflare R2")

else:
    st.sidebar.info("Using local files")


# ==================================================
# 5. SIDEBAR FILTERS
# ==================================================

st.sidebar.divider()
st.sidebar.header("Dashboard Filters")

junction_options = sorted(df["Junction"].unique().tolist())

selected_junctions = st.sidebar.multiselect(
    "Select junctions",
    options=junction_options,
    default=junction_options,
)

if not selected_junctions:
    st.warning("Select at least one junction.")
    st.stop()

filtered_df = df[
    df["Junction"].isin(selected_junctions)
].copy()

filtered_recommendations = recommendations[
    recommendations["Junction"].isin(selected_junctions)
].copy()


# ==================================================
# 6. KEY PERFORMANCE INDICATORS
# ==================================================

st.subheader("Traffic Overview")

total_records = len(filtered_df)
average_vehicles = filtered_df["Vehicles"].mean()

peak_hour = (
    filtered_df.groupby("Hour")["Vehicles"]
    .mean()
    .idxmax()
)

busiest_junction = (
    filtered_df.groupby("Junction")["Vehicles"]
    .mean()
    .idxmax()
)

c1, c2, c3, c4 = st.columns(4)

c1.metric("Traffic Records", f"{total_records:,}")
c2.metric("Average Vehicles", f"{average_vehicles:.2f}")
c3.metric("Busiest Hour", f"{int(peak_hour):02d}:00")
c4.metric(
    "Busiest Selected Junction",
    f"Junction {int(busiest_junction)}",
)

st.divider()


# ==================================================
# 7. HOURLY TRAFFIC PATTERNS
# ==================================================

st.subheader("Traffic Patterns by Hour")

hourly = (
    filtered_df.groupby(["Junction", "Hour"])["Vehicles"]
    .mean()
    .reset_index(name="Average Vehicles")
)

fig_hourly = px.line(
    hourly,
    x="Hour",
    y="Average Vehicles",
    color="Junction",
    markers=True,
    title="Average Hourly Traffic by Junction",
)

fig_hourly.update_xaxes(
    tickmode="linear",
    dtick=1,
    title="Hour of Day",
)

fig_hourly.update_layout(
    legend_title_text="Junction",
    hovermode="x unified",
)

st.plotly_chart(fig_hourly, use_container_width=True)


# ==================================================
# 8. JUNCTION COMPARISON AND WEEKDAY ANALYSIS
# ==================================================

left, right = st.columns(2)

with left:
    st.subheader("Junction Comparison")

    junction_summary = (
        filtered_df.groupby("Junction")["Vehicles"]
        .mean()
        .reset_index(name="Average Vehicles")
    )

    fig_junction = px.bar(
        junction_summary,
        x="Junction",
        y="Average Vehicles",
        color="Junction",
        title="Average Vehicles by Junction",
    )

    st.plotly_chart(
        fig_junction,
        use_container_width=True,
    )

with right:
    st.subheader("Traffic by Day of Week")

    day_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    weekday_summary = (
        filtered_df.groupby("DayOfWeek")["Vehicles"]
        .mean()
        .reindex(day_order)
        .reset_index(name="Average Vehicles")
    )

    fig_weekday = px.bar(
        weekday_summary,
        x="DayOfWeek",
        y="Average Vehicles",
        title="Average Traffic by Day",
    )

    st.plotly_chart(
        fig_weekday,
        use_container_width=True,
    )


# ==================================================
# 9. TRAFFIC DEMAND CLASSIFICATION
# ==================================================

st.divider()
st.subheader("Traffic Demand Classification")

category_counts = (
    filtered_recommendations["demand_category"]
    .value_counts()
    .rename_axis("Demand Category")
    .reset_index(name="Number of Hourly Profiles")
)

fig_categories = px.pie(
    category_counts,
    names="Demand Category",
    values="Number of Hourly Profiles",
    title="Hourly Demand Profiles",
    hole=0.4,
)

st.plotly_chart(
    fig_categories,
    use_container_width=True,
)


# ==================================================
# 10. SIGNAL TIMING RECOMMENDATIONS
# ==================================================

st.subheader("Signal Timing Recommendations")

st.caption(
    "Prototype recommendations based on historical hourly averages. "
    "These are not live signal commands or validated engineering timings."
)

recommendation_view = filtered_recommendations[
    [
        "Junction",
        "Hour",
        "average_vehicles",
        "demand_ratio",
        "demand_category",
        "recommended_green_seconds",
    ]
].copy()

recommendation_view = recommendation_view.rename(
    columns={
        "average_vehicles": "Average Vehicles",
        "demand_ratio": "Demand Ratio",
        "demand_category": "Demand Category",
        "recommended_green_seconds": "Recommended Green (sec)",
    }
)

recommendation_view["Hour"] = (
    recommendation_view["Hour"]
    .astype(int)
    .map(lambda hour: f"{hour:02d}:00")
)

recommendation_view = recommendation_view.sort_values(
    ["Junction", "Hour"]
)

st.dataframe(
    recommendation_view,
    use_container_width=True,
    hide_index=True,
)

csv_data = recommendation_view.to_csv(
    index=False
).encode("utf-8")

st.download_button(
    "Download Signal Recommendations (CSV)",
    data=csv_data,
    file_name="signal_recommendations.csv",
    mime="text/csv",
)


# ==================================================
# 11. STATUS MESSAGE
# ==================================================

if load_error:
    st.warning(
        "Dashboard is using local data because R2 was unavailable."
    )

elif data_source == "Cloudflare R2":
    st.success(
        "Dashboard loaded successfully from Cloudflare R2."
    )

else:
    st.success(
        "Dashboard loaded successfully from local files."
    )
