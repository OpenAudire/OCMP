"""Tests for the framework pack import API: preview, confirm, limits and templates."""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import framework_packs
from app.core.config import Settings
from app.models import AuditLog, Framework, FrameworkItem, TagList
from app.models.framework import FrameworkStatus
from tests.test_curriculum_edit_api import sign_in

API = "/api/v1/framework-packs"
JSON = {"content-type": "application/json"}


def pack(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "metadata": {"key": "api-pack", "name": "API pack", "version": "1", "publisher": "Tests"},
        "items": [
            {"code": "A", "title": "A", "order": 1},
            {"code": "A.1", "title": "A.1", "parent_code": "A"},
            {"code": "B", "title": "B", "order": 2},
        ],
    }
    data.update(overrides)
    return data


async def preview(client: AsyncClient, data: Any) -> dict[str, Any]:
    body = data if isinstance(data, bytes) else json.dumps(data).encode()
    response = await client.post(f"{API}/preview", content=body, headers=JSON)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("POST", "/preview"),
            ("POST", "/import"),
            ("GET", "/templates"),
            ("GET", "/templates/graduate-attributes"),
        ],
    )
    async def test_requires_sign_in(self, api_client: AsyncClient, method: str, path: str) -> None:
        response = await api_client.request(method, f"{API}{path}", json={})
        assert response.status_code == 401

    @pytest.mark.parametrize(
        ("method", "path"),
        [("POST", "/preview"), ("POST", "/import"), ("GET", "/templates")],
    )
    async def test_needs_framework_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
        method: str,
        path: str,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, None)

        response = await api_client.request(method, f"{API}{path}", json={"token": "x" * 12})

        assert response.status_code == 403


class TestPreviewAndImport:
    @pytest.fixture(autouse=True)
    async def office(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")

    async def test_valid_pack_previews_then_imports(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        result = await preview(api_client, pack())

        assert result["valid"] is True
        assert result["errors"] == []
        assert result["token"]
        assert result["counts"]["items"] == 3
        assert result["counts"]["levels"] == 2
        assert result["counts"]["root_items"] == 2
        assert [i["code"] for i in result["sample"]] == ["A", "A.1", "B"]
        # Nothing is saved by a preview.
        assert await db_session.scalar(select(func.count()).select_from(Framework)) == 0

        response = await api_client.post(
            f"{API}/import", json={"token": result["token"], "activate": True}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["items"] == 3
        assert body["status"] == FrameworkStatus.ACTIVE.value
        assert await db_session.scalar(select(func.count()).select_from(FrameworkItem)) == 3
        audited = await db_session.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.context["operation"].astext == "framework.import"
            )
        )
        assert audited and audited >= 4  # framework and items, labelled

    async def test_import_without_activating_leaves_a_draft(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        token = (await preview(api_client, pack()))["token"]

        response = await api_client.post(f"{API}/import", json={"token": token})

        assert response.json()["status"] == "draft"

    async def test_token_works_once(self, api_client: AsyncClient) -> None:
        token = (await preview(api_client, pack()))["token"]
        assert (await api_client.post(f"{API}/import", json={"token": token})).status_code == 201

        again = await api_client.post(f"{API}/import", json={"token": token})

        assert again.status_code == 404

    async def test_unknown_token(self, api_client: AsyncClient) -> None:
        response = await api_client.post(f"{API}/import", json={"token": "n" * 20})
        assert response.status_code == 404

    async def test_someone_elses_token_is_refused(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
    ) -> None:
        token = (await preview(api_client, pack()))["token"]
        other = await sign_in(api_client, db_session, test_settings, "platform_admin")
        assert other.email == "platform_admin@example.org"

        response = await api_client.post(f"{API}/import", json={"token": token})

        assert response.status_code == 404

    async def test_version_imported_meanwhile_is_refused(self, api_client: AsyncClient) -> None:
        first = (await preview(api_client, pack()))["token"]
        second = (await preview(api_client, pack()))["token"]
        assert (await api_client.post(f"{API}/import", json={"token": first})).status_code == 201

        response = await api_client.post(f"{API}/import", json={"token": second})

        assert response.status_code == 422  # the re-check reports the version as taken

    async def test_already_imported_version_is_an_error_in_the_preview(
        self, api_client: AsyncClient
    ) -> None:
        token = (await preview(api_client, pack()))["token"]
        await api_client.post(f"{API}/import", json={"token": token})

        result = await preview(api_client, pack())

        assert result["valid"] is False
        assert result["token"] is None
        assert "already imported" in result["errors"][0]["message"]

    async def test_other_versions_are_a_warning(self, api_client: AsyncClient) -> None:
        token = (await preview(api_client, pack()))["token"]
        await api_client.post(f"{API}/import", json={"token": token})
        newer = pack()
        newer["metadata"]["version"] = "2"

        result = await preview(api_client, newer)

        assert result["valid"] is True
        assert "Other versions" in result["warnings"][0]

    async def test_every_problem_is_listed(self, api_client: AsyncClient) -> None:
        data = pack(
            items=[{"code": "A", "title": ""}, {"code": "B", "title": "B", "parent_code": "Z"}]
        )
        data["metadata"]["key"] = "Bad Key"

        result = await preview(api_client, data)

        assert result["valid"] is False
        paths = {e["path"] for e in result["errors"]}
        assert {"metadata.key", "items[0].title"} <= paths

    async def test_semantic_problems_come_with_a_location(self, api_client: AsyncClient) -> None:
        data = pack(items=[{"code": "B", "title": "B", "parent_code": "Z"}])

        result = await preview(api_client, data)

        assert result["errors"] == [
            {"path": "items[0].parent_code", "message": "Item 'B' has an unknown parent 'Z'."}
        ]

    @pytest.mark.parametrize(
        ("body", "message"),
        [
            (b"", "empty"),
            (b"{not json", "not valid JSON"),
            (b"\xff\xfe\x00", "UTF-8"),
            (b"[1]", "JSON object"),
        ],
    )
    async def test_bad_files(self, api_client: AsyncClient, body: bytes, message: str) -> None:
        result = await preview(api_client, body)

        assert result["valid"] is False
        assert message in result["errors"][0]["message"]

    async def test_json_error_names_line_and_column(self, api_client: AsyncClient) -> None:
        result = await preview(api_client, b'{\n  "metadata": ,\n}')

        assert "line 2" in result["errors"][0]["message"]

    async def test_a_file_with_a_byte_order_mark_is_read(self, api_client: AsyncClient) -> None:
        result = await preview(api_client, b"\xef\xbb\xbf" + json.dumps(pack()).encode())

        assert result["valid"] is True

    async def test_too_large_a_file_is_refused(
        self, api_client: AsyncClient, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(test_settings, "pack_max_upload_mb", 1)
        big = json.dumps(pack(), indent=0).encode() + b" " * (1024 * 1024 + 1)

        response = await api_client.post(f"{API}/preview", content=big, headers=JSON)

        assert response.status_code == 413
        assert "1 MB" in response.json()["detail"]

    async def test_too_many_items_is_refused(
        self, api_client: AsyncClient, test_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(test_settings, "pack_max_items", 2)

        result = await preview(api_client, pack())

        assert result["valid"] is False
        assert "PACK_MAX_ITEMS" in result["errors"][0]["message"]

    async def test_template_cannot_be_imported(self, api_client: AsyncClient) -> None:
        data = pack()
        data["metadata"]["template"] = True

        result = await preview(api_client, data)

        assert result["valid"] is False
        assert result["metadata"]["template"] is True
        assert "blank template" in result["errors"][0]["message"]

    async def test_shipped_templates_preview_as_blank_templates(
        self, api_client: AsyncClient
    ) -> None:
        listing = await api_client.get(f"{API}/templates")
        assert listing.status_code == 200
        assert {t["name"] for t in listing.json()} == {
            "hpcsa-core-competencies",
            "nqf-level-descriptors",
            "graduate-attributes",
            "mesh-subset",
        }
        download = await api_client.get(f"{API}/templates/nqf-level-descriptors")
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]

        result = await preview(api_client, download.content)

        assert result["valid"] is False
        assert result["counts"]["items"] == 10

    async def test_unknown_template(self, api_client: AsyncClient) -> None:
        assert (await api_client.get(f"{API}/templates/nope")).status_code == 404
        assert (await api_client.get(f"{API}/templates/..%2Fsecret")).status_code == 404

    async def test_format_two_pack_with_tag_lists_and_references(
        self, api_client: AsyncClient, db_session: AsyncSession
    ) -> None:
        base = (await preview(api_client, pack()))["token"]
        await api_client.post(f"{API}/import", json={"token": base})
        newer = pack(
            format_version=2,
            cross_references=[
                {"from_code": "A", "to_code": "B", "type": "related", "to_framework": "api-pack"}
            ],
            crosswalks=[
                {
                    "from_version": "1",
                    "entries": [{"type": "equivalent", "from_code": "A", "to_code": "A"}],
                }
            ],
            tag_lists=[{"key": "pack-tags", "name": "Pack tags", "values": [{"label": "One"}]}],
        )
        newer["metadata"]["version"] = "2"

        result = await preview(api_client, newer)

        assert result["valid"] is True
        assert result["counts"]["external_references"] == 1
        assert result["counts"]["crosswalk_entries"] == 1
        assert result["counts"]["tag_values"] == 1
        response = await api_client.post(f"{API}/import", json={"token": result["token"]})
        assert response.status_code == 201
        body = response.json()
        assert (body["crosswalks"], body["tag_lists_created"], body["external_references"]) == (
            1,
            1,
            1,
        )
        assert await db_session.scalar(select(func.count()).select_from(TagList)) == 1

    async def test_preview_rate_limit(
        self, api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(framework_packs, "PREVIEWS_PER_MINUTE", 2)
        for _ in range(2):
            await preview(api_client, pack())

        response = await api_client.post(f"{API}/preview", json=pack())

        assert response.status_code == 429


class TestTagListPermission:
    async def test_tag_lists_need_the_tag_list_permission(
        self,
        api_client: AsyncClient,
        db_session: AsyncSession,
        test_settings: Settings,
        system_roles: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await sign_in(api_client, db_session, test_settings, "curriculum_office")
        data = pack(
            format_version=2,
            tag_lists=[{"key": "t", "name": "T", "values": [{"label": "x"}]}],
        )
        assert (await preview(api_client, data))["valid"] is True

        async def refuse(*_args: object) -> bool:
            return False

        monkeypatch.setattr(framework_packs, "has_permission", refuse)
        result = await preview(api_client, data)

        assert result["valid"] is False
        assert result["errors"][0]["path"] == "tag_lists"
