MODEL_NAME = "facebook/dinov2-base"

CATEGORICAL_HEADS = (
    "passage_width",
    "obstruction",
    "surface_condition",
    "level_change",
    "path_continuity",
)

MULTILABEL_HEADS = (
    "obstacle_type",
    "surface_obstacle",
)

ALL_HEADS = (*CATEGORICAL_HEADS, *MULTILABEL_HEADS)
