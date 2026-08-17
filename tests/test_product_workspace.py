from imperaos.artifacts.rpc_protocol import ArtifactRpcMethod, RpcPrincipal, RpcRequest
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService
from imperaos.product_workspace import ProductWorkspaceService, ProductWorkspaceStore


def test_workspace_project_task_and_message_are_durable_and_scoped(tmp_path):
    service = ProductWorkspaceService(ProductWorkspaceStore(tmp_path / "product.sqlite3"))
    project = service.create_project("workspace-a", "Launch")
    task = service.create_task("workspace-a", project.project_id, "Prepare release", "session-a")
    service.add_message("workspace-a", task.task_id, "user", "Prepare release")
    link = service.add_link("workspace-a", task.task_id, "artifact", "artifact-a")
    service.set_preference("workspace-a", "operator-a", "shell", '{"theme":"dark"}')
    assert service.list_projects("workspace-a")[0].project_id == project.project_id
    assert (
        service.list_tasks("workspace-a", project.project_id)[0].assistant_session_id == "session-a"
    )
    assert service.list_projects("workspace-b") == []
    assert link.target_id == "artifact-a"
    assert (
        service.get_preference("workspace-a", "operator-a", "shell").value_json
        == '{"theme":"dark"}'
    )
    try:
        service.create_task("workspace-b", project.project_id, "Escape")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-workspace project access must be denied")


def test_projects_keep_pin_archive_order_and_pagination_after_restart(tmp_path):
    database = tmp_path / "product.sqlite3"
    service = ProductWorkspaceService(ProductWorkspaceStore(database))
    first = service.create_project("workspace-a", "First")
    second = service.create_project("workspace-a", "Second")
    third = service.create_project("workspace-a", "Third")

    service.update_project(
        "workspace-a", second.project_id, pinned=True, manual_order=10
    )
    service.update_project(
        "workspace-a", third.project_id, pinned=True, manual_order=1
    )
    service.archive_project("workspace-a", first.project_id, "completed")

    reopened = ProductWorkspaceService(ProductWorkspaceStore(database))
    active_page = reopened.list_project_page(
        "workspace-a", limit=1, sort="manual", status="active"
    )
    assert [project.project_id for project in active_page.projects] == [third.project_id]
    assert active_page.next_cursor is not None

    second_page = reopened.list_project_page(
        "workspace-a", cursor=active_page.next_cursor, limit=1, sort="manual", status="active"
    )
    assert [project.project_id for project in second_page.projects] == [second.project_id]
    assert second_page.next_cursor is None
    assert second_page.projects[0].pinned is True
    assert second_page.projects[0].manual_order == 10
    archived = reopened.list_project_page("workspace-a", status="archived")
    assert archived.projects[0].project_id == first.project_id


def test_project_registration_never_persists_or_returns_its_folder_ticket(tmp_path):
    service = ProductWorkspaceService(ProductWorkspaceStore(tmp_path / "product.sqlite3"))

    project = service.register_project(
        "workspace-a", "folder-ticket-opaque-123", "Release workspace"
    )

    assert project.root_ref.startswith("root-")
    assert project.root_display_name == "Release workspace"
    assert "folder-ticket-opaque-123" not in project.model_dump_json(by_alias=True)


def test_task_runtime_options_and_cancelled_status_survive_restart(tmp_path):
    database = tmp_path / "product.sqlite3"
    service = ProductWorkspaceService(ProductWorkspaceStore(database))
    project = service.create_project("workspace-a", "Release")
    task = service.create_task(
        "workspace-a",
        project.project_id,
        "Prepare release",
        "session-a",
        runtime_options={
            "reasoningEffort": "high",
            "speedProfile": "fast",
            "approvalProfile": "always_ask",
        },
    )
    assert task.reasoning_effort == "high"
    assert task.speed_profile == "fast"
    assert task.approval_profile == "always_ask"

    updated = service.update_task(
        "workspace-a",
        task.task_id,
        status="cancelled",
        runtime_options={"reasoningEffort": "very_high"},
    )
    assert updated.status == "cancelled"
    assert updated.reasoning_effort == "very_high"
    assert updated.speed_profile == "fast"

    reopened = ProductWorkspaceService(ProductWorkspaceStore(database))
    restored = reopened.list_tasks("workspace-a", project.project_id)[0]
    assert restored.status == "cancelled"
    assert restored.approval_profile == "always_ask"


def test_task_get_is_workspace_scoped_for_durable_route_hydration(tmp_path):
    service = ProductWorkspaceService(ProductWorkspaceStore(tmp_path / "product.sqlite3"))
    project = service.create_project("workspace-a", "Release")
    task = service.create_task("workspace-a", project.project_id, "Prepare release", "session-a")

    restored = service.get_task("workspace-a", task.task_id)

    assert restored.task_id == task.task_id
    try:
        service.get_task("workspace-b", task.task_id)
    except PermissionError:
        pass
    else:
        raise AssertionError("task lookup must not cross a workspace boundary")


def test_tasks_keep_pin_priority_order_and_archive_metadata_after_restart(tmp_path):
    database = tmp_path / "product.sqlite3"
    service = ProductWorkspaceService(ProductWorkspaceStore(database))
    project = service.create_project("workspace-a", "Release")
    first = service.create_task("workspace-a", project.project_id, "First", "session-a")
    second = service.create_task("workspace-a", project.project_id, "Second", "session-b")

    updated = service.update_task(
        "workspace-a",
        second.task_id,
        pinned=True,
        priority=7,
        manual_order=1,
    )
    archived = service.archive_task("workspace-a", first.task_id, "completed from task list")

    assert updated.pinned is True
    assert updated.priority == 7
    assert updated.manual_order == 1
    assert archived.status == "archived"
    assert archived.archived_at_utc is not None

    reopened = ProductWorkspaceService(ProductWorkspaceStore(database))
    restored = reopened.list_tasks("workspace-a", project.project_id)
    assert [task.task_id for task in restored] == [second.task_id, first.task_id]
    assert restored[0].pinned is True
    assert restored[1].archived_at_utc is not None


def test_project_list_rpc_respects_the_bounded_page_contract(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    server.product_workspace.create_project("workspace-a", "First")
    server.product_workspace.create_project("workspace-a", "Second")

    response = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-page-1",
            method=ArtifactRpcMethod.PROJECT_LIST,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            params={"limit": 1, "status": "active", "sort": "manual"},
        )
    )

    assert response.ok
    assert len(response.result["projects"]) == 1
    assert response.result["nextCursor"] is not None


def test_project_register_update_and_archive_are_workspace_scoped_rpc_mutations(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    principal = RpcPrincipal(principalId="operator-a", principalType="user")
    registered = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-register-1",
            method=ArtifactRpcMethod.PROJECT_REGISTER,
            workspaceId="workspace-a",
            principal=principal,
            idempotencyKey="project-register-1",
            params={
                "folderTicket": "folder-ticket-opaque-123",
                "name": "Release workspace",
                "idempotencyKey": "project-register-1",
            },
        )
    )
    assert registered.ok
    assert registered.result["rootRef"].startswith("root-")
    assert "folder-ticket-opaque-123" not in str(registered.result)

    updated = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-update-1",
            method=ArtifactRpcMethod.PROJECT_UPDATE,
            workspaceId="workspace-a",
            principal=principal,
            idempotencyKey="project-update-1",
            params={
                "projectId": registered.result["projectId"],
                "pinned": True,
                "manualOrder": 4,
                "idempotencyKey": "project-update-1",
            },
        )
    )
    assert updated.ok
    assert updated.result["pinned"] is True
    assert updated.result["manualOrder"] == 4

    archived = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-archive-1",
            method=ArtifactRpcMethod.PROJECT_ARCHIVE,
            workspaceId="workspace-a",
            principal=principal,
            idempotencyKey="project-archive-1",
            params={
                "projectId": registered.result["projectId"],
                "reason": "completed",
                "idempotencyKey": "project-archive-1",
            },
        )
    )
    assert archived.ok
    assert archived.result["status"] == "archived"
    assert archived.result["archivedAtUtc"] is not None


def test_task_create_rpc_carries_typed_runtime_options(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    project = server.product_workspace.create_project("workspace-a", "Release")
    response = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="task-create-runtime-1",
            method=ArtifactRpcMethod.TASK_CREATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            idempotencyKey="task-create-runtime-1",
            params={
                "projectId": project.project_id,
                "title": "Prepare release",
                "assistantSessionId": "session-a",
                "runtime": {
                    "reasoningEffort": "high",
                    "speedProfile": "fast",
                    "approvalProfile": "always_ask",
                },
                "idempotencyKey": "task-create-runtime-1",
            },
        )
    )
    assert response.ok
    assert response.result["reasoningEffort"] == "high"
    assert response.result["speedProfile"] == "fast"
    assert response.result["approvalProfile"] == "always_ask"

    cancelled = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="task-update-runtime-1",
            method=ArtifactRpcMethod.TASK_UPDATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            idempotencyKey="task-update-runtime-1",
            params={
                "taskId": response.result["taskId"],
                "status": "cancelled",
                "idempotencyKey": "task-update-runtime-1",
            },
        )
    )
    assert cancelled.ok
    assert cancelled.result["status"] == "cancelled"


def test_task_get_and_archive_rpc_keep_workspace_scope_and_archive_reason(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    principal = RpcPrincipal(principalId="operator-a", principalType="user")
    project = server.product_workspace.create_project("workspace-a", "Release")
    task = server.product_workspace.create_task(
        "workspace-a", project.project_id, "Prepare release", "session-a"
    )

    fetched = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="task-get-1",
            method=ArtifactRpcMethod.TASK_GET,
            workspaceId="workspace-a",
            principal=principal,
            params={"taskId": task.task_id},
        )
    )
    archived = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="task-archive-1",
            method=ArtifactRpcMethod.TASK_ARCHIVE,
            workspaceId="workspace-a",
            principal=principal,
            idempotencyKey="task-archive-1",
            params={
                "taskId": task.task_id,
                "reason": "completed from task list",
                "idempotencyKey": "task-archive-1",
            },
        )
    )

    assert fetched.ok
    assert fetched.result["taskId"] == task.task_id
    assert archived.ok
    assert archived.result["status"] == "archived"
    assert archived.result["archivedAtUtc"] is not None


def test_task_links_are_listed_through_the_workspace_scoped_rpc(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    principal = RpcPrincipal(principalId="operator-a", principalType="user")
    project = server.product_workspace.create_project("workspace-a", "Release")
    task = server.product_workspace.create_task(
        "workspace-a", project.project_id, "Prepare release", "session-a"
    )
    server.product_workspace.add_link("workspace-a", task.task_id, "artifact", "artifact-release")

    listed = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="task-link-list-1",
            method=ArtifactRpcMethod.TASK_LINK_LIST,
            workspaceId="workspace-a",
            principal=principal,
            params={"taskId": task.task_id},
        )
    )

    assert listed.ok
    assert listed.result["links"] == [
        {
            "linkId": listed.result["links"][0]["linkId"],
            "workspaceId": "workspace-a",
            "taskId": task.task_id,
            "targetType": "artifact",
            "targetId": "artifact-release",
            "createdAtUtc": listed.result["links"][0]["createdAtUtc"],
        }
    ]


def test_product_workspace_rpc_reuses_the_artifact_sidecar(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    response = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-create-1",
            method=ArtifactRpcMethod.PROJECT_CREATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            idempotencyKey="project-create-1",
            params={"title": "Launch", "idempotencyKey": "project-create-1"},
        )
    )
    assert response.ok
    project_id = response.result["projectId"]
    listed = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-list-1",
            method=ArtifactRpcMethod.PROJECT_LIST,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            params={},
        )
    )
    assert listed.result["projects"][0]["projectId"] == project_id


def test_product_workspace_mutations_require_bound_keys_and_replay_retries(tmp_path):
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    missing_key = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-create-missing-key",
            method=ArtifactRpcMethod.PROJECT_CREATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            params={"title": "Launch"},
        )
    )
    assert not missing_key.ok
    assert missing_key.error.code == "ARTIFACT_RPC_PROTOCOL_MISMATCH"

    first = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-create-retry-1",
            method=ArtifactRpcMethod.PROJECT_CREATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            idempotencyKey="project-create-retry",
            params={"title": "Launch", "idempotencyKey": "project-create-retry"},
        )
    )
    replay = server.handle_request(
        RpcRequest(
            contractVersion="1.0",
            requestId="project-create-retry-2",
            method=ArtifactRpcMethod.PROJECT_CREATE,
            workspaceId="workspace-a",
            principal=RpcPrincipal(principalId="operator-a", principalType="user"),
            idempotencyKey="project-create-retry",
            params={"title": "Launch", "idempotencyKey": "project-create-retry"},
        )
    )
    assert first.ok and replay.ok
    assert first.result["projectId"] == replay.result["projectId"]
    assert len(server.product_workspace.list_projects("workspace-a")) == 1
