"""Demo issue generation for dogcat.

Creates a realistic set of issues that look like a proper team with a PO, PM,
and developers has worked on it. Includes descriptions, notes, acceptance
criteria, close reasons, labels, external references, and comments.

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

from dogcat.idgen import IDGenerator
from dogcat.models import Comment, Issue, IssueType, Status
from dogcat.storage import JSONLStorage


def _make_comment(counter: list[int], issue_id: str, author: str, text: str) -> Comment:
    """Create a comment with auto-incremented ID."""
    counter[0] += 1
    return Comment(
        id=f"comment-{counter[0]}",
        issue_id=issue_id,
        author=author,
        text=text,
    )


def generate_demo_issues(storage: JSONLStorage) -> list[str]:
    """Generate demo issues for testing and exploration.

    Creates ~50 sample issues including epics, features, tasks, bugs, and stories
    with various priorities, parent-child relationships, dependencies, labels,
    external references, comments, and other metadata.

    Args:
        storage: The storage instance to create issues in

    Returns:
        List of created issue IDs
    """
    idgen = IDGenerator(prefix="demo")
    created_issues: list[str] = []
    comment_counter = [0]

    def make_comment(issue_id: str, author: str, text: str) -> Comment:
        return _make_comment(comment_counter, issue_id, author, text)

    # =========================================================================
    # Epic 1: Platform Modernization
    # =========================================================================
    epic1_id = idgen.generate()
    epic1 = Issue(
        id=epic1_id,
        title="Platform Modernization Initiative",
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
        status=Status.IN_PROGRESS,
        priority=0,
        issue_type=IssueType.EPIC,
        labels=["infrastructure", "strategic", "q1-2026", "backend"],
        external_ref="PLAT-100",
        owner="charlie@example.com",
        created_by="alice@example.com",
    )
    storage.create(epic1)
    storage.update(
        epic1_id,
        {
            "updated_by": "bob@example.com",
            "comments": [
                make_comment(
                    epic1_id,
                    "alice@example.com",
                    "Kickoff meeting scheduled for Monday. "
                    "Please review the design doc beforehand.",
                ),
                make_comment(
                    epic1_id,
                    "charlie@example.com",
                    "Design doc looks solid. I have some questions about the "
                    "Kafka setup - let's discuss in the meeting.",
                ),
                make_comment(
                    epic1_id,
                    "bob@example.com",
                    "Added this to the Q1 roadmap. "
                    "Stakeholders are aligned on timeline.",
                ),
            ],
        },
    )
    created_issues.append(epic1_id)

    # Feature 1.1: Microservices migration
    feature1_id = idgen.generate()
    feature1 = Issue(
        id=feature1_id,
        title="Migrate to microservices architecture",
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
        status=Status.IN_PROGRESS,
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["backend", "architecture", "microservices"],
        external_ref="PLAT-101",
        parent=epic1.full_id,
        owner="charlie@example.com",
        created_by="alice@example.com",
    )
    storage.create(feature1)
    storage.update(feature1_id, {"updated_by": "charlie@example.com"})
    created_issues.append(feature1_id)

    # Task 1.1.1: Design service boundaries (CLOSED)
    task1_id = idgen.generate()
    task1 = Issue(
        id=task1_id,
        title="Design service boundaries",
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
        status=Status.CLOSED,
        priority=1,
        issue_type=IssueType.TASK,
        labels=["backend", "design", "documentation"],
        external_ref="PLAT-102",
        parent=feature1.full_id,
        owner="charlie@example.com",
        created_by="alice@example.com",
    )
    storage.create(task1)
    storage.close(task1_id, "Architecture design complete. Approved in tech review.")
    storage.update(
        task1_id,
        {
            "closed_by": "bob@example.com",
            "updated_by": "charlie@example.com",
            "comments": [
                make_comment(
                    task1_id,
                    "charlie@example.com",
                    "Draft design uploaded to Confluence. Ready for review.",
                ),
                make_comment(
                    task1_id,
                    "diana@example.com",
                    "Reviewed. LGTM with one suggestion - consider event "
                    "sourcing for Order service.",
                ),
                make_comment(
                    task1_id,
                    "charlie@example.com",
                    "Good point Diana. Added event sourcing to Phase 2 scope.",
                ),
            ],
        },
    )
    created_issues.append(task1_id)

    # Task 1.1.2: Implement API gateway (IN_PROGRESS)
    task2_id = idgen.generate()
    task2 = Issue(
        id=task2_id,
        title="Implement API gateway",
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
        status=Status.IN_PROGRESS,
        priority=1,
        issue_type=IssueType.TASK,
        labels=["backend", "infrastructure", "api"],
        external_ref="PLAT-103",
        parent=feature1.full_id,
        owner="eve@example.com",
        created_by="alice@example.com",
    )
    storage.create(task2)
    storage.add_dependency(task2_id, task1_id, "blocks")
    storage.update(
        task2_id,
        {
            "updated_by": "eve@example.com",
            "comments": [
                make_comment(
                    task2_id,
                    "eve@example.com",
                    "Kong deployed to staging. Working on rate limiting config.",
                ),
                make_comment(
                    task2_id,
                    "jack@example.com",
                    "I can help with the K8s ingress config if needed.",
                ),
            ],
        },
    )
    created_issues.append(task2_id)

    # Task 1.1.3: Set up service mesh (OPEN)
    task3_id = idgen.generate()
    task3 = Issue(
        id=task3_id,
        title="Set up service mesh",
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
        status=Status.OPEN,
        priority=2,
        issue_type=IssueType.TASK,
        labels=["backend", "infrastructure", "observability"],
        external_ref="PLAT-104",
        parent=feature1.full_id,
        created_by="alice@example.com",
    )
    storage.create(task3)
    storage.add_dependency(task3_id, task2_id, "blocks")
    created_issues.append(task3_id)

    # Feature 1.2: CI/CD pipeline
    feature2_id = idgen.generate()
    feature2 = Issue(
        id=feature2_id,
        title="Implement CI/CD pipeline",
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
        status=Status.OPEN,
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["devops", "ci-cd", "automation"],
        external_ref="PLAT-110",
        parent=epic1.full_id,
        owner="jack@example.com",
        created_by="bob@example.com",
    )
    storage.create(feature2)
    created_issues.append(feature2_id)

    # Tasks under feature 2
    feature2_tasks = [
        (
            "Set up GitHub Actions workflows",
            Status.CLOSED,
            1,
            "jack@example.com",
            "jack@example.com",
            ["devops", "ci-cd"],
            "PLAT-111",
            "Initial workflow created with lint, test, and build stages.",
        ),
        (
            "Configure Docker build pipeline",
            Status.CLOSED,
            1,
            "jack@example.com",
            "jack@example.com",
            ["devops", "docker"],
            "PLAT-112",
            "Multi-stage Dockerfile, build time reduced from 8min to 3min.",
        ),
        (
            "Add automated testing stage",
            Status.IN_PROGRESS,
            1,
            "igor@example.com",
            None,
            ["devops", "testing"],
            "PLAT-113",
            None,
        ),
        (
            "Implement blue-green deployment",
            Status.OPEN,
            2,
            "jack@example.com",
            None,
            ["devops", "deployment"],
            "PLAT-114",
            None,
        ),
        (
            "Add rollback mechanism",
            Status.OPEN,
            2,
            "jack@example.com",
            None,
            ["devops", "deployment"],
            "PLAT-115",
            None,
        ),
    ]
    for (
        title,
        status,
        pri,
        creator,
        closer,
        labels,
        ext_ref,
        close_reason,
    ) in feature2_tasks:
        task_id = idgen.generate()
        task = Issue(
            id=task_id,
            title=title,
            status=status,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            parent=feature2.full_id,
            owner=creator if status != Status.CLOSED else None,
            created_by=creator,
        )
        storage.create(task)
        created_issues.append(task_id)
        if status == Status.CLOSED:
            storage.close(task_id, close_reason or "Completed")
            storage.update(task_id, {"closed_by": closer or creator})

    # =========================================================================
    # Epic 2: User Experience Enhancement
    # =========================================================================
    epic2_id = idgen.generate()
    epic2 = Issue(
        id=epic2_id,
        title="User Experience Enhancement",
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
        status=Status.OPEN,
        priority=1,
        issue_type=IssueType.EPIC,
        labels=["frontend", "ux", "strategic", "q1-2026"],
        external_ref="UX-200",
        owner="diana@example.com",
        created_by="alice@example.com",
    )
    storage.create(epic2)
    storage.update(
        epic2_id,
        {
            "updated_by": "diana@example.com",
            "comments": [
                make_comment(
                    epic2_id,
                    "alice@example.com",
                    "User research report attached. Top 3 pain points identified.",
                ),
                make_comment(
                    epic2_id,
                    "diana@example.com",
                    "Design team starting wireframes this week. ETA 2 weeks "
                    "for initial mockups.",
                ),
            ],
        },
    )
    created_issues.append(epic2_id)

    # Feature 2.1: Dashboard redesign
    feature3_id = idgen.generate()
    feature3 = Issue(
        id=feature3_id,
        title="Redesign dashboard interface",
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
        status=Status.IN_PROGRESS,
        priority=1,
        issue_type=IssueType.FEATURE,
        labels=["frontend", "ux", "dashboard"],
        external_ref="UX-201",
        parent=epic2.full_id,
        owner="diana@example.com",
        created_by="alice@example.com",
    )
    storage.create(feature3)
    storage.update(feature3_id, {"updated_by": "diana@example.com"})
    created_issues.append(feature3_id)

    # Story under feature 3
    story1_id = idgen.generate()
    story1 = Issue(
        id=story1_id,
        title="As a user, I want a customizable dashboard",
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
        status=Status.IN_PROGRESS,
        priority=2,
        issue_type=IssueType.STORY,
        labels=["frontend", "ux", "user-story"],
        external_ref="UX-202",
        parent=feature3.full_id,
        owner="eve@example.com",
        created_by="diana@example.com",
    )
    storage.create(story1)
    created_issues.append(story1_id)

    # Subtasks for story
    subtask_specs = [
        (
            "Design widget system",
            Status.CLOSED,
            "diana@example.com",
            "diana@example.com",
            "Design review approved. Figma files shared.",
            ["frontend", "design"],
            "UX-203",
        ),
        (
            "Implement drag-and-drop",
            Status.IN_PROGRESS,
            "eve@example.com",
            None,
            None,
            ["frontend", "react"],
            "UX-204",
        ),
        (
            "Add widget preferences API",
            Status.OPEN,
            "frank@example.com",
            None,
            None,
            ["backend", "api"],
            "UX-205",
        ),
    ]
    for title, status, creator, closer, close_reason, labels, ext_ref in subtask_specs:
        subtask_id = idgen.generate()
        subtask = Issue(
            id=subtask_id,
            title=title,
            status=status,
            priority=2,
            issue_type=IssueType.SUBTASK,
            labels=labels,
            external_ref=ext_ref,
            parent=story1.full_id,
            owner=creator if status != Status.CLOSED else None,
            created_by=creator,
        )
        storage.create(subtask)
        created_issues.append(subtask_id)
        if status == Status.CLOSED:
            storage.close(subtask_id, close_reason or "Completed")
            storage.update(subtask_id, {"closed_by": closer or creator})

    # =========================================================================
    # Bugs
    # =========================================================================
    bug1_id = idgen.generate()
    bug1 = Issue(
        id=bug1_id,
        title="Dashboard crashes on mobile Safari",
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
        status=Status.OPEN,
        priority=0,
        issue_type=IssueType.BUG,
        labels=["frontend", "mobile", "critical", "customer-reported"],
        external_ref="BUG-301",
        created_by="igor@example.com",
    )
    storage.create(bug1)
    storage.update(
        bug1_id,
        {
            "comments": [
                make_comment(
                    bug1_id,
                    "igor@example.com",
                    "Reproduced on iPhone 12 Pro and iPhone 13. iOS 16.x affected.",
                ),
                make_comment(
                    bug1_id,
                    "eve@example.com",
                    "Looking into this. Suspect it's the Chart.js memory leak "
                    "we saw before.",
                ),
                make_comment(
                    bug1_id,
                    "alice@example.com",
                    "Customer is Enterprise tier - please prioritize. They "
                    "have escalated.",
                ),
            ],
        },
    )
    created_issues.append(bug1_id)

    bug2_id = idgen.generate()
    bug2 = Issue(
        id=bug2_id,
        title="Memory leak in WebSocket connection",
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
        status=Status.IN_PROGRESS,
        priority=1,
        issue_type=IssueType.BUG,
        labels=["backend", "performance", "memory-leak"],
        external_ref="BUG-302",
        owner="frank@example.com",
        created_by="igor@example.com",
    )
    storage.create(bug2)
    storage.update(
        bug2_id,
        {
            "updated_by": "frank@example.com",
            "comments": [
                make_comment(
                    bug2_id,
                    "frank@example.com",
                    "Found the leak - event listeners not being removed on "
                    "disconnect. Fix in progress.",
                ),
            ],
        },
    )
    created_issues.append(bug2_id)

    bug3_id = idgen.generate()
    bug3 = Issue(
        id=bug3_id,
        title="Login fails with special characters in password",
        description=(
            "Users cannot log in if their password contains certain special characters "
            "(specifically: &, <, >). Error: 'Invalid credentials' even with "
            "correct password."
        ),
        notes=(
            "HTML encoding issue in the auth form. "
            "Password is being escaped before submission."
        ),
        status=Status.CLOSED,
        priority=1,
        issue_type=IssueType.BUG,
        labels=["frontend", "security", "auth"],
        external_ref="BUG-303",
        owner=None,
        created_by="igor@example.com",
    )
    storage.create(bug3)
    storage.close(bug3_id, "Fixed HTML encoding in auth form. Added regression test.")
    storage.update(
        bug3_id,
        {"closed_by": "eve@example.com", "updated_by": "eve@example.com"},
    )
    created_issues.append(bug3_id)

    # Feature 2.2: Accessibility compliance
    feature4_id = idgen.generate()
    feature4 = Issue(
        id=feature4_id,
        title="WCAG 2.1 AA compliance",
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
        status=Status.OPEN,
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["frontend", "accessibility", "compliance"],
        external_ref="UX-210",
        parent=epic2.full_id,
        owner="grace@example.com",
        created_by="alice@example.com",
    )
    storage.create(feature4)
    created_issues.append(feature4_id)

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
        task_id = idgen.generate()
        task = Issue(
            id=task_id,
            title=title,
            status=Status.OPEN,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            parent=feature4.full_id,
            created_by=creator,
        )
        storage.create(task)
        created_issues.append(task_id)

    # =========================================================================
    # Epic 3: Performance Optimization
    # =========================================================================
    epic3_id = idgen.generate()
    epic3 = Issue(
        id=epic3_id,
        title="Performance Optimization",
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
        status=Status.OPEN,
        priority=2,
        issue_type=IssueType.EPIC,
        labels=["performance", "strategic", "q2-2026"],
        external_ref="PERF-400",
        owner="charlie@example.com",
        created_by="bob@example.com",
    )
    storage.create(epic3)
    created_issues.append(epic3_id)

    # Feature: Database optimization
    feature5_id = idgen.generate()
    feature5 = Issue(
        id=feature5_id,
        title="Database query optimization",
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
        status=Status.OPEN,
        priority=2,
        issue_type=IssueType.FEATURE,
        labels=["backend", "database", "performance"],
        external_ref="PERF-401",
        parent=epic3.full_id,
        owner="frank@example.com",
        created_by="charlie@example.com",
    )
    storage.create(feature5)
    created_issues.append(feature5_id)

    perf_tasks = [
        ("Profile slow queries in production", "PERF-402"),
        ("Add missing indexes", "PERF-403"),
        ("Implement query caching with Redis", "PERF-404"),
        ("Optimize N+1 queries in user listing", "PERF-405"),
    ]
    for title, ext_ref in perf_tasks:
        task_id = idgen.generate()
        task = Issue(
            id=task_id,
            title=title,
            status=Status.OPEN,
            priority=2,
            issue_type=IssueType.TASK,
            labels=["backend", "database", "performance"],
            external_ref=ext_ref,
            parent=feature5.full_id,
            created_by="charlie@example.com",
        )
        storage.create(task)
        created_issues.append(task_id)

    # =========================================================================
    # Chores
    # =========================================================================
    chore1_id = idgen.generate()
    chore1 = Issue(
        id=chore1_id,
        title="Update dependencies to latest versions",
        description=(
            "Security and maintenance updates for all npm packages. Review changelogs "
            "for breaking changes and plan upgrades accordingly."
        ),
        notes=(
            "22 packages have security vulnerabilities. "
            "Some require major version bumps."
        ),
        status=Status.OPEN,
        priority=3,
        issue_type=IssueType.CHORE,
        labels=["maintenance", "security", "dependencies"],
        external_ref="MAINT-501",
        created_by="jack@example.com",
    )
    storage.create(chore1)
    created_issues.append(chore1_id)

    chore2_id = idgen.generate()
    chore2 = Issue(
        id=chore2_id,
        title="Refactor authentication middleware",
        description=(
            "Clean up technical debt in auth code. Current implementation has multiple "
            "responsibilities that should be separated."
        ),
        notes="Deferred pending completion of API gateway feature to avoid conflicts.",
        status=Status.DEFERRED,
        priority=3,
        issue_type=IssueType.CHORE,
        labels=["backend", "tech-debt", "refactoring"],
        external_ref="MAINT-502",
        created_by="kate@example.com",
    )
    storage.create(chore2)
    storage.update(
        chore2_id,
        {
            "comments": [
                make_comment(
                    chore2_id,
                    "kate@example.com",
                    "Deferring until API gateway is done - too much overlap.",
                ),
                make_comment(
                    chore2_id,
                    "charlie@example.com",
                    "Agreed. Let's revisit in Q2.",
                ),
            ],
        },
    )
    created_issues.append(chore2_id)

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
        ),
    ]
    for (
        title,
        status,
        pri,
        creator,
        closer,
        labels,
        ext_ref,
        close_reason,
    ) in standalone_tasks:
        task_id = idgen.generate()
        task = Issue(
            id=task_id,
            title=title,
            status=status,
            priority=pri,
            issue_type=IssueType.TASK,
            labels=labels,
            external_ref=ext_ref,
            owner=creator if status != Status.CLOSED else None,
            created_by=creator,
        )
        storage.create(task)
        created_issues.append(task_id)
        if status == Status.CLOSED:
            storage.close(task_id, close_reason or "Completed")
            storage.update(task_id, {"closed_by": closer or creator})

    # =========================================================================
    # Questions
    # =========================================================================
    question1_id = idgen.generate()
    question1 = Issue(
        id=question1_id,
        title="Should we use GraphQL or REST for the new API?",
        description=(
            "Need to decide on API architecture for the new services. Both "
            "have tradeoffs.\n\n"
            "**GraphQL pros:** Flexible queries, single endpoint, strong typing\n"
            "**REST pros:** Simpler, better caching, more tooling support"
        ),
        notes="Need decision by end of sprint for planning purposes.",
        status=Status.CLOSED,
        priority=2,
        issue_type=IssueType.QUESTION,
        labels=["architecture", "api", "decision"],
        external_ref="ARCH-701",
        created_by="charlie@example.com",
    )
    storage.create(question1)
    storage.close(
        question1_id,
        "Decision: REST for public APIs, GraphQL for internal dashboard. "
        "Rationale documented in ADR-005.",
    )
    storage.update(
        question1_id,
        {
            "closed_by": "alice@example.com",
            "comments": [
                make_comment(
                    question1_id,
                    "diana@example.com",
                    "GraphQL would be great for the dashboard - lots of "
                    "flexible queries.",
                ),
                make_comment(
                    question1_id,
                    "frank@example.com",
                    "REST is simpler for external consumers. Most of our "
                    "customers expect REST.",
                ),
                make_comment(
                    question1_id,
                    "alice@example.com",
                    "Let's do both - REST for public, GraphQL for internal. "
                    "Best of both worlds.",
                ),
            ],
        },
    )
    created_issues.append(question1_id)

    question2_id = idgen.generate()
    question2 = Issue(
        id=question2_id,
        title="Which monitoring stack should we use?",
        description=(
            "Evaluating monitoring solutions for the microservices architecture.\n\n"
            "Options:\n"
            "1. Datadog (managed, expensive)\n"
            "2. Prometheus + Grafana (self-hosted, free)\n"
            "3. New Relic (managed, mid-range price)"
        ),
        status=Status.OPEN,
        priority=2,
        issue_type=IssueType.QUESTION,
        labels=["devops", "monitoring", "decision"],
        external_ref="ARCH-702",
        created_by="jack@example.com",
    )
    storage.create(question2)
    storage.update(
        question2_id,
        {
            "comments": [
                make_comment(
                    question2_id,
                    "jack@example.com",
                    "I've set up Prometheus before - it's powerful but "
                    "requires maintenance.",
                ),
                make_comment(
                    question2_id,
                    "bob@example.com",
                    "Budget allows for Datadog. Less operational overhead "
                    "might be worth it.",
                ),
            ],
        },
    )
    created_issues.append(question2_id)

    # =========================================================================
    # Tombstoned (deleted) issues
    # =========================================================================
    tombstone1_id = idgen.generate()
    tombstone1 = Issue(
        id=tombstone1_id,
        title="[Deleted] Old legacy feature flag system",
        description=(
            "This feature was removed and replaced with LaunchDarkly integration."
        ),
        notes="Deprecated in favor of LaunchDarkly. Migration completed 2025-12-15.",
        status=Status.TOMBSTONE,
        priority=4,
        issue_type=IssueType.FEATURE,
        labels=["deprecated"],
        external_ref="LEGACY-801",
        created_by="charlie@example.com",
    )
    storage.create(tombstone1)
    storage.update(
        tombstone1_id,
        {
            "deleted_by": "alice@example.com",
            "delete_reason": "Feature replaced with LaunchDarkly. All flags migrated.",
        },
    )
    created_issues.append(tombstone1_id)

    tombstone2_id = idgen.generate()
    tombstone2 = Issue(
        id=tombstone2_id,
        title="[Deleted] Duplicate: Dashboard performance issue",
        description="Marked as duplicate of PERF-400.",
        notes="This was a duplicate report of the main performance epic.",
        status=Status.TOMBSTONE,
        priority=2,
        issue_type=IssueType.BUG,
        labels=["duplicate"],
        external_ref="BUG-802",
        duplicate_of=epic3.full_id,
        created_by="igor@example.com",
    )
    storage.create(tombstone2)
    storage.update(
        tombstone2_id,
        {
            "deleted_by": "bob@example.com",
            "delete_reason": (
                f"Duplicate of {epic3_id}. Consolidating discussion there."
            ),
        },
    )
    created_issues.append(tombstone2_id)

    # =========================================================================
    # Draft issue
    # =========================================================================
    draft1_id = idgen.generate()
    draft1 = Issue(
        id=draft1_id,
        title="[Draft] Mobile app redesign",
        description=(
            "Initial thoughts on redesigning the mobile app. Not ready for dev yet."
        ),
        notes="Still gathering requirements from stakeholders.",
        status=Status.OPEN,
        priority=3,
        issue_type=IssueType.DRAFT,
        labels=["mobile", "ux", "draft"],
        created_by="diana@example.com",
    )
    storage.create(draft1)
    created_issues.append(draft1_id)

    return created_issues
