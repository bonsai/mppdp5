# Software Factory — mppdp5

## Purpose

Treat requirements, architecture, contracts, implementation, tests, deployment, and improvement as one traceable flow. PlantUML diagrams describe the system and workflow; JSON files remain the machine-readable source of truth for gate rules.

## Flow

`PRD → Design/UML + Ontology → GATE → Kanban/Issues → Agent implementation → Tests → Deploy → Observe → Kaizen`

- **PRD**: state the user problem, scope, acceptance criteria, and constraints.
- **Design / Ontology**: define component responsibilities, data concepts, protocol boundaries, and failure behavior before implementation.
- **GATE**: check explicit entry/exit criteria and retain machine-readable evidence. Failed checks return work to the responsible stage.
- **Kanban / GitHub Issues**: one independently verifiable work item per card; pull work only when the next stage has capacity.
- **Agent implementation**: keep each task scoped to a repository issue and existing project conventions.
- **Tests**: verify schemas, tracking-loss behavior, transport contracts, and privacy invariants.
- **Deploy / Observe**: publish only after required checks pass; observe failures and regressions.
- **Kaizen**: feed findings back into requirements, diagrams, contracts, tests, and ADRs.

## Toyota-style flow controls

- Visualize work by stage and make blocked work visible.
- Set WIP limits for active issues/agent tasks; avoid starting more work than can be reviewed and tested.
- Prefer pull flow: start the next task when downstream capacity exists.
- Build quality into each stage; do not pass a failed gate downstream.
- Treat failed checks and tracking-loss regressions as an andon signal requiring attention.
- Convert recurring defects and operational observations into small, traceable improvements.

## PlantUML usage

- Use component/package/class diagrams for structure and dependencies.
- Use sequence diagrams for runtime behavior, especially tracking-loss and recovery paths.
- Keep source diagrams in `docs/*.puml`; render SVG/PNG in CI or a documented local command.
- Keep gate policies in `factory/gates.json` and interface schemas in `schemas/`. Diagrams explain the design but do not replace executable contracts.

## Initial implementation order

1. Review the current ecosystem and robustness diagrams against the actual code.
2. Add the factory gate contract and workflow diagram.
3. Add syntax/render checks for PlantUML.
4. Add schema validation for browser/WebSocket and OSC contracts where contracts are formalized.
5. Publish validation results as CI evidence and link the design, ADRs, and issues from the project documentation.

## Current limitations

This document defines the proposed workflow; it does not claim that all gates, Kanban automation, schema validation, or deployment checks are already implemented. Keep the distinction visible until CI evidence confirms each capability.
