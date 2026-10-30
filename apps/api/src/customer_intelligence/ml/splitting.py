from sklearn.model_selection import train_test_split


class SplitValidationError(ValueError):
    pass


def make_partitions(labels: list[int], random_seed: int) -> dict[str, list[int]]:
    if set(labels) != {0, 1}:
        raise SplitValidationError("Splitting requires both binary classes.")

    positions = list(range(len(labels)))

    try:
        train, remaining = train_test_split(
            positions,
            test_size=0.30,
            random_state=random_seed,
            stratify=labels,
        )
        validation, test = train_test_split(
            remaining,
            test_size=0.50,
            random_state=random_seed,
            stratify=[labels[index] for index in remaining],
        )
    except ValueError as exc:
        raise SplitValidationError(
            "The class counts cannot support a stratified 70/15/15 split. "
            "Add labeled examples or choose another evaluation strategy."
        ) from exc

    partitions = {
        "train": list(train),
        "validation": list(validation),
        "test": list(test),
    }

    assigned = [index for rows in partitions.values() for index in rows]

    if sorted(assigned) != positions:
        raise SplitValidationError("The split must assign every row exactly once.")

    for name, rows in partitions.items():
        if {labels[index] for index in rows} != {0, 1}:
            raise SplitValidationError(f"The {name} partition is missing a class.")

    return partitions


def make_time_partitions(labels: list[int], times: list[object]) -> dict[str, list[int]]:
    """Oldest ~70% of rows train, the next ~15% validate, the newest ~15% are the final test.

    Rows sharing a timestamp stay in one partition, so no snapshot date straddles a boundary
    and the model is never evaluated on a period older than its training data.
    """
    import pandas as pd

    if set(labels) != {0, 1}:
        raise SplitValidationError("Splitting requires both binary classes.")
    stamps = pd.to_datetime(pd.Series(times), errors="coerce")
    if bool(stamps.isna().any()):
        raise SplitValidationError("Every row needs a valid date in the time column.")
    distinct = sorted(stamps.unique())
    if len(distinct) < 3:
        raise SplitValidationError("Time-ordered evaluation needs at least three distinct dates.")
    counts = stamps.value_counts()
    total = len(labels)
    cumulative = 0
    train_end = validation_end = None
    for stamp in distinct:
        cumulative += int(counts[stamp])
        if train_end is None and cumulative >= 0.70 * total:
            train_end = stamp
        elif train_end is not None and validation_end is None and cumulative >= 0.85 * total:
            validation_end = stamp
    if train_end is None or validation_end is None or validation_end == distinct[-1]:
        # Too few dates for 70/15/15: the last two dates become validation and test.
        train_end, validation_end = distinct[-3], distinct[-2]
    partitions: dict[str, list[int]] = {"train": [], "validation": [], "test": []}
    for index, stamp in enumerate(stamps):
        name = (
            "train" if stamp <= train_end else "validation" if stamp <= validation_end else "test"
        )
        partitions[name].append(index)
    for name, rows in partitions.items():
        if not rows or {labels[index] for index in rows} != {0, 1}:
            raise SplitValidationError(
                f"The {name} period has no examples of both classes. Add more snapshot dates."
            )
    return partitions
