import type { Row } from "../../types/index";
export function prepareReview(
  row: Row,
  username: string,
  finalize: boolean,
  timestamp: string,
): Row {
  const author = row.annotator_id || username;
  if (!author.trim() || (finalize && !username.trim()))
    throw Error("Entre novamente para registrar a autoria da revisão.");
  const update: Row = {
    ...row,
    annotator_id: author,
    annotation_timestamp: timestamp,
  };
  if (finalize) {
    const metadata = JSON.parse(row.source_metadata || "{}");
    if (
      metadata.workspace_reviews !== undefined &&
      !Array.isArray(metadata.workspace_reviews)
    )
      throw Error(
        "Histórico de revisão inválido; nenhum dado foi sobrescrito.",
      );
    update.workflow_status = "finalized";
    update.review_acknowledged = "true";
    update.reviewed_at = timestamp;
    update.source_metadata = JSON.stringify({
      ...metadata,
      workspace_reviews: [
        ...(metadata.workspace_reviews || []),
        {
          by: username,
          at: timestamp,
          action: "finalized",
          previous_annotator_id: row.annotator_id || null,
          previous_reviewed_at: row.reviewed_at || null,
        },
      ],
    });
  }
  return update;
}
