#!/bin/bash

pred_save_path=${1:-"demo/validation_output_actual.csv"}

if [ ! -e  "${pred_save_path}" ]
then
  python scripts/main.py  --model_name mirai_full --img_encoder_snapshot snapshots/mgh_mammo_MIRAI_Base_May20_2019.p --transformer_snapshot snapshots/mgh_mammo_cancer_MIRAI_Transformer_Jan13_2020.p  --callibrator_snapshot snapshots/callibrators/MIRAI_FULL_PRED_RF.callibrator.p --batch_size 1 --dataset csv_mammo_risk_all_full_future --img_mean 7047.99 --img_size 1664 2048 --img_std 12005.5 --metadata_path demo/sample_metadata.csv --test --prediction_save_path "$pred_save_path"
fi

original_output_path="demo/validation_output.csv"

md5sum "$pred_save_path" "$original_output_path"
cmp "$pred_save_path" "$original_output_path" && echo "Validation output matches expected" || echo "Validation output is different from expected"
