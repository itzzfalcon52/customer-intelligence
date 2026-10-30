from customer_intelligence.schemas.comparison import ComparisonReport


def computed_briefing(report: ComparisonReport) -> dict:
    best = next(
        r
        for r in report.results
        if (r.candidate_id or r.model_name)
        == (report.best_validation_candidate_id or report.best_validation_model)
    )
    m = best.validation
    base = next(
        (r.validation.average_precision for r in report.results if r.model_name == "dummy_prior"),
        None,
    )
    return {
        "source": "computed",
        "partition": "validation",
        "paragraphs": [
            (
                f"Compared {len(report.results)} candidates using "
                f"{report.training_row_count} training rows. Selected {best.model_name} "
                f"by validation average precision ({m.average_precision:.3f})."
            ),
            (
                f"At cutoff {report.classification_threshold:.3f}, the model flagged "
                f"{m.predicted_positive_count} of {m.row_count} validation customers: "
                f"{m.true_positive} true alerts and {m.false_positive} false alerts. It "
                f"missed {m.false_negative} churners."
            ),
            (
                "Review pre-outcome feature availability and contact costs before "
                "launching outreach. No intervention effect or financial return has "
                "been measured. Final test data is reserved until you evaluate it."
            ),
        ],
        "baseline_average_precision": base,
        "average_precision_lift": m.average_precision / base if base else None,
        "limitations": [
            "Static labels do not establish a future prediction horizon.",
            (
                "Validation selection can be optimistic; precision depends on "
                "threshold and population."
            ),
        ],
    }
