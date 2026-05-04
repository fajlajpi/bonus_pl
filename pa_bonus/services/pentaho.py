"""
Pentaho CDA Integration Service
================================
Fetches unpaid invoice data from Pentaho Community Dashboard via its CDA API.

The external system uses HTTP Basic Authentication and exposes data through
a CDA (Community Data Access) endpoint that returns JSON.

Usage:
    from pa_bonus.services.pentaho import get_unpaid_invoices

    result = get_unpaid_invoices("CUSTOMER_CODE_123")
    if result["success"]:
        for invoice in result["invoices"]:
            print(invoice["invoice_number"], invoice["amount"])
    else:
        print(result["error"])
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class UnpaidInvoice:
    """Represents a single unpaid invoice returned from Pentaho."""
    invoice_number: str
    date_issued: datetime
    amount_excl_vat: float
    invoice_id: str

    @property
    def date_issued_formatted(self) -> str:
        """Return date in a human-readable format (d. M. YYYY)."""
        return self.date_issued.strftime("%-d. %-m. %Y") if self.date_issued else ""


def get_unpaid_invoices(customer_code: str) -> dict:
    """
    Fetch unpaid invoices for a given customer from the Pentaho CDA endpoint.

    Args:
        customer_code: The customer code (maps to User.user_number in Django).

    Returns:
        dict with keys:
            - success (bool): Whether the request succeeded.
            - invoices (list[UnpaidInvoice]): Parsed invoice objects (empty list if none).
            - total_rows (int): Number of unpaid invoices.
            - total_amount (float): Sum of all unpaid amounts.
            - error (str | None): Error message if the request failed.
    """
    # Validate configuration
    base_url = getattr(settings, "PENTAHO_BASE_URL", None)
    username = getattr(settings, "PENTAHO_USERNAME", None)
    password = getattr(settings, "PENTAHO_PASSWORD", None)

    if not all([base_url, username, password]):
        logger.error("Pentaho credentials not configured in settings.")
        return {
            "success": False,
            "invoices": [],
            "total_rows": 0,
            "total_amount": 0.0,
            "error": "Pentaho credentials are not configured. Check PENTAHO_* settings.",
        }

    # Build CDA query URL
    cda_path = getattr(
        settings,
        "PENTAHO_CDA_PATH",
        "/public/PAA/karta-klienta/karta klienta.cda",
    )
    data_access_id = getattr(settings, "PENTAHO_DATA_ACCESS_ID", "sqlFaktury")

    url = f"{base_url.rstrip('/')}/pentaho/plugin/cda/api/doQuery"
    params = {
        "path": cda_path,
        "dataAccessId": data_access_id,
        "paramparamKodZakaznika": customer_code,
    }

    try:
        response = requests.get(
            url,
            params=params,
            auth=(username, password),
            timeout=15,
            verify=True,  # Set to False only if the server uses a self-signed cert
        )
        response.raise_for_status()

    except requests.exceptions.Timeout:
        logger.warning("Pentaho request timed out for customer %s", customer_code)
        return _error_result("Request to Pentaho timed out. Please try again.")

    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to Pentaho at %s", base_url)
        return _error_result(f"Cannot connect to Pentaho server at {base_url}.")

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        if status == 401:
            logger.error("Pentaho authentication failed (401).")
            return _error_result("Authentication failed. Check Pentaho credentials.")
        logger.error("Pentaho HTTP error %s for customer %s", status, customer_code)
        return _error_result(f"Pentaho returned HTTP {status}.")

    except requests.exceptions.RequestException as e:
        logger.error("Pentaho request error: %s", e)
        return _error_result(f"Unexpected error contacting Pentaho: {e}")

    # Parse response
    try:
        data = response.json()
    except ValueError:
        logger.error("Pentaho returned non-JSON response for customer %s", customer_code)
        return _error_result("Pentaho returned an invalid response (not JSON).")

    return _parse_cda_response(data)


def _parse_cda_response(data: dict) -> dict:
    """
    Parse the Pentaho CDA JSON response into UnpaidInvoice objects.

    Expected format:
        {
            "queryInfo": {"totalRows": "2"},
            "resultset": [
                ["F1-5970/2026", "2026-04-07 00:00:00.0", 4577.66, "C43L600101"],
                ...
            ],
            "metadata": [
                {"colIndex": 0, "colType": "String", "colName": "cislo_faktury"},
                {"colIndex": 1, "colType": "Date", "colName": "datum_vystaveni"},
                {"colIndex": 2, "colType": "Numeric", "colName": "celkem_bez_dph"},
                {"colIndex": 3, "colType": "String", "colName": "id"}
            ]
        }
    """
    invoices = []

    resultset = data.get("resultset", [])
    for row in resultset:
        if len(row) < 4:
            logger.warning("Skipping malformed row: %s", row)
            continue

        # Parse date — Pentaho returns "2026-04-07 00:00:00.0"
        date_issued = _parse_pentaho_date(row[1])

        invoices.append(
            UnpaidInvoice(
                invoice_number=str(row[0]),
                date_issued=date_issued,
                amount_excl_vat=float(row[2]) if row[2] is not None else 0.0,
                invoice_id=str(row[3]),
            )
        )

    total_amount = sum(inv.amount_excl_vat for inv in invoices)

    return {
        "success": True,
        "invoices": invoices,
        "total_rows": len(invoices),
        "total_amount": total_amount,
        "error": None,
    }


def _parse_pentaho_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse a Pentaho date string like '2026-04-07 00:00:00.0' into a datetime."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except ValueError:
            continue
    logger.warning("Could not parse Pentaho date: %s", date_str)
    return None


def _error_result(message: str) -> dict:
    """Return a standardised error result dict."""
    return {
        "success": False,
        "invoices": [],
        "total_rows": 0,
        "total_amount": 0.0,
        "error": message,
    }