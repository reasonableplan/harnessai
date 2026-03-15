"""GitHub API 기반 GitService — issues, board, git ops."""
from __future__ import annotations

import subprocess
from typing import Any

import httpx

from src.core.config import AppConfig
from src.core.errors import GitServiceError
from src.core.logging.logger import get_logger
from src.core.resilience.api_retry import with_retry
from src.core.resilience.circuit_breaker import CircuitBreaker
from src.core.types import BoardIssue, IssueSpec

log = get_logger("GitService")

GH_API = "https://api.github.com"
GH_GRAPHQL = "https://api.github.com/graphql"


class GitService:
    def __init__(self, config: AppConfig) -> None:
        self._token = config.github_token
        self._owner = config.github_owner
        self._repo = config.github_repo
        self._project_number = config.github_project_number
        self._work_dir = config.git_work_dir
        self._circuit = CircuitBreaker("GitHub", failure_threshold=5, reset_timeout_ms=30_000)
        self._client = httpx.AsyncClient(timeout=30.0)
        # Board field cache
        self._project_id: str = ""
        self._status_field_id: str = ""
        self._status_options: dict[str, str] = {}  # column_name → option_id
        self._item_id_cache: dict[int, str] = {}   # issue_number → project item ID

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _rest(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{GH_API}{path}"
        async def _call():
            resp = await self._client.request(method, url, headers=self._headers(), **kwargs)
            if resp.status_code == 422:
                return resp.json()  # already exists — not an error
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        try:
            return await self._circuit.execute(lambda: with_retry(_call, label=f"GitHub {method} {path}"))
        except Exception as e:
            raise GitServiceError(f"{method} {path}", cause=e) from e

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        async def _call():
            resp = await self._client.post(
                GH_GRAPHQL,
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            if "errors" in data:
                raise GitServiceError(f"GraphQL errors: {data['errors']}")
            return data
        try:
            return await self._circuit.execute(lambda: with_retry(_call, label="GitHub GraphQL"))
        except Exception as e:
            raise GitServiceError("GraphQL", cause=e) from e

    async def validate_connection(self) -> None:
        await self._rest("GET", f"/repos/{self._owner}/{self._repo}")
        log.info("GitHub connection validated", owner=self._owner, repo=self._repo)

    # ===== Issues =====

    async def create_issue(self, spec: IssueSpec) -> int:
        data = await self._rest(
            "POST",
            f"/repos/{self._owner}/{self._repo}/issues",
            json={
                "title": spec.title,
                "body": spec.body,
                "labels": spec.labels,
                **({"milestone": spec.milestone} if spec.milestone else {}),
            },
        )
        return int(data["number"])

    async def update_issue(self, issue_number: int, updates: dict[str, Any]) -> None:
        await self._rest(
            "PATCH",
            f"/repos/{self._owner}/{self._repo}/issues/{issue_number}",
            json=updates,
        )

    async def close_issue(self, issue_number: int) -> None:
        await self.update_issue(issue_number, {"state": "closed"})

    async def get_issue(self, issue_number: int) -> BoardIssue:
        data = await self._rest("GET", f"/repos/{self._owner}/{self._repo}/issues/{issue_number}")
        return self._parse_issue(data, column="")

    async def get_issues_by_label(self, label: str) -> list[BoardIssue]:
        data = await self._rest(
            "GET",
            f"/repos/{self._owner}/{self._repo}/issues",
            params={"labels": label, "state": "open", "per_page": 100},
        )
        return [self._parse_issue(i, column="") for i in data]

    async def add_comment(self, issue_number: int, body: str) -> None:
        try:
            await self._rest(
                "POST",
                f"/repos/{self._owner}/{self._repo}/issues/{issue_number}/comments",
                json={"body": body},
            )
        except Exception as e:
            # non-fatal
            log.warn("Failed to add comment", issue=issue_number, err=str(e))

    # ===== Board =====

    async def get_all_project_items(self) -> list[BoardIssue]:
        if not self._project_number:
            return []
        query = """
        query($owner: String!, $number: Int!, $cursor: String) {
          organization(login: $owner) {
            projectV2(number: $number) {
              items(first: 100, after: $cursor) {
                nodes {
                  id
                  fieldValues(first: 10) {
                    nodes {
                      ... on ProjectV2ItemFieldSingleSelectValue {
                        name
                        field { ... on ProjectV2FieldCommon { name } }
                      }
                    }
                  }
                  content {
                    ... on Issue {
                      number title body labels(first: 10) { nodes { name } }
                      assignees(first: 1) { nodes { login } }
                    }
                  }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
        """
        items: list[BoardIssue] = []
        cursor = None
        while True:
            data = await self._graphql(query, {
                "owner": self._owner, "number": self._project_number, "cursor": cursor
            })
            project = (
                data.get("data", {})
                .get("organization", {})
                .get("projectV2", {})
            )
            if not project:
                break
            page = project["items"]
            for node in page["nodes"]:
                content = node.get("content", {})
                if not content or "number" not in content:
                    continue
                column = ""
                for fv in node.get("fieldValues", {}).get("nodes", []):
                    field = fv.get("field", {})
                    if field.get("name", "").lower() == "status":
                        column = fv.get("name", "")
                self._item_id_cache[content["number"]] = node["id"]
                items.append(BoardIssue(
                    issue_number=content["number"],
                    title=content["title"],
                    body=content.get("body", "") or "",
                    labels=[l["name"] for l in content.get("labels", {}).get("nodes", [])],
                    column=column,
                    assignee=(content.get("assignees", {}).get("nodes") or [{}])[0].get("login"),
                ))
            if not page["pageInfo"]["hasNextPage"]:
                break
            cursor = page["pageInfo"]["endCursor"]
        return items

    async def move_issue_to_column(self, issue_number: int, column: str) -> None:
        """Project V2 이슈의 Status 필드를 업데이트한다."""
        if not self._project_number:
            return

        await self._ensure_project_field_cache()

        option_id = self._status_options.get(column)
        if not option_id:
            log.warn("Column not found in project status options", column=column, available=list(self._status_options))
            return

        item_id = await self._get_project_item_id(issue_number)
        if not item_id:
            log.warn("Issue not found as project item", issue=issue_number)
            return

        await self._graphql(
            """
            mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $projectId
                itemId: $itemId
                fieldId: $fieldId
                value: { singleSelectOptionId: $optionId }
              }) {
                projectV2Item { id }
              }
            }
            """,
            {
                "projectId": self._project_id,
                "itemId": item_id,
                "fieldId": self._status_field_id,
                "optionId": option_id,
            },
        )
        log.info("Moved issue to column", issue=issue_number, column=column)

    async def _ensure_project_field_cache(self) -> None:
        """프로젝트 Status 필드 ID + 옵션 맵을 캐싱한다. 첫 호출 시만 쿼리."""
        if self._status_field_id:
            return

        data = await self._graphql(
            """
            query($owner: String!, $number: Int!) {
              organization(login: $owner) {
                projectV2(number: $number) {
                  id
                  fields(first: 20) {
                    nodes {
                      ... on ProjectV2SingleSelectField {
                        id
                        name
                        options { id name }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"owner": self._owner, "number": self._project_number},
        )
        project = (
            data.get("data", {})
            .get("organization", {})
            .get("projectV2", {})
        )
        self._project_id = project.get("id", "")
        for field in project.get("fields", {}).get("nodes", []):
            if field.get("name", "").lower() == "status":
                self._status_field_id = field["id"]
                self._status_options = {opt["name"]: opt["id"] for opt in field.get("options", [])}
                break

        if not self._status_field_id:
            raise GitServiceError("Status field not found in project")

    async def _get_project_item_id(self, issue_number: int) -> str | None:
        """이슈 번호로 Project V2 item ID를 조회한다. 캐싱 포함."""
        if issue_number in self._item_id_cache:
            return self._item_id_cache[issue_number]

        data = await self._graphql(
            """
            query($owner: String!, $repo: String!, $issueNumber: Int!) {
              repository(owner: $owner, name: $repo) {
                issue(number: $issueNumber) {
                  projectItems(first: 10) {
                    nodes {
                      id
                      project { ... on ProjectV2 { number } }
                    }
                  }
                }
              }
            }
            """,
            {"owner": self._owner, "repo": self._repo, "issueNumber": issue_number},
        )
        items = (
            data.get("data", {})
            .get("repository", {})
            .get("issue", {})
            .get("projectItems", {})
            .get("nodes", [])
        )
        for item in items:
            project = item.get("project", {})
            if project.get("number") == self._project_number:
                item_id = item["id"]
                self._item_id_cache[issue_number] = item_id
                return item_id
        return None

    async def get_epic_issues(self, epic_id: str) -> list[BoardIssue]:
        return await self.get_issues_by_label(f"epic:{epic_id}")

    # ===== Git Operations =====

    async def create_branch(self, branch_name: str, base_branch: str = "main") -> None:
        # 안전한 브랜치 이름 검증
        import re
        if not re.match(r'^[\w\-./]+$', branch_name):
            raise GitServiceError(f"Invalid branch name: {branch_name!r}")
        try:
            subprocess.run(
                ["git", "-C", self._work_dir, "checkout", "-b", branch_name, f"origin/{base_branch}"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as e:
            raise GitServiceError(f"create_branch {branch_name}", cause=RuntimeError(e.stderr)) from e

    async def create_pr(
        self,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        linked_issues: list[int] | None = None,
    ) -> int:
        full_body = body
        if linked_issues:
            closes = " ".join(f"Closes #{n}" for n in linked_issues)
            full_body = f"{body}\n\n{closes}"
        data = await self._rest(
            "POST",
            f"/repos/{self._owner}/{self._repo}/pulls",
            json={"title": title, "body": full_body, "head": head, "base": base},
        )
        return int(data["number"])

    # ===== Helpers =====

    def _parse_issue(self, data: dict, column: str) -> BoardIssue:
        labels = [l["name"] for l in data.get("labels", [])]
        return BoardIssue(
            issue_number=data["number"],
            title=data["title"],
            body=data.get("body", "") or "",
            labels=labels,
            column=column,
            assignee=data.get("assignee", {}).get("login") if data.get("assignee") else None,
        )
