# Architecture Decision Records

Architecture Decision Records (ADRs) preserve why lasting design choices exist.
Use them for ownership, protocol, public API, persistence, compatibility, and
verification decisions that future work might otherwise undo accidentally.

## Records

- [ADR-0001: One Manager-Owned Runtime](0001-manager-owned-runtime.md)
- [ADR-0002: Main-Thread File-Queue Codex Bridge](0002-file-queue-codex-bridge.md)
- [ADR-0003: Popup-Unsafe Native Actions Require Manager Features](0003-popup-native-actions-require-manager-features.md)

## Process

1. Copy [`TEMPLATE.md`](TEMPLATE.md).
2. Use the next four-digit number and a short kebab-case title.
3. Record context, decision, consequences, and alternatives.
4. Set status to proposed, accepted, deprecated, or superseded.
5. Once accepted, do not rewrite history. Add a new ADR and supersession link.
