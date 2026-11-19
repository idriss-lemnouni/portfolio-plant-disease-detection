from study import load, split

def test_perceptual_groups_are_disjoint_and_classes_retained():
    images, labels, hashes = load()
    samples, groups = split(labels, hashes)
    for indexes in samples:
        assert set(labels[indexes]) == {0, 1, 2}
    assert len(images)==315
    assert sum(len(set(groups[s])) for s in samples) == len(set(groups[list(samples[0])+list(samples[1])+list(samples[2])]))
