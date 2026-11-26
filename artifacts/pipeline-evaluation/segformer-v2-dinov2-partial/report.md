# Effect of predicted circulation masks on DINOv2 v2-partial

Paired evaluation on the same 29 frozen DINO test images, checkpoint epoch 10,
batch size 8, evaluation mode, AMP, threshold 0.5. No training or calibration.
Human masks reproduce the prior aggregate macro F1 exactly.

| Head | Human mask macro F1 | SegFormer v2 mask macro F1 | Delta |
|---|---:|---:|---:|
| passage_width | 0.2500 | 0.1465 | -0.1035 |
| obstruction | 0.4729 | 0.3788 | -0.0941 |
| surface_condition | 0.4872 | 0.5210 | +0.0338 |
| level_change | 0.3598 | 0.3435 | -0.0163 |
| path_continuity | 0.4824 | 0.4138 | -0.0686 |
| obstacle_type | 0.2828 | 0.3844 | +0.1016 |
| surface_obstacle | 0.2987 | 0.3164 | +0.0177 |
| Aggregate | 0.3762 | 0.3578 | -0.0185 |

Multilabel micro F1: obstacle_type 0.4151 -> 0.5091;
surface_obstacle 0.3544 -> 0.3896.

21 correct decisions became incorrect; 20 incorrect decisions became correct.
These count one decision per categorical head and one per modeled multilabel
label, excluding unknown categorical targets. Seven images had identical
discrete predictions in both scenarios; their probabilities still changed.

Examples of degradation:
- curb_ramp/gsv-cdmx-4700-CurbRamp.png: obstruction partial -> full
  (ground truth partial); surface_condition minor_problem -> regular
  (ground truth minor_problem).
- curb_ramp/gsv-oradell-6731-CurbRamp.png: passage_width narrow -> wide
  (ground truth narrow); obstruction partial -> none (ground truth partial).

Examples without changed decisions:
- curb_ramp/gsv-newberg-9692-CurbRamp.png: max probability change 0.0737.
- curb_ramp/gsv-walla_walla-1221-CurbRamp.png: max probability change 0.1181.

Panels show the DINO input with human mask on the left and predicted mask on
the right. decisions.csv and samples.csv contain all cases, not only examples.
Predicted masks use the current SegFormer inference postprocessing, including
small-component removal. The predicted binary mask is used directly, without
polygon approximation. Checkpoint SHA256 hashes are recorded in metrics.json
and were verified unchanged after evaluation.

Limitation: 27 of these 29 images belong to SegFormer v2's training split;
only two belong to its test split. This is a valid paired sensitivity experiment
on the frozen DINO test, but not an independent end-to-end generalization test.
The aggregate loss of 0.0185 can therefore be optimistic for unseen scenes.
No visual cause is inferred from individual prediction transitions.
