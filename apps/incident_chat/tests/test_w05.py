"""W05a-d — incident chat: live exchange, restricted rooms, reconnect
history, nonce dedup, system posts, sanitization."""
import pytest

from incident_chat import (
    ChatDenied,
    ChatService,
    PrincipalRole,
    RoomKind,
    sanitize,
)

INC = "inc-1"


@pytest.fixture
def chat():
    c = ChatService()
    c.register_user("cmd", PrincipalRole.COMMANDER, {INC})
    c.register_user("resp", PrincipalRole.RESPONDER, {INC})
    c.register_user("obs", PrincipalRole.OBSERVER, {INC})
    c.register_user("cmd2", PrincipalRole.COMMANDER, {"inc-2"})
    c.create_room(INC)
    c.create_room(INC, RoomKind.COMMAND)
    c.create_room("inc-2")
    return c


def join_all(c):
    c.join("cmd", INC)
    c.join("resp", INC)
    c.join("obs", INC)


# ---------- W05a: commander + responder exchange ----------

def test_w05a_live_exchange(chat):
    join_all(chat)
    m1, dup = chat.post("cmd", INC, "containment approved for rack-01")
    m2, _ = chat.post("resp", INC, "isolating now, monitoring")
    assert not dup and m1.seq == 1 and m2.seq == 2
    hist = chat.history(INC)
    assert [m.sender_id for m in hist] == ["cmd", "resp"]
    assert hist[0].sender_role == PrincipalRole.COMMANDER
    # unread: cmd's cursor=1 (sent m1), resp's=2 (sent m2), obs's=0
    # -> observer sees both messages as unread
    assert chat.unread_counts(INC)["obs"] == 2
    assert chat.unread_counts(INC)["resp"] == 0
    chat.mark_read("obs", INC, 2)
    assert chat.unread_counts(INC)["obs"] == 0


# ---------- W05b: restricted room + observer restrictions ----------

def test_w05b_command_room_restricted(chat):
    chat.join("cmd", INC)
    chat.join("resp", INC, RoomKind.INCIDENT)
    # observer cannot join command channel
    with pytest.raises(ChatDenied):
        chat.join("obs", INC, RoomKind.COMMAND)
    # responder cannot join command channel either
    with pytest.raises(ChatDenied):
        chat.join("resp", INC, RoomKind.COMMAND)
    # observer CAN join incident room but CANNOT post
    chat.join("obs", INC)
    with pytest.raises(ChatDenied):
        chat.post("obs", INC, "just watching")
    # out-of-scope user cannot touch inc-1 at all
    with pytest.raises(ChatDenied):
        chat.join("cmd2", INC)


# ---------- W05c: reconnect retrieves missing history ----------

def test_w05c_reconnect_history_no_duplicates(chat):
    join_all(chat)
    for i in range(5):
        chat.post("cmd", INC, f"update {i}", client_nonce=f"n{i}")
    # client reconnects having seen seq 2 -> gets 3,4,5 only
    missed = chat.history(INC, since_seq=2)
    assert [m.seq for m in missed] == [3, 4, 5]
    assert [m.body for m in missed] == ["update 2", "update 3", "update 4"]


# ---------- W05d: nonce dedup + system posts + sanitization ----------

def test_w05d_nonce_dedup_no_duplicate(chat):
    join_all(chat)
    m1, d1 = chat.post("cmd", INC, "hello", client_nonce="abc123")
    m2, d2 = chat.post("cmd", INC, "hello", client_nonce="abc123")
    assert d1 is False and d2 is True
    assert m1.msg_id == m2.msg_id           # same message returned
    assert len(chat.history(INC)) == 1      # no duplicate stored


def test_w05d_system_posts_link_actions(chat):
    join_all(chat)
    sysmsg = chat.system_post(
        INC, "containment VERIFIED: port isolated on rack-01",
        links={"action_id": "act-77", "evidence_id": "ev-55"})
    assert sysmsg.kind == "system"
    assert sysmsg.sender_role == PrincipalRole.SYSTEM
    assert sysmsg.links["action_id"] == "act-77"
    hist = chat.history(INC)
    assert hist[-1].kind == "system"


def test_w05d_input_sanitized(chat):
    join_all(chat)
    m, _ = chat.post("cmd", INC,
                     "<script>alert(1)</script>check <b>this</b> & that")
    assert "<script>" not in m.body and "<b>" not in m.body
    assert "&" in m.body or "that" in m.body
    # pure-markup message -> empty after sanitize -> denied
    with pytest.raises(ChatDenied):
        chat.post("cmd", INC, "<b></b>")
    assert sanitize("<img src=x onerror=alert(1)>") == ""
