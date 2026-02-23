import hashlib

import pytest

from agentctx.security.audit import AuditEntry, AuditLog


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

class TestAuditLogHashing:
    def test_hash_is_deterministic(self):
        content = "some observation text"
        assert AuditLog.hash_content(content) == AuditLog.hash_content(content)

    def test_different_inputs_produce_different_hashes(self):
        assert AuditLog.hash_content("a") != AuditLog.hash_content("b")

    def test_hash_matches_stdlib_sha256(self):
        content = "test content"
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        assert AuditLog.hash_content(content) == expected

    def test_empty_string_hash(self):
        h = AuditLog.hash_content("")
        assert isinstance(h, str)
        assert len(h) == 64  # SHA-256 hex digest length


# ---------------------------------------------------------------------------
# Empty / missing state
# ---------------------------------------------------------------------------

class TestAuditLogEmpty:
    def test_last_entry_none_when_no_file(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        assert log.last_entry() is None

    def test_last_hash_none_when_no_file(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        assert log.last_hash() is None

    def test_all_entries_empty_when_no_file(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        assert log.all_entries() == []

    def test_verify_true_when_no_history(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        assert log.verify("anything") is True


# ---------------------------------------------------------------------------
# Append behaviour
# ---------------------------------------------------------------------------

class TestAuditLogAppend:
    def test_append_creates_file(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("manual", "", "first content")
        assert log.path.exists()

    def test_append_returns_entry_with_correct_fields(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        entry = log.append("observer", "old", "new content")
        assert entry.source == "observer"
        assert entry.char_delta == len("new content") - len("old")
        assert entry.sha256 == AuditLog.hash_content("new content")

    def test_append_char_delta_positive_on_growth(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        entry = log.append("observer", "", "new content")
        assert entry.char_delta > 0

    def test_append_char_delta_negative_on_shrink(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        entry = log.append("reflector", "long content here", "short")
        assert entry.char_delta < 0

    def test_append_multiple_entries_all_stored(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "first")
        log.append("reflector", "first", "first second")
        assert len(log.all_entries()) == 2

    def test_append_is_append_only(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "v1")
        log.append("observer", "v1", "v2")
        log.append("observer", "v2", "v3")
        entries = log.all_entries()
        assert len(entries) == 3
        assert entries[0].sha256 == AuditLog.hash_content("v1")
        assert entries[2].sha256 == AuditLog.hash_content("v3")


# ---------------------------------------------------------------------------
# last_entry / last_hash
# ---------------------------------------------------------------------------

class TestAuditLogLastEntry:
    def test_last_entry_returns_most_recent(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "content v1")
        log.append("reflector", "content v1", "content v2")
        last = log.last_entry()
        assert last.source == "reflector"
        assert last.sha256 == AuditLog.hash_content("content v2")

    def test_last_hash_matches_last_entry(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "content")
        assert log.last_hash() == AuditLog.hash_content("content")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

class TestAuditLogVerify:
    def test_verify_passes_for_matching_content(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "current content")
        assert log.verify("current content") is True

    def test_verify_fails_for_tampered_content(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "original content")
        assert log.verify("tampered content") is False

    def test_verify_after_multiple_appends_uses_last(self, tmp_path):
        log = AuditLog(tmp_path / "audit.jsonl")
        log.append("observer", "", "v1")
        log.append("reflector", "v1", "v2")
        assert log.verify("v2") is True
        assert log.verify("v1") is False
