"""Hello probe for the container runtime (docs/SPEC.md §4 F1, F7). Throwaway; not a deploy path."""

import sys

import streamlit as st
from snowflake.snowpark.context import get_active_session

session = get_active_session()
(row,) = session.sql("SELECT CURRENT_ROLE()").collect()
st.title("Bob Killer hello probe")
st.write({"sys_version": sys.version, "streamlit": st.__version__, "role": row[0]})
