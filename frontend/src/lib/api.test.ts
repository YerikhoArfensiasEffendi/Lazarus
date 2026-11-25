import { describe, expect, it, vi } from "vitest";
import { z } from "zod";
import { createLazarusClient, formatConfidence, formatStars, riskBadgeLabel } from "./api";

describe("Lazarus API helpers & TS Agentic Schema", () => {
  it("formats confidence percentages cleanly and clamps bounds", () => {
    expect(formatConfidence(0.95)).toBe("95%");
    expect(formatConfidence(1.4)).toBe("100%");
    expect(formatConfidence(-0.2)).toBe("0%");
  });

  it("formats GitHub star ratings concisely", () => {
    expect(formatStars(198096)).toBe("198.1k ★");
    expect(formatStars(500)).toBe("500 ★");
    expect(formatStars(0)).toBe("Core");
  });

  it("maps risk levels to clear labels", () => {
    expect(riskBadgeLabel("safe")).toBe("SAFE");
    expect(riskBadgeLabel("review")).toBe("NEEDS CREATOR CONFIRMATION");
    expect(riskBadgeLabel("blocked")).toBe("BLOCKED — NON-HARM RULE");
  });

  it("validates agent tool schemas with Zod", () => {
    const skillQuerySchema = z.object({
      query: z.string().min(1),
      category: z.string().optional(),
    });
    expect(skillQuerySchema.parse({ query: "ponytail" }).query).toBe("ponytail");
  });

  it("sends properly formatted evaluation and skills requests", async () => {
    const mockFetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => ({
        allowed: false,
        risk_level: "blocked",
        matched_rules: ["never_harm_creator.creator_harm"],
        reason: "Blocked",
        note: "Do not execute.",
      }),
    })) as unknown as typeof fetch;

    const client = createLazarusClient("http://127.0.0.1:8000/", mockFetch);
    const result = await client.evaluateAction("harm creator");

    expect(result.allowed).toBe(false);
    expect(result.risk_level).toBe("blocked");
    expect(mockFetch).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/constitution/evaluate",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ action: "harm creator" }),
      }),
    );
  });
});
