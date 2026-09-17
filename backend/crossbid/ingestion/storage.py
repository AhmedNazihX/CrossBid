"""S2.2.2 — every uploaded file under its company's prefix, behind a ten-minute URL.

Supabase Storage is an object store: a bucket holds flat keys, and the only isolation a
private bucket gives us for free is "nobody without a key or a signed URL". Crossbid does
not use Storage's own policies for tenancy — the plan settles isolation at the application
level (`company_id` filtering, not RLS) — so the *key layout* is the isolation, and this
module is the single definition of it: `{company_id}/{document_id}/{filename}`.

That makes two things load-bearing, and both are why this file is longer than a wrapper
over two API calls would be.

**1. A filename is untrusted input.** It arrives in a multipart part and reaches an object
key, which is a path. `../../etc/passwd`, `/etc/passwd`, `..\\..\\win.ini`, a NUL byte and
a right-to-left override are all things a bidder can call a file, and one of them landing
verbatim in the key would put the object outside the prefix that *is* the tenant boundary.
The rule is therefore an allowlist rather than a blocklist: take the basename, keep only
`[A-Za-z0-9._-]`, replace every other character with `_`, drop leading punctuation, bound
the length. Umlauts become `_`, which is a real loss of readability and deliberate — the
original filename is a column on `documents`, so the key never has to be pretty, only
safe. Company and document ids are validated instead of rewritten: they come from our own
tables, so anything not identifier-shaped is a bug and should say so.

**2. Asking for someone else's key answers "not found", never "forbidden".** A permission
error confirms that a document with that id exists, which is itself the leak the story is
about. `signed_url` therefore refuses any key it could not have built itself for *this*
company — that is one comparison against `object_key`'s own rules, so the check and the
builder cannot drift — and raises `ObjectNotFoundError`, which the router (S2.2.3/S3.1.1;
not here) maps to HTTP 404. Storage's own 404 is mapped to the same exception for the same
reason.

The bucket is a constructor argument and the client builder a keyword, so tests run with a
fake and never open a socket. Nothing in this module puts a key, a URL or a token in an
exception message: the service-role key bypasses every Storage policy, and a signed URL is
a bearer credential for the file it points at.

Verified against the installed client (supabase 2.31.0 / storage3 2.31.0, 2026-09-10):
`create_client(url, key).storage.from_(bucket)` builds a `SyncBucketProxy` with no network
call, `upload(path, file, file_options)` takes the HTTP headers as a `FileOptions` dict,
and `create_signed_url(path, expires_in)` returns a mapping carrying both `signedURL` and
`signedUrl`. The client validates neither key format nor key type — it only requires a
non-empty string and an `http(s)://` URL — so the newer `sb_secret_...` keys work exactly
like the legacy service-role JWTs.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Protocol

from storage3.exceptions import StorageApiError
from storage3.types import FileOptions
from storage3.utils import StorageException
from supabase import create_client

from crossbid.settings import MAX_SIGNED_URL_TTL_SECONDS, Settings

KEY_SEPARATOR: Final = "/"
KEY_SEGMENTS: Final = 3
"""Company, document, filename. The count is part of the boundary: a key with any other
number of segments is not one this module built, whatever it starts with."""

IDENTIFIER_PATTERN: Final = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
"""Company and document ids. UUIDs fit, and so does a dev-mode company slug; a separator,
a dot-segment, whitespace and anything longer than a UUID do not."""

UNSAFE_FILENAME_CHARACTERS: Final = re.compile(r"[^A-Za-z0-9._-]+")
"""Everything not in the allowlist, in runs, so `my report (v2)` collapses rather than
turning into a row of underscores. Path separators and control characters are in here by
being absent from the allowlist, which is why no new attack character has to be foreseen."""

LEADING_PUNCTUATION: Final = ".-_"
"""Trimmed from the front: it is what is left of `..` and `.hidden` after the allowlist,
and a key segment that begins with a dot is a dot-segment to something, somewhere."""

MAX_FILENAME_CHARS: Final = 120
FALLBACK_FILENAME: Final = "document"
"""Used when nothing survives sanitising. Refusing the upload instead would fail a bidder
whose filename is legitimately all non-Latin characters, and the key is not the name."""

DEFAULT_CONTENT_TYPE: Final = "application/pdf"
XML_CONTENT_TYPE: Final = "application/xml"
"""What a published ESPD request (DUME) is stored as — the only non-PDF kind (S2.5.1). The
stored type is decided by the server after the bytes have been checked, never echoed from
what the client declared, so these two constants are the complete list."""
CACHE_CONTROL: Final = "private, max-age=0, no-store"
"""Stored on the object and returned with it. A signed URL is a public URL for as long as
it lives, so no shared cache should keep a company document after it expires."""

NO_OVERWRITE: Final = "false"
"""`x-upsert`. Document ids are minted per upload, so an existing object at the same key
means two uploads collided and one is about to be lost: fail instead."""

API_URL_SCHEMES: Final = ("https://", "http://")
NOT_FOUND_STATUS: Final = 404


class StorageError(RuntimeError):
    """A Storage operation could not be performed. Never carries a key, URL or token."""


class ObjectNotFoundError(StorageError):
    """No such document *for this company*.

    Raised both when the object is missing and when the key belongs to someone else, and
    routers map it to **HTTP 404** in either case: a 403 on another company's document id
    would confirm that the document exists, which is the leak S2.2.2 is about. It is a
    `StorageError`, so a router that catches only the base class still catches it — but
    the 404 mapping has to be on this class, not on the base.
    """


@dataclass(frozen=True, slots=True)
class SignedUrl:
    """A download URL and when it stops working. `expires_at` is UTC and aware."""

    url: str
    expires_in: int
    expires_at: datetime


class StorageBucket(Protocol):
    """The three calls this module makes on a bucket, so the client is injectable.

    A Protocol rather than the concrete `SyncBucketProxy`: tests pass a fake, and the
    plan's "nothing is Supabase-specific except the JWKS URL and the Storage client" stays
    true of one file. `SyncBucketProxy` satisfies it structurally, which pyright checks at
    the one place a real client is built.
    """

    def upload(
        self, path: str, file: bytes, file_options: FileOptions | None = None
    ) -> object: ...

    def create_signed_url(self, path: str, expires_in: int) -> Mapping[str, Any]: ...

    def remove(self, paths: list[str]) -> object: ...


class _BucketSource(Protocol):
    def from_(self, bucket_id: str, /) -> StorageBucket: ...


class _StorageClient(Protocol):
    @property
    def storage(self) -> _BucketSource: ...


SupabaseClientFactory = Callable[[str, str], _StorageClient]
"""`create_client`'s shape. Injectable so that no test builds a real client."""

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def object_key(*, company_id: str, document_id: str, filename: str) -> str:
    """The one definition of where a company's document lives.

    Raises `StorageError` if either id is not identifier-shaped. The filename is not
    rejected but rewritten, because it is the one part a bidder chose.
    """
    company = _checked_identifier(company_id, "company_id")
    document = _checked_identifier(document_id, "document_id")
    return KEY_SEPARATOR.join((company, document, _safe_filename(filename)))


class CompanyDocumentStore:
    """Uploads and signs company documents, scoped to one bucket and one TTL.

    The TTL is re-checked here and not only in `settings.py`, because a router could
    construct this directly and the ten-minute cap is an acceptance criterion rather than
    a preference.
    """

    def __init__(
        self, bucket: StorageBucket, *, ttl_seconds: int, clock: Clock = _utc_now
    ) -> None:
        if not 0 < ttl_seconds <= MAX_SIGNED_URL_TTL_SECONDS:
            raise StorageError(
                f"ttl_seconds must be between 1 and {MAX_SIGNED_URL_TTL_SECONDS}: a "
                "document's signed URL has to expire within ten minutes (S2.2.2)"
            )
        self._bucket = bucket
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def upload(
        self,
        *,
        company_id: str,
        document_id: str,
        filename: str,
        content: bytes,
        content_type: str = DEFAULT_CONTENT_TYPE,
    ) -> str:
        """Store `content` under this company's prefix and return the key to persist.

        The key is built before anything else, so both ids are known to be
        identifier-shaped by the time a message names one.
        """
        key = object_key(company_id=company_id, document_id=document_id, filename=filename)
        if not content:
            raise StorageError(f"document {document_id} is empty, so there is nothing to store")

        options: FileOptions = {
            "content-type": content_type,
            "cache-control": CACHE_CONTROL,
            "x-upsert": NO_OVERWRITE,
        }
        try:
            self._bucket.upload(key, content, options)
        except StorageException as exc:
            # The document id is ours and safe to name; the key and the client's own
            # message are not repeated, so nothing about the bucket leaves the server.
            raise StorageError(
                f"document {document_id} could not be stored: Storage refused the upload"
            ) from exc
        return key

    def signed_url(self, *, company_id: str, key: str) -> SignedUrl:
        """A short-lived download URL for a key that belongs to `company_id`.

        Raises `ObjectNotFoundError` -- HTTP 404 -- when the key is not one this company
        could have, and when Storage says the object is gone.
        """
        own = _own_key(company_id, key)
        try:
            response = self._bucket.create_signed_url(own, self._ttl_seconds)
        except StorageException as exc:
            # Storage's own 404 becomes the router's 404. `status` is typed as either an
            # int or a string, so the comparison is made on the string form of both.
            if isinstance(exc, StorageApiError) and str(exc.status) == str(NOT_FOUND_STATUS):
                raise ObjectNotFoundError("no such document for this company") from exc
            raise StorageError("the document URL could not be signed") from exc

        return SignedUrl(
            url=_url_from(response),
            expires_in=self._ttl_seconds,
            expires_at=self._clock() + timedelta(seconds=self._ttl_seconds),
        )

    def remove(self, *, company_id: str, key: str) -> None:
        """Delete a key that belongs to `company_id`. Deleting twice is not an error.

        Raises `ObjectNotFoundError` when the key is not one this company could have, so a
        caller cannot delete across the tenant boundary by guessing a path, and
        `StorageError` when Storage refuses for any other reason -- the caller keeps the row
        in that case, because a row without its file is invisible and a file without its row
        is unreachable, and the second is the cheaper of the two to repair.

        **Storage answers 200 for a key it does not hold**, so "already gone" arrives here as
        success rather than as the 404 `signed_url` has to translate. That is the behaviour
        the router relies on to stay idempotent.
        """
        own = _own_key(company_id, key)
        try:
            self._bucket.remove([own])
        except StorageException as exc:
            if isinstance(exc, StorageApiError) and str(exc.status) == str(NOT_FOUND_STATUS):
                raise ObjectNotFoundError("no such document for this company") from exc
            raise StorageError("the document could not be deleted") from exc


def storage_bucket(
    settings: Settings, *, create: SupabaseClientFactory = create_client
) -> StorageBucket:
    """The configured private bucket. Builds a client; performs no request.

    `create` is the seam that keeps every test offline. Missing wiring is refused here
    rather than at startup because Storage is not mocked locally (project-plan,
    Environments): `make test` and the offline stories run with none of it set.
    """
    url = (settings.env.supabase_url or "").strip()
    secret = settings.env.supabase_service_role_key
    key = secret.get_secret_value().strip() if secret is not None else ""
    bucket = settings.env.supabase_storage_bucket.strip()

    unset = [
        name
        for name, value in (
            ("SUPABASE_URL", url),
            ("SUPABASE_SERVICE_KEY", key),
            ("SUPABASE_STORAGE_BUCKET", bucket),
        )
        if not value
    ]
    if unset:
        raise StorageError(
            f"{', '.join(unset)} is not set, so company documents cannot be stored. "
            "See infra/.env.example."
        )
    if not url.startswith(API_URL_SCHEMES):
        raise StorageError(
            "SUPABASE_URL must be the project's https:// API URL, not a database DSN or a "
            "bare host name. See infra/.env.example."
        )
    return create(url, key).storage.from_(bucket)


def company_document_store(
    settings: Settings, *, bucket: StorageBucket | None = None
) -> CompanyDocumentStore:
    """The store a router depends on: settings in, one wired object out.

    `bucket` is for tests and for a caller that already holds one; the TTL always comes
    from the settings, so there is no call site that can pick its own expiry.
    """
    return CompanyDocumentStore(
        storage_bucket(settings) if bucket is None else bucket,
        ttl_seconds=settings.env.signed_url_ttl_seconds,
    )


def _checked_identifier(value: str, name: str) -> str:
    """A company or document id, or `StorageError` naming the field but not the value."""
    if not _is_identifier(value):
        raise StorageError(
            f"{name} is not a valid identifier: it must be 1-64 characters of letters, "
            f"digits, '.', '_' or '-', starting with a letter or a digit (got "
            f"{len(value)} characters)"
        )
    return value


def _is_identifier(value: str) -> bool:
    return IDENTIFIER_PATTERN.fullmatch(value) is not None


def _safe_filename(filename: str) -> str:
    """The last path component of `filename`, reduced to characters safe in a key.

    Splitting on both separators first is what defeats traversal: `../../etc/passwd` and
    `..\\..\\win.ini` are basenames, and a Windows drive letter goes with the rest.
    """
    basename = re.split(r"[\\/]", filename)[-1]
    allowed = UNSAFE_FILENAME_CHARACTERS.sub("_", basename)
    trimmed = allowed.lstrip(LEADING_PUNCTUATION)[:MAX_FILENAME_CHARS]
    return trimmed or FALLBACK_FILENAME


def _own_key(company_id: str, key: str) -> str:
    """`key` if this module could have built it for `company_id`, else not found.

    Comparing against `object_key`'s own rules rather than a `startswith` check is what
    makes the guard total: a company id that merely *starts* the same, a segment count we
    never emit, and a filename we would have rewritten are all rejected, so the only keys
    that can be signed are the ones we wrote.
    """
    company = _checked_identifier(company_id, "company_id")
    segments = key.split(KEY_SEPARATOR)
    if (
        len(segments) == KEY_SEGMENTS
        and segments[0] == company
        and _is_identifier(segments[1])
        and _safe_filename(segments[2]) == segments[2]
    ):
        return key
    raise ObjectNotFoundError("no such document for this company")


def _url_from(response: Mapping[str, Any]) -> str:
    """The URL out of Storage's answer, which is external data like any other.

    The client returns the same value under two spellings and types both as optional, so
    "it answered" is not "it signed something". The message never quotes the response.
    """
    for name in ("signedURL", "signedUrl"):
        candidate = response.get(name)
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    raise StorageError("Storage returned no signed URL for the document")
