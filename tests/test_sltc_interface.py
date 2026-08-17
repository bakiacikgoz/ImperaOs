from __future__ import annotations

from imperaos.router.sltc_interface import FeatureMappedSLTCRouter, PlaceholderSLTCRouter
from imperaos.schemas.models import ExpertName


def test_feature_mapped_sltc_router_maps_features() -> None:
    router = FeatureMappedSLTCRouter(confidence_threshold=0.2)

    decision = router.decide(
        {
            "task_type": "code",
            "confidence": 0.9,
            "needs_expert": True,
            "expert_candidates": "code_expert,plan_expert",
            "latency_budget_ms": 2500,
        }
    )

    assert decision.selected_expert in {ExpertName.CODE, ExpertName.PLAN, ExpertName.LLM_ONLY}
    assert decision.estimated_latency_ms >= 100


def test_placeholder_alias_behaves_like_feature_mapped() -> None:
    router = PlaceholderSLTCRouter(confidence_threshold=0.2)
    decision = router.decide({"task_type": "chat", "confidence": 0.9})

    assert decision.selected_expert == ExpertName.LLM_ONLY
