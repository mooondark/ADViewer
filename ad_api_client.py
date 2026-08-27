# -*- coding: utf-8 -*-
"""
ad_api_client.py
Couche de communication HTTP avec l'API Advance Design.

Contient :
  - AdvanceDesignApiClient : client HTTP (open_project, get_element_ids, get_results...)
  - Fonctions utilitaires internes : _check, _extract_diagnostics_text, _is_already_open_diagnostic
  - Wrappers module-level : get_api_client, open_project, close_project, get_element_ids, etc.

Dépend de viewer_config pour :
  - tr_err (messages d'erreur localisés)
  - ApiUnavailableError, ProjectAlreadyOpenError (exceptions)
  - normalize_windows_path (normalisation des chemins Windows)
"""

import socket
import urllib.parse

import requests

from viewer_config import (
    tr_err,
    ApiUnavailableError,
    ProjectAlreadyOpenError,
    normalize_windows_path,
)


# ======================================================================
#  Utilitaires internes de diagnostic
# ======================================================================

def _extract_diagnostics_text(details: dict) -> str:
    diagnostics = details.get("diagnostics", []) or []
    parts = []
    for d in diagnostics:
        sev = str(d.get("severity", "")).strip()
        code = str(d.get("code", "")).strip()
        msg = str(d.get("message", "")).strip()
        src = str(d.get("source", "")).strip()
        chunk = " | ".join(x for x in [sev, code, msg, src] if x)
        if chunk:
            parts.append(chunk)
    return " ; ".join(parts)


def _is_already_open_diagnostic(details: dict) -> bool:
    diagnostics = details.get("diagnostics", []) or []
    for d in diagnostics:
        code = str(d.get("code", "")).strip().lower()
        msg = str(d.get("message", "")).strip().lower()
        src = str(d.get("source", "")).strip().lower()
        blob = f"{code} {msg} {src}"
        if (
            "already open" in blob
            or "already opened" in blob
            or "deja ouvert" in blob
            or "déjà ouvert" in blob
            or "file is open" in blob
            or "project is open" in blob
            or "used by another process" in blob
            or "being used by another process" in blob
            or "cannot access the file" in blob
        ):
            return True
    return False


def _check(response: requests.Response, label: str) -> dict:
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        try:
            body = response.json()
        except Exception:
            body = response.text[:800]
        raise RuntimeError(
            tr_err("http_error", label=label, status=response.status_code, body=body)
        ) from e

    data = response.json()
    details = data.get("details", {}) or {}

    if not details.get("success", True):
        diag_text = _extract_diagnostics_text(details)

        if label == "OpenProject" and _is_already_open_diagnostic(details):
            raise ProjectAlreadyOpenError(
                tr_err("project_already_open", details=diag_text).strip()
            )

        raise RuntimeError(
            tr_err("api_failure", label=label, details=diag_text)
        )

    return data


# ======================================================================
#  Client API Advance Design
# ======================================================================

def check_port(host: str) -> None:
    AdvanceDesignApiClient(host).check_port()


class AdvanceDesignApiClient:
    def __init__(self, host: str):
        self.host = str(host or "").strip().rstrip("/")

    def _post(self, path: str, *, json_payload=None, params=None, timeout=30, label: str = "") -> dict:
        try:
            resp = requests.post(
                f"{self.host}{path}",
                json={} if json_payload is None else json_payload,
                params=params,
                timeout=timeout,
            )
        except requests.exceptions.RequestException as e:
            raise ApiUnavailableError(
                tr_err("api_contact_failed", host=self.host)
            ) from e
        return _check(resp, label or path)

    def check_port(self) -> None:
        parsed = urllib.parse.urlparse(self.host)
        hostname = parsed.hostname
        port = parsed.port
        if hostname is None:
            raise ApiUnavailableError(tr_err("invalid_api_url", host=self.host))
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((hostname, port))
        sock.close()

        if result != 0:
            raise ApiUnavailableError(
                tr_err("api_unreachable", hostname=hostname, port=port)
            )

    def open_project(self, fto_path: str) -> None:
        win_path = normalize_windows_path(fto_path)
        self._post(
            "/api/Model/management/OpenProject",
            params={"filename": win_path},
            json_payload={},
            timeout=30,
            label="OpenProject",
        )

    def close_project(self) -> bool:
        try:
            self._post(
                "/api/Model/management/CloseProject",
                json_payload={},
                timeout=15,
                label="CloseProject",
            )
            return True
        except (ApiUnavailableError, RuntimeError, requests.exceptions.RequestException):
            return False

    def close_session(self) -> bool:
        try:
            self._post(
                "/api/Model/management/CloseSession",
                json_payload={},
                timeout=15,
                label="CloseSession",
            )
            return True
        except (ApiUnavailableError, RuntimeError, requests.exceptions.RequestException):
            return False

    def get_element_ids(self, element_type: str) -> list:
        payload = [{
            "$type": "QueryElementsModel",
            "elementType": element_type
        }]
        return self._post(
            "/api/Model/elements/GetElementsID",
            json_payload=payload,
            timeout=30,
            label=f"GetElementsID({element_type})",
        ).get("data", [])

    def get_element_ids_for_types(self, element_types: list) -> list:
        """Récupère les EIDs pour plusieurs types d'éléments en une seule requête HTTP.

        L'API GetElementsID accepte un tableau de QueryElementsModel, ce qui
        permet d'envoyer N types en un seul appel au lieu de N appels séparés.
        Pour 4 types de supports (ex. PUNCTUAL_SUPPORT_TYPES), cela réduit le
        nombre de round-trips de 4 à 1.

        Si la liste est vide, retourne [] sans appel réseau.
        Si elle ne contient qu'un seul type, délègue à get_element_ids() pour
        conserver le label d'erreur précis.
        """
        if not element_types:
            return []
        if len(element_types) == 1:
            return self.get_element_ids(element_types[0])
        payload = [
            {"$type": "QueryElementsModel", "elementType": et}
            for et in element_types
        ]
        return self._post(
            "/api/Model/elements/GetElementsID",
            json_payload=payload,
            timeout=30,
            label=f"GetElementsID({', '.join(element_types)})",
        ).get("data", [])

    def get_elements_objects(self, ids: list) -> list:
        if not ids:
            return []
        return self._post(
            "/api/Model/elements/GetElementsObject",
            json_payload=ids,
            timeout=60,
            label="GetElementsObject",
        ).get("data", [])

    def get_materials(self, ids: list) -> list:
        if not ids:
            return []
        return self._post(
            "/api/Model/materials/GetMaterials",
            json_payload=ids,
            timeout=30,
            label="GetMaterials",
        ).get("data", [])

    def get_sections(self, ids: list) -> list:
        if not ids:
            return []
        return self._post(
            "/api/Model/sections/GetSections",
            json_payload=ids,
            timeout=30,
            label="GetSections",
        ).get("data", [])

    def get_informational_ids(self, info_type: str) -> list:
        payload = [{
            "$type": "QueryInfoModel",
            "informationalElementType": info_type
        }]
        return self._post(
            "/api/Model/elements/GetElementsID",
            json_payload=payload,
            timeout=30,
            label=f"GetElementsID({info_type})",
        ).get("data", [])

    def get_informational_elements_objects(self, ids: list) -> list:
        if not ids:
            return []
        return self._post(
            "/api/Model/elements/GetInformationalElementsObject",
            json_payload=ids,
            timeout=60,
            label="GetInformationalElementsObject",
        ).get("data", [])

    def get_results(self, result_type: str, analysis_case_id: int, element_ids: list) -> list:
        ids = [int(eid) for eid in (element_ids or []) if eid is not None]
        if not ids:
            return []
        return self._post(
            "/api/Model/analysis/GetResults",
            params={"eResType": result_type, "IDAnalysisCase": int(analysis_case_id)},
            json_payload=ids,
            timeout=60,
            label=f"GetResults({result_type})",
        ).get("data", []) or []


# ======================================================================
#  Wrappers module-level (interface procédurale)
# ======================================================================

def get_api_client(host: str) -> AdvanceDesignApiClient:
    return AdvanceDesignApiClient(host)


def open_project(host: str, fto_path: str) -> None:
    get_api_client(host).open_project(fto_path)


def close_project(host: str) -> bool:
    return get_api_client(host).close_project()


def close_session(host: str) -> bool:
    return get_api_client(host).close_session()


def get_element_ids(host: str, element_type: str) -> list:
    return get_api_client(host).get_element_ids(element_type)


def get_element_ids_for_types(host: str, element_types: list) -> list:
    return get_api_client(host).get_element_ids_for_types(element_types)


def get_elements_objects(host: str, ids: list) -> list:
    return get_api_client(host).get_elements_objects(ids)


def get_materials(host: str, ids: list) -> list:
    return get_api_client(host).get_materials(ids)


def get_sections(host: str, ids: list) -> list:
    return get_api_client(host).get_sections(ids)


def get_informational_ids(host: str, info_type: str) -> list:
    return get_api_client(host).get_informational_ids(info_type)


def get_informational_elements_objects(host: str, ids: list) -> list:
    return get_api_client(host).get_informational_elements_objects(ids)


def get_results(host: str, result_type: str, analysis_case_id: int, element_ids: list) -> list:
    return get_api_client(host).get_results(result_type, analysis_case_id, element_ids)
