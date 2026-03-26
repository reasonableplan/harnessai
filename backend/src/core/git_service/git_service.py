"""GitHub API 기반 GitService — issues, board, git ops."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
from typing import Any

import httpx

from src.core.config import AppConfig
from src.core.errors import GitServiceError, RateLimitError
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
        self._owner_gql_type: str = "user"         # "user" or "organization" — detected at startup
        self._field_cache_lock = asyncio.Lock()

    @property
    def work_dir(self) -> str:
        return self._work_dir

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
                body = resp.json()
                errors = body.get("errors", [])
                if any(
                    "already_exists" in str(e.get("message", ""))
                    or e.get("code") == "already_exists"
                    for e in errors
                ):
                    return body  # already exists — not an error
                resp.raise_for_status()  # 실제 validation 에러는 전파
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
                for err in data["errors"]:
                    if err.get("type") == "RATE_LIMITED":
                        raise RateLimitError("GitHub GraphQL")
                raise GitServiceError(f"GraphQL errors: {data['errors']}")
            return data
        try:
            return await self._circuit.execute(lambda: with_retry(_call, label="GitHub GraphQL"))
        except Exception as e:
            raise GitServiceError("GraphQL", cause=e) from e

    async def check_rate_limit(self) -> int:
        """GitHub API rate limit 잔여 횟수를 반환한다."""
        data = await self._rest("GET", "/rate_limit")
        return data.get("rate", {}).get("remaining", 0)

    def _project_owner_field(self) -> str:
        """GraphQL 쿼리에서 owner 타입 필드명을 반환한다 (user 또는 organization)."""
        return self._owner_gql_type

    def _extract_project(self, data: dict) -> dict:
        """GraphQL 응답에서 projectV2 데이터를 추출한다."""
        owner_data = data.get("data", {}).get(self._owner_gql_type, {})
        return owner_data.get("projectV2", {}) if owner_data else {}

    async def validate_connection(self) -> None:
        user_data = await self._rest("GET", f"/users/{self._owner}")
        self._owner_gql_type = "organization" if user_data.get("type") == "Organization" else "user"
        await self._rest("GET", f"/repos/{self._owner}/{self._repo}")
        log.info("GitHub connection validated", owner=self._owner, repo=self._repo, owner_type=self._owner_gql_type)

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
            log.warning("Failed to add comment", issue=issue_number, err=str(e))

    # ===== Board =====

    async def get_all_project_items(self) -> list[BoardIssue]:
        if not self._project_number:
            return []
        owner_type = self._project_owner_field()
        query = f"""
        query($owner: String!, $number: Int!, $cursor: String) {{
          {owner_type}(login: $owner) {{
            projectV2(number: $number) {{
              items(first: 100, after: $cursor) {{
                nodes {{
                  id
                  fieldValues(first: 10) {{
                    nodes {{
                      ... on ProjectV2ItemFieldSingleSelectValue {{
                        name
                        field {{ ... on ProjectV2FieldCommon {{ name }} }}
                      }}
                    }}
                  }}
                  content {{
                    ... on Issue {{
                      number title body labels(first: 10) {{ nodes {{ name }} }}
                      assignees(first: 1) {{ nodes {{ login }} }}
                    }}
                  }}
                }}
                pageInfo {{ hasNextPage endCursor }}
              }}
            }}
          }}
        }}
        """
        items: list[BoardIssue] = []
        cursor = None
        while True:
            data = await self._graphql(query, {
                "owner": self._owner, "number": self._project_number, "cursor": cursor
            })
            project = self._extract_project(data)
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
            raise GitServiceError(
                f"Column '{column}' not found in project status options: {list(self._status_options)}"
            )

        item_id = await self._get_project_item_id(issue_number)
        if not item_id:
            raise GitServiceError(
                f"Issue #{issue_number} not found as project item"
            )

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

        async with self._field_cache_lock:
            # double-check after lock
            if self._status_field_id:
                return

            owner_type = self._project_owner_field()
            data = await self._graphql(
                f"""
                query($owner: String!, $number: Int!) {{
                  {owner_type}(login: $owner) {{
                    projectV2(number: $number) {{
                      id
                      fields(first: 20) {{
                        nodes {{
                          ... on ProjectV2SingleSelectField {{
                            id
                            name
                            options {{ id name }}
                          }}
                        }}
                      }}
                    }}
                  }}
                }}
                """,
                {"owner": self._owner, "number": self._project_number},
            )
            project = self._extract_project(data)
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

    # ===== Project Board Management =====

    async def add_issue_to_project(self, issue_number: int, column: str = "Backlog") -> str:
        """이슈를 Project V2에 추가하고 지정 컬럼으로 이동한다. item_id를 반환한다."""
        await self._ensure_project_field_cache()

        # 이슈의 node ID 조회
        data = await self._graphql(
            """
            query($owner: String!, $repo: String!, $number: Int!) {
              repository(owner: $owner, name: $repo) {
                issue(number: $number) { id }
              }
            }
            """,
            {"owner": self._owner, "repo": self._repo, "number": issue_number},
        )
        content_id = (
            data.get("data", {}).get("repository", {}).get("issue", {}).get("id")
        )
        if not content_id:
            raise GitServiceError(f"Issue #{issue_number} not found in repository")

        # 프로젝트에 추가
        result = await self._graphql(
            """
            mutation($projectId: ID!, $contentId: ID!) {
              addProjectV2ItemById(input: {
                projectId: $projectId, contentId: $contentId
              }) { item { id } }
            }
            """,
            {"projectId": self._project_id, "contentId": content_id},
        )
        item_id = result.get("data", {}).get("addProjectV2ItemById", {}).get("item", {}).get("id", "")
        if not item_id:
            raise GitServiceError(f"Failed to add issue #{issue_number} to project")

        self._item_id_cache[issue_number] = item_id

        # 컬럼 설정
        option_id = self._status_options.get(column)
        if option_id:
            await self._graphql(
                """
                mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
                  updateProjectV2ItemFieldValue(input: {
                    projectId: $projectId, itemId: $itemId, fieldId: $fieldId,
                    value: { singleSelectOptionId: $optionId }
                  }) { projectV2Item { id } }
                }
                """,
                {
                    "projectId": self._project_id,
                    "itemId": item_id,
                    "fieldId": self._status_field_id,
                    "optionId": option_id,
                },
            )
        log.info("Added issue to project", issue=issue_number, column=column)
        return item_id

    async def link_sub_issue(self, parent_issue_number: int, child_issue_number: int) -> None:
        """자식 이슈를 부모 이슈의 서브이슈로 연결한다."""
        # 부모/자식 node ID 조회
        data = await self._graphql(
            """
            query($owner: String!, $repo: String!, $parent: Int!, $child: Int!) {
              repository(owner: $owner, name: $repo) {
                parent: issue(number: $parent) { id }
                child: issue(number: $child) { id }
              }
            }
            """,
            {
                "owner": self._owner, "repo": self._repo,
                "parent": parent_issue_number, "child": child_issue_number,
            },
        )
        repo = data.get("data", {}).get("repository", {})
        parent_id = repo.get("parent", {}).get("id")
        child_id = repo.get("child", {}).get("id")
        if not parent_id or not child_id:
            log.warning("Sub-issue link: issue not found",
                        parent=parent_issue_number, child=child_issue_number)
            return

        await self._graphql(
            """
            mutation($parentId: ID!, $childId: ID!) {
              addSubIssue(input: { issueId: $parentId, subIssueId: $childId }) {
                issue { id }
              }
            }
            """,
            {"parentId": parent_id, "childId": child_id},
        )
        log.debug("Linked sub-issue", parent=parent_issue_number, child=child_issue_number)

    async def ensure_label(self, label: str, color: str = "ededed") -> None:
        """라벨이 없으면 생성한다. 이미 있으면 무시."""
        try:
            await self._rest(
                "POST",
                f"/repos/{self._owner}/{self._repo}/labels",
                json={"name": label, "color": color},
            )
        except Exception as e:
            log.warning("ensure_label failed", label=label, err=str(e))

    # add_comment의 alias (호환성 유지)
    add_issue_comment = add_comment

    # ===== Worktree Management =====

    async def create_worktree(self, task_id: str, branch_name: str) -> str:
        """태스크용 독립 worktree를 생성한다.

        main 최신 상태에서 브랜치를 만들어 격리된 작업 공간을 제공한다.
        동시에 여러 에이전트가 작업해도 파일 간섭이 없다.

        Returns: worktree 절대 경로
        """
        # task_id를 짧은 해시로 변환 (Windows 경로 길이 제한 대응)
        short_id = task_id[:8]
        safe_branch = re.sub(r'[^a-zA-Z0-9\-]', '-', branch_name)[:40].strip('-')
        worktree_name = f"{safe_branch}-{short_id}"
        worktree_path = os.path.join(self._work_dir, ".worktrees", worktree_name)

        # .worktrees 디렉토리 생성
        os.makedirs(os.path.join(self._work_dir, ".worktrees"), exist_ok=True)

        # main 최신화
        try:
            await self._run_git("fetch", "origin", "main")
        except GitServiceError:
            pass  # offline이면 현재 main 기준

        # 기존 worktree/브랜치 정리 (재시도 시 충돌 방지)
        full_branch = f"wt/{worktree_name}"
        if os.path.isdir(worktree_path):
            await self.remove_worktree(task_id, worktree_name)
        else:
            # 디렉토리 없어도 고아 브랜치가 남아있을 수 있음
            try:
                await self._run_git("branch", "-D", full_branch)
            except GitServiceError:
                pass
        try:
            await self._run_git(
                "worktree", "add", worktree_path,
                "-b", full_branch, "origin/main",
            )
        except GitServiceError:
            # 첫 시도 실패 시 브랜치가 부분 생성됐을 수 있음 → 정리
            try:
                await self._run_git("branch", "-D", full_branch)
            except GitServiceError:
                pass
            # origin/main이 없는 경우 (빈 repo) → HEAD 기반
            await self._run_git(
                "worktree", "add", worktree_path,
                "-b", full_branch,
            )

        log.info("Worktree created",
                 task_id=task_id, path=worktree_path, branch=full_branch)
        return worktree_path

    async def remove_worktree(
        self, task_id: str, worktree_name: str | None = None,
    ) -> None:
        """태스크 worktree를 정리한다 (디렉토리 + 브랜치)."""
        if worktree_name is None:
            short_id = task_id[:8]
            # 정확한 이름을 모르면 패턴으로 찾기 (suffix 매칭으로 오삭제 방지)
            worktrees_dir = os.path.join(self._work_dir, ".worktrees")
            if os.path.isdir(worktrees_dir):
                for name in os.listdir(worktrees_dir):
                    if name.endswith(f"-{short_id}"):
                        worktree_name = name
                        break
            if worktree_name is None:
                return

        worktree_path = os.path.join(self._work_dir, ".worktrees", worktree_name)
        branch_name = f"wt/{worktree_name}"

        # worktree 제거
        try:
            await self._run_git("worktree", "remove", worktree_path, "--force")
        except GitServiceError:
            # git worktree remove 실패 시 디렉토리 직접 삭제
            if os.path.isdir(worktree_path):
                shutil.rmtree(worktree_path, ignore_errors=True)
            try:
                await self._run_git("worktree", "prune")
            except GitServiceError:
                pass

        # 브랜치 정리
        try:
            await self._run_git("branch", "-D", branch_name)
        except GitServiceError:
            pass  # 이미 삭제됨

        log.info("Worktree removed", task_id=task_id, path=worktree_path)

    async def cleanup_orphan_worktrees(self) -> None:
        """시스템 시작 시 이전 세션에서 남은 orphan worktree를 정리한다.

        3단계:
        1. .git/worktrees 레지스트리에서 실제 디렉토리 없는 항목 삭제
        2. git worktree prune 실행
        3. 모든 wt/ 브랜치를 삭제 (활성 worktree가 아닌 것만)
        """
        worktrees_dir = os.path.join(self._work_dir, ".worktrees")
        git_worktrees_dir = os.path.join(self._work_dir, ".git", "worktrees")

        # Step 1: .git/worktrees 레지스트리에서 실제 디렉토리 없는 항목 삭제
        if os.path.isdir(git_worktrees_dir):
            for name in os.listdir(git_worktrees_dir):
                reg_path = os.path.join(git_worktrees_dir, name)
                if not os.path.isdir(reg_path):
                    continue
                wt_path = os.path.join(worktrees_dir, name) if os.path.isdir(worktrees_dir) else ""
                if not os.path.isdir(wt_path):
                    shutil.rmtree(reg_path, ignore_errors=True)
                    log.info("Removed orphan worktree registry", name=name)

        # Step 2: git worktree prune
        try:
            await self._run_git("worktree", "prune")
        except GitServiceError:
            pass

        # Step 3: 모든 wt/ 브랜치 정리 (활성 worktree 제외)
        try:
            branch_output = await self._run_git("branch", "--list", "wt/*")
            for line in branch_output.split("\n"):
                branch = line.strip().lstrip("* +")
                if not branch:
                    continue
                try:
                    await self._run_git("branch", "-D", branch)
                    log.info("Orphan branch deleted", branch=branch)
                except GitServiceError:
                    pass  # 활성 worktree에서 사용 중이면 삭제 불가 — 정상
        except GitServiceError:
            pass

        # Step 4: .worktrees 디렉토리 내 orphan 디렉토리 삭제
        if os.path.isdir(worktrees_dir):
            active_paths: set[str] = set()
            try:
                wt_list = await self._run_git("worktree", "list", "--porcelain")
                for line in wt_list.split("\n"):
                    if line.startswith("worktree "):
                        active_paths.add(os.path.normpath(line[9:].strip()))
            except GitServiceError:
                pass
            for name in os.listdir(worktrees_dir):
                full_path = os.path.join(worktrees_dir, name)
                if os.path.isdir(full_path) and os.path.normpath(full_path) not in active_paths:
                    shutil.rmtree(full_path, ignore_errors=True)
                    log.info("Removed orphan worktree dir", path=full_path)

        # 고아 브랜치 정리 (wt/ 접두사)
        try:
            branches_output = await self._run_git("branch", "--list", "wt/*")
            for line in branches_output.strip().split("\n"):
                branch = line.strip().lstrip("* ")
                if branch.startswith("wt/"):
                    try:
                        await self._run_git("branch", "-D", branch)
                    except GitServiceError:
                        pass
        except GitServiceError:
            pass

    async def run_git_in_worktree(
        self, worktree_path: str, *args: str, timeout_s: float = 60.0,
    ) -> str:
        """특정 worktree에서 git 명령을 실행한다."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", worktree_path,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise GitServiceError(f"git {args[0] if args else ''} timed out in worktree")
        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            err_msg = err_msg.replace(self._token, "***")
            raise GitServiceError(f"git {' '.join(args)} in worktree: {err_msg}")
        return stdout.decode().strip()

    # ===== Git Operations =====

    async def _run_git(self, *args: str, timeout_s: float = 60.0) -> str:
        """workspace에서 git 명령을 실행한다. 인증은 gh credential helper가 처리."""
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", self._work_dir,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise GitServiceError(f"git {args[0] if args else ''} timed out after {timeout_s}s")
        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            err_msg = err_msg.replace(self._token, "***")
            raise GitServiceError(f"git {' '.join(args)}: {err_msg}")
        return stdout.decode().strip()

    async def init_workspace(self) -> None:
        """workspace를 target repo의 클론으로 초기화한다. 이미 올바른 클론이면 pull만."""
        import shutil as _shutil

        repo_url = f"https://github.com/{self._owner}/{self._repo}.git"
        git_dir = os.path.join(self._work_dir, ".git")

        # workspace에 유효한 .git이 없으면 삭제 후 재클론
        # (불완전/부재 .git 상태에서 git 명령 실행 시 부모 repo의 .git을 오염시킴)
        head_file = os.path.join(git_dir, "HEAD")
        if os.path.isdir(self._work_dir) and not os.path.isfile(head_file):
            _shutil.rmtree(self._work_dir, ignore_errors=True)
            log.info("Removed workspace with invalid/missing .git", path=self._work_dir)

        if os.path.isfile(head_file):
            # 이미 git repo — remote 확인 후 pull
            try:
                remote = await self._run_git("remote", "get-url", "origin")
                if self._repo not in remote:
                    # 다른 repo를 가리키고 있으면 remote 교체 (토큰 미포함 URL)
                    await self._run_git("remote", "set-url", "origin", repo_url)
                    log.info("Workspace remote updated", repo=f"{self._owner}/{self._repo}")
                # 최신 상태로 pull (빈 repo면 실패할 수 있음)
                try:
                    await self._run_git("pull", "--rebase", "origin", "main")
                except GitServiceError:
                    log.debug("Pull failed (empty repo or no main branch yet)")
            except GitServiceError as e:
                log.warning("Workspace git check failed, re-cloning", err=str(e))
                shutil.rmtree(self._work_dir, ignore_errors=True)
                await self._clone_repo()
        else:
            await self._clone_repo()

        # .worktrees를 git 추적에서 제외
        if os.path.isdir(self._work_dir):
            gitignore_path = os.path.join(self._work_dir, ".gitignore")
            gitignore_entry = ".worktrees/\n"
            if os.path.isfile(gitignore_path):
                content = open(gitignore_path).read()
                if ".worktrees" not in content:
                    with open(gitignore_path, "a") as f:
                        f.write(f"\n{gitignore_entry}")
            else:
                with open(gitignore_path, "w") as f:
                    f.write(gitignore_entry)

        log.info("Workspace initialized", path=self._work_dir, repo=f"{self._owner}/{self._repo}")

    async def _clone_repo(self) -> None:
        """repo를 workspace 경로로 클론한다. 인증은 gh credential helper가 처리."""
        repo_url = f"https://github.com/{self._owner}/{self._repo}.git"
        os.makedirs(self._work_dir, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone", repo_url, self._work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            err_msg = stderr.decode().strip()
            err_msg = err_msg.replace(self._token, "***")
            # 빈 repo 경고는 정상
            if "empty repository" not in err_msg.lower():
                raise GitServiceError(f"git clone failed: {err_msg}")
            # 빈 repo: clone이 부분 생성했을 수 있으므로 상태 확인 후 init
            git_dir = os.path.join(self._work_dir, ".git")
            if not os.path.isdir(git_dir):
                await self._run_git("init")
            try:
                await self._run_git("remote", "set-url", "origin", repo_url)
            except GitServiceError:
                await self._run_git("remote", "add", "origin", repo_url)

    async def commit_all(self, message: str) -> bool:
        """workspace의 모든 변경사항을 commit한다. 변경이 없으면 False 반환."""
        await self._run_git("add", "-A")
        # .worktrees가 stage되지 않도록 안전장치
        try:
            await self._run_git("reset", "HEAD", "--", ".worktrees")
        except GitServiceError:
            pass
        # 변경사항 확인
        try:
            await self._run_git("diff", "--cached", "--quiet")
            return False  # 변경 없음
        except GitServiceError:
            pass  # diff --quiet는 변경이 있으면 exit 1
        await self._run_git("commit", "-m", message)
        log.info("Committed changes", message=message[:80])
        return True

    async def push(self, branch: str = "main") -> None:
        """workspace의 변경사항을 remote에 push한다."""
        await self._run_git("push", "-u", "origin", branch, timeout_s=120.0)
        log.info("Pushed to remote", branch=branch)

    async def commit_and_push(self, message: str, branch: str = "main") -> bool:
        """commit + push를 한 번에. 변경이 없으면 False."""
        committed = await self.commit_all(message)
        if committed:
            await self.push(branch)
        return committed

    async def commit_and_pr(
        self, message: str, issue_number: int | None = None,
    ) -> int | None:
        """branch 생성 → commit → push → PR 생성 → merge. PR 번호 반환.

        변경이 없으면 None. 머지 충돌 시 rebase 재시도 (최대 2회).
        """
        safe_title = re.sub(r'[^a-zA-Z0-9]', '-', message)[:40].strip('-')
        branch_name = f"feat/{safe_title}-{issue_number or 'task'}"

        # 변경사항을 먼저 stash (checkout 시 유실 방지)
        await self._run_git("add", "-A")
        try:
            await self._run_git("reset", "HEAD", "--", ".worktrees")
        except GitServiceError:
            pass
        try:
            await self._run_git("stash", "--include-untracked")
            stashed = True
        except GitServiceError:
            stashed = False

        # main 최신 상태로
        try:
            await self._run_git("checkout", "main")
            await self._run_git("pull", "--rebase", "origin", "main")
        except GitServiceError:
            pass

        # 브랜치 생성 + stash 복원 + commit (기존 브랜치 있으면 로컬+리모트 삭제 후 재생성)
        try:
            await self._run_git("branch", "-D", branch_name)
        except GitServiceError:
            pass
        try:
            await self._run_git("push", "origin", "--delete", branch_name)
        except GitServiceError:
            pass
        await self._run_git("checkout", "-b", branch_name)
        if stashed:
            try:
                await self._run_git("stash", "pop")
            except GitServiceError as e:
                log.error("Stash pop failed, work may be in stash", branch=branch_name, err=str(e))
                try:
                    await self._run_git("checkout", "main")
                except GitServiceError:
                    pass
                raise
        committed = await self.commit_all(message)
        if not committed:
            await self._run_git("checkout", "main")
            return None

        # main과 rebase (충돌 감지 + 해결 시도)
        try:
            await self._run_git("fetch", "origin", "main")
            await self._run_git("rebase", "origin/main")
        except GitServiceError as e:
            if "conflict" in str(e).lower() or "CONFLICT" in str(e):
                log.warning("Merge conflict detected, aborting rebase", branch=branch_name)
                try:
                    await self._run_git("rebase", "--abort")
                except GitServiceError:
                    pass
                # 충돌 시 main으로 복귀, 브랜치 삭제
                await self._run_git("checkout", "main")
                try:
                    await self._run_git("branch", "-D", branch_name)
                except GitServiceError:
                    pass
                raise GitServiceError(f"Merge conflict on branch {branch_name}. Task needs retry.")
            # 충돌이 아닌 다른 에러는 무시하고 진행

        # push + PR 생성
        await self.push(branch_name)
        linked = [issue_number] if issue_number else None
        pr_number = await self.create_pr(
            title=message,
            body=f"자동 생성된 PR\n\n이슈: #{issue_number or 'N/A'}",
            head=branch_name,
            base="main",
            linked_issues=linked,
        )
        log.info("PR created", pr=pr_number, branch=branch_name)

        # 자동 머지
        try:
            await self._rest(
                "PUT",
                f"/repos/{self._owner}/{self._repo}/pulls/{pr_number}/merge",
                json={"merge_method": "squash"},
            )
            log.info("PR merged", pr=pr_number)
        except Exception as e:
            log.warning("PR auto-merge failed", pr=pr_number, err=str(e))

        # main으로 복귀 + 최신화
        await self._run_git("checkout", "main")
        try:
            await self._run_git("pull", "--rebase", "origin", "main")
        except GitServiceError:
            pass

        return pr_number

    async def create_branch(self, branch_name: str, base_branch: str = "main") -> None:
        # 안전한 브랜치 이름 검증 (.. 차단으로 path traversal 방지)
        for name in (branch_name, base_branch):
            if not re.match(r'^[\w\-./]+$', name) or '..' in name:
                raise GitServiceError(f"Invalid branch name: {name!r}")
        await self._run_git("checkout", "-b", branch_name, f"origin/{base_branch}")

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
