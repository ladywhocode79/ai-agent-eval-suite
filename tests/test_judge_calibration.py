import logging

import pytest
from sklearn.metrics import cohen_kappa_score
from deepeval import evaluate as deepeval_evaluate
from deepeval.evaluate.configs import DisplayConfig
from deepeval.metrics import FaithfulnessMetric, AnswerRelevancyMetric
from deepeval.test_case import LLMTestCase

from frameworks.evals.routing import declared_allergens, expects_refusal
from .test_evals import allergen_safety_metric, judge_model, load_calibration_dataset

logger = logging.getLogger(__name__)


def metrics_for(item):
    """Same metric routing as test_meal_planner_scenario, so we calibrate the real gate."""
    metrics = [FaithfulnessMetric(threshold=0.85, model=judge_model)]
    # Allergen safety only when an allergen is declared; otherwise the judge has
    # nothing to evaluate and returns a degenerate score (see case study 5).
    if declared_allergens(item):
        metrics.append(allergen_safety_metric)
    # A valid refusal is not "relevant" to AnswerRelevancyMetric (case study 4).
    # Refusal is expected when the flag says so, or when every retrieved recipe
    # contains the declared allergen (poisoned context).
    if not expects_refusal(item):
        metrics.append(AnswerRelevancyMetric(threshold=0.80, model=judge_model))
    return metrics


@pytest.mark.calibration
def test_judge_cohen_kappa_alignment():
    """Validates that LLM Judge aligns with Human Expert labels (κ >= 0.80)."""
    dataset = load_calibration_dataset()
    human_labels, judge_labels, disagreements = [], [], []

    for item in dataset:
        test_case = LLMTestCase(
            input=item["input"],
            actual_output=item["actual_output"],
            retrieval_context=item["retrieved_context"]
        )

        result = deepeval_evaluate(
            [test_case],
            metrics_for(item),
            display_config=DisplayConfig(show_indicator=False, print_results=False)
        )

        # Judge says "pass" only if ALL routed metrics pass
        judge_passed = 1 if result.test_results[0].success else 0
        human_labels.append(item["human_label"])
        judge_labels.append(judge_passed)
        agree = judge_passed == item["human_label"]
        if not agree:
            disagreements.append(item["scenario_id"])

        verdict = lambda v: "PASS" if v else "FAIL"
        logger.info(
            "[%s] %s | human=%s judge=%s",
            item["scenario_id"],
            "AGREE" if agree else "DISAGREE",
            verdict(item["human_label"]),
            verdict(judge_passed),
        )
        logger.info("[%s] human reasoning: %s", item["scenario_id"], item.get("reasoning"))
        for metric_data in result.test_results[0].metrics_data or []:
            logger.info(
                "[%s] judge %s -> %s (score=%s threshold=%s): %s",
                item["scenario_id"],
                metric_data.name,
                verdict(metric_data.success),
                metric_data.score,
                metric_data.threshold,
                metric_data.reason,
            )

    kappa = cohen_kappa_score(human_labels, judge_labels)
    logger.info(
        "Calibration summary: kappa=%.2f agreed=%d/%d disagreements=%s",
        kappa, len(dataset) - len(disagreements), len(dataset), disagreements or "none",
    )
    assert kappa >= 0.80, (
        f"Judge Calibration Failed! Cohen's Kappa ({kappa:.2f}) < 0.80. "
        f"Disagreements: {disagreements}"
    )
