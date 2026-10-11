from typing import Self

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer, make_column_selector
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted


class PreprocessingError(ValueError):
    pass


class FeatureSchema(TransformerMixin, BaseEstimator):
    def __init__(self, feature_columns: list[str]) -> None:
        self.feature_columns = feature_columns

    def _select(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise PreprocessingError("Features must be supplied as a DataFrame.")

        if not frame.columns.is_unique:
            raise PreprocessingError("Duplicate column names are not supported.")

        missing = [name for name in self.feature_columns if name not in frame.columns]
        if missing:
            raise PreprocessingError(f"Required feature columns are missing: {missing}")

        return frame.loc[:, self.feature_columns].replace(r"^\s*$", pd.NA, regex=True)

    def fit(self, X: pd.DataFrame, y: object = None) -> Self:
        if not self.feature_columns or len(set(self.feature_columns)) != len(self.feature_columns):
            raise PreprocessingError("Choose a non-empty list of distinct features.")

        selected = self._select(X)
        self.numeric_columns_: list[str] = []
        self.categorical_columns_: list[str] = []

        for name in self.feature_columns:
            values = selected[name].dropna()
            if values.empty:
                raise PreprocessingError(f"{name}: every training value is missing.")

            converted = pd.to_numeric(values, errors="coerce")

            if bool(converted.notna().all()):
                if not bool(np.isfinite(converted.to_numpy(dtype=float)).all()):
                    raise PreprocessingError(f"{name}: numeric values must be finite.")
                self.numeric_columns_.append(name)
            else:
                if int(values.nunique()) > 100:
                    raise PreprocessingError(
                        f"{name}: more than 100 training categories. "
                        "Review whether this is an identifier or free-text column."
                    )
                self.categorical_columns_.append(name)

        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, ["numeric_columns_", "categorical_columns_"])
        selected = self._select(X)
        result = pd.DataFrame(index=selected.index)

        for name in self.numeric_columns_:
            values = selected[name]
            converted = pd.to_numeric(values, errors="coerce")
            if bool((values.notna() & converted.isna()).any()):
                raise PreprocessingError(f"{name}: contains an invalid numeric value.")

            numeric = converted.to_numpy(dtype=float, na_value=np.nan)
            if bool(np.isinf(numeric).any()):
                raise PreprocessingError(f"{name}: numeric values must be finite.")
            result[name] = numeric

        for name in self.categorical_columns_:
            values = selected[name].astype("string")
            result[name] = values.astype(object).where(values.notna(), np.nan)

        return result.loc[:, self.feature_columns]


def build_preprocessing_pipeline(feature_columns: list[str]) -> Pipeline:
    numeric = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=True)),
        ]
    )
    columns = ColumnTransformer(
        transformers=[
            ("numeric", numeric, make_column_selector(dtype_include=np.number)),
            ("categorical", categorical, make_column_selector(dtype_include=object)),
        ],
        remainder="drop",
        sparse_threshold=1.0,
    )
    return Pipeline(
        steps=[
            ("schema", FeatureSchema(feature_columns=feature_columns)),
            ("columns", columns),
        ]
    )