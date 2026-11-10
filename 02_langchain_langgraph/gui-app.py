

import streamlit as st
data = ""
st.write("hello world")
st.button("Click me")
st.download_button("Download file", data)

with st.chat_message("user"):
    st.write("Hello 👋")


# Display a chat input widget inline.
with st.container():
    st.chat_input("Say something")


with st.sidebar:
    st.button("Seessions")

