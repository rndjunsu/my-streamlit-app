# ==================================================
# PART 1. 기본 코드
# 환경 설정, PDF 로딩, 청크 분할, 벡터DB 생성
# ==================================================

import os
import re
import json
import logging
import math
import hashlib
import tempfile
from pathlib import Path
from collections import Counter

import streamlit as st
import io
import pymupdf
from review_panel import render_review_sidebar
from followup_questions import render_followup_questions
from big_project_planner import render_big_project_planner
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "ai_study_helper_banner.png"

# 1. Streamlit 페이지 설정
st.set_page_config(
    page_title="에이블 백서 | AIVLE School",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 화면 디자인
st.markdown("""
<style>
.stApp {
    background-color: #F7F9FC;
}
[data-testid="stSidebar"] {
    background-color: #EEF3F8;
    border-right: 1px solid #DCE4EC;
}
.block-container {
    max-width: 1100px;
    padding-top: 2rem;
}
h1, h2, h3 {
    color: #17283D;
    letter-spacing: -0.03em;
}
[data-testid="stChatMessage"] {
    background: white;
    border: 1px solid #DFE7EF;
    border-radius: 12px;
}
.stButton > button {
    border-radius: 9px;
    border-color: #DCE4EC;
}
.stButton > button[kind="primary"] {
    background-color: #1D416D;
    color: white;
    border-color: #1D416D;
}
</style>
""", unsafe_allow_html=True)

# 3. 임베딩 모델과 LLM 생성
@st.cache_resource(show_spinner=False)
def get_embeddings():
    return OpenAIEmbeddings(model="text-embedding-3-small")

@st.cache_resource(show_spinner=False)
def get_llm():
    return ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    )

# 4. 기존 ChromaDB 연결
# 이전 컬렉션 ID가 저장 DB에서 사라졌을 때만 PDF 원문으로 복구합니다.
def _is_collection_missing_error(error):
    message = str(error).lower()
    return "collection" in message and ("does not exist" in message or "not found" in message)


def get_default_db():
    db_path = Path("chroma_db")
    pdf_path = Path("AIVLE School 백서.pdf")
    if not db_path.is_dir():
        return None

    try:
        db = Chroma(
            collection_name="aivle_docs",
            embedding_function=get_embeddings(),
            persist_directory=str(db_path)
        )
        count = db._collection.count()
    except Exception as error:
        if not _is_collection_missing_error(error):
            raise
        if not pdf_path.is_file():
            raise RuntimeError(
                "기본 ChromaDB의 컬렉션 연결이 끊어졌으며 복구에 필요한 "
                "'AIVLE School 백서.pdf'도 없습니다. PDF와 DB를 함께 배포해 주세요."
            ) from error
        st.warning("기본 백서 DB의 기존 컬렉션을 찾지 못해 PDF 원문으로 새 인덱스를 준비합니다.")
        return rag_pipeline(pdf_path)

    # 원본 코드의 manifest 검증은 유지합니다.
    if count <= 0:
        return None

    manifest_path = "chroma_manifest.json"
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        if manifest.get("collection") != "aivle_docs" or manifest.get("chunk_count") != count:
            raise ValueError("기본 벡터DB와 백서 인덱스 정보가 일치하지 않습니다. Colab에서 DB를 재생성해 주세요.")
        if pdf_path.is_file():
            actual_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
            if actual_hash != manifest.get("pdf_sha256"):
