import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the enterprise login console", () => {
    window.history.pushState({}, "", "/login");

    render(<App />);

    expect(screen.getByText("Sign in to the operations console")).toBeTruthy();
    expect(screen.getAllByText("Admin").length).toBeGreaterThan(0);
    expect(screen.getByText("Select an access profile to inspect role-based controls, approval routing, and audit behavior across engineering operations.")).toBeTruthy();
    expect(screen.getByText("Gateway ignores model-supplied roles and approval tokens.")).toBeTruthy();
  });

  it("renders dashboard metrics on the dashboard route", async () => {
    window.history.pushState({}, "", "/dashboard");

    render(<App />);

    expect(await screen.findByText("Fleet status")).toBeTruthy();
    expect(screen.getByText("Operations command center")).toBeTruthy();
    expect(screen.getAllByText("Pending approvals").length).toBeGreaterThan(0);
  });

  it("renders the data assistant page", async () => {
    window.history.pushState({}, "", "/assistant");

    render(<App />);

    expect(await screen.findByText("Governed LLM agent")).toBeTruthy();
    expect(screen.getByText("What is the fleet health and business impact?")).toBeTruthy();
  });

  it("renders engineering knowledge content", async () => {
    window.history.pushState({}, "", "/knowledge");

    render(<App />);

    expect(await screen.findByText("Engineering knowledge")).toBeTruthy();
    expect(screen.getByText("Network Troubleshooting Guide")).toBeTruthy();
  });

  it("renders semantic tool discovery debug view", async () => {
    window.history.pushState({}, "", "/tool-discovery");

    render(<App />);

    expect(await screen.findByText("Semantic tool discovery")).toBeTruthy();
    expect(screen.getByLabelText("Engineering request for tool discovery")).toBeTruthy();
    expect(screen.getByText("Retrieve tools")).toBeTruthy();
  });

  it("renders workflow planner debug view", async () => {
    window.history.pushState({}, "", "/workflows");

    render(<App />);

    expect(await screen.findByText("Workflow planner")).toBeTruthy();
    expect(screen.getByLabelText("Engineering request for workflow planning")).toBeTruthy();
    expect(screen.getByText("Plan workflow")).toBeTruthy();
  });

  it("renders capability graph inspector", async () => {
    window.history.pushState({}, "", "/capabilities");

    render(<App />);

    expect(await screen.findByText("Capability graph")).toBeTruthy();
    expect(screen.getByLabelText("Capability source resource")).toBeTruthy();
    expect(screen.getByText("Find path")).toBeTruthy();
  });

  it("renders security governance view", async () => {
    window.history.pushState({}, "", "/security");

    render(<App />);

    expect(await screen.findByText("Control-plane security")).toBeTruthy();
    expect(screen.getByText("Blocked tool calls")).toBeTruthy();
    expect(screen.getByText("Suspicious MCP metadata")).toBeTruthy();
  });

  it("renders evaluation metrics from latest benchmark results", async () => {
    window.history.pushState({}, "", "/evaluation");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          available: true,
          mode: "mock",
          generated_at: "2026-08-11T06:03:26Z",
          dataset_path: "evaluation/datasets/engineering_tasks.json",
          result_path: "evaluation/results/latest.json",
          summaries: [
            {
              config: "semantic_rag_graph",
              mode: "mock",
              cases: 330,
              tool_recall: 0.63,
              tool_precision: 0.86,
              exact_tool_set_accuracy: 0.09,
              workflow_validity_rate: 0.75,
              workflow_completion_rate: 0.64,
              hallucinated_tool_rate: 0.18,
              unnecessary_tool_call_rate: 0.1,
              policy_violation_attempt_rate: 0,
              approval_classification_accuracy: 0.81,
              rag_recall_at_k: 0.74,
              rag_mrr: 0.46,
              average_workflow_length: 2.75,
              execution_success_rate: 0.64,
              planner_latency_ms: 9.8,
              end_to_end_latency_ms: 57.4,
              token_usage: 0,
              estimated_model_cost_usd: null,
            },
          ],
        }),
      })),
    );

    render(<App />);

    expect(await screen.findByText("AI workflow evaluation")).toBeTruthy();
    expect(screen.getByText("Workflow validity")).toBeTruthy();
    expect(screen.getByText("Hallucination rate")).toBeTruthy();
    vi.unstubAllGlobals();
  });
});
