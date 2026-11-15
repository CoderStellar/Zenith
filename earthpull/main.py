"""Entry point. Run:  .venv/bin/streamlit run earthpull/main.py"""
import streamlit as st

st.set_page_config(page_title="Earth data finder", layout="wide")
pg = st.navigation([st.Page("app.py", title="Explore a region", default=True),
                    st.Page("viz_app.py", title="Trend viewer"),
                    st.Page("news_app.py", title="News lens"),
                    st.Page("engine_app.py", title="Correlation engine"),
                    st.Page("links_app.py", title="Links between places")])
pg.run()
