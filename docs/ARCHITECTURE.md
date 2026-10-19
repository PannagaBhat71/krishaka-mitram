# Architecture Documentation

## System Overview

Krishaka Mitram follows a modular Django architecture with clear separation of concerns across 6 applications, unified by Django ORM and Django Channels for real-time communication.

## Application Boundaries

### accounts — Identity & Access
- **Responsibility**: User authentication, authorization, role management
- **Key Model**: `CustomUser` extending `AbstractUser`
- **Roles**: `farmer`, `buyer`, `moderator`, `owner`
- **Moderation Fields**: `is_restricted`, `restriction_reason`, `restriction_until`, `violation_count`
- **API**: Forms-based signup/login/logout; no REST API

### farmer — Marketplace Core
- **Responsibility**: Produce listings, crop catalog, buyer inquiries
- **Key Models**:
  - `Crop` — Reference data (10 Karnataka crops)
  - `Farmer` — Listing with price, quantity, quality, location, farm size, phone, ration card
  - `Buyer` — Inquiry linking buyer user to farmer listing
- **Views**: Class-based generic views (ListView, DetailView, CreateView, UpdateView, DeleteView)
- **Authorization**: `UserPassesTestMixin` ensures owners can only edit/delete their listings

### chat — Real-Time Messaging
- **Responsibility**: WebSocket conversations, message persistence, HTTP fallback
- **Key Models**:
  - `Conversation` — Links farmer user + buyer user + optional farmer listing
  - `Message` — Filtered content only; `is_filtered`, `filter_types` JSON field
- **Consumers**:
  - `ChatConsumer` — Per-conversation room groups, auth + participant checks
  - `NotificationConsumer` — Per-user notification groups
  - `ModeratorConsumer` — Shared `moderators` group for violation alerts
- **Routing**: `chat/routing.py` → `ws/chat/<conversation_id>/`, `ws/notifications/`
- **Fallback**: `send_message_view` AJAX endpoint for non-WebSocket clients

### moderation — Content Safety
- **Responsibility**: Filter engine, violation tracking, user restrictions, moderator workflow
- **Key Models**:
  - `FilterRule` — Regex patterns with type, severity, action (block/warn/log)
  - `ModerationIncident` — Groups violations from single submission; holds blocked content temporarily
  - `ModerationViolation` — Individual violation linked to rule; mirrors incident state
  - `UserRestriction` — Links to incident (not violation); updates user restriction fields
- **Filter Engine** (`filters.py`):
  - `MessageFilteringEngine` with 7 detection modules (phone, email, UPI, bank, URL, address, keyword)
  - Returns `FilterResult` with `filtered_content`, `violations[]`, `filter_types[]`, `should_block`, `should_warn`
  - Redaction replaces detected entities with `[TYPE REDACTED]` tags
- **State Machine**: `NEW` → `VIEWED` → `PENDING_ACTION` → `RESOLVED` (atomic, cascades to violations)
- **Purge**: `purge_expired_moderation_data` command respects `VIOLATION_AUTO_PURGE_DAYS`

### notifications — User Alerts
- **Responsibility**: Database + real-time notifications for chat, violations, restrictions
- **Key Model**: `Notification` with generic FK to any model
- **Types**: `violation_new`, `violation_assigned`, `violation_resolved`, `user_restricted`, `user_unrestricted`, `chat_message`, `chat_started`, `rule_triggered`, `system`
- **Consumer**: `NotificationConsumer` — per-user WebSocket group

### audit — Security Trail
- **Responsibility**: Append-only log of security-relevant actions
- **Key Model**: `AuditLog` with action enum, actor, object_type, object_id, JSON details, IP, user-agent
- **Actions**: LOGIN, LOGOUT, FAILED_LOGIN, VIEW_VIOLATION, RESOLVE_VIOLATION, WARN_USER, RESTRICT_USER, UNRESTRICT_USER, CREATE_RULE, UPDATE_RULE, DELETE_RULE, TOGGLE_RULE, PURGE_SENSITIVE_DATA, MESSAGE_BLOCKED, MESSAGE_FLAGGED, CONVERSATION_STARTED, CONVERSATION_CLOSED
- **Privacy**: Never stores sensitive content; only metadata

## Data Flow: Message Sending

```
User sends message (WebSocket or AJAX)
        │
        ▼
┌───────────────────────┐
│  MessageFilteringEngine.filter_message(content)  │
└───────────┬───────────┘
            │
            ▼
    ┌───────────────┐
    │ FilterResult  │
    │ - filtered_content    │
    │ - violations[]        │
    │ - filter_types[]      │
    │ - should_block        │  (computed but NOT used per policy)
    │ - should_warn         │
    └───────┬─────────┘
            │
            ▼
┌───────────────────────────────┐
│ Create Message record         │
│ content = filtered_content    │
│ is_filtered = not is_clean    │
│ filter_types = filter_types   │
└───────────┬───────────────────┘
            │
            ▼
    ┌─────────────────┐
    │ If violations:  │
    │ Create ModerationIncident  │
    │ Create ModerationViolation(s)  │
    │ Signal → notify moderators  │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Broadcast to    │
    │ conversation    │
    │ room group      │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────┐
    │ Create          │
    │ Notification    │
    │ for other user  │
    └─────────────────┘
```

## Channel Layer Topology

```
┌─────────────────────────────────────────────────────────┐
│                    Redis Channel Layer                   │
│  (prod) / InMemoryChannelLayer (dev)                    │
├─────────────────────────────────────────────────────────┤
│  Groups:                                                │
│  - chat_<conversation_id>     → ChatConsumer instances  │
│  - notifications_<user_id>    → NotificationConsumer    │
│  - moderators                 → ModeratorConsumer       │
└─────────────────────────────────────────────────────────┘
```

## Security Boundaries

| Boundary | Enforcement |
|----------|-------------|
| HTTP Views | `@login_required`, `UserPassesTestMixin`, `user_passes_test(is_moderator/owner)` |
| WebSocket Connect | `AuthMiddlewareStack` + `AllowedHostsOriginValidator` + custom participant check |
| Message Send | Participant verification in consumer; conversation active check |
| Moderator Actions | Role check (`user.is_moderator` / `user.is_owner`) in views and consumers |
| Data Access | `select_related`/`prefetch_related` with explicit filters; no raw SQL |

## Deployment Architecture

```
                    ┌──────────────────┐
                    │   Client Browser  │
                    └────────┬─────────┘
                             │ HTTPS/WSS
                             ▼
                    ┌──────────────────┐
                    │    Nginx/Cloud    │
                    │  (SSL Termination)│
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │  Daphne    │ │  Daphne    │ │  Daphne    │  (horizontal scaling)
       │  (ASGI)    │ │  (ASGI)    │ │  (ASGI)    │
       └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                   ┌──────────────────┐
                   │  Redis Cluster   │  (channel layer)
                   └────────┬─────────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌────────────┐ ┌────────────┐ ┌────────────┐
       │ PostgreSQL │ │ PostgreSQL │ │ PostgreSQL │  (read replicas)
       │  Primary   │ │  Replica 1 │ │  Replica 2 │
       └────────────┘ └────────────┘ └────────────┘
```

## Configuration Strategy

- **Single settings module** (`kisan.settings.py`) with environment-driven behavior
- **Test settings** (`kisan.test_settings.py`) — completely independent, no import from production settings
- **Local overrides** — `kisan/settings.local.py` or `kisan/local_settings.py` (gitignored)
- **Environment variables** — All secrets and environment-specific values

## Scaling Considerations

1. **WebSocket Horizontal Scaling** — Multiple Daphne workers behind load balancer with sticky sessions or Redis channel layer
2. **Database** — PostgreSQL with read replicas for query-heavy views (moderation dashboard)
3. **Redis** — Cluster mode for high-availability channel layer
4. **Static Files** — CDN (Cloudflare, AWS CloudFront) in front of Nginx/WhiteNoise
5. **Caching** — Add Redis cache backend for template fragments and query results