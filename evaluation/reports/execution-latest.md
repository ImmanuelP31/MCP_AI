# AI Engineering Workflow Execution Benchmark

Generated: `2026-08-21T18:03:56Z`
Mode: `deterministic-execution`

This benchmark uses deterministic MCP/tool simulators. It measures execution engine semantics, not live LLM quality.

## Summary

| Metric | Value |
| --- | ---: |
| cases | 5 |
| planning_success_rate | 1.0 |
| policy_correctness_rate | 1.0 |
| approval_correctness_rate | 1.0 |
| execution_success_rate | 1.0 |
| compensation_success_rate | 1.0 |
| retry_recovery_rate | 1.0 |
| final_state_correctness_rate | 1.0 |
| average_planner_latency_ms | 44.8156 |
| average_execution_latency_ms | 80.819 |

## Cases

| Case | Terminal | Planning | Policy | Approval | Execution | Retry | Compensation | Final State |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EXEC-001 | COMPLETED | yes | yes | yes | yes | n/a | n/a | yes |
| EXEC-002 | COMPLETED | yes | yes | yes | yes | n/a | n/a | yes |
| EXEC-003 | COMPLETED | yes | yes | yes | yes | yes | n/a | yes |
| EXEC-004 | COMPLETED | yes | yes | yes | yes | n/a | yes | yes |
| EXEC-005 | COMPLETED | yes | yes | yes | yes | n/a | n/a | yes |
