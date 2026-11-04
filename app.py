"""AIVLE AI Assistant v7 · Streamlit Cloud entrypoint."""
import hashlib
import hmac
import io
import json
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from aivle_core import analyze_meeting, create_html_report, general_chat, send_email

st.set_page_config(page_title="AIVLE AI 개인비서", page_icon="🤖", layout="wide")
st.title("🤖 AIVLE | AI 개인비서")
st.caption("음성 대화 · 회의 분석 · 업무 체크리스트 · HTML 이메일")

# Secrets는 세션에만 읽고, 화면/로그에 값을 출력하지 않습니다.
def setting(name):
    value = os.getenv(name)
    if value:
        return str(value)
    try:
        return str(st.secrets.get(name, ""))
    except Exception:
        return ""

for name in ("OPENAI_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD"):
    value = setting(name)
    if value:
        os.environ[name] = value

password = setting("AIVLE_ACCESS_PASSWORD")
if not password:
    st.error("AIVLE_ACCESS_PASSWORD를 Streamlit Secrets에 설정해주세요.")
    st.stop()
if not st.session_state.get("aivle_authenticated", False):
    entered = st.text_input("AIVLE 접속 비밀번호", type="password")
    if st.button("로그인"):
        if hmac.compare_digest(entered, password):
            st.session_state.aivle_authenticated = True
            st.rerun()
        else:
            st.error("비밀번호를 확인해주세요.")
    st.stop()
if not setting("OPENAI_API_KEY"):
    st.error("OPENAI_API_KEY를 환경변수 또는 Streamlit Secrets에 등록해주세요.")
    st.stop()
client = OpenAI()

initial = {
    "chat_history": [], "chat_tts": None, "chat_audio_hash": None,
    "stt_cache": {}, "meeting_draft": "", "meeting_source_hash": None,
    "meeting_data": None, "meeting_hash": None, "report_usage": None,
    "meeting_tts": None, "token_total": 0, "sent_hashes": set(),
    "send_log": [], "task_checks": {}, "send_result": None
}
for key, value in initial.items():
    if key not in st.session_state:
        st.session_state[key] = value


def sha256(contents):
    if isinstance(contents, str):
        contents = contents.encode("utf-8")
    return hashlib.sha256(contents).hexdigest()


def add_usage(usage):
    if usage:
        st.session_state.token_total += usage.get("total", 0)


def transcribe(audio):
    """One STT API call per unique audio bytes per current session."""
    audio_bytes = audio.getvalue()
    digest = sha256(audio_bytes)
    if digest not in st.session_state.stt_cache:
        stream = io.BytesIO(audio_bytes)
        stream.name = getattr(audio, "name", None) or "recording.wav"
        result = client.audio.transcriptions.create(
            model="whisper-1", file=stream, language="ko"
        )
        st.session_state.stt_cache[digest] = result.text
        return result.text, False
    return st.session_state.stt_cache[digest], True


def say(text):
    result = client.audio.speech.create(
        model="gpt-4o-mini-tts", voice="nova", input=text[:4000]
    )
    return result.content


def write_chat(text):
    if not text.strip():
        return
    reply, usage = general_chat(text, st.session_state.chat_history, client)
    st.session_state.chat_history.extend([
        {"role": "user", "content": text}, {"role": "assistant", "content": reply}
    ])
    st.session_state.chat_history = st.session_state.chat_history[-10:]
    st.session_state.chat_tts = None
    add_usage(usage)


def new_meeting_text(text, source_key=None):
    """Only overwrite editable draft when input source changes."""
    if source_key is not None and st.session_state.meeting_source_hash == source_key:
        return False
    st.session_state.meeting_draft = text
    st.session_state.meeting_source_hash = source_key
    return True


tab_chat, tab_meeting, tab_tasks = st.tabs(["💬 AI 대화", "🎙️ 회의 분석", "✅ 업무 관리"])

with tab_chat:
    st.subheader("일반 질문 및 음성 대화")
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    with st.expander("🎙️ 음성으로 질문하기"):
        chat_audio = st.audio_input("질문을 녹음하세요", key="chat_microphone")
        chat_upload = st.file_uploader(
            "또는 녹음 파일 업로드", type=["mp3", "wav", "m4a", "mp4", "webm"], key="chat_upload"
        )
        selected = chat_audio or chat_upload
        if st.button("음성 질문 실행", disabled=selected is None):
            try:
                with st.spinner("Whisper-1 음성 인식 및 답변 생성 중..."):
                    text, reused = transcribe(selected)
                    write_chat(text)
                st.info(f"인식된 질문: {text}" + (" (캐시 재사용)" if reused else ""))
                st.rerun()
            except Exception as exc:
                st.error(f"음성 질문 처리 실패: {exc}")

    typed = st.chat_input("AIVLE에게 질문하세요")
    if typed:
        try:
            with st.spinner("답변 생성 중..."):
                write_chat(typed)
            st.rerun()
        except Exception as exc:
            st.error(f"대화 오류: {exc}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔊 마지막 답변 읽기", disabled=not st.session_state.chat_history):
            try:
                last = st.session_state.chat_history[-1]
                if last["role"] == "assistant":
                    st.session_state.chat_tts = say(last["content"])
            except Exception as exc:
                st.error(f"TTS 오류: {exc}")
    with c2:
        if st.button("대화 기록 초기화"):
            st.session_state.chat_history = []
            st.session_state.chat_tts = None
            st.rerun()
    if st.session_state.chat_tts:
        st.audio(st.session_state.chat_tts, format="audio/mp3")

with tab_meeting:
    st.subheader("회의록 입력 / 음성 변환")
    txt = st.file_uploader("회의록 TXT 업로드 (음성 없이 바로 분석 가능)", type=["txt"], key="meeting_txt")
    if txt is not None:
        try:
            raw = txt.getvalue()
            key = "txt:" + sha256(raw)
            if st.session_state.meeting_source_hash != key:
                new_meeting_text(raw.decode("utf-8-sig"), key)
                st.rerun()
        except UnicodeDecodeError:
            st.error("TXT 파일 인코딩은 UTF-8이어야 합니다.")

    mode = st.radio("회의 음성 입력", ["마이크 녹음", "녹음 파일 업로드"], horizontal=True)
    audio = st.audio_input("회의 녹음", key="meeting_microphone") if mode == "마이크 녹음" else st.file_uploader(
        "회의 녹음 파일", type=["mp3", "wav", "m4a", "mp4", "webm"], key="meeting_upload"
    )
    if audio is not None:
        st.audio(audio)
    if st.button("🎙️ Whisper-1 STT 변환", disabled=audio is None):
        try:
            with st.spinner("Whisper-1로 변환 중..."):
                text, reused = transcribe(audio)
                new_meeting_text(text, "audio:" + sha256(audio.getvalue()))
            st.success("텍스트 변환 완료" + (" (캐시 재사용)" if reused else ""))
            st.rerun()
        except Exception as exc:
            st.error(f"STT 오류: {exc}")

    st.text_area("회의록 / STT 결과 (수정 가능)", key="meeting_draft", height=230)
    content = st.session_state.meeting_draft
    current_hash = sha256(content)
    up_to_date = st.session_state.meeting_hash == current_hash
    if st.button("🔍 회의 분석", type="primary"):
        if not content.strip():
            st.warning("회의록을 입력하거나 파일을 업로드해주세요.")
        elif up_to_date and st.session_state.meeting_data is not None:
            st.info("이전 분석 결과 재사용: 추가 LLM 토큰 없음")
        else:
            try:
                with st.spinner("회의 분석 중..."):
                    data, usage = analyze_meeting(content, client)
                st.session_state.meeting_data = data
                st.session_state.meeting_hash = current_hash
                st.session_state.report_usage = usage
                st.session_state.meeting_tts = None
                st.session_state.send_result = None
                add_usage(usage)
                st.success("분석 완료")
                st.rerun()
            except Exception as exc:
                st.error(f"분석 실패: {exc}")

    if st.session_state.meeting_data is not None and up_to_date:
        data = st.session_state.meeting_data
        st.divider()
        st.subheader("회의 분석 결과")
        a, b, c = st.columns(3)
        a.metric("결정 사항", len(data["decisions"]))
        b.metric("담당 업무", len(data["tasks"]))
        c.metric("높은 우선순위", sum(t["priority"] == "높음" for t in data["tasks"]))
        st.write(data["summary"])
        with st.expander("분석 JSON 확인"):
            st.json(data)
        if st.button("🔊 회의 요약 TTS"):
            try:
                st.session_state.meeting_tts = say(data["summary"])
            except Exception as exc:
                st.error(f"TTS 오류: {exc}")
        if st.session_state.meeting_tts:
            st.audio(st.session_state.meeting_tts, format="audio/mp3")

        report_html = create_html_report(data)
        st.subheader("📧 HTML 메일 미리보기")
        components.html(report_html, height=720, scrolling=True)
        col1, col2 = st.columns(2)
        col1.download_button("HTML 다운로드", report_html, "aivle_meeting_report.html", "text/html")
        col2.download_button("JSON 다운로드", json.dumps(data, ensure_ascii=False, indent=2), "aivle_meeting_report.json", "application/json")

        recipient = setting("GMAIL_ADDRESS").strip()
        st.caption(f"수신자: {recipient or '설정 필요'} (본인 메일만 허용)")
        already_sent = current_hash in st.session_state.sent_hashes
        if already_sent:
            st.success("이 세션에서 동일 회의록 보고서를 이미 발송했습니다.")
        approved = st.checkbox("내용 확인 후 이메일 발송에 동의합니다.", key="approve_" + current_hash[:12])
        if st.button("📨 이메일 발송", disabled=(not recipient or not approved or already_sent)):
            result = send_email(recipient, "AIVLE | 회의 요약 및 업무 보고", report_html)
            st.session_state.send_result = result
            if result["status"] == "success":
                st.session_state.sent_hashes.add(current_hash)
                st.session_state.send_log.append({"회의록": current_hash[:12], "수신자": recipient, "상태": "SMTP 수락"})
                st.success(result["message"])
            else:
                st.error(result.get("message", "발송 오류"))
        if st.session_state.report_usage:
            st.caption(f"분석 토큰 사용량: {st.session_state.report_usage}")
    elif st.session_state.meeting_data is not None:
        st.info("회의록이 수정되었습니다. 현재 내용으로 다시 분석해야 메일을 발송할 수 있습니다.")

with tab_tasks:
    st.subheader("김 대리 담당 업무")
    data = st.session_state.meeting_data
    if data is None:
        st.info("회의 분석을 완료하면 담당 업무가 여기에 나타납니다.")
    elif st.session_state.meeting_hash != sha256(st.session_state.meeting_draft):
        st.warning("회의록이 변경되었습니다. 새로 분석한 뒤 업무를 확인해주세요.")
    elif not data["tasks"]:
        st.info("추출된 담당 업무가 없습니다.")
    else:
        for index, task in enumerate(data["tasks"]):
            uid = sha256(st.session_state.meeting_hash + str(index) + task["title"])
            widget_key = "task_" + uid
            if widget_key not in st.session_state:
                st.session_state[widget_key] = st.session_state.task_checks.get(uid, False)
            done = st.checkbox(
                f"{task['title']} | 마감: {task['due_date']} | 우선순위: {task['priority']}",
                key=widget_key
            )
            st.session_state.task_checks[uid] = done
        done_count = sum(st.session_state.task_checks.get(sha256(st.session_state.meeting_hash + str(i) + t["title"]), False) for i, t in enumerate(data["tasks"]))
        st.progress(done_count / len(data["tasks"]), text=f"완료 {done_count}/{len(data['tasks'])}")
        st.caption("업무 체크 상태는 현재 Streamlit 세션에만 저장됩니다.")

if st.session_state.send_log:
    with st.expander("📬 세션 이메일 발송 기록"):
        st.dataframe(st.session_state.send_log, use_container_width=True)
st.divider()
st.caption(f"현재 세션 텍스트 LLM 토큰: {st.session_state.token_total:,} (STT/TTS 사용량 및 비용 별도)")
