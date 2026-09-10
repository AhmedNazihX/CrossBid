"""Private company documents in Supabase Storage (S2.2.2).

Two acceptance criteria, and both are security properties rather than features: an upload
lands under the uploader's `company_id` prefix, and a signed URL expires within ten
minutes. So the bulk of this file is adversarial -- a filename is bidder-supplied text,
and the question is not whether the happy path works but whether a crafted one can leave
the prefix.

Everything is offline. No test constructs a real Supabase client, opens a socket, or reads
a real key: the store takes its bucket as a constructor argument and the factory takes the
client builder, so the fakes below are the only Storage there is. The clock is injected for
the same reason -- an expiry assertion should not depend on how long the test took.

Fixtures are module-local: `conftest.py` is shared ground and this story does not own it.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from storage3.exceptions import StorageApiError
from storage3.utils import StorageException

from crossbid.ingestion.storage import (
    CACHE_CONTROL,
    DEFAULT_CONTENT_TYPE,
    FALLBACK_FILENAME,
    KEY_SEGMENTS,
    KEY_SEPARATOR,
    MAX_FILENAME_CHARS,
    CompanyDocumentStore,
    ObjectNotFoundError,
    StorageError,
    company_document_store,
    object_key,
    storage_bucket,
)
from crossbid.settings import MAX_SIGNED_URL_TTL_SECONDS, Settings, load_settings

COMPANY = "11111111-1111-1111-1111-111111111111"
OTHER_COMPANY = "22222222-2222-2222-2222-222222222222"
DOCUMENT = "33333333-3333-3333-3333-333333333333"

FIXED_NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
SIGNED = "https://project.supabase.co/storage/v1/object/sign/company-documents/x?token=T"

FAKE_SERVICE_KEY = "sb_secret_LEAKED-SERVICE-ROLE-KEY"
FAKE_SUPABASE_URL = "https://abcdefghijklmnopqrst.supabase.co"

SUPABASE_ENV_VARS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_STORAGE_BUCKET",
    "SIGNED_URL_TTL_SECONDS",
)


class FakeBucket:
    """The two Storage calls the store makes, recorded rather than performed."""

    def __init__(
        self,
        *,
        signed: Mapping[str, Any] | None = None,
        upload_error: Exception | None = None,
        sign_error: Exception | None = None,
    ) -> None:
        self.signed = {"signedURL": SIGNED} if signed is None else signed
        self.upload_error = upload_error
        self.sign_error = sign_error
        self.uploads: list[tuple[str, bytes, Mapping[str, Any] | None]] = []
        self.signings: list[tuple[str, int]] = []

    def upload(
        self, path: str, file: bytes, file_options: Mapping[str, Any] | None = None
    ) -> object:
        self.uploads.append((path, file, file_options))
        if self.upload_error is not None:
            raise self.upload_error
        return {"path": path}

    def create_signed_url(self, path: str, expires_in: int) -> Mapping[str, Any]:
        self.signings.append((path, expires_in))
        if self.sign_error is not None:
            raise self.sign_error
        return self.signed


@pytest.fixture
def bucket() -> FakeBucket:
    return FakeBucket()


@pytest.fixture
def store(bucket: FakeBucket) -> CompanyDocumentStore:
    return CompanyDocumentStore(
        bucket, ttl_seconds=MAX_SIGNED_URL_TTL_SECONDS, clock=lambda: FIXED_NOW
    )


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Real settings off the real defaults file, with fake wiring and no dotenv layer."""
    for name in ("DATABASE_URL", "ENV", "AUTH_MODE", *SUPABASE_ENV_VARS):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-fake")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "fake-encryption-key")
    monkeypatch.setenv("SUPABASE_URL", FAKE_SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", FAKE_SERVICE_KEY)
    return load_settings(env_file=None)


def key_of(filename: str, *, company: str = COMPANY) -> str:
    return object_key(company_id=company, document_id=DOCUMENT, filename=filename)


# --------------------------------------------------- the company prefix, happy path


def test_the_object_key_is_company_then_document_then_filename() -> None:
    # Act
    key = key_of("Leistungsbeschreibung.pdf")

    # Assert -- the acceptance criterion: stored under my company prefix
    assert key == f"{COMPANY}/{DOCUMENT}/Leistungsbeschreibung.pdf"


def test_two_companies_never_share_a_prefix() -> None:
    # Act / Assert
    assert not key_of("a.pdf").startswith(f"{OTHER_COMPANY}{KEY_SEPARATOR}")


# ------------------------------------------------------- the company prefix, attacked

TRAVERSAL_FILENAMES = [
    pytest.param("../../etc/passwd", id="posix-traversal"),
    pytest.param("/etc/passwd", id="absolute-posix"),
    pytest.param("..\\..\\windows\\win.ini", id="windows-traversal"),
    pytest.param("C:\\secrets\\keys.txt", id="windows-drive"),
    pytest.param("..", id="dotdot"),
    pytest.param("....", id="only-dots"),
    pytest.param("./.././x.pdf", id="mixed-traversal"),
    pytest.param(f"{OTHER_COMPANY}/{DOCUMENT}/theirs.pdf", id="another-companys-key"),
    pytest.param("report\x00.pdf", id="nul-byte"),
    pytest.param("re\nport\r.pdf", id="newlines"),
    pytest.param("re\u202eport.pdf", id="bidi-override"),
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace"),
    pytest.param("\\", id="lone-backslash"),
    pytest.param("Eigenerklärung_Ausschlussgründe.pdf", id="umlauts"),
    pytest.param("x" * (MAX_FILENAME_CHARS * 3), id="overlong"),
]


@pytest.mark.parametrize("filename", TRAVERSAL_FILENAMES)
def test_no_filename_can_leave_the_company_prefix(filename: str) -> None:
    """The one property that matters: whatever the bidder called the file, the key is
    three segments deep and the first of them is the caller's own company."""
    # Act
    key = key_of(filename)

    # Assert
    segments = key.split(KEY_SEPARATOR)
    assert len(segments) == KEY_SEGMENTS
    assert segments[0] == COMPANY
    assert segments[1] == DOCUMENT
    assert segments[2] not in {"", ".", ".."}
    assert not segments[2].startswith((".", "-", "_"))
    assert len(segments[2]) <= MAX_FILENAME_CHARS


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        pytest.param("../../etc/passwd", "passwd", id="basename-only"),
        pytest.param("/etc/passwd", "passwd", id="absolute-basename"),
        pytest.param("..\\..\\win.ini", "win.ini", id="windows-basename"),
        pytest.param("report\x00.pdf", "report_.pdf", id="control-character-replaced"),
        pytest.param("my report (v2).pdf", "my_report_v2_.pdf", id="spaces-and-brackets"),
        pytest.param("..", FALLBACK_FILENAME, id="dotdot-has-nothing-left"),
        pytest.param("", FALLBACK_FILENAME, id="empty-has-nothing-left"),
        pytest.param(".hidden", "hidden", id="leading-dot-dropped"),
    ],
)
def test_the_sanitised_filename_is_what_we_expect(filename: str, expected: str) -> None:
    # Act / Assert -- pinned, so a change to the rule is a change to this table
    assert key_of(filename).split(KEY_SEPARATOR)[2] == expected


def test_an_overlong_filename_is_truncated_not_refused() -> None:
    """A bidder with a very long filename should still be able to upload."""
    # Act
    filename = key_of("a" * 500 + ".pdf").split(KEY_SEPARATOR)[2]

    # Assert
    assert len(filename) == MAX_FILENAME_CHARS


REFUSED_IDENTIFIERS = [
    pytest.param("", id="empty"),
    pytest.param("   ", id="whitespace"),
    pytest.param("..", id="dotdot"),
    pytest.param("acme/evil", id="slash"),
    pytest.param("acme\\evil", id="backslash"),
    pytest.param("acme\nevil", id="newline"),
    pytest.param(".acme", id="leading-dot"),
    pytest.param("acme id", id="space"),
    pytest.param("a" * 200, id="overlong"),
]


@pytest.mark.parametrize("identifier", REFUSED_IDENTIFIERS)
def test_a_company_id_that_is_not_an_identifier_is_refused(identifier: str) -> None:
    # Act / Assert
    with pytest.raises(StorageError, match="company_id"):
        object_key(company_id=identifier, document_id=DOCUMENT, filename="a.pdf")


@pytest.mark.parametrize("identifier", REFUSED_IDENTIFIERS)
def test_a_document_id_that_is_not_an_identifier_is_refused(identifier: str) -> None:
    # Act / Assert
    with pytest.raises(StorageError, match="document_id"):
        object_key(company_id=COMPANY, document_id=identifier, filename="a.pdf")


def test_a_refused_identifier_is_not_echoed_back() -> None:
    """An error message built from untrusted input is how untrusted input escapes."""
    # Act / Assert
    with pytest.raises(StorageError) as caught:
        object_key(company_id="<script>alert(1)</script>", document_id=DOCUMENT, filename="a")
    assert "script" not in str(caught.value)


# ------------------------------------------------------------------------------ upload


def test_upload_stores_the_content_under_the_key_it_returns(
    store: CompanyDocumentStore, bucket: FakeBucket
) -> None:
    # Act
    key = store.upload(
        company_id=COMPANY, document_id=DOCUMENT, filename="pack.pdf", content=b"%PDF-1.7"
    )

    # Assert
    assert key == f"{COMPANY}/{DOCUMENT}/pack.pdf"
    assert len(bucket.uploads) == 1
    assert bucket.uploads[0][0] == key
    assert bucket.uploads[0][1] == b"%PDF-1.7"


def test_upload_declares_the_content_type_and_refuses_to_overwrite(
    store: CompanyDocumentStore, bucket: FakeBucket
) -> None:
    # Act
    store.upload(
        company_id=COMPANY, document_id=DOCUMENT, filename="pack.pdf", content=b"%PDF-1.7"
    )

    # Assert
    options = bucket.uploads[0][2] or {}
    assert options["content-type"] == DEFAULT_CONTENT_TYPE
    assert options["cache-control"] == CACHE_CONTROL
    assert options["x-upsert"] == "false"


def test_upload_accepts_a_content_type_from_the_caller(
    store: CompanyDocumentStore, bucket: FakeBucket
) -> None:
    # Act
    store.upload(
        company_id=COMPANY,
        document_id=DOCUMENT,
        filename="offer.docx",
        content=b"PK",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    # Assert
    assert (bucket.uploads[0][2] or {})["content-type"].endswith("wordprocessingml.document")


def test_upload_refuses_empty_content(store: CompanyDocumentStore) -> None:
    """An empty upload is a client bug, and it would create an unreadable document row."""
    # Act / Assert
    with pytest.raises(StorageError, match="empty"):
        store.upload(company_id=COMPANY, document_id=DOCUMENT, filename="pack.pdf", content=b"")


def test_a_failed_upload_becomes_a_storage_error() -> None:
    # Arrange
    bucket = FakeBucket(upload_error=StorageException("bucket not found"))
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    with pytest.raises(StorageError, match="could not be stored") as caught:
        store.upload(
            company_id=COMPANY, document_id=DOCUMENT, filename="pack.pdf", content=b"%PDF"
        )
    assert DOCUMENT in str(caught.value)


# -------------------------------------------------------------------------- signed URLs


def test_a_signed_url_expires_within_ten_minutes(
    store: CompanyDocumentStore, bucket: FakeBucket
) -> None:
    # Arrange
    key = key_of("pack.pdf")

    # Act
    signed = store.signed_url(company_id=COMPANY, key=key)

    # Assert -- the acceptance criterion
    assert signed.url == SIGNED
    assert 0 < signed.expires_in <= MAX_SIGNED_URL_TTL_SECONDS
    assert signed.expires_at == FIXED_NOW + timedelta(seconds=signed.expires_in)
    assert bucket.signings == [(key, signed.expires_in)]


def test_the_ttl_comes_from_the_settings(settings: Settings, bucket: FakeBucket) -> None:
    # Arrange
    store = company_document_store(settings, bucket=bucket)

    # Act
    signed = store.signed_url(company_id=COMPANY, key=key_of("pack.pdf"))

    # Assert
    assert signed.expires_in == settings.env.signed_url_ttl_seconds
    assert signed.expires_in <= MAX_SIGNED_URL_TTL_SECONDS


def test_the_expiry_is_timezone_aware(store: CompanyDocumentStore) -> None:
    """A naive expiry compared against a UTC clock is an hour of unintended validity."""
    # Act
    signed = store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))

    # Assert
    assert signed.expires_at.tzinfo is not None


def test_the_lowercase_response_key_is_accepted() -> None:
    """storage3 returns both `signedURL` and `signedUrl`; neither spelling is ours."""
    # Arrange
    bucket = FakeBucket(signed={"signedUrl": SIGNED})
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    assert store.signed_url(company_id=COMPANY, key=key_of("a.pdf")).url == SIGNED


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({}, id="no-url-key"),
        pytest.param({"signedURL": None}, id="null-url"),
        pytest.param({"signedURL": ""}, id="empty-url"),
        pytest.param({"signedURL": "   "}, id="blank-url"),
        pytest.param({"signedURL": 7}, id="not-a-string"),
    ],
)
def test_a_response_without_a_usable_url_is_refused(response: Mapping[str, Any]) -> None:
    """Storage's answer is external data like any other, so it is validated, not trusted."""
    # Arrange
    bucket = FakeBucket(signed=response)
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    with pytest.raises(StorageError, match="no signed URL"):
        store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))


def test_a_failed_signing_becomes_a_storage_error() -> None:
    # Arrange
    bucket = FakeBucket(sign_error=StorageException("upstream is down"))
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    with pytest.raises(StorageError, match="could not be signed"):
        store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))


def test_a_missing_object_becomes_a_not_found_error() -> None:
    """Storage's own 404 is the router's 404, not a 500."""
    # Arrange
    error = StorageApiError(message="Object not found", code="404", status=404)
    bucket = FakeBucket(sign_error=error)
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    with pytest.raises(ObjectNotFoundError):
        store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))


def test_another_storage_api_error_is_not_a_not_found_error() -> None:
    # Arrange
    error = StorageApiError(message="rate limited", code="429", status=429)
    bucket = FakeBucket(sign_error=error)
    store = CompanyDocumentStore(bucket, ttl_seconds=60, clock=lambda: FIXED_NOW)

    # Act / Assert
    with pytest.raises(StorageError) as caught:
        store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))
    assert not isinstance(caught.value, ObjectNotFoundError)


# ------------------------------------------------------------------ tenant enforcement

FOREIGN_KEYS = [
    pytest.param(f"{OTHER_COMPANY}/{DOCUMENT}/theirs.pdf", id="another-companys-prefix"),
    pytest.param(f"{COMPANY}x/{DOCUMENT}/theirs.pdf", id="prefix-that-only-starts-the-same"),
    pytest.param(f"{DOCUMENT}/theirs.pdf", id="two-segments"),
    pytest.param(f"{COMPANY}/{DOCUMENT}/sub/theirs.pdf", id="four-segments"),
    pytest.param(f"{COMPANY}/{DOCUMENT}/..", id="dotdot-as-the-filename"),
    pytest.param(f"{COMPANY}/{DOCUMENT}/my file.pdf", id="filename-we-would-never-build"),
    pytest.param(f"{COMPANY}/../{DOCUMENT}", id="traversal-in-the-document-segment"),
    pytest.param("", id="empty"),
    pytest.param(f"{COMPANY}/{DOCUMENT}/", id="trailing-separator"),
]


@pytest.mark.parametrize("key", FOREIGN_KEYS)
def test_a_key_outside_my_prefix_is_not_found(
    store: CompanyDocumentStore, bucket: FakeBucket, key: str
) -> None:
    """Not a permission error: saying "forbidden" would confirm the document exists."""
    # Act / Assert
    with pytest.raises(ObjectNotFoundError):
        store.signed_url(company_id=COMPANY, key=key)

    # Assert -- and Storage was never asked, so nothing was signed
    assert bucket.signings == []


@pytest.mark.parametrize("filename", TRAVERSAL_FILENAMES)
def test_every_key_we_build_is_a_key_we_will_sign(
    store: CompanyDocumentStore, bucket: FakeBucket, filename: str
) -> None:
    """The other half of the guard, and the half a strict check gets wrong: the rule that
    rejects a foreign key must accept every key `object_key` produced, or an upload with
    an awkward filename would become a document that can never be opened."""
    # Arrange
    key = key_of(filename)

    # Act
    store.signed_url(company_id=COMPANY, key=key)

    # Assert
    assert bucket.signings == [(key, MAX_SIGNED_URL_TTL_SECONDS)]


def test_the_not_found_error_does_not_echo_the_key(store: CompanyDocumentStore) -> None:
    """The key holds another company's id; a 404 body must not carry it."""
    # Act / Assert
    with pytest.raises(ObjectNotFoundError) as caught:
        store.signed_url(company_id=COMPANY, key=f"{OTHER_COMPANY}/{DOCUMENT}/theirs.pdf")
    assert OTHER_COMPANY not in str(caught.value)


def test_a_not_found_error_is_a_storage_error() -> None:
    """One `except StorageError` in a router still catches it; the 404 mapping is narrower."""
    # Act / Assert
    assert issubclass(ObjectNotFoundError, StorageError)


def test_asking_with_a_bad_company_id_is_refused(store: CompanyDocumentStore) -> None:
    # Act / Assert
    with pytest.raises(StorageError, match="company_id"):
        store.signed_url(company_id="a/b", key=key_of("a.pdf"))


# --------------------------------------------------------------- the store's own guards


@pytest.mark.parametrize("ttl", [0, -1, MAX_SIGNED_URL_TTL_SECONDS + 1, 3600])
def test_a_store_built_with_an_out_of_range_ttl_is_refused(
    bucket: FakeBucket, ttl: int
) -> None:
    """Startup validates `SIGNED_URL_TTL_SECONDS`; this is the same rule at the seam a
    router could construct directly, so the ten-minute cap holds on both paths."""
    # Act / Assert
    with pytest.raises(StorageError, match="ttl_seconds"):
        CompanyDocumentStore(bucket, ttl_seconds=ttl)


def test_the_signed_url_object_is_immutable(store: CompanyDocumentStore) -> None:
    # Arrange
    signed = store.signed_url(company_id=COMPANY, key=key_of("a.pdf"))

    # Act / Assert
    with pytest.raises(AttributeError):
        signed.url = "https://elsewhere.example"  # type: ignore[misc]


# --------------------------------------------------------------------------- the factory


class FakeStorageClient:
    """`create_client(url, key).storage.from_(bucket)`, without a client."""

    def __init__(self, url: str, key: str) -> None:
        self.url = url
        self.key = key
        self.buckets: list[str] = []

    @property
    def storage(self) -> FakeStorageClient:
        return self

    def from_(self, bucket_id: str, /) -> FakeBucket:
        self.buckets.append(bucket_id)
        return FakeBucket()


def test_the_factory_passes_the_wiring_to_the_client(settings: Settings) -> None:
    # Arrange
    built: list[FakeStorageClient] = []

    def create(url: str, key: str) -> FakeStorageClient:
        client = FakeStorageClient(url, key)
        built.append(client)
        return client

    # Act
    storage_bucket(settings, create=create)

    # Assert
    assert built[0].url == FAKE_SUPABASE_URL
    assert built[0].key == FAKE_SERVICE_KEY
    assert built[0].buckets == [settings.env.supabase_storage_bucket]


@pytest.mark.parametrize(
    ("unset", "expected"),
    [
        pytest.param("SUPABASE_URL", "SUPABASE_URL", id="url"),
        pytest.param("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY", id="service-key"),
    ],
)
def test_the_factory_names_the_variable_that_is_missing(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, unset: str, expected: str
) -> None:
    # Arrange
    monkeypatch.delenv(unset, raising=False)
    incomplete = load_settings(env_file=None)

    # Act / Assert
    with pytest.raises(StorageError, match=expected) as caught:
        storage_bucket(incomplete)
    assert FAKE_SERVICE_KEY not in str(caught.value)


def test_the_factory_refuses_a_blank_bucket_name(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "   ")

    # Act / Assert
    with pytest.raises(StorageError, match="SUPABASE_STORAGE_BUCKET"):
        storage_bucket(load_settings(env_file=None))


@pytest.mark.parametrize(
    "url",
    [
        pytest.param("abcdefghijklmnopqrst.supabase.co", id="no-scheme"),
        pytest.param("ftp://abcdefghijklmnopqrst.supabase.co", id="wrong-scheme"),
        pytest.param("postgresql://db.abc.supabase.co:5432/postgres", id="the-database-dsn"),
    ],
)
def test_the_factory_refuses_a_url_that_is_not_an_api_url(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """The two Supabase URLs are easy to confuse, and the DSN carries a password."""
    # Arrange
    monkeypatch.setenv("SUPABASE_URL", url)

    # Act / Assert
    with pytest.raises(StorageError, match="SUPABASE_URL"):
        storage_bucket(load_settings(env_file=None))


def test_the_store_factory_wires_the_bucket_and_the_ttl(
    settings: Settings, bucket: FakeBucket
) -> None:
    # Act
    store = company_document_store(settings, bucket=bucket)

    # Act / Assert -- the injected bucket is the one used, so no client was built
    store.upload(company_id=COMPANY, document_id=DOCUMENT, filename="a.pdf", content=b"%PDF")
    assert bucket.uploads[0][0] == key_of("a.pdf")


def test_the_store_factory_builds_a_bucket_when_it_is_given_none(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange -- the real factory would need a client, so the seam is stubbed
    monkeypatch.setattr(
        "crossbid.ingestion.storage.storage_bucket", lambda _settings: FakeBucket()
    )

    # Act / Assert
    assert (
        company_document_store(settings).signed_url(company_id=COMPANY, key=key_of("a.pdf")).url
        == SIGNED
    )
