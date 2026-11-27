import { describe, it, expect } from "vitest";
import { prepareReview } from "../src/features/annotation/review";
const row = {
  annotator_id: "historical-author",
  workflow_status: "pending_review",
  review_acknowledged: "false",
  reviewed_at: "2026-10-01",
  source_metadata: JSON.stringify({ source: "fixture", keep: 7 }),
  comment: "preserve this",
  legacy_annotation: '{"untouched":true}',
};
describe("explicit review action", () => {
  it("records authenticated authorship without replacing the historical identifier", () => {
    const result = prepareReview(
      row,
      "current-user",
      true,
      "2026-11-26T10:00:00Z",
    );
    expect(result.annotator_id).toBe("historical-author");
    expect(result.review_acknowledged).toBe("true");
    expect(result.workflow_status).toBe("finalized");
    expect(result.reviewed_at).toBe("2026-11-26T10:00:00Z");
    expect(JSON.parse(result.source_metadata)).toMatchObject({
      source: "fixture",
      keep: 7,
      workspace_reviews: [
        {
          by: "current-user",
          previous_annotator_id: "historical-author",
          previous_reviewed_at: "2026-10-01",
        },
      ],
    });
    expect(result.comment).toBe(row.comment);
    expect(row.review_acknowledged).toBe("false");
  });
  it("fills missing authors from the session and leaves drafts unconfirmed", () => {
    const result = prepareReview(
      { ...row, annotator_id: "" },
      "current-user",
      false,
      "now",
    );
    expect(result.annotator_id).toBe("current-user");
    expect(result.workflow_status).toBe("pending_review");
    expect(result.review_acknowledged).toBe("false");
    expect(result.source_metadata).toBe(row.source_metadata);
  });
  it("rejects finalization without a session or with invalid existing review history", () => {
    expect(() => prepareReview(row, "", true, "now")).toThrow();
    expect(() =>
      prepareReview(
        { ...row, source_metadata: '{"workspace_reviews":"invalid"}' },
        "current-user",
        true,
        "now",
      ),
    ).toThrow();
  });
});
