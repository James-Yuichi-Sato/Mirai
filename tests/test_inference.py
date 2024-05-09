import json
import datetime
import logging
import traceback
import unittest
import sys
import os
import warnings
import zipfile

import pydicom


from torch.serialization import SourceChangeWarning
warnings.filterwarnings("ignore", category=SourceChangeWarning, append=True)
warnings.filterwarnings("ignore", category=UserWarning, append=True)
warnings.filterwarnings("ignore", message=".*Manufacturer not GE or C-View/VOI LUT doesn't exist.*", append=True)

# append module root directory to sys.path
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_DIR)

import onconet

__doc__ = """
End-to-end test. 
Run the model on sample data.
"""


def download_file(url, destination):
    import urllib.request

    try:
        urllib.request.urlretrieve(url, destination)
    except Exception as e:
        logging.getLogger("mirai_full").error(f"An error occurred while downloading from {url} to {destination}: {e}")
        raise e


class TestInferenceRegression(unittest.TestCase):
    """
    Test that the model predictions are the same as the expected predictions.
    Running this test will be very time consuming, since we need to process so many scans.
    """
    def setUp(self):
        pass

    def inference_inbreast(self):
        import scripts.inference as inference
        import pandas as pd

        allow_resume = True
        save_view_tags = True

        group_col = "Patient ID"
        filename_col = "Full File Name"
        temp_dir = os.path.join(PROJECT_DIR, "tests/.cache/temp")
        os.makedirs(temp_dir, exist_ok=True)

        # Must download the INBreast dataset first
        # https://www.academicradiology.org/article/S1076-6332(11)00451-X/abstract
        # https://pubmed.ncbi.nlm.nih.gov/22078258/
        # https://www.kaggle.com/datasets/martholi/inbreast
        test_data_dir = os.path.join(PROJECT_DIR, "tests/test_data")
        image_data_dir = os.path.join(test_data_dir, "inbreast", "ALL-IMGS")
        input_table = os.path.join(PROJECT_DIR, "tests/test_data/inbreast_table_v01.tsv")

        version = onconet.__version__
        cur_pred_results = os.path.join("tests", f"inbreast_predictions_{version}.json")

        all_results = {
            "__metadata__": {
                "version": version,
                "start_time": datetime.datetime.now().isoformat(),
                "input_table": input_table,
            }
        }
        if os.path.exists(cur_pred_results):
            if allow_resume:
                with open(cur_pred_results, 'r') as f:
                    all_results = json.load(f)
            else:
                os.remove(cur_pred_results)

        input_df = pd.read_csv(input_table, sep="\t")
        num_patients = input_df[group_col].nunique()

        print(f"About to process {num_patients} patients.")
        idx = 0
        for patient_id, group_df in input_df.groupby(group_col):
            idx += 1
            print(f"{datetime.datetime.now()} Processing {patient_id} ({idx}/{num_patients})")
            if patient_id in all_results:
                print(f"Already processed {patient_id}, skipping")
                continue

            dicom_file_names = group_df[filename_col].tolist()
            dicom_file_paths = []
            if save_view_tags:
                for rn, row in group_df.iterrows():
                    dicom_file_name = row[filename_col]
                    dicom_file = os.path.join(image_data_dir, row[filename_col])
                    dicom = pydicom.dcmread(dicom_file)
                    view_str = row['View']
                    side_str = row['Laterality']
                    # view = 0 if view_str == 'CC' else 1
                    # side = 0 if side_str == 'R' else 1

                    dicom.Manufacturer = "GE"  # ???
                    dicom.ViewPosition = view_str
                    dicom.ImageLaterality = side_str
                    new_dicom_file = os.path.join(temp_dir, dicom_file_name.replace(".dcm", f"_resaved.dcm"))
                    dicom.save_as(new_dicom_file)
                    assert os.path.exists(new_dicom_file)
                    dicom_file_paths.append(new_dicom_file)
            else:
                dicom_file_paths = [os.path.join(image_data_dir, f) for f in dicom_file_names]

            prediction = {}

            try:
                prediction = inference.inference(dicom_file_paths, inference.DEFAULT_CONFIG_PATH, use_pydicom=False)
            except Exception as e:
                print(f"An error occurred while processing {patient_id}: {e}")
                prediction["error"] = traceback.format_exc()

            cur_dict = {"files": dicom_file_names,
                        group_col: patient_id}
            cur_dict.update(prediction)

            all_results[patient_id] = cur_dict

            with open(cur_pred_results, 'w') as f:
                json.dump(all_results, f, indent=2)


class TestInference(unittest.TestCase):
    def setUp(self):
        # Download demo data if it doesn't exist
        self.data_dir = os.path.join(PROJECT_DIR, "mirai_demo_data")
        latest_url = "https://github.com/reginabarzilaygroup/Mirai/releases/latest/download/mirai_demo_data.zip"
        pegged_url = "https://github.com/reginabarzilaygroup/Mirai/releases/download/v0.8.0/mirai_demo_data.zip"
        if not os.path.exists(self.data_dir):
            if not os.path.exists("mirai_demo_data.zip"):
                download_file(pegged_url, "mirai_demo_data.zip")
            # Unzip file
            with zipfile.ZipFile("mirai_demo_data.zip", 'r') as zip_ref:
                zip_ref.extractall(self.data_dir)

    def test_demo_data_v070(self):
        # Can only unpickle the old calibration file with sklearn 0.23.2
        import sklearn
        data_dir = self.data_dir
        dicom_files = [f"{data_dir}/ccl1.dcm",
                       f"{data_dir}/ccr1.dcm",
                       f"{data_dir}/mlol2.dcm",
                       f"{data_dir}/mlor2.dcm"]

        import scripts.inference as inference

        v07_config_path = os.path.join(inference.config_dir, "mirai_trained_v0.7.0.json")
        prediction = inference.inference(dicom_files, v07_config_path)
        expected_result = {'predictions': {'Year 1': 0.0298, 'Year 2': 0.0483, 'Year 3': 0.0684, 'Year 4': 0.09, 'Year 5': 0.1016}}

        self.assertEqual(prediction, expected_result, "Prediction does not match expected result.")

    def test_demo_data(self):
        data_dir = self.data_dir
        dicom_files = [f"{data_dir}/ccl1.dcm",
                       f"{data_dir}/ccr1.dcm",
                       f"{data_dir}/mlol2.dcm",
                       f"{data_dir}/mlor2.dcm"]

        import scripts.inference as inference

        prediction = inference.inference(dicom_files, inference.DEFAULT_CONFIG_PATH)
        expected_result = {'predictions': {'Year 1': 0.0298, 'Year 2': 0.0483, 'Year 3': 0.0684, 'Year 4': 0.09, 'Year 5': 0.1016}}

        self.assertEqual(prediction, expected_result, "Prediction does not match expected result.")

        # Try again with dicom files in a different order
        dicom_files = [dicom_files[2], dicom_files[3], dicom_files[0], dicom_files[1]]
        prediction = inference.inference(dicom_files, inference.DEFAULT_CONFIG_PATH)
        self.assertEqual(prediction, expected_result, "Prediction does not match expected result in new order.")


if __name__ == '__main__':
    unittest.main()
    # TestInferenceRegression().test_inbreast()
