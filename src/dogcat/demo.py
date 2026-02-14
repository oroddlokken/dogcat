"""Demo issue generation for dogcat.

Creates a realistic set of issues that look like a proper team with a PO, PM,
and developers has worked on it. Includes descriptions, notes, acceptance
criteria, close reasons, labels, external references, and comments.

Uses the same code paths as the CLI: IDGenerator for realistic hash-based IDs,
reference validation for parents and dependencies, and the same comment-adding
logic as ``dcat comment add``.

Team members:
- alice@example.com - Product Owner
- bob@example.com - Project Manager
- charlie@example.com - Tech Lead
- diana@example.com, eve@example.com - Senior Developers
- frank@example.com, grace@example.com, henry@example.com - Developers
- igor@example.com - QA Lead
- jack@example.com - DevOps Engineer
- kate@example.com, liam@example.com - Junior Developers
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dogcat.config import get_issue_prefix
from dogcat.idgen import IDGenerator
from dogcat.models import Comment, Issue, IssueType, Status

if TYPE_CHECKING:
    from dogcat.storage import JSONLStorage


def _add_comment(
    storage: JSONLStorage,
    issue_id: str,
    author: str,
    text: str,
) -> None:
    """Add a comment to an issue, mirroring the ``dcat comment add`` code path.

    Uses the same comment-ID format ({issue_id}-c{n}) and append-then-update
    logic that the CLI command uses.
    """
    issue = storage.get(issue_id)
    if issue is None:
        msg = f"Issue {issue_id} not found"
        raise ValueError(msg)
    n = len(issue.comments) + 1
    new_comment = Comment(
        id=f"{issue_id}-c{n}",
        issue_id=issue.full_id,
        author=author,
        text=text,
    )
    issue.comments.append(new_comment)
    storage.update(issue_id, {"comments": issue.comments})


def generate_demo_issues(storage: JSONLStorage, dogcats_dir: str) -> list[str]:
    """Generate demo issues for testing and exploration.

    Creates ~50 sample issues including epics, features, tasks, bugs, and stories
    with various priorities, parent-child relationships, dependencies, labels,
    external references, comments, and other metadata.

    Uses the same code paths as the CLI:
    - IDGenerator for realistic hash-based IDs (not sequential)
    - Reference validation for parents, duplicate_of, and dependency targets
    - Comment-ID format matching ``dcat comment add`` ({issue_id}-c{n})
    - Close/delete flows matching ``dcat close`` and ``dcat delete``

    Args:
        storage: The storage instance to create issues in
        dogcats_dir: Path to .dogcats directory (used to derive issue prefix)

    Returns:
        List of created full issue IDs
    """
    namespace = get_issue_prefix(dogcats_dir)
    idgen = IDGenerator(existing_ids=storage.get_issue_ids(), prefix=namespace)
    created_ids: list[str] = []

    def _create(title: str, **kwargs: Any) -> str:
        """Create an issue with IDGenerator (same ID generation as ``dcat create``)."""
        issue_id = idgen.generate_issue_id(title, namespace=namespace)

        # Validate parent reference (same as CLI)
        if "parent" in kwargs and kwargs["parent"] is not None:
            resolved = storage.resolve_id(kwargs["parent"])
            if resolved is None:
                msg = f"Parent issue {kwargs['parent']} not found"
                raise ValueError(msg)
            kwargs["parent"] = resolved

        # Validate duplicate_of reference (same as CLI)
        if "duplicate_of" in kwargs and kwargs["duplicate_of"] is not None:
            resolved = storage.resolve_id(kwargs["duplicate_of"])
            if resolved is None:
                msg = f"Duplicate target {kwargs['duplicate_of']} not found"
                raise ValueError(msg)
            kwargs["duplicate_of"] = resolved

        issue = Issue(id=issue_id, namespace=namespace, title=title, **kwargs)
        storage.create(issue)
        created_ids.append(issue.full_id)
        return issue.full_id

    def _close(issue_id: str, reason: str, *, closed_by: str) -> None:
        """Close an issue (same as ``dcat close``)."""
        storage.close(issue_id, reason)
        storage.update(issue_id, {"closed_by": closed_by})

    def _delete(issue_id: str, reason: str, *, deleted_by: str) -> None:
        """Tombstone an issue (same as ``dcat delete``)."""
        storage.delete(issue_id, reason)
        storage.update(issue_id, {"deleted_by": deleted_by})

    def _comment(issue_id: str, author: str, text: str) -> None:
        """Add a comment (same as ``dcat comment add``)."""
        _add_comment(storage, issue_id, author, text)

    def _dep(issue_id: str, depends_on: str) -> None:
        """Add a dependency with validation (same as ``dcat dep add``)."""
        resolved_issue = storage.resolve_id(issue_id)
        if resolved_issue is None:
            msg = f"Issue {issue_id} not found"
            raise ValueError(msg)
        resolved_dep = storage.resolve_id(depends_on)
        if resolved_dep is None:
            msg = f"Dependency target {depends_on} not found"
            raise ValueError(msg)
        storage.add_dependency(resolved_issue, resolved_dep, "blocks")

    def _update(issue_id: str, updates: dict[str, Any], *, updated_by: str) -> None:
        """Update fields on an issue (generates event log entries)."""
        storage.update(issue_id, {**updates, "updated_by": updated_by})

    # =========================================================================
    # Epic 1: Platform Modernization
    # =========================================================================
    epic1_id = _create(
        "Platform Modernization Initiative",
        description=(
            "Modernize the platform architecture and infrastructure to improve "
            "scalability, maintainability, and deployment efficiency. This is a "
            "critical multi-quarter initiative that will fundamentally change how "
            "our systems operate.\n\n"
            "Key objectives:\n"
            "- Migrate from monolith to microservices\n"
            "- Implement CI/CD pipelines\n"
            "- Improve observability and monitoring\n"
            "- Reduce deployment time from hours to minutes"
        ),
        design=(
            "## Architecture Overview\n\n"
            "The platform will be decomposed into the following services:\n"
            "- **User Service** - Authentication, authorization, user management\n"
            "- **Order Service** - Order processing, fulfillment\n"
            "- **Inventory Service** - Stock management, reservations\n"
            "- **Notification Service** - Email, SMS, push notifications\n\n"
            "Communication: gRPC for internal, REST for external APIs\n"
            "Data: Each service owns its database (PostgreSQL)\n"
            "Events: Kafka for async communication"
        ),
        notes=(
            "Initiated after Q1 performance review. Expected to take 4-6 months "
            "with potential for phased rollout. Budget approved by leadership."
        ),
        priority=0,
        issue_type=IssueType.EPIC,
        labels=["infrastructure", "strategic", "q1-2026", "backend"],
        external_ref="PLAT-100",
        created_by="alice@example.com",
    )
    _update(epic1_id, {"owner": "charlie@example.com"}, updated_by="bob@example.com")
    _update(epic1_id, {"status": "in_progress"}, updated_by="charlie@example.com")
    _comment(
        epic1_id,
        "alice@example.com",
        "Kickoff meeting scheduled for Monday. "
        "Please review the design doc beforehand.",
    )
    _comment(
        epic1_id,
        "charlie@example.com",
        "Design doc looks solid. I have some questions about the "
        "Kafka setup - let's discuss in the meeting.",
    )
    _comment(
        epic1_id,
        "bob@example.com",
        "Added this to the Q1 roadmap. Stakeholders are aligned on timeline.",
    )

    # Feature 1.1: Microservices migration
    feature1_id = _create(
        "Migrate to microservices architecture",
        description=(
            "Break monolith into scalable microservices. This involves decomposing "
            "the application into domain-driven services that can be developed and "
            "deployed independently.\n\n"
            "Phase 1: Extract User Service\n"
            "Phase 2: Extract Order Service\n"
            "Phase 3: Extract remaining services"
        ),
        acceptance=(
            "- Service boundaries clearly documented\n"
            "- Service communication via well-defined APIs\n"
            "- Deployment pipeline supports independent service rollout\n"
            "- Documentation complete with architecture diagrams\n"
            "- Zero downtime during migration"
        ),
        notes=(
            "Started with architectural assessment. "
            "Current focus: identifying service boundaries."
        ),
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["backend", "architecture", "microservices"],
        external_ref="PLAT-101",
        parent=epic1_id,
        created_by="alice@example.com",
    )
    _update(
        feature1_id,
        {"owner": "charlie@example.com", "status": "in_progress"},
        updated_by="charlie@example.com",
    )

    # Task 1.1.1: Design service boundaries (CLOSED)
    task1_id = _create(
        "Design service boundaries",
        description=(
            "Define clear boundaries between services based on business domains. "
            "Involves domain analysis, dependency mapping, and stakeholder alignment."
        ),
        acceptance=(
            "- Domain boundaries documented\n"
            "- Service interfaces defined\n"
            "- Dependency graph created\n"
            "- Technical review completed and approved"
        ),
        design=(
            "Used event storming to identify bounded contexts. Key findings:\n"
            "- User context is cleanly separable\n"
            "- Order and Inventory have some overlap (reservations)\n"
            "- Notifications can be fully async"
        ),
        priority=1,
        issue_type=IssueType.TASK,
        labels=["backend", "design", "documentation"],
        external_ref="PLAT-102",
        parent=feature1_id,
        created_by="alice@example.com",
    )
    _update(
        task1_id,
        {"owner": "charlie@example.com", "status": "in_progress"},
        updated_by="charlie@example.com",
    )
    _close(
        task1_id,
        "Architecture design complete. Approved in tech review.",
        closed_by="bob@example.com",
    )
    _comment(
        task1_id,
        "charlie@example.com",
        "Draft design uploaded to Confluence. Ready for review.",
    )
    _comment(
        task1_id,
        "diana@example.com",
        "Reviewed. LGTM with one suggestion - consider event "
        "sourcing for Order service.",
    )
    _comment(
        task1_id,
        "charlie@example.com",
        "Good point Diana. Added event sourcing to Phase 2 scope.",
    )

    # Task 1.1.2: Implement API gateway (IN_PROGRESS)
    task2_id = _create(
        "Implement API gateway",
        description=(
            "Set up Kong as API gateway for request routing, rate limiting, and "
            "protocol translation. The gateway will handle authentication and "
            "request enrichment."
        ),
        acceptance=(
            "- Gateway deployed to staging\n"
            "- Request routing working for all services\n"
            "- Rate limiting configured per service (100 req/s default)\n"
            "- Monitoring and alerting enabled\n"
            "- mTLS configured for service-to-service calls"
        ),
        notes=(
            "Kong selected after evaluating Kong, Nginx, and Ambassador. "
            "Best fit for our K8s setup."
        ),
        priority=1,
        issue_type=IssueType.TASK,
        labels=["backend", "infrastructure", "api"],
        external_ref="PLAT-103",
        parent=feature1_id,
        created_by="alice@example.com",
    )
    _dep(task2_id, task1_id)
    _update(
        task2_id,
        {"owner": "eve@example.com", "status": "in_progress"},
        updated_by="eve@example.com",
    )
    _comment(
        task2_id,
        "eve@example.com",
        "Kong deployed to staging. Working on rate limiting config.",
    )
    _comment(
        task2_id,
        "jack@example.com",
        "I can help with the K8s ingress config if needed.",
    )

    # Task 1.1.3: Set up service mesh (OPEN)
    task3_id = _create(
        "Set up service mesh",
        description=(
            "Deploy Istio for service-to-service communication, traffic management, "
            "and observability. This will provide automatic service discovery "
            "and failover."
        ),
        acceptance=(
            "- Istio deployed to staging cluster\n"
            "- Service-to-service communication working\n"
            "- Traffic policies tested (circuit breaker, retry)\n"
            "- Distributed tracing operational with Jaeger"
        ),
        priority=2,
        issue_type=IssueType.TASK,
        labels=["backend", "infrastructure", "observability"],
        external_ref="PLAT-104",
        parent=feature1_id,
        created_by="alice@example.com",
    )
    _dep(task3_id, task2_id)

    # Feature 1.2: CI/CD pipeline
    feature2_id = _create(
        "Implement CI/CD pipeline",
        description=(
            "Automate build, test, and deployment using GitHub Actions. This will "
            "enable faster, safer releases and reduce manual operations.\n\n"
            "Goals:\n"
            "- Build time < 10 minutes\n"
            "- Automated rollback on failure\n"
            "- Feature flags for gradual rollout"
        ),
        acceptance=(
            "- All services building in GitHub Actions\n"
            "- Automated tests run on every PR\n"
            "- Staging deployments are automatic\n"
            "- Production deployments gated by approval\n"
            "- Deployment time < 5 minutes"
        ),
        notes="Coordinating with DevOps team. Need to plan for database migrations.",
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["devops", "ci-cd", "automation"],
        external_ref="PLAT-110",
        parent=epic1_id,
        owner="jack@example.com",
        created_by="bob@example.com",
    )

    # Tasks under feature 2
    feature2_tasks = [
        (
            "Set up GitHub Actions workflows",
            True,
            1,
            "jack@example.com",
            "jack@example.com",
            ["devops", "ci-cd"],
            "PLAT-111",
            "Initial workflow created with lint, test, and build stages.",
        ),
        (
            "Configure Docker build pipeline",
            True,
            1,
            "jack@example.com",
            "jack@example.com",
            ["devops", "docker"],
            "PLAT-112",
            "Multi-stage Dockerfile, build time reduced from 8min to 3min.",
        ),
        (
            "Add automated testing stage",
            False,
            1,
            "igor@example.com",
            None,
            ["devops", "testing"],
            "PLAT-113",
            None,
        ),
        (
            "Implement blue-green deployment",
            False,
            2,
            "jack@example.com",
            None,
            ["devops", "deployment"],
            "PLAT-114",
            None,
        ),
        (
            "Add rollback mechanism",
            False,
            2,
            "jack@example.com",
            None,
            ["devops", "deployment"],
            "PLAT-115",
            None,
        ),
    ]
    # Map: index 2 is IN_PROGRESS, others are OPEN (unless closed)
    feature2_statuses = [
        Status.OPEN,
        Status.OPEN,
        Status.IN_PROGRESS,
        Status.OPEN,
        Status.OPEN,
    ]
    for idx, (
        title,
        should_close,
        pri,
        creator,
        closer,
        labels,
        ext_ref,
        close_reason,
    ) in enumerate(feature2_tasks):
        task_id = _create(
            title,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            parent=feature2_id,
            owner=creator if not should_close else None,
            created_by=creator,
        )
        if should_close:
            _update(
                task_id,
                {"owner": creator, "status": "in_progress"},
                updated_by=creator,
            )
            _close(
                task_id,
                close_reason or "Completed",
                closed_by=closer or creator,
            )
        elif feature2_statuses[idx] != Status.OPEN:
            _update(
                task_id,
                {"status": feature2_statuses[idx].value},
                updated_by=creator,
            )

    # =========================================================================
    # Epic 2: User Experience Enhancement
    # =========================================================================
    epic2_id = _create(
        "User Experience Enhancement",
        description=(
            "Improve overall user experience and accessibility. Focus areas include "
            "dashboard redesign, accessibility compliance, and performance "
            "improvements "
            "for end users.\n\n"
            "Key initiatives:\n"
            "- Modern dashboard with customizable widgets\n"
            "- WCAG 2.1 AA compliance\n"
            "- Mobile-first responsive design"
        ),
        notes=(
            "User research completed. Accessibility audit identified 50+ items "
            "to address. "
            "Customer satisfaction scores dropped 15% last quarter - this is priority."
        ),
        priority=1,
        issue_type=IssueType.EPIC,
        labels=["frontend", "ux", "strategic", "q1-2026"],
        external_ref="UX-200",
        created_by="alice@example.com",
    )
    _update(epic2_id, {"owner": "diana@example.com"}, updated_by="diana@example.com")
    _comment(
        epic2_id,
        "alice@example.com",
        "User research report attached. Top 3 pain points identified.",
    )
    _comment(
        epic2_id,
        "diana@example.com",
        "Design team starting wireframes this week. ETA 2 weeks "
        "for initial mockups.",
    )

    # Feature 2.1: Dashboard redesign
    feature3_id = _create(
        "Redesign dashboard interface",
        description=(
            "Modern, responsive dashboard design using latest UI frameworks. "
            "New design "
            "should support both desktop and mobile viewing with customizable widgets."
        ),
        acceptance=(
            "- Design comps approved by stakeholders\n"
            "- Responsive design tested on all target devices\n"
            "- Widget system implemented\n"
            "- Performance meets <2s load time target\n"
            "- A/B test shows 20% improvement in task completion"
        ),
        design=(
            "## Design System\n\n"
            "Using Material UI v5 with custom theme.\n"
            "- Primary: #1976d2\n"
            "- Secondary: #dc004e\n"
            "- Grid system: 12-column responsive\n\n"
            "## Widget Architecture\n"
            "Each widget is a lazy-loaded React component with:\n"
            "- Standard props interface (data, config, actions)\n"
            "- Local state management\n"
            "- Error boundary wrapper"
        ),
        notes=(
            "Design team completed mockups. "
            "Waiting for product approval before dev starts."
        ),
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["frontend", "ux", "dashboard"],
        external_ref="UX-201",
        parent=epic2_id,
        created_by="alice@example.com",
    )
    _update(
        feature3_id,
        {"owner": "diana@example.com", "status": "in_progress"},
        updated_by="diana@example.com",
    )

    # Story under feature 3
    story1_id = _create(
        "As a user, I want a customizable dashboard",
        description=(
            "Users should be able to arrange widgets to create their ideal view. "
            "This includes drag-and-drop reordering, widget selection, and "
            "saving preferences."
        ),
        acceptance=(
            "- Drag-and-drop widget reordering works\n"
            "- User preferences saved to backend\n"
            "- Preferences persist across sessions\n"
            "- Mobile gesture support included\n"
            "- Undo/redo for layout changes"
        ),
        notes=(
            "High user demand based on support tickets. "
            "UX research validates this is a top priority."
        ),
        priority=2,
        issue_type=IssueType.STORY,
        labels=["frontend", "ux", "user-story"],
        external_ref="UX-202",
        parent=feature3_id,
        created_by="diana@example.com",
    )
    _update(
        story1_id,
        {"owner": "eve@example.com", "status": "in_progress"},
        updated_by="eve@example.com",
    )

    # Subtasks for story
    subtask_specs = [
        (
            "Design widget system",
            True,
            "diana@example.com",
            "diana@example.com",
            "Design review approved. Figma files shared.",
            ["frontend", "design"],
            "UX-203",
        ),
        (
            "Implement drag-and-drop",
            False,
            "eve@example.com",
            None,
            None,
            ["frontend", "react"],
            "UX-204",
        ),
        (
            "Add widget preferences API",
            False,
            "frank@example.com",
            None,
            None,
            ["backend", "api"],
            "UX-205",
        ),
    ]
    subtask_statuses = [Status.OPEN, Status.IN_PROGRESS, Status.OPEN]
    for idx, (
        title,
        should_close,
        creator,
        closer,
        close_reason,
        labels,
        ext_ref,
    ) in enumerate(subtask_specs):
        subtask_id = _create(
            title,
            priority=2,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            parent=story1_id,
            owner=creator if not should_close else None,
            created_by=creator,
        )
        if should_close:
            _update(
                subtask_id,
                {"owner": creator, "status": "in_progress"},
                updated_by=creator,
            )
            _close(
                subtask_id,
                close_reason or "Completed",
                closed_by=closer or creator,
            )
        elif subtask_statuses[idx] != Status.OPEN:
            _update(
                subtask_id,
                {"status": subtask_statuses[idx].value},
                updated_by=creator,
            )

    # =========================================================================
    # Bugs
    # =========================================================================
    bug1_id = _create(
        "Dashboard crashes on mobile Safari",
        description=(
            "Reproducible crash when viewing analytics on iOS Safari. Occurs when "
            "scrolling rapidly through charts or when memory usage exceeds 80MB.\n\n"
            "**Steps to reproduce:**\n"
            "1. Open dashboard on iPhone Safari\n"
            "2. Navigate to Analytics tab\n"
            "3. Rapidly scroll through charts\n"
            "4. App crashes after ~30 seconds"
        ),
        notes=(
            "Customer reported this in production. Happens on iPhone 12 Pro. "
            "Stack trace shows memory allocation failure. Likely related to chart "
            "library not cleaning up properly."
        ),
        priority=0,
        issue_type=IssueType.BUG,
        labels=["frontend", "mobile", "critical", "customer-reported"],
        external_ref="BUG-301",
        created_by="igor@example.com",
    )
    _update(
        bug1_id,
        {"owner": "eve@example.com", "status": "in_progress"},
        updated_by="eve@example.com",
    )
    _comment(
        bug1_id,
        "igor@example.com",
        "Reproduced on iPhone 12 Pro and iPhone 13. iOS 16.x affected.",
    )
    _comment(
        bug1_id,
        "eve@example.com",
        "Looking into this. Suspect it's the Chart.js memory leak we saw before.",
    )
    _comment(
        bug1_id,
        "alice@example.com",
        "Customer is Enterprise tier - please prioritize. They have escalated.",
    )

    bug2_id = _create(
        "Memory leak in WebSocket connection",
        description=(
            "Connection grows unbounded after 24h of operation. Memory usage increases "
            "~50MB per hour. Issue only occurs in production with real "
            "traffic, not in testing.\n\n"
            "**Impact:** Requires daily pod restarts to prevent OOM kills."
        ),
        notes=(
            "Identified during production monitoring. Appears to be related to "
            "unreleased "
            "event listeners. Heap dump shows accumulating Socket objects."
        ),
        priority=1,
        issue_type=IssueType.BUG,
        labels=["backend", "performance", "memory-leak"],
        external_ref="BUG-302",
        created_by="igor@example.com",
    )
    _update(
        bug2_id,
        {"owner": "frank@example.com", "status": "in_progress"},
        updated_by="frank@example.com",
    )
    _comment(
        bug2_id,
        "frank@example.com",
        "Found the leak - event listeners not being removed on "
        "disconnect. Fix in progress.",
    )

    bug3_id = _create(
        "Login fails with special characters in password",
        description=(
            "Users cannot log in if their password contains certain special characters "
            "(specifically: &, <, >). Error: 'Invalid credentials' even with "
            "correct password."
        ),
        notes=(
            "HTML encoding issue in the auth form. "
            "Password is being escaped before submission."
        ),
        priority=1,
        issue_type=IssueType.BUG,
        labels=["frontend", "security", "auth"],
        external_ref="BUG-303",
        created_by="igor@example.com",
    )
    _update(
        bug3_id,
        {"owner": "eve@example.com", "status": "in_progress"},
        updated_by="eve@example.com",
    )
    _close(
        bug3_id,
        "Fixed HTML encoding in auth form. Added regression test.",
        closed_by="eve@example.com",
    )

    # Feature 2.2: Accessibility compliance
    feature4_id = _create(
        "WCAG 2.1 AA compliance",
        description=(
            "Make platform accessible to all users including those with "
            "visual, hearing, "
            "motor, and cognitive disabilities. Achieve WCAG 2.1 Level AA compliance "
            "across entire application."
        ),
        acceptance=(
            "- All images have alt text\n"
            "- All form inputs have labels\n"
            "- Color contrast ratios meet 4.5:1 standard\n"
            "- Keyboard navigation complete\n"
            "- Screen reader testing passed (NVDA, VoiceOver)\n"
            "- Automated a11y testing in CI"
        ),
        notes=(
            "Legal requires AA compliance by end of Q2. "
            "Running full accessibility audit now."
        ),
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["frontend", "accessibility", "compliance"],
        external_ref="UX-210",
        parent=epic2_id,
        owner="grace@example.com",
        created_by="alice@example.com",
    )

    # Tasks under feature 4
    accessibility_tasks = [
        (
            "Add ARIA labels to all interactive elements",
            2,
            "grace@example.com",
            ["frontend", "accessibility"],
            "UX-211",
        ),
        (
            "Ensure keyboard navigation works everywhere",
            2,
            "grace@example.com",
            ["frontend", "accessibility"],
            "UX-212",
        ),
        (
            "Add screen reader support",
            2,
            "grace@example.com",
            ["frontend", "accessibility"],
            "UX-213",
        ),
        (
            "Improve color contrast ratios",
            3,
            "henry@example.com",
            ["frontend", "accessibility", "design"],
            "UX-214",
        ),
        (
            "Add skip navigation links",
            3,
            "henry@example.com",
            ["frontend", "accessibility"],
            "UX-215",
        ),
    ]
    for title, pri, creator, labels, ext_ref in accessibility_tasks:
        _create(
            title,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            parent=feature4_id,
            created_by=creator,
        )

    # =========================================================================
    # Epic 3: Performance Optimization
    # =========================================================================
    epic3_id = _create(
        "Performance Optimization",
        description=(
            "Improve application performance and scalability. Target: 50% reduction "
            "in page load time and support 10x increase in concurrent users.\n\n"
            "Focus areas:\n"
            "- Database query optimization\n"
            "- Caching strategy\n"
            "- CDN setup\n"
            "- Bundle size reduction"
        ),
        notes=(
            "Performance degradation reported by multiple customers. P99 "
            "latency at 5s, "
            "should be <500ms. APM shows DB queries as main bottleneck."
        ),
        priority=2,
        issue_type=IssueType.EPIC,
        labels=["performance", "strategic", "q2-2026"],
        external_ref="PERF-400",
        owner="charlie@example.com",
        created_by="bob@example.com",
    )

    # Feature: Database optimization
    feature5_id = _create(
        "Database query optimization",
        description=(
            "Optimize slow queries and add missing indexes. Expected to reduce query "
            "time by 70% for analytical workloads."
        ),
        acceptance=(
            "- All queries <500ms on production volume\n"
            "- N+1 queries eliminated\n"
            "- Indexes added with performance validation\n"
            "- Query plans reviewed and optimized\n"
            "- Slow query log clean (<10 entries/day)"
        ),
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["backend", "database", "performance"],
        external_ref="PERF-401",
        parent=epic3_id,
        owner="frank@example.com",
        created_by="charlie@example.com",
    )

    perf_tasks = [
        ("Profile slow queries in production", "PERF-402"),
        ("Add missing indexes", "PERF-403"),
        ("Implement query caching with Redis", "PERF-404"),
        ("Optimize N+1 queries in user listing", "PERF-405"),
    ]
    for title, ext_ref in perf_tasks:
        _create(
            title,
            priority=2,
            issue_type=IssueType.TASK,
            labels=["backend", "database", "performance"],
            external_ref=ext_ref,
            parent=feature5_id,
            created_by="charlie@example.com",
        )

    # =========================================================================
    # Epic 4: Data Analytics Platform (DEFERRED)
    # =========================================================================
    epic4_id = _create(
        "Data Analytics Platform",
        description=(
            "Build a comprehensive analytics platform for business intelligence "
            "and data-driven decision making.\n\n"
            "Key deliverables:\n"
            "- Real-time analytics dashboard\n"
            "- Data pipeline for ETL processing\n"
            "- Self-service reporting tools\n"
            "- ML-powered anomaly detection"
        ),
        notes=(
            "Deferred to Q3 after leadership decided to prioritize platform "
            "modernization and performance work first. Revisit after microservices "
            "migration is complete."
        ),
        priority=2,
        issue_type=IssueType.EPIC,
        labels=["analytics", "strategic", "q3-2026", "data"],
        external_ref="DATA-900",
        created_by="alice@example.com",
    )
    _update(epic4_id, {"owner": "charlie@example.com"}, updated_by="bob@example.com")
    _update(epic4_id, {"status": "deferred"}, updated_by="alice@example.com")
    _comment(
        epic4_id,
        "alice@example.com",
        "Deferring to Q3. Platform modernization needs to land first.",
    )
    _comment(
        epic4_id,
        "bob@example.com",
        "Agreed. Let's revisit once the microservices migration is stable.",
    )

    # Feature 4.1: Data pipeline
    feature6_id = _create(
        "Build ETL data pipeline",
        description=(
            "Design and implement an ETL pipeline for ingesting, transforming, "
            "and loading data from multiple sources into the analytics warehouse."
        ),
        acceptance=(
            "- Pipeline handles 1M+ records/hour\n"
            "- Supports at-least-once delivery\n"
            "- Schema evolution handled gracefully\n"
            "- Monitoring and alerting for pipeline failures"
        ),
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["analytics", "data", "backend"],
        external_ref="DATA-901",
        parent=epic4_id,
        created_by="charlie@example.com",
    )

    # Tasks under feature 4.1
    _create(
        "Evaluate streaming frameworks",
        priority=2,
        issue_type=IssueType.TASK,
        labels=["analytics", "research"],
        external_ref="DATA-902",
        parent=feature6_id,
        created_by="charlie@example.com",
    )
    _create(
        "Design data warehouse schema",
        priority=2,
        issue_type=IssueType.TASK,
        labels=["analytics", "database", "design"],
        external_ref="DATA-903",
        parent=feature6_id,
        created_by="charlie@example.com",
    )

    # Feature 4.2: Analytics dashboard
    feature7_id = _create(
        "Real-time analytics dashboard",
        description=(
            "Interactive dashboard with real-time data visualization, "
            "customizable charts, and drill-down capabilities."
        ),
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["analytics", "frontend", "dashboard"],
        external_ref="DATA-910",
        parent=epic4_id,
        created_by="diana@example.com",
    )

    _create(
        "Design analytics widget library",
        priority=2,
        issue_type=IssueType.TASK,
        labels=["analytics", "frontend", "design"],
        external_ref="DATA-911",
        parent=feature7_id,
        created_by="diana@example.com",
    )

    # =========================================================================
    # Chores
    # =========================================================================
    _create(
        "Update dependencies to latest versions",
        description=(
            "Security and maintenance updates for all npm packages. Review changelogs "
            "for breaking changes and plan upgrades accordingly."
        ),
        notes=(
            "22 packages have security vulnerabilities. "
            "Some require major version bumps."
        ),
        priority=3,
        issue_type=IssueType.CHORE,
        labels=["maintenance", "security", "dependencies"],
        external_ref="MAINT-501",
        created_by="jack@example.com",
    )

    chore2_id = _create(
        "Refactor authentication middleware",
        description=(
            "Clean up technical debt in auth code. Current implementation has multiple "
            "responsibilities that should be separated."
        ),
        notes="Deferred pending completion of API gateway feature to avoid conflicts.",
        priority=3,
        issue_type=IssueType.CHORE,
        labels=["backend", "tech-debt", "refactoring"],
        external_ref="MAINT-502",
        created_by="kate@example.com",
    )
    _update(chore2_id, {"status": "deferred"}, updated_by="kate@example.com")
    _comment(
        chore2_id,
        "kate@example.com",
        "Deferring until API gateway is done - too much overlap.",
    )
    _comment(
        chore2_id,
        "charlie@example.com",
        "Agreed. Let's revisit in Q2.",
    )

    # =========================================================================
    # Standalone tasks
    # =========================================================================
    standalone_tasks = [
        (
            "Update API documentation",
            Status.OPEN,
            3,
            "liam@example.com",
            None,
            ["documentation", "api"],
            "DOC-601",
            None,
            False,
        ),
        (
            "Set up monitoring alerts",
            Status.IN_REVIEW,
            2,
            "jack@example.com",
            None,
            ["devops", "monitoring"],
            "INFRA-602",
            None,
            False,
        ),
        (
            "Configure backup strategy",
            Status.CLOSED,
            1,
            "jack@example.com",
            "jack@example.com",
            ["devops", "infrastructure"],
            "INFRA-603",
            "Daily backups to S3 with 30-day retention. Tested restore procedure.",
            True,
        ),
        (
            "Review security policies",
            Status.IN_REVIEW,
            2,
            "charlie@example.com",
            None,
            ["security", "compliance"],
            "SEC-604",
            None,
            True,
        ),
        (
            "Plan Q2 roadmap",
            Status.OPEN,
            1,
            "alice@example.com",
            None,
            ["planning", "strategic"],
            "PLAN-605",
            None,
            False,
        ),
    ]
    for (
        title,
        target_status,
        pri,
        creator,
        closer,
        labels,
        ext_ref,
        close_reason,
        manual,
    ) in standalone_tasks:
        should_close = target_status == Status.CLOSED
        task_id = _create(
            title,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            owner=creator if not should_close else None,
            created_by=creator,
            **({"metadata": {"manual": True}} if manual else {}),
        )
        if should_close:
            _update(
                task_id,
                {"owner": creator, "status": "in_progress"},
                updated_by=creator,
            )
            _close(
                task_id,
                close_reason or "Completed",
                closed_by=closer or creator,
            )
        elif target_status != Status.OPEN:
            # Transition through in_progress for issues going to in_review
            if target_status == Status.IN_REVIEW:
                _update(task_id, {"status": "in_progress"}, updated_by=creator)
            _update(task_id, {"status": target_status.value}, updated_by=creator)

    # =========================================================================
    # Questions
    # =========================================================================
    question1_id = _create(
        "Should we use GraphQL or REST for the new API?",
        description=(
            "Need to decide on API architecture for the new services. Both "
            "have tradeoffs.\n\n"
            "**GraphQL pros:** Flexible queries, single endpoint, strong typing\n"
            "**REST pros:** Simpler, better caching, more tooling support"
        ),
        notes="Need decision by end of sprint for planning purposes.",
        priority=2,
        issue_type=IssueType.QUESTION,
        labels=["architecture", "api", "decision"],
        external_ref="ARCH-701",
        created_by="charlie@example.com",
    )
    _update(question1_id, {"status": "in_progress"}, updated_by="charlie@example.com")
    _close(
        question1_id,
        "Decision: REST for public APIs, GraphQL for internal dashboard. "
        "Rationale documented in ADR-005.",
        closed_by="alice@example.com",
    )
    _comment(
        question1_id,
        "diana@example.com",
        "GraphQL would be great for the dashboard - lots of flexible queries.",
    )
    _comment(
        question1_id,
        "frank@example.com",
        "REST is simpler for external consumers. Most of our customers expect REST.",
    )
    _comment(
        question1_id,
        "alice@example.com",
        "Let's do both - REST for public, GraphQL for internal. "
        "Best of both worlds.",
    )

    question2_id = _create(
        "Which monitoring stack should we use?",
        description=(
            "Evaluating monitoring solutions for the microservices architecture.\n\n"
            "Options:\n"
            "1. Datadog (managed, expensive)\n"
            "2. Prometheus + Grafana (self-hosted, free)\n"
            "3. New Relic (managed, mid-range price)"
        ),
        priority=2,
        issue_type=IssueType.QUESTION,
        labels=["devops", "monitoring", "decision"],
        external_ref="ARCH-702",
        created_by="jack@example.com",
    )
    _comment(
        question2_id,
        "jack@example.com",
        "I've set up Prometheus before - it's powerful but requires maintenance.",
    )
    _comment(
        question2_id,
        "bob@example.com",
        "Budget allows for Datadog. Less operational overhead might be worth it.",
    )

    # =========================================================================
    # Tombstoned (deleted) issues
    # =========================================================================
    tombstone1_id = _create(
        "Old legacy feature flag system",
        description=(
            "This feature was removed and replaced with LaunchDarkly integration."
        ),
        notes="Deprecated in favor of LaunchDarkly. Migration completed 2025-12-15.",
        priority=4,
        issue_type=IssueType.FEATURE,
        labels=["deprecated"],
        external_ref="LEGACY-801",
        created_by="charlie@example.com",
    )
    _delete(
        tombstone1_id,
        "Feature replaced with LaunchDarkly. All flags migrated.",
        deleted_by="alice@example.com",
    )

    tombstone2_id = _create(
        "Duplicate: Dashboard performance issue",
        description="Marked as duplicate of PERF-400.",
        notes="This was a duplicate report of the main performance epic.",
        priority=2,
        issue_type=IssueType.BUG,
        labels=["duplicate"],
        external_ref="BUG-802",
        duplicate_of=epic3_id,
        created_by="igor@example.com",
    )
    _delete(
        tombstone2_id,
        f"Duplicate of {epic3_id}. Consolidating discussion there.",
        deleted_by="bob@example.com",
    )

    # =========================================================================
    # Draft issue
    # =========================================================================
    _create(
        "Mobile app redesign",
        description=(
            "Initial thoughts on redesigning the mobile app. Not ready for dev yet."
        ),
        notes="Still gathering requirements from stakeholders.",
        priority=3,
        issue_type=IssueType.TASK,
        status=Status.DRAFT,
        labels=["mobile", "ux", "draft"],
        created_by="diana@example.com",
    )

    return created_ids
