"""W02a-e — admin-managed identities + incident-scoped RBAC."""
import pytest

from identity import (
    Access,
    AuthzDenied,
    IdentityService,
    PrincipalKind,
    Role,
)


def svc_with_users():
    s = IdentityService()
    admin = "admin-root"
    resp = s.add_user(admin, "alice", Role.RESPONDER, PrincipalKind.HUMAN,
                      incident_scope={"inc-1"})
    obs = s.add_user(admin, "bob", Role.OBSERVER, PrincipalKind.HUMAN,
                     incident_scope={"inc-1"})
    other = s.add_user(admin, "carol", Role.RESPONDER, PrincipalKind.HUMAN,
                       incident_scope={"inc-2"})
    dev = s.add_user(admin, "puck-a", Role.DEVICE, PrincipalKind.MACHINE)
    agent = s.add_user(admin, "nemotron", Role.AGENT, PrincipalKind.MACHINE,
                       incident_scope={"inc-1"})
    return s, {"admin": admin, "resp": resp.user_id, "obs": obs.user_id,
               "other": other.user_id, "dev": dev.user_id,
               "agent": agent.user_id}


# ---------- W02a: add/revoke users with audit ----------

def test_w02a_add_revoke_audited():
    s, u = svc_with_users()
    trail = s.audit_trail(u["resp"])
    assert any(a.operation == "user_add" for a in trail)
    s.revoke_user(u["admin"], u["resp"])
    ops = [a.operation for a in s.audit_trail(u["resp"])]
    assert "user_revoke" in ops
    # revoked user loses all access
    d = s.authorize(u["resp"], Access.READ_INCIDENT, "inc-1")
    assert not d.allowed


def test_w02a_non_admin_cannot_manage_users():
    s, u = svc_with_users()
    with pytest.raises(AuthzDenied):
        s.add_user(u["resp"], "eve", Role.OBSERVER, PrincipalKind.HUMAN)
    with pytest.raises(AuthzDenied):
        s.revoke_user(u["obs"], u["other"])


# ---------- W02b: observer is read-only ----------

def test_w02b_observer_read_only():
    s, u = svc_with_users()
    assert s.authorize(u["obs"], Access.READ_INCIDENT, "inc-1").allowed
    assert s.authorize(u["obs"], Access.READ_CHAT, "inc-1").allowed
    for denied in (Access.WRITE_INCIDENT, Access.UPLOAD_EVIDENCE,
                   Access.POST_CHAT, Access.APPROVE_ACTION,
                   Access.PROPOSE_ACTION, Access.MANAGE_USERS):
        d = s.authorize(u["obs"], denied, "inc-1")
        assert not d.allowed, f"observer allowed {denied}"


# ---------- W02c: no cross-incident data leaks ----------

def test_w02c_incident_scope_blocks_cross_incident():
    s, u = svc_with_users()
    # alice scoped to inc-1 only
    assert s.authorize(u["resp"], Access.READ_INCIDENT, "inc-1").allowed
    d = s.authorize(u["resp"], Access.READ_INCIDENT, "inc-2")
    assert not d.allowed and "scope" in d.reason
    # writes also scoped
    d = s.authorize(u["resp"], Access.WRITE_INCIDENT, "inc-2")
    assert not d.allowed
    # admin/commander implicit-all only when no explicit scope
    cmd = s.add_user(u["admin"], "cmd", Role.COMMANDER, PrincipalKind.HUMAN)
    assert s.authorize(cmd.user_id, Access.READ_INCIDENT, "inc-2").allowed


# ---------- W02d: revocation takes effect immediately ----------

def test_w02d_revoke_immediate_no_cache():
    s, u = svc_with_users()
    tok = s.login("alice")
    assert tok is not None
    s.revoke_user(u["admin"], u["resp"])
    # session destroyed + every authorize fails
    assert s.sessions.get(tok) is None
    assert not s.authorize(u["resp"], Access.READ_INCIDENT, "inc-1").allowed


def test_w02d_suspended_denied():
    s, u = svc_with_users()
    user = s.users[u["other"]]
    from identity.models import UserStatus
    user.status = UserStatus.SUSPENDED
    assert not s.authorize(u["other"], Access.READ_INCIDENT, "inc-2").allowed


# ---------- W02e: devices/machines cannot human-login ----------

def test_w02e_machine_principals_no_human_login():
    s, u = svc_with_users()
    assert s.login("puck-a") is None          # device
    assert s.login("nemotron") is None        # agent
    assert s.login("alice") is not None       # human ok
    # device role has no API capabilities at all
    for a in Access:
        d = s.authorize(u["dev"], a, "inc-1")
        assert not d.allowed
    # agent can propose but never approve/manage
    assert s.authorize(u["agent"], Access.PROPOSE_ACTION, "inc-1").allowed
    assert not s.authorize(u["agent"], Access.APPROVE_ACTION, "inc-1").allowed
    assert not s.authorize(u["agent"], Access.MANAGE_USERS).allowed
