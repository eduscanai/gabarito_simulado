import os
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pandas as pd

from src.core import ImageInstanceOps
from src.defaults.config import CONFIG_DEFAULTS
from src.template import Bubble
from src.tests.test_samples.sample2.boilerplate import (
    CONFIG_BOILERPLATE,
    TEMPLATE_BOILERPLATE,
)
from src.tests.utils import (
    generate_write_jsons_and_run,
    remove_file,
    run_entry_point,
    setup_mocker_patches,
)

from time import strftime, localtime

from freezegun import freeze_time
from src.tests.utils import FROZEN_TIMESTAMP

with freeze_time(FROZEN_TIMESTAMP):
    TIME_NOW_HRS = strftime("%I%p", localtime())

CURRENT_DIR = Path("src/tests")
BASE_SAMPLE_PATH = CURRENT_DIR.joinpath("test_samples", "sample2")
BASE_RESULTS_CSV_PATH = os.path.join(
    "outputs", BASE_SAMPLE_PATH, "Results", f"Results_{TIME_NOW_HRS}.csv"
)
BASE_MULTIMARKED_CSV_PATH = os.path.join(
    "outputs", BASE_SAMPLE_PATH, "Manual", "MultiMarkedFiles.csv"
)


def run_sample(mocker, input_path):
    setup_mocker_patches(mocker)
    output_dir = os.path.join("outputs", input_path)
    run_entry_point(input_path, output_dir)


def extract_output_data(path):
    output_data = pd.read_csv(path, keep_default_na=False)
    return output_data


write_jsons_and_run = generate_write_jsons_and_run(
    run_sample,
    sample_path=BASE_SAMPLE_PATH,
    template_boilerplate=TEMPLATE_BOILERPLATE,
    config_boilerplate=CONFIG_BOILERPLATE,
)


def test_config_low_dimensions(mocker):
    def modify_config(config):
        config["dimensions"]["processing_height"] = 1000
        config["dimensions"]["processing_width"] = 1000

    exception = write_jsons_and_run(mocker, modify_config=modify_config)

    assert str(exception) == "No Error"


def test_different_bubble_dimensions(mocker):
    # Prevent appending to output csv:
    remove_file(BASE_RESULTS_CSV_PATH)
    remove_file(BASE_MULTIMARKED_CSV_PATH)

    exception = write_jsons_and_run(mocker)
    assert str(exception) == "No Error"
    original_output_data = extract_output_data(BASE_RESULTS_CSV_PATH)

    def modify_template(template):
        # Incorrect global bubble size
        template["bubbleDimensions"] = [5, 5]
        # Correct bubble size for MCQBlock1a1
        template["fieldBlocks"]["MCQBlock1a1"]["bubbleDimensions"] = [32, 32]
        # Incorrect bubble size for MCQBlock1a11
        template["fieldBlocks"]["MCQBlock1a11"]["bubbleDimensions"] = [10, 10]

    remove_file(BASE_RESULTS_CSV_PATH)
    remove_file(BASE_MULTIMARKED_CSV_PATH)
    exception = write_jsons_and_run(mocker, modify_template=modify_template)
    assert str(exception) == "No Error"

    results_output_data = extract_output_data(BASE_RESULTS_CSV_PATH)

    assert results_output_data.empty

    output_data = extract_output_data(BASE_MULTIMARKED_CSV_PATH)

    equal_columns = [f"q{i}" for i in range(1, 18)]
    assert (
        output_data[equal_columns].iloc[0].to_list()
        == original_output_data[equal_columns].iloc[0].to_list()
    )

    unequal_columns = [f"q{i}" for i in range(168, 185)]
    assert not (
        output_data[unequal_columns].iloc[0].to_list()
        == original_output_data[unequal_columns].iloc[0].to_list()
    )


def test_oversized_mark_outside_exact_bubble_is_still_detected():
    ops = ImageInstanceOps(CONFIG_DEFAULTS)

    image = np.full((80, 120), 255, dtype=np.uint8)

    # The ink frame sits outside the exact bubble box, but inside the
    # padded measurement window.
    cv2.rectangle(image, (14, 14), (46, 46), 0, thickness=-1)
    cv2.rectangle(image, (20, 20), (40, 40), 255, thickness=-1)

    bubble_a = Bubble([20, 20], "q1", "QTYPE_MCQ4", "A")
    bubble_b = Bubble([52, 20], "q1", "QTYPE_MCQ4", "B")

    field_block = SimpleNamespace(
        bubble_dimensions=[20, 20],
        bubbles_gap=32,
        labels_gap=40,
        direction="horizontal",
        shift=0,
        name="QUESTION_1",
        origin=[20, 20],
        dimensions=[52, 20],
        empty_val="",
        traverse_bubbles=[[bubble_a, bubble_b]],
    )

    template = SimpleNamespace(
        page_dimensions=[120, 80],
        field_blocks=[field_block],
        custom_labels={},
        non_custom_labels=["q1"],
    )

    detected, *_rest = ops.read_omr_response(template, image, "synthetic")

    assert detected["q1"] == "A"
