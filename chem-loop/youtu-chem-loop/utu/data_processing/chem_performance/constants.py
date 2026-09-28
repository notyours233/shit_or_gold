from __future__ import annotations

from typing import Final

# Non-metric fields that may appear in raw extracted records.
NON_METRIC_KEYS: Final[set[str]] = {
    "id",
    "metals",
    "reaction_type",
    "task_type",
    # Material-name-first experimental feedback fields. They are prompt context,
    # not performance metrics, and must never leak into metrics_gt.
    "material_name",
    "material_description",
    "material_input",
    "major_category",
    "components",
    "structure_relationships",
    "precursors",
    "feed_ratio",
    "preparation_method",
    "elements",
    "element_content",
    "conditions",
    "custom_prompt",
    "pos",
    "block_index",
    "product",  # CO2RR input condition, not a performance metric
    # Optional bibliographic fields (may be added by manual curation imports).
    "doi",
    "doc_id",
    "title",
}


REACTION_TYPES: Final[set[str]] = {
    "HER",
    "OER",
    "ORR",
    "HOR",
    "UOR",
    "EOR",
    "HzOR",
    "O5H",
    "CO2RR",
}


# Only O5H has known casing aliases in the current extracted dataset.
O5H_KEY_ALIASES: Final[dict[str, str]] = {
    "Faradaic_efficiency": "faradaic_efficiency",
}


# Reaction-specific metric scope for the current project stage.
# We intentionally keep only the metrics we plan to optimize/judge for each reaction_type.
REACTION_ALLOWED_METRICS: Final[dict[str, set[str]]] = {
    # For this project stage, overpotential is interpreted as η@10 mA cm^-2 (η10).
    # We encode this condition explicitly in the metric key so the model can copy it
    # and avoid ambiguity during prediction.
    "HER": {"overpotential_10mAcm-2"},
    "OER": {"overpotential_10mAcm-2"},
    "ORR": {"half_wave_potential"},
    "HOR": {"exchange_current_density"},
    # UOR: treat "potential" and "overpotential" extractions as the same target,
    # and interpret them as the (over)potential at 10 mA cm^-2 with unit V.
    "UOR": {"potential_10mAcm-2"},
    "EOR": {"mass_activity"},
    # HzOR raw extracted keys include "overpotential_10mAcm-2" (and sometimes other current densities).
    "HzOR": {"overpotential_10mAcm-2"},
    # O5H: current requirement is to optimize FE only.
    "O5H": {"faradaic_efficiency"},
    # CO2RR is handled specially:
    # - task 1 predicts the top-FE product and its Faradaic efficiency
    # - task 2 regresses the partial current density for that product
    "CO2RR": {"faradaic_efficiency", "partial_current_density"},
}
