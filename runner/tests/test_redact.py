"""F05: secrets and PII never reach Storage or the AI."""
import json
import zipfile

from reprova_runner.redact import Redactor


def test_exact_secret_value_is_replaced_by_its_ref_name():
    r = Redactor({"demo_web_login": "S3cret-Pa55!"})
    out = r.text("fill #password = S3cret-Pa55!")
    assert "S3cret-Pa55!" not in out
    assert "[REDACTED:demo_web_login]" in out


def test_patterns_cover_tokens_emails_and_numbers():
    r = Redactor()
    out = r.text("Authorization: Bearer abcdefghijklmnop user dana@example.com card 4111 1111 1111 1111 "
                 "call +972-50-123-4567 password=hunter2")
    for leaked in ("abcdefghijklmnop", "dana@example.com", "4111 1111 1111 1111", "123-4567", "hunter2"):
        assert leaked not in out


def test_json_stays_valid_after_redaction(tmp_path):
    f = tmp_path / "results.json"
    f.write_text(json.dumps({"password": "hunter2", "wallTime": 1731840000000, "ok": True}))
    Redactor().file(f)
    data = json.loads(f.read_text())
    assert data["password"] == "[REDACTED]"
    assert data["wallTime"] == 1731840000000   # numbers in structured files are not touched


def test_text_members_of_a_trace_zip_are_redacted(tmp_path):
    z = tmp_path / "t_trace.zip"
    with zipfile.ZipFile(z, "w") as w:
        w.writestr("trace.trace", '{"type":"input","value":"S3cret-Pa55!"}')
        w.writestr("resources/shot.png", b"\x89PNG not text")
    Redactor({"ref": "S3cret-Pa55!"}).file(z)
    with zipfile.ZipFile(z) as rz:
        assert b"S3cret-Pa55!" not in rz.read("trace.trace")
        assert rz.read("resources/shot.png") == b"\x89PNG not text"
