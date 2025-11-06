"""SSRS SOAP helpers built on zeep."""
from __future__ import annotations

import os
from functools import lru_cache

from requests_ntlm import HttpNtlmAuth
from zeep import Client
from zeep.transports import Transport

from .config import get_settings


@lru_cache(maxsize=1)
def _client() -> Client:
    settings = get_settings()
    session = None
    user = os.getenv("DOMAIN_USER")
    password = os.getenv("DOMAIN_PASS")
    if user and password:
        import requests

        session = requests.Session()
        session.auth = HttpNtlmAuth(user, password)
    transport = Transport(session=session, timeout=15)
    return Client(settings.ssrs_soap_wsdl, transport=transport)


def upload_rdl(folder: str, name: str, rdl_bytes: bytes) -> dict:
    client = _client()
    result = client.service.CreateCatalogItem(
        ItemType="Report",
        Parent=folder,
        Name=name,
        Overwrite=True,
        Definition=rdl_bytes,
        Properties=[],
    )
    return {"path": result.Path, "id": result.ID}


def set_shared_datasource(item_path: str, ds_name: str, shared_path: str) -> None:
    client = _client()
    data_sources = [
        {
            "Name": ds_name,
            "Item": {"Reference": shared_path},
        }
    ]
    client.service.SetItemDataSources(ItemPath=item_path, DataSources=data_sources)
