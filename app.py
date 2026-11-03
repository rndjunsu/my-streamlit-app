
import os
import streamlit as st
from openai import OpenAI

client = OpenAI()

import streamlit as st

# 페이지 설정
st.set_page_config(
    page_title="에이블 | AI 개인비서",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 에이블 | AI 개인비서")
st.write("김 대리의 업무를 지원하는 AI 개인비서입니다.")

# 시스템 역할
sys_role = """
당신은 김 대리의 전문 AI 개인비서 '에이블'입니다.
김 대리의 업무를 정확하고 효율적으로 지원합니다.

[주요 업무]
1. 일반적인 질문에 답변합니다.
2. 미팅 내용을 핵심 위주로 요약합니다.
3. 주요 논의 사항과 최종 결정 사항을 구분합니다.
4. 김 대리의 담당 업무를 정리합니다.
5. 담당자, 마감일, 우선순위를 명확히 표시합니다.

[응답 원칙]
- 정확하고 간결하게 답변합니다.
- 확인되지 않은 정보는 '확인 필요'로 표시합니다.
- 미팅에 없는 내용을 임의로 생성하지 않습니다.
"""

# 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# 사용자 입력
prompt = st.chat_input("에이블에게 질문하세요.")

if prompt:
    # 사용자 메시지 저장
    st.session_state.messages.append({
        "role": "user",
        "content": prompt
    })

    with st.chat_message("user"):
        st.write(prompt)

    # LLM 호출
    with st.chat_message("assistant"):
        with st.spinner("에이블이 답변 중입니다..."):

            response = client.responses.create(
                model="gpt-4o-mini",
                input=[
                    {"role": "system", "content": sys_role},
                    *st.session_state.messages
                ]
            )

            answer = response.output_text
            st.write(answer)

    # AI 응답 저장
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer
    })

    # 최근 10턴(사용자+AI 20개 메시지) 유지
    st.session_state.messages = st.session_state.messages[-20:]

# 사이드바
with st.sidebar:
    st.header("⚙️ 대화 관리")

    st.write(
        f"저장된 대화: {len(st.session_state.messages) // 2}턴"
    )

    if st.button("🗑️ 대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()
