"""ClinicalTrials.gov client.

Two surfaces, and the difference between them is the whole project.

`/api/v2` is the documented, keyless, versioned API. It serves the registry as
it stands today and it is authoritative for anything currently public. It also
cannot answer the question this project asks: its search index admits a trial
only once that trial's results have been posted, so a results record under
review is not findable through it by any query. Measured 2026-08-30 -- the
counts of records carrying a submit date, a QC date and a post date are all
79,892, and none of 120 sampled completed-but-unposted trials carried a submit
date.

`/api/int` is the route the registry's own website uses to render a record's
revision history. It is undocumented, and it is the only public way to see what
a record looked like on a past date. The same route is used by `cthist`, an R
package written for peer-reviewed research on registry histories, so this is an
established method rather than a trick. Two consequences follow, and both are
honoured here: call it politely, and cache every version on first sight, because
an undocumented endpoint may be withdrawn and a version already stored is one we
never have to ask for again.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, Iterator

from .http import Http

BASE_V2 = "https://clinicaltrials.gov/api/v2"
BASE_INT = "https://clinicaltrials.gov/api/int"

# The fields the collector needs. Requesting whole records for every study would
# multiply the bytes by roughly forty, for data we do not read.
STATUS_FIELDS = (
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.statusModule",
    "protocolSection.sponsorCollaboratorsModule.leadSponsor",
    "protocolSection.designModule.studyType",
    "hasResults",
)


@dataclass(frozen=True)
class Version:
    """One entry in a record's revision history.

    `module_labels` names which sections changed at this version. It is the
    cheap signal: it says a results section moved without our having to download
    the record to find out.
    """

    nct_id: str
    version: int
    version_date: dt.date
    status: str | None
    module_labels: tuple[str, ...]

    @property
    def touched_results(self) -> bool:
        return any("Results" in label for label in self.module_labels)


class CtGov:
    def __init__(self, http: Http) -> None:
        self.http = http

    # -- documented API ------------------------------------------------------

    def data_timestamp(self) -> dict[str, Any]:
        """The registry's own statement of how fresh it is.

        Observed to move once a day around 09:00 UTC. The collector records it
        on every run rather than trusting that, because a source that stops
        refreshing while still answering 200 is the failure that looks like
        success.
        """
        return self.http.get_json(f"{BASE_V2}/version")

    def search(
        self,
        *,
        query_term: str | None = None,
        page_size: int = 1000,
        fields: tuple[str, ...] = STATUS_FIELDS,
        max_pages: int | None = None,
        **filters: str,
    ) -> Iterator[dict[str, Any]]:
        """Page through a search, yielding study records."""
        params: dict[str, Any] = {
            "pageSize": page_size,
            "fields": ",".join(fields),
        }
        if query_term:
            params["query.term"] = query_term
        params.update(filters)

        token: str | None = None
        pages = 0
        while True:
            page = dict(params)
            if token:
                page["pageToken"] = token
            data = self.http.get_json(f"{BASE_V2}/studies", **page)
            for study in data.get("studies", []):
                yield study
            token = data.get("nextPageToken")
            pages += 1
            if not token or (max_pages is not None and pages >= max_pages):
                return

    def count(self, *, query_term: str | None = None, **filters: str) -> int:
        """The registry's own count for a filter. Gate 2 marks us against this."""
        params: dict[str, Any] = {
            "pageSize": 1,
            "countTotal": "true",
            "fields": "protocolSection.identificationModule.nctId",
        }
        if query_term:
            params["query.term"] = query_term
        params.update(filters)
        return int(self.http.get_json(f"{BASE_V2}/studies", **params)["totalCount"])

    def study(self, nct_id: str) -> dict[str, Any]:
        return self.http.get_json(f"{BASE_V2}/studies/{nct_id}", fields=",".join(STATUS_FIELDS))

    # -- undocumented history route -----------------------------------------

    def history(self, nct_id: str) -> list[Version]:
        """Every revision of a record, as metadata only.

        Cheap: a few kilobytes regardless of how large the record itself is.
        """
        data = self.http.get_json(f"{BASE_INT}/studies/{nct_id}/history")
        out: list[Version] = []
        for change in data.get("changes", []):
            try:
                when = dt.date.fromisoformat(change["date"])
            except (KeyError, TypeError, ValueError):
                continue
            out.append(
                Version(
                    nct_id=nct_id,
                    version=int(change["version"]),
                    version_date=when,
                    status=change.get("status"),
                    module_labels=tuple(change.get("moduleLabels") or ()),
                )
            )
        return out

    def version(self, nct_id: str, version: int) -> dict[str, Any]:
        """The full record as it stood at one revision.

        This is the point-in-time primitive. Everything the project claims about
        what was knowable on a past date is ultimately a claim about what this
        returns.
        """
        return self.http.get_json(f"{BASE_INT}/studies/{nct_id}/history/{version}")


def parse_date(value: str | None) -> tuple[dt.date | None, bool]:
    """Parse a registry date. Returns (date, is_partial).

    The registry publishes some dates to month precision. PREREGISTRATION.md
    fixes the convention -- a month resolves to its first day -- and requires
    anything derived from a partial date to be flagged rather than silently
    pooled with day-precision values. The flag is the second element, and
    callers are expected to carry it.
    """
    if not value:
        return None, False
    parts = value.split("-")
    try:
        if len(parts) == 3:
            return dt.date(int(parts[0]), int(parts[1]), int(parts[2])), False
        if len(parts) == 2:
            return dt.date(int(parts[0]), int(parts[1]), 1), True
        if len(parts) == 1:
            return dt.date(int(parts[0]), 1, 1), True
    except ValueError:
        return None, False
    return None, False


def status_dates(study: dict[str, Any]) -> dict[str, Any]:
    """Pull the dates this project turns on out of a study record."""
    protocol = study.get("protocolSection") or {}
    status = protocol.get("statusModule") or {}
    ident = protocol.get("identificationModule") or {}
    sponsor = (protocol.get("sponsorCollaboratorsModule") or {}).get("leadSponsor") or {}

    submit, submit_partial = parse_date(status.get("resultsFirstSubmitDate"))
    post, post_partial = parse_date((status.get("resultsFirstPostDateStruct") or {}).get("date"))
    primary_completion, pc_partial = parse_date(
        (status.get("primaryCompletionDateStruct") or {}).get("date")
    )

    return {
        "nct_id": ident.get("nctId"),
        "brief_title": ident.get("briefTitle"),
        "lead_sponsor": sponsor.get("name"),
        "sponsor_class": sponsor.get("class"),
        "overall_status": status.get("overallStatus"),
        "results_first_submit": submit,
        "results_first_post": post,
        "primary_completion": primary_completion,
        "primary_completion_type": (status.get("primaryCompletionDateStruct") or {}).get("type"),
        "has_partial_date": submit_partial or post_partial or pc_partial,
        "has_results": bool(study.get("hasResults")),
    }


def wait_days(dates: dict[str, Any]) -> int | None:
    """The quantity the project is about, in whole days.

    Returns None when the trial has not both submitted and posted. A negative
    result is returned as-is: PREREGISTRATION.md requires negative waits to be
    excluded and counted as anomalies by the caller, never clamped to zero,
    because a clamp moves the median in a known direction.
    """
    submit, post = dates.get("results_first_submit"), dates.get("results_first_post")
    if not submit or not post:
        return None
    return (post - submit).days
