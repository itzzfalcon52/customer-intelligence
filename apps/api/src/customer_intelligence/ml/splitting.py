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