from fastapi.testclient import TestClient

from app.main import create_app


def test_root_page_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ChatRobot_v3" in response.text
    assert "/static/app.js" in response.text
    assert 'id="workspaceStats" class="hero-stats hidden"' in response.text
    assert 'for="loginIdentifierInput"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'class="skip-link" href="#mainContent"' in response.text
    assert 'class="hero product-topbar"' in response.text
    assert 'class="workspace-sidebar"' in response.text
    assert 'id="workspaceOverview"' in response.text


def test_workspace_nav_switches_views_instead_of_scrolling() -> None:
    """Sidebar items must be real view switches, not anchors to adjacent
    regions of the same scroll container."""
    client = TestClient(create_app())
    page = client.get("/").text

    # Every nav entry drives a view, and every view has a panel to show.
    for view in ("overview", "knowledge", "documents", "chat"):
        assert f'data-view="{view}"' in page
        assert f'data-view-panel="{view}"' in page

    # The old same-page anchors must not come back.
    for dead_anchor in ('href="#knowledgePanel"', 'href="#documentsWorkspace"', 'href="#chatPanel"'):
        assert dead_anchor not in page

    # Documents is its own view, no longer nested inside the knowledge panel.
    assert page.index('id="knowledgePanel"') < page.index('id="documentsWorkspace"')
    assert 'class="panel panel-operations workspace-view" data-view-panel="documents"' in page

    # Active state is driven by script, so the button exposes a pressed state.
    assert 'aria-pressed="true"' in page
    assert 'id="navDocumentsBadge"' in page


def test_documents_view_can_switch_collection_without_leaving() -> None:
    """The documents view needs its own collection picker so users do not have
    to bounce back to the knowledge view just to change context."""
    client = TestClient(create_app())
    page = client.get("/").text

    assert 'id="documentsCollectionSelect"' in page
    # Both pickers exist and are separate controls that the script keeps in sync.
    assert 'id="collectionSelect"' in page
    assert page.index('id="collectionSelect"') != page.index('id="documentsCollectionSelect"')


def test_overview_carries_actions_and_activity() -> None:
    """Overview should offer work to do, not only summary counters."""
    client = TestClient(create_app())
    page = client.get("/").text

    assert 'id="workspaceActions"' in page
    assert 'id="recentActivityList"' in page
    assert 'id="workspaceRefreshButton"' in page


def test_register_page_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/register")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "register.js" in response.text
    assert 'for="registerStandaloneEmailInput"' in response.text
    assert 'autocomplete="new-password"' in response.text
    assert 'class="auth-product-panel register-product-panel"' in response.text


def test_evaluations_page_serves_frontend() -> None:
    client = TestClient(create_app())
    response = client.get("/evaluations")
    script_response = client.get("/static/evaluations.js")

    assert response.status_code == 200
    assert script_response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "RAG Evaluation" in response.text
    assert "/static/evaluations.js" in response.text
    assert 'id="evalHeroStats" class="hero-stats hidden"' in response.text
    assert 'for="evalDatasetSelect"' in response.text
    assert 'for="evalCollectionSelect"' in response.text
    assert 'id="evalCollectionSelect" aria-describedby="evalCollectionHint" required disabled' in response.text
    assert 'id="evalCollectionHint"' in response.text
    assert 'id="evalCollectionIdInput"' not in response.text
    assert 'id="evalRunProgress"' in response.text
    assert 'id="evalRunProgressBar"' in response.text
    assert 'class="workspace-app evaluation-app hidden"' in response.text
    assert 'id="evaluationOverview"' in response.text
    assert 'request(`${apiPrefix}/collections`)' in script_response.text
    assert "collection_id: state.selectedCollectionId" in script_response.text
    assert "已完成 ${task.completed_cases}/${task.total_cases}" in script_response.text
    assert "runs/${encodeURIComponent(taskId)}" in script_response.text
    assert "function getPrimaryMetricDisplay" in script_response.text
    assert "仅能测来源命中" in script_response.text
    assert "主检索指标不可测" in script_response.text
    assert "最近主指标" in response.text
    assert "最近 Recall@K" not in response.text
