# Table: audit_logs_unstructured
**Domain:** Security & Operations
**Grain:** Event-based log.

### Key Columns
- `action_type` (VARCHAR): The category of event (e.g., 'SYSTEM_SYNC', 'MANUAL_OVERRIDE').
- `metadata_json` (JSONB): Contains source IP, user agents, and internal tags.
- **Trap (JSON Extraction):** To extract the IP address, use: `metadata_json->>'ip'`.
- **Trap (Action Filter):** Do NOT look for action_type inside the JSON; it is a top-level column.

### Purpose
Used for troubleshooting billing overrides or high-priority system changes.