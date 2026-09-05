import pandas as pd

from htfa.data.tabular import build_overview_dataset, numeric_variable_names


def test_numeric_variable_names_preserve_dataframe_column_labels():
    frame = pd.DataFrame({2020: [1.0, 2.0], "text": ["a", "b"]})

    assert numeric_variable_names(frame) == [2020]
    dataset = build_overview_dataset(frame, "sample", "identity")
    assert dataset.frame[2020].tolist() == [1.0, 2.0]
