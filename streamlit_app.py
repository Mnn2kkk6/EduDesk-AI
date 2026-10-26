"""Streamlit demo UI for EduDesk AI."""
from __future__ import annotations

import json
import os

import requests
import streamlit as st
from dotenv import load_dotenv

from app.config import API_URL

load_dotenv()
st.set_page_config(page_title="EduDesk AI", page_icon="🎓", layout="wide")

API_BASE = os.getenv("EDUDESK_API_URL", API_URL).rstrip("/")
STUDENT_OPTIONS = {
    "SV001 — Nguyen An (payment done, access pending)": "SV001",
    "SV002 — Tran Binh (active course access)": "SV002",
    "SV003 — Le Chi (payment pending)": "SV003",
}


def api_get(path: str, timeout: int = 5):
    return requests.get(f"{API_BASE}{path}", timeout=timeout)


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption("Không có đoạn tài liệu liên quan đủ điểm để hiển thị.")
        return
    with st.expander(f"Nguồn RAG ({len(sources)} đoạn)", expanded=False):
        for number, source in enumerate(sources, start=1):
            page = f", trang {source['page']}" if source.get("page") else ""
            st.markdown(
                f"**{number}. {source.get('source', 'unknown')}{page}** "
                f"· relevance {source.get('score', 0):.3f}"
            )
            st.write(source.get("text", ""))
            st.divider()


def render_tool_calls(tool_calls: list[dict]) -> None:
    if not tool_calls:
        return
    with st.expander(f"Agent trace — {len(tool_calls)} tool call(s)", expanded=False):
        for call in tool_calls:
            st.markdown(f"**{call.get('tool_name')}**")
            st.caption(call.get("created_at", ""))
            st.code(
                json.dumps(
                    {"arguments": call.get("arguments"), "result": call.get("result")},
                    ensure_ascii=False,
                    indent=2,
                ),
                language="json",
            )


st.title("🎓 EduDesk AI")
st.caption("Student Support & Workflow Agent · RAG · Tool Calling · SQLite")

with st.sidebar:
    st.header("Demo settings")
    selected_label = st.selectbox("Sinh viên đang mô phỏng", list(STUDENT_OPTIONS))
    student_id = STUDENT_OPTIONS[selected_label]
    st.caption(f"Student ID: {student_id}")
    try:
        health_response = api_get("/api/v1/health")
        health_response.raise_for_status()
        health = health_response.json()
        if health.get("llm_configured"):
            st.success("Gemini API đã cấu hình")
        else:
            st.info("Demo Mode: RAG + tool rules, chưa cần API key")
        st.caption(f"Indexed chunks: {health.get('retrieval_chunks', 0)}")
    except requests.RequestException:
        st.error("Không kết nối được FastAPI")
        st.code("uvicorn app.main:app --reload", language="powershell")
        st.caption(f"API URL: {API_BASE}")

chat_tab, tickets_tab, documents_tab = st.tabs(["💬 Trợ lý AI", "🎫 Ticket dashboard", "📚 Tài liệu"])

with chat_tab:
    st.markdown(
        "Hỏi về chính sách, lịch học hoặc trạng thái đăng ký. "
        "Agent có thể tra cứu database và tạo ticket khi điều kiện phù hợp."
    )
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("mode"):
                if message["mode"] == "gemini":
                    st.caption("Đã dùng Gemini API")
                elif message["mode"] == "demo_fallback_after_api_error":
                    st.caption("Demo fallback sau lỗi API")
                else:
                    st.caption("Demo Mode — rule-based fallback")
            if message.get("warning"):
                st.warning(message["warning"])
            if message.get("sources"):
                render_sources(message["sources"])
            if message.get("tool_calls"):
                render_tool_calls(message["tool_calls"])

    prompt = st.chat_input("Ví dụ: Em đã thanh toán PY101 nhưng chưa truy cập được...")
    if prompt:
        prior_history = [
            {"role": item["role"], "content": item["content"]}
            for item in st.session_state.messages[-6:]
            if item["role"] in {"user", "assistant"}
        ]
        st.session_state.messages.append({"role": "user", "content": prompt})
        try:
            response = requests.post(
                f"{API_BASE}/api/v1/chat",
                json={
                    "student_id": student_id,
                    "message": prompt,
                    "history": prior_history,
                },
                timeout=120,
            )
            response.raise_for_status()
            payload = response.json()
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": payload.get("answer", "Không có câu trả lời."),
                    "mode": payload.get("mode"),
                    "warning": payload.get("warning"),
                    "sources": payload.get("sources", []),
                    "tool_calls": payload.get("tool_calls", []),
                }
            )
        except requests.HTTPError as exc:
            detail = exc.response.text[:500] if exc.response is not None else str(exc)
            st.session_state.messages.append(
                {"role": "assistant", "content": f"API trả về lỗi: {detail}"}
            )
        except requests.RequestException as exc:
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"Không gọi được backend tại {API_BASE}. Hãy kiểm tra terminal chạy FastAPI. Chi tiết: {exc}",
                }
            )
        st.rerun()

    if st.button("Xóa hội thoại", key="clear_chat"):
        st.session_state.messages = []
        st.rerun()

with tickets_tab:
    st.subheader("Các phiếu hỗ trợ đã tạo")
    filter_student = st.checkbox("Chỉ xem ticket của sinh viên đang chọn", value=False)
    try:
        query = f"?student_id={student_id}" if filter_student else ""
        response = api_get(f"/api/v1/tickets{query}")
        response.raise_for_status()
        ticket_rows = response.json().get("tickets", [])
        if ticket_rows:
            st.dataframe(ticket_rows, use_container_width=True, hide_index=True)
        else:
            st.info("Chưa có ticket. Thử báo một lỗi truy cập trong tab Trợ lý AI.")
        st.caption(f"Tổng ticket đang hiển thị: {len(ticket_rows)}")
        if st.button("Làm mới danh sách ticket"):
            st.rerun()
    except requests.RequestException as exc:
        st.error(f"Không tải được ticket: {exc}")

with documents_tab:
    st.subheader("Knowledge base")
    st.write("Tài liệu mặc định nằm trong data/knowledge_base. Có thể nạp thêm PDF, MD hoặc TXT (tối đa 10 MB).")
    uploaded_file = st.file_uploader("Chọn tài liệu", type=["pdf", "md", "txt"])
    if uploaded_file is not None and st.button("Tải lên và lập chỉ mục"):
        try:
            response = requests.post(
                f"{API_BASE}/api/v1/documents/upload",
                files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json()
            st.success(result.get("message", "Uploaded"))
            st.json(result)
        except requests.HTTPError as exc:
            st.error(exc.response.text[:500] if exc.response is not None else str(exc))
        except requests.RequestException as exc:
            st.error(f"Không tải được tài liệu: {exc}")

    try:
        response = api_get("/api/v1/documents")
        response.raise_for_status()
        document_payload = response.json()
        st.metric("Tổng đoạn đã index", document_payload.get("chunks", 0))
        st.write("Tài liệu được tìm thấy:")
        st.write(document_payload.get("documents", []))
    except requests.RequestException as exc:
        st.warning(f"Chưa lấy được danh sách tài liệu: {exc}")

st.divider()
st.caption("Dữ liệu sinh viên, khóa học và ticket là dữ liệu giả lập. Không dùng cho dữ liệu cá nhân hoặc nghiệp vụ thật.")
