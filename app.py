"""AIVLE School 백서 RAG — 2일차 Streamlit 화면 + PDF 업로드.

1일차의 aivle_whitepaper_baseline_rag.rag_pipeline()을 그대로 import해 사용합니다.
문서 업로드는 기본 백서와 분리된 세션 검색으로 작동합니다.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st
from aivle_whitepaper_baseline_rag import rag_pipeline

st.set_page_config(page_title="AIVLE School 학습 도우미", page_icon="📘")

APP_DIR = Path(__file__).resolve().parent
BASE_PDF = APP_DIR / "AIVLE School 백서_개정본(2).pdf"
UPLOAD_DIR = APP_DIR / ".uploaded_pdfs"
DB_DIR = APP_DIR / "aivle_chroma_baseline"


# 2일차 실습의 api_key.txt 읽기 방식 유지 (환경에 이미 키가 있으면 그대로 사용)
def load_api_key():
    for candidate in (APP_DIR / "api_key.txt", APP_DIR / "project04" / "api_key.txt"):
        if candidate.is_file():
            with candidate.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip().strip('"').strip("'")
            break


load_api_key()
if not os.environ.get("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY가 없습니다. 실습의 api_key.txt 설정을 확인하세요.")
    st.stop()

@st.cache_resource(show_spinner="백서 RAG 파이프라인 불러오는 중...")
def load_chain(pdf_path: str, pdf_digest: str):
    # 파일의 실제 내용 해시가 캐시 키에 포함되어 수정시 올바르게 갱신됩니다.
    return rag_pipeline(pdf_path, db_dir=DB_DIR)

st.title("📘 AIVLE School 학습 도우미")
st.caption("1일차 RAG 파이프라인을 재사용하는 2일차 Streamlit 챗봇")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "active_digest" not in st.session_state:
    st.session_state.active_digest = None

with st.sidebar:
    st.subheader("검색 문서")
    uploaded = st.file_uploader("PDF 문서 업로드", type=["pdf"], help="새 PDF를 업로드하면 해당 문서만 검색합니다.")
    use_uploaded = st.checkbox("업로드한 문서로 질문하기", value=True, disabled=uploaded is None)
    if st.button("대화 삭제", use_container_width=True):
        st.session_state.messages = []
        st.rerun()
    st.caption("기본 백서는 별도로 유지됩니다. 업로드한 문서는 다른 인덱스로 저장됩니다.")

if uploaded is not None and use_uploaded:
    content = uploaded.getvalue()
    if not content.startswith(b"%PDF-"):
        st.error("유효한 PDF 형식인지 확인해 주세요.")
        st.stop()
    if len(content) > 20 * 1024 * 1024:
        st.error("최대 20MB PDF까지만 업로드할 수 있습니다.")
        st.stop()
    digest = hashlib.sha256(content).hexdigest()
    UPLOAD_DIR.mkdir(exist_ok=True)
    pdf_path = UPLOAD_DIR / f"{digest}.pdf"  # 파일명에 사용자 입력을 포함하지 않음
    if not pdf_path.exists():
        pdf_path.write_bytes(content)
    doc_label = uploaded.name
else:
    if not BASE_PDF.is_file():
        st.warning(f"기본 백서 PDF를 찾을 수 없습니다: {BASE_PDF.name}")
        st.info("사이드바에서 PDF를 업로드하거나 기본 백서 파일을 앱 폴더에 넣어주세요.")
        st.stop()
    pdf_path = BASE_PDF
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    doc_label = BASE_PDF.name

if st.session_state.active_digest != digest:
    st.session_state.messages = []  # 다른 문서의 대화 내용이 섞이지 않도록 초기화
    st.session_state.active_digest = digest

st.caption(f"현재 검색 문서: {doc_label}")
try:
    chain = load_chain(str(pdf_path), digest)
except Exception as exc:
    st.error(f"RAG 파이프라인 준비 중 오류: {exc}")
    st.stop()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("sources"):
            with st.expander("검색된 백서 근거"):
                for src in message["sources"]:
                    st.markdown(f"**{src['page_label']} · {src['id']}**")
                    st.caption(src["excerpt"])

user_input = st.chat_input("문서에 관해 질문하세요.")
if user_input:
    st.session_state.messages.append({"role":"user", "content":user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    with st.chat_message("assistant"):
        with st.spinner("문서에서 근거를 검색하는 중..."):
            try:
                result = chain.invoke({"input":user_input})
            except Exception as exc:
                st.error(f"답변 생성 오류: {exc}")
                st.stop()
        st.markdown(result["answer"])
        with st.expander("검색된 백서 근거"):
            for src in result["sources"]:
                st.markdown(f"**{src['page_label']} · {src['id']}**")
                st.caption(src["excerpt"])
    st.session_state.messages.append({"role":"assistant", "content":result["answer"], "sources":result["sources"]})
